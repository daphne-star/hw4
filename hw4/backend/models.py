from typing import Any
from pydantic import BaseModel, Field

class SearchFilters(BaseModel):
    query: str = ""
    category: str | None = None
    color: str | None = None
    size: str | None = None
    max_price: float | None = None

class StockRow(BaseModel):
    size: str
    quantity: int

class ProductInfo(BaseModel):
    product_id: str
    name: str
    garment_type: str
    category: str
    description: str
    colors: list[str]
    search_tags: list[str]
    image_file_path: str
    price: float
    inventory: list[StockRow]
    in_stock_sizes: list[str] = Field(default_factory=list)
    sold_out_sizes: list[str] = Field(default_factory=list)
    total_in_stock: int = 0
    category_gate: str | None = None

class SearchResult(BaseModel):
    products: list[ProductInfo]
    matched_query: str

class ToolContext(BaseModel):
    user_first_name: str
    first_name: str = ""
    last_name: str = ""
    member_since: str = ""
    is_returning: bool = False
    recent_products: list[dict[str, Any]] = Field(default_factory=list)
    page_context: dict[str, Any] = Field(default_factory=dict)
    # Path, not a live connection: agent tools run on worker threads and SQLite
    # connections cannot cross threads. Each tool opens its own short-lived one.
    db_path: str = ""

    model_config = {"arbitrary_types_allowed": True}

class AgentReply(BaseModel):
    prose: str
    product_ids: list[str] = Field(default_factory=list)

class PageContext(BaseModel):
    route: str = "home"
    product_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    visible_product_ids: list[str] = Field(default_factory=list)
