import json
import sqlite3
from typing import Any
from models import SearchFilters

def _array(value: str | None) -> list[str]:
    try: return json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError): return []

def _category(value: str) -> str:
    text=value.lower().replace('-', ' ').replace('_',' ')
    if 'quarter' in text or '1 4' in text: return 'quarter-zip'
    if 'hood' in text and 'full zip' in text: return 'full-zip hoodie'
    if 'hood' in text: return 'hoodie'
    if 'fleece' in text or 'jacket' in text: return 'fleece/jacket'
    if 'crew' in text: return 'crewneck'
    if 'long sleeve' in text or ' l s ' in f' {text} ': return 'long-sleeve'
    if 'shirt' in text: return 't-shirt'
    return text

def _query_categories(query: str) -> set[str] | None:
    text = query.lower().replace('_', ' ').replace('-', ' ')
    for phrase in ('full zip hoodie', 'quarter zip', 'long sleeve', 't shirt', 'crewneck', 'hoodie', 'fleece', 'jacket'):
        if phrase in text:
            category = _category(phrase)
            if category == 'hoodie' and 'full zip' not in text:
                return {'hoodie', 'full-zip hoodie'}
            return {category}
    return None

def _product(row: sqlite3.Row, connection: sqlite3.Connection) -> dict[str, Any]:
    item=dict(row); item['colors']=_array(item['colors']); item['search_tags']=_array(item['search_tags']); item['category']=_category(item['garment_type']); item['image_url']=f"/media/{item['image_file_path']}"
    item['inventory']=[dict(x) for x in connection.execute('SELECT size,quantity FROM inventory WHERE product_id=? ORDER BY id',(item['product_id'],))]
    item['in_stock_sizes']=[row['size'] for row in item['inventory'] if row['quantity'] > 0]
    item['sold_out_sizes']=[row['size'] for row in item['inventory'] if row['quantity'] <= 0]
    item['total_in_stock']=sum(row['quantity'] for row in item['inventory'])
    return item

def search_products(connection: sqlite3.Connection, filters: SearchFilters) -> list[dict[str, Any]]:
    query=filters.query.lower(); terms={x.rstrip('s') for x in query.split() if len(x)>2 and x not in {'what','whats','your','got','cheapest','show','find','anything','with'}}; gate_categories={filters.category} if filters.category else _query_categories(query)
    results=[]; color=filters.color.lower().replace('navy blue','navy') if filters.color else None
    for row in connection.execute('SELECT * FROM catalogue ORDER BY name'):
        item=_product(row,connection); hay=' '.join([item['name'],item['garment_type'],item['description'],*item['colors'],*item['search_tags']]).lower(); normalized_colors={x.lower().replace('navy blue','navy') for x in item['colors']}
        item['category_gate']=','.join(sorted(gate_categories)) if gate_categories else None
        if gate_categories and item['category'] not in gate_categories: continue
        if color and color not in normalized_colors: continue
        if filters.size and not any(x['size']==filters.size and x['quantity']>0 for x in item['inventory']): continue
        if filters.max_price is not None and item['price']>filters.max_price: continue
        score=sum(term in hay for term in terms)
        if gate_categories or not terms or score: results.append((score,item))
    ordered=sorted(results,key=lambda value: ((value[1]['price'] if 'cheapest' in query else -value[0]), value[1]['name']))
    return [item for _,item in ordered]

def get_product(connection: sqlite3.Connection, product_id: str) -> dict[str, Any] | None:
    row=connection.execute('SELECT * FROM catalogue WHERE product_id=?',(product_id,)).fetchone(); return _product(row,connection) if row else None

def check_stock(connection: sqlite3.Connection, product_id: str, size: str | None = None) -> list[dict[str, Any]]:
    query='SELECT size,quantity FROM inventory WHERE product_id=?'; args=[product_id]
    if size: query+=' AND size=?'; args.append(size)
    return [dict(row) for row in connection.execute(query+' ORDER BY id',args)]
