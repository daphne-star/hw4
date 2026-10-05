import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import logging
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, field_validator
from models import AgentReply, ToolContext, SearchFilters, PageContext
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
from tools import search_products as db_search_products, get_product as db_get_product, check_stock as db_check_stock
logger = logging.getLogger(__name__)
try:
    from agent import agent
except Exception:
    logger.exception("Unable to load PydanticAI agent")
    agent = None

try:
    from pydantic_ai import Agent
except ImportError:  # Keeps browsing/search usable before optional AI deps are installed.
    Agent = None

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB", ROOT / "data" / "campus_customs.db"))
PRODUCTS_PATH = ROOT / "data"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"
# The seeded campus_customs.db users were hashed at this cost; changing it locks them out.
PBKDF2_ROUNDS = 120_000
app = FastAPI(title="Campus Customs API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=PRODUCTS_PATH), name="media")

def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()

@app.on_event("startup")
def initialize_sessions():
    connection = sqlite3.connect(DB_PATH)
    connection.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at REAL NOT NULL, FOREIGN KEY (user_id) REFERENCES users(id))")
    connection.commit()
    connection.close()

def parse_array(value: str | None) -> list[str]:
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except (TypeError, json.JSONDecodeError):
        return []

def normalize_category(value: str) -> str:
    text = value.lower().replace("-", " ").replace("_", " ")
    if "quarter" in text or "1 4" in text: return "quarter-zip"
    if "hood" in text and "full zip" in text: return "full-zip hoodie"
    if "hood" in text: return "hoodie"
    if "fleece" in text or "jacket" in text: return "fleece/jacket"
    if "crew" in text: return "crewneck"
    if "long sleeve" in text or "l s" in text: return "long-sleeve"
    if "shirt" in text: return "t-shirt"
    return text

def product(row: sqlite3.Row, connection: sqlite3.Connection) -> dict[str, Any]:
    item = dict(row)
    item["colors"] = parse_array(item["colors"])
    item["search_tags"] = parse_array(item["search_tags"])
    item["category"] = normalize_category(item["garment_type"])
    item["image_url"] = f"/media/{item['image_file_path']}"
    item["inventory"] = [dict(x) for x in connection.execute("SELECT size, quantity FROM inventory WHERE product_id=? ORDER BY id", (item["product_id"],))]
    return item

def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${salt}${digest}"

def password_matches(password: str, stored: str) -> bool:
    parts = stored.split("$")
    return len(parts) == 3 and hmac.compare_digest(password_hash(password, parts[1]), stored)

def resolve_user(authorization: str | None, connection: sqlite3.Connection):
    """Return the session's user row, or None when there is no valid session."""
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not token: return None
    record = connection.execute("SELECT user_id, expires_at FROM sessions WHERE token=?", (token,)).fetchone()
    if not record: return None
    if record[1] < time.time():
        connection.execute("DELETE FROM sessions WHERE token=?", (token,)); connection.commit()
        return None
    return connection.execute("SELECT id, name, email, first_name, last_name FROM users WHERE id=?", (record[0],)).fetchone()

def current_user(authorization: str | None = Header(default=None), connection: sqlite3.Connection = Depends(db)):
    user = resolve_user(authorization, connection)
    if not user: raise HTTPException(401, "Please log in")
    return user

def optional_user(authorization: str | None = Header(default=None), connection: sqlite3.Connection = Depends(db)):
    """Guests may chat; they just get no stored history and no identity context."""
    return resolve_user(authorization, connection)

