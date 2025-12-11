from typing import Optional, List
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    brand: Optional[str] = None
    price: float
    currency: str
    store_name: str
    product_url: str
    image_url: Optional[str] = None


class SearchFilters(BaseModel):
    raw_query: str
    normalized_query: str
    brand: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class ChatResponse(BaseModel):
    """
    Respuesta del endpoint /chat:
    - answer: texto generado por la IA (explicación/recomendación)
    - products: lista de productos encontrados
    """
    answer: str
    products: List[Product]
