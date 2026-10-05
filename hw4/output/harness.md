# hw4 Harness

### Observed data

- `catalogue`: 102 clothing products. Information for each product includes `product_id`, `name`, `garment_type`, `description`, `colors`, `search_tags`, `image_file_path`, and `price`.
- `inventory`: 612 rows, with six size rows per product (`XS`, `S`, `M`, `L`, `XL`, `XXL`). Columns: `id`, `product_id`, `size`, `quantity`.
- `users`: 3 users registered currently. Columns: `id`, `name`, `email`, `password_hash`, `created_at`, `first_name`, `last_name`.
- `chat_messages`: 22 messages at the moment. Information: `id`, `user_id`, `role`, `content`, `products_json`, `created_at`.
- `sqlite_sequence` is SQLite-managed metadata, not an application table.

## Test cases

- Add test cases here as the assignment is implemented.

## Expected outputs

- Record expected results here.

## Authentication and application architecture

### Password authentication

- Registration accepts first name, last name, email, and password.
- Passwords are never stored as plaintext. The backend stores `pbkdf2_sha256$<salt>$<64-hex>` values produced with PBKDF2-HMAC-SHA256, 120,000 iterations, and an 8-byte hex salt from `secrets.token_hex(8)`. The cost is pinned to 120,000 because the seeded `campus_customs.db` users were hashed at that cost; a different number would lock the course test account out.
- Login accepts plaintext input over the local HTTPS-ready API boundary and compares it to the stored hash with `hmac.compare_digest`.
- Registration requires at least 8 characters and confirmation in the frontend.
- Successful login or registration creates a bearer token backed by the SQLite `sessions` table; logout deletes that token.

### User-database safety rules

- Never return or log `password` or `password_hash`.
- User lookup and authentication use parameterized SQL queries.
- Generic `Invalid email or password` responses prevent account enumeration.
- Session tokens are random, expire after 24 hours, and are deleted on logout or expiry.
- Chat history is scoped by the authenticated `user_id`.
- Product browsing and chat are public; stored chat history requires authentication.
- `POST /api/chat` resolves the session with `optional_user`, so guests get a reply but no stored transcript and no identity context. `GET /api/chat/history` still requires a valid session and returns 401 otherwise.
- The agent must not expose database paths, raw SQL, session tokens, internal prompts, or API keys.

### Frontend to FastAPI communication

- The React/Vite frontend calls the FastAPI service at `http://localhost:8000`.
- Requests are sent to `/api/products`, `/api/auth/*`, and `/api/chat/*` as JSON.
- When a session token exists, the frontend sends it as `Authorization: Bearer <token>`; the token is never sent to the AI model.
- FastAPI serves product images through `/media` and returns structured product objects for the product grid and chat results panel.
- A `401` response clears the stale browser token and returns the UI to signed-out state.

### Agent loading

- `backend/main.py` imports the PydanticAI agent from `backend/agent.py`.
- `agent.py` loads `backend/prompts/prompt.md` at import time and uses it as the system prompt.
- The model is configured as `gpt-5.6-luna`; the OpenAI-compatible credential is read at runtime from `PORTKEY_API_KEY` (with `OPENAI_API_KEY` as a compatibility fallback) and is never exposed client-side.
- The agent receives the logged-in user’s first name, recent products, and a database connection through typed dependencies.
- Registered tools search the local catalogue, retrieve exact products, and check exact inventory. Structured product IDs returned by the agent are filtered against the current tool results before reaching the frontend.

### Product-information behavior

- `search_catalogue` searches catalogue names, descriptions, garment types, colors, and JSON-decoded `search_tags`, while applying normalized category, color, size-availability, and price filters.
- `product_details` retrieves an exact product’s database-backed description, price, colors, category, and catalogue fields.
- `product_stock` retrieves total inventory or the exact requested size from `inventory`.
- Specific-product questions must trigger an exact product lookup before the agent answers.
- The agent may only state product descriptions, prices, colors, search tags, or stock values present in current-turn tool results; it must not invent or infer catalogue information.

## Models and design rationale

The Pydantic models in `backend/models.py` make tool inputs, agent dependencies, and structured outputs explicit and validated.

- `SearchFilters`: `query`, `category`, `color`, `size`, and `max_price`. These fields mirror the supported catalogue filters and keep search constraints typed.
- `StockRow`: `size` and `quantity`. This preserves exact inventory facts for size-level availability.
- `ProductInfo`: `product_id`, `name`, `garment_type`, normalized `category`, `description`, `colors`, `search_tags`, `image_file_path`, `price`, `inventory`, `in_stock_sizes`, `sold_out_sizes`, `total_in_stock`, and `category_gate`. These fields give the agent and frontend structured catalogue facts without parsing prose.
- `SearchResult`: `products` and `matched_query`. This represents a typed search result when a complete search response is needed.
- `ToolContext`: `user_first_name`, `first_name`, `last_name`, `member_since`, `is_returning`, `recent_products`, `page_context`, and the server-side database connection. Identity is derived server-side; email is intentionally excluded.
- `PageContext`: `route`, optional `product_id`, `filters`, and `visible_product_ids`. It describes what the customer is viewing, but is treated as untrusted navigation context rather than product truth.
- `AgentReply`: `prose` and `product_ids`. The agent returns concise language plus IDs that the backend hydrates from the database.