class Account(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_length(cls, value: str):
        if len(value) < 8: raise ValueError("Password must be at least 8 characters")
        return value

class Login(BaseModel):
    email: EmailStr
    password: str

class ChatIn(BaseModel):
    message: str
    context: PageContext = PageContext()

AUDIT_FIELD_LIMIT = 200

def audit_snippet(value: Any, limit: int = AUDIT_FIELD_LIMIT) -> str:
    """Render any tool argument or result as one short, log-safe string."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."

def tool_trace(result: Any) -> list[dict[str, Any]]:
    """Pair each tool call in the agent loop with the result it returned."""
    calls: list[dict[str, Any]] = []
    try:
        for message in result.new_messages():
            for part in getattr(message, "parts", []):
                kind = getattr(part, "part_kind", "")
                if kind == "tool-call":
                    calls.append({"tool_name": part.tool_name, "args": audit_snippet(part.args)})
                elif kind == "tool-return":
                    for entry in reversed(calls):
                        if entry["tool_name"] == part.tool_name and "result" not in entry:
                            entry["result"] = audit_snippet(part.content)
                            break
    except Exception:
        logger.exception("Unable to summarize agent tool calls for the audit trail")
    return calls

def record_audit(event: dict[str, Any]):
    """Append one sanitized JSON object per line; existing records are never rewritten."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as audit_file:
        audit_file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

@app.get("/api/health")
def health(): return {"ok": True}

@app.get("/api/products")
def products(category: str | None = None, color: str | None = None, size: str | None = None, max_price: float | None = None, connection: sqlite3.Connection = Depends(db)):
    rows = [product(row, connection) for row in connection.execute("SELECT * FROM catalogue ORDER BY name")]
    wanted_color = color.lower().replace("navy blue", "navy") if color else None
    result = []
    for item in rows:
        colors = {x.lower().replace("navy blue", "navy") for x in item["colors"]}
        in_size = not size or any(x["size"] == size and x["quantity"] > 0 for x in item["inventory"])
        if (not category or item["category"] == category) and (not wanted_color or wanted_color in colors) and in_size and (max_price is None or item["price"] <= max_price): result.append(item)
    return result

@app.get("/api/products/{product_id}")
def product_detail(product_id: str, connection: sqlite3.Connection = Depends(db)):
    row = connection.execute("SELECT * FROM catalogue WHERE product_id=?", (product_id,)).fetchone()
    if not row: raise HTTPException(404, "Product not found")
    return product(row, connection)

@app.post("/api/auth/register")
def register(account: Account, connection: sqlite3.Connection = Depends(db)):
    try:
        cursor = connection.execute("INSERT INTO users (name,email,password_hash,first_name,last_name) VALUES (?,?,?,?,?)", (f"{account.first_name} {account.last_name}", str(account.email).lower(), password_hash(account.password), account.first_name, account.last_name))
        connection.commit()
    except sqlite3.IntegrityError: raise HTTPException(409, "An account with that email already exists")
    return create_session(cursor.lastrowid, connection)

@app.post("/api/auth/login")
def login(credentials: Login, connection: sqlite3.Connection = Depends(db)):
    user = connection.execute("SELECT * FROM users WHERE email=?", (str(credentials.email).lower(),)).fetchone()
    if not user or not password_matches(credentials.password, user["password_hash"]): raise HTTPException(401, "Invalid email or password")
    return create_session(user["id"], connection)

def create_session(user_id: int, connection: sqlite3.Connection):
    token = secrets.token_urlsafe(32); connection.execute("INSERT INTO sessions (token,user_id,expires_at) VALUES (?,?,?)", (token, user_id, time.time() + 86400)); connection.commit()
    user = connection.execute("SELECT id,name,email,first_name,last_name FROM users WHERE id=?", (user_id,)).fetchone()
    return {"token": token, "user": dict(user)}

@app.get("/api/auth/me")
def me(user=Depends(current_user)): return dict(user)

@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None), connection: sqlite3.Connection = Depends(db)):
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    connection.execute("DELETE FROM sessions WHERE token=?", (token,)); connection.commit()
    return {"ok": True}

def search_products(message: str, connection: sqlite3.Connection):
    terms = set(message.lower().split())
    scored = []
    for row in connection.execute("SELECT * FROM catalogue"):
        item = product(row, connection); haystack = " ".join([item["name"], item["garment_type"], item["description"], *item["colors"], *item["search_tags"]]).lower()
        score = sum(term in haystack for term in terms if len(term) > 2)
        if score: scored.append((score, item))
    return [item for _, item in sorted(scored, key=lambda x: (-x[0], x[1]["name"]))[:8]]

@app.get("/api/chat/history")
def history(user=Depends(current_user), connection: sqlite3.Connection = Depends(db)):
    return [dict(row) for row in connection.execute("SELECT id,role,content,products_json,created_at FROM chat_messages WHERE user_id=? ORDER BY id", (user["id"],))]

