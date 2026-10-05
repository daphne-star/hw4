import os
import sqlite3
from contextlib import closing
from pathlib import Path
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from models import AgentReply, ToolContext, SearchFilters
from tools import search_products, get_product, check_stock

for parent in Path(__file__).resolve().parents:
    env_file = parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        break
PROMPT = (Path(__file__).parent / 'prompts' / 'prompt.md').read_text(encoding='utf-8')
api_key = os.getenv('PORTKEY_API_KEY') or os.getenv('OPENAI_API_KEY')
agent = None
if api_key:
    provider = OpenAIProvider(api_key=api_key, base_url=os.getenv('OPENAI_BASE_URL', 'https://api.portkey.ai/v1'))
    agent = Agent(OpenAIChatModel(os.getenv('AI_MODEL', 'gpt-5.6-luna'), provider=provider), deps_type=ToolContext, output_type=AgentReply, system_prompt=PROMPT)

def _connect(ctx: RunContext[ToolContext]) -> sqlite3.Connection:
    """Open a connection on the calling thread.

    PydanticAI runs sync tools in a worker thread, so a connection created by the
    FastAPI request thread cannot be reused here.
    """
    connection = sqlite3.connect(ctx.deps.db_path)
    connection.row_factory = sqlite3.Row
    return connection

def recent_products(ctx: RunContext[ToolContext]) -> list[dict]:
    """Products shown in recent turns, used to resolve pronouns."""
    return ctx.deps.recent_products

def page_context(ctx: RunContext[ToolContext]) -> dict:
    """Describe what the customer is viewing; use tools for all product facts."""
    return ctx.deps.page_context

def search_catalogue(ctx: RunContext[ToolContext], query: str = "", category: str | None = None, color: str | None = None, size: str | None = None, max_price: float | None = None) -> list[dict]:
    """Search the local catalogue using normalized category, color, size, and price filters."""
    with closing(_connect(ctx)) as connection:
        return search_products(connection, SearchFilters(query=query, category=category, color=color, size=size, max_price=max_price))

def product_details(ctx: RunContext[ToolContext], product_id: str) -> dict | None:
    """Get one exact product from the local catalogue."""
    with closing(_connect(ctx)) as connection:
        return get_product(connection, product_id)

def product_stock(ctx: RunContext[ToolContext], product_id: str, size: str | None = None) -> list[dict]:
    """Check exact inventory rows for a product."""
    with closing(_connect(ctx)) as connection:
        return check_stock(connection, product_id, size)

if agent:
    agent.tool(recent_products)
    agent.tool(page_context)
    agent.tool(search_catalogue)
    agent.tool(product_details)
    agent.tool(product_stock)