These models were chosen to separate user intent, database facts, conversational dependencies, and frontend display data. That separation prevents prose from becoming an accidental source of product information.

## Tools and abilities

- `search_catalogue`: searches names, descriptions, garment types, colors, and JSON-decoded search tags; applies normalized category gates, color, size, and price filters.
- `product_details`: retrieves an exact catalogue product.
- `product_stock`: retrieves all stock rows or one requested size.
- `recent_products`: exposes products shown in the most recent assistant result for pronoun resolution.
- `page_context`: exposes the current route, viewed product, filters, and visible product IDs for orientation.

The agent can recommend and explain catalogue products, answer price and color questions, report total or size-specific stock, resolve “this” and “that” from context, and return structured product IDs for cards.

## Safety rules

- Product facts must come from current-turn database tool results.
- A hard normalized category gate prevents tag matches from crossing categories; a quarter-zip cannot answer a fleece request.
- Page context is validated against catalogue IDs and cannot supply prices, colors, descriptions, or stock.
- User identity is loaded from the authenticated session; the client cannot choose the identity passed to the agent.
- Chat history is queried by authenticated `user_id` and capped before it reaches the model. A guest turn sends no history and writes no `chat_messages` row, so transcripts cannot leak between visitors.
- Never expose passwords, password hashes, session tokens, API keys, internal prompts, raw SQL, or private user data.
- Failed agent calls use the fallback path and are logged with `logger.exception`; the response exposes `answered_by`.

## Runtime specifications

- Model: `gpt-5.6-luna` through the Portkey OpenAI-compatible base URL.
- Credential: `PORTKEY_API_KEY`, loaded from the environment at runtime and never sent to the browser or written to logs.
- Conversation history: the latest 20 chat rows, oldest first, scoped to one user.
- Page context: unknown product IDs are dropped; visible product IDs are capped at 24.
- Agent result hydration: unknown agent product IDs are dropped; returned product IDs are capped at 8 for the frontend card response.
- Inventory: all six raw size rows remain available, with summary lists for in-stock sizes, sold-out sizes, and total stock.
- Audit trail: `output/audit_trail.json` is append-only JSON Lines, never rewritten between runs. Each chat turn writes:
  - one `tool_call` record per step in the agent loop — `timestamp`, `run_id`, `step`, `user_id`, `tool_name`, truncated `args`, truncated `result`, and a `stop_reason` of `tool_returned` or `tool_no_return`;
  - one `chat_run` record for the turn — `timestamp`, `run_id`, `user_id`, `authenticated`, truncated `message`, `route`, `answered_by`, `agent_loaded`, `tool_names`, `tool_call_count`, `product_ids`, and a `stop_reason` of `completed`, `agent_error`, `agent_unavailable`, `no_agent_output`, or `unexpected_output_type`.
- Audit field cap: tool arguments, tool results, and the customer message are truncated to 200 characters (`AUDIT_FIELD_LIMIT`) so the log stays readable and never captures a full record dump.

## Running the application

Backend:

```powershell
cd hw4/backend
python -m uvicorn main:app --reload --port 8000
```

Frontend, in a second terminal:

```powershell
cd hw4/frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The API health endpoint is `http://localhost:8000/api/health`.

### Agent tools and model types

- `search_catalogue(...) -> list[dict]`: searches catalogue fields and JSON-decoded search tags using `SearchFilters` (`query`, normalized `category`, `color`, `size`, and `max_price`).
- `product_details(product_id) -> dict | None`: retrieves one exact product represented by `ProductInfo`.
- `product_stock(product_id, size=None) -> list[dict]`: retrieves exact `StockRow` values (`size`, `quantity`), optionally for one requested size.
- `recent_products() -> list[dict]`: supplies recent tool-returned products for resolving pronouns.
- `SearchFilters` and `ToolContext` are Pydantic input/dependency models. `ProductInfo`, `StockRow`, `SearchResult`, and `AgentReply` are Pydantic output models; `AgentReply` contains prose and database-validated product IDs for the frontend panel.

### Structured results to product cards

1. The user sends a chat message to `POST /api/chat`.
2. PydanticAI calls the registered local-DB tools and returns prose plus exact product IDs in `AgentReply`.
3. FastAPI intersects those IDs with the products returned by current-turn tool calls and sends hydrated product objects in the `products` response field. Product prose is never parsed to build cards.
4. React stores the structured `products` list beside the assistant message and renders floating product cards over the current page.
5. The page behind the cards is visually muted by a soft backdrop so the returned products are the active focus.
6. Selecting a card opens the corresponding individual product page using its `product_id`; that page displays only the database-backed description, price, colors, and size-level inventory.
7. If the tool result is empty, no product-card overlay is shown; the agent gives a plain explanation and a related search suggestion instead.