@app.post("/api/chat")
def chat(payload: ChatIn, user=Depends(optional_user), connection: sqlite3.Connection = Depends(db)):
    user_id = user["id"] if user else None
    recent: list[dict[str, Any]] = []
    message_history: list[Any] = []
    first_name = last_name = member_since = ""
    prior_count = 0
    if user_id:
        previous = connection.execute("SELECT products_json FROM chat_messages WHERE user_id=? AND role='assistant' AND products_json IS NOT NULL ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        recent = json.loads(previous[0]) if previous else []
        prior_rows = list(reversed(connection.execute("SELECT role, content FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,)).fetchall()))
        for row in prior_rows:
            part = UserPromptPart(content=row[1]) if row[0] == "user" else TextPart(content=row[1])
            message_history.append(ModelRequest(parts=[part]) if row[0] == "user" else ModelResponse(parts=[part]))
        account = connection.execute("SELECT first_name,last_name,created_at FROM users WHERE id=?", (user_id,)).fetchone()
        first_name, last_name, member_since = account[0] or "", account[1] or "", account[2] or ""
        prior_count = connection.execute("SELECT COUNT(*) FROM chat_messages WHERE user_id=?", (user_id,)).fetchone()[0]

    valid_ids = {row[0] for row in connection.execute("SELECT product_id FROM catalogue")}
    safe_page = payload.context.model_dump()
    safe_page["product_id"] = payload.context.product_id if payload.context.product_id in valid_ids else None
    safe_page["visible_product_ids"] = [item for item in payload.context.visible_product_ids if item in valid_ids][:24]

    display_name = (first_name or user["name"]) if user else ""
    greeting = f"{display_name}, " if display_name else ""
    found = db_search_products(connection, SearchFilters(query=payload.message))
    prose = (f"{greeting}I found {len(found)} Campus Customs item{'s' if len(found) != 1 else ''} that may fit your request." if found
             else f"{greeting}I couldn't find a matching item in the current catalogue. Try a garment type, Yale group, color, or size.")

    answered_by = "fallback"
    stop_reason = "agent_unavailable" if agent is None else "no_agent_output"
    tool_calls: list[dict[str, Any]] = []
    run_id = None
    if agent:
        try:
            result = agent.run_sync(payload.message, message_history=message_history, deps=ToolContext(user_first_name=display_name, first_name=first_name, last_name=last_name, member_since=member_since, is_returning=prior_count > 0, recent_products=recent, page_context=safe_page, db_path=str(DB_PATH)))
            run_id = getattr(result, "run_id", None)
            tool_calls = tool_trace(result)
            if isinstance(result.output, AgentReply):
                prose = result.output.prose
                found = [item for item_id in result.output.product_ids if (item := db_get_product(connection, item_id))]
                answered_by = "agent"
                stop_reason = "completed"
            else:
                stop_reason = "unexpected_output_type"
        except Exception:
            logger.exception("PydanticAI chat turn failed")
            stop_reason = "agent_error"

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # One record per tool call, then one for the turn, so the loop reads end to end.
    for step, call in enumerate(tool_calls, start=1):
        record_audit({"timestamp": timestamp, "event": "tool_call", "run_id": run_id, "step": step,
                      "user_id": user_id, "tool_name": call["tool_name"], "args": call.get("args", ""),
                      "result": call.get("result", ""),
                      "stop_reason": "tool_returned" if "result" in call else "tool_no_return"})
    record_audit({
        "timestamp": timestamp,
        "event": "chat_run",
        "run_id": run_id,
        "user_id": user_id,
        "authenticated": user is not None,
        "message": audit_snippet(payload.message),
        "route": safe_page.get("route", "home"),
        "answered_by": answered_by,
        "agent_loaded": agent is not None,
        "tool_names": [call["tool_name"] for call in tool_calls],
        "tool_call_count": len(tool_calls),
        "product_ids": [item["product_id"] for item in found[:8]],
        "stop_reason": stop_reason,
    })

    if user_id:
        connection.execute("INSERT INTO chat_messages (user_id,role,content) VALUES (?,?,?)", (user_id, "user", payload.message))
        connection.execute("INSERT INTO chat_messages (user_id,role,content,products_json) VALUES (?,?,?,?)", (user_id, "assistant", prose, json.dumps(found)))
        connection.commit()
    return {"prose": prose, "products": found, "answered_by": answered_by}
