import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
import os
import requests
from bs4 import BeautifulSoup
import unicodedata
from math import radians, sin, cos, asin, sqrt
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

from sqlalchemy.orm import Session
from sqlalchemy import or_

from db import SessionLocal, engine, Base
from models import Store, Product, InventoryItem

logger = logging.getLogger("simple_backend")

# Config para Hiraoka (búsqueda en vivo)
HIRAOKA_BASE_URL = "https://hiraoka.com.pe/gpsearch/"
HIRAOKA_LAT = -12.06   # aprox Lima centro
HIRAOKA_LON = -77.04

# Config para Falabella (búsqueda en vivo)
FALABELLA_BASE_URL = "https://www.falabella.com.pe/falabella-pe/search"
FALABELLA_LAT = -12.06   # Lima aprox
FALABELLA_LON = -77.04


app = FastAPI(
    title="Simple API",
    description="Backend de Simple: búsqueda de productos con IA + mapa",
    version="0.3.1"
)


def _seed_default_stores(db: Session) -> int:
    existing = db.query(Store).count()
    if existing > 0:
        return 0

    stores = [
        Store(
            name="Hiraoka",
            code="hiraoka",
            address=None,
            district=None,
            city="Online",
            latitude=-12.06,
            longitude=-77.04,
            payment_methods="tarjeta,efectivo,yape,plin",
        ),
        Store(
            name="Promart",
            code="promart",
            address=None,
            district=None,
            city="Online",
            latitude=-12.06,
            longitude=-77.04,
            payment_methods="tarjeta,efectivo",
        ),
        Store(
            name="Oechsle",
            code="oechsle",
            address=None,
            district=None,
            city="Online",
            latitude=-12.06,
            longitude=-77.04,
            payment_methods="tarjeta,efectivo",
        ),
        Store(
            name="PlazaVea",
            code="plazavea",
            address=None,
            district=None,
            city="Online",
            latitude=-12.06,
            longitude=-77.04,
            payment_methods="tarjeta,efectivo",
        ),
    ]

    for store in stores:
        db.add(store)

    db.commit()
    return len(stores)


@app.on_event("startup")
def _startup_init_db() -> None:
    # En Render el servicio puede arrancar con una BD vacía.
    # Creamos tablas y sembramos tiendas por defecto si es necesario.
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            inserted = _seed_default_stores(db)
            if inserted:
                logger.info("Seed de tiendas creado: %s", inserted)
        finally:
            db.close()
    except Exception:
        logger.exception("DB init/seed failed (continuando sin bloquear el arranque)")

# ========= DEPENDENCIA DE BD =========

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ========= MODELOS Pydantic =========

class Location(BaseModel):
    lat: float
    lon: float


class SearchFilters(BaseModel):
    max_price: Optional[float] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    payment_method: Optional[str] = None


class ProductResult(BaseModel):
    product_id: int
    name: str
    brand: Optional[str]
    category: Optional[str]
    image_url: Optional[str]
    product_url: Optional[str] = None
    price: float
    currency: str
    store_id: int
    store_name: str
    store_location: Location
    distance_km: Optional[float]
    payment_methods: List[str]


class SearchRequest(BaseModel):
    query: Optional[str] = None
    user_location: Optional[Location] = None
    filters: Optional[SearchFilters] = None


class SearchResponse(BaseModel):
    results: List[ProductResult]
    total: int
    message: str


class ChatMessage(BaseModel):
    user_id: Optional[str] = None
    message: str
    user_location: Optional[Location] = None


class ChatResponse(BaseModel):
    answer: str
    suggestions: List[str]
    attached_results: Optional[SearchResponse] = None


class StoreCreate(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = "Lima"
    latitude: float
    longitude: float
    payment_methods: Optional[List[str]] = None


class StoreOut(StoreCreate):
    id: int


class ProductCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProductOut(ProductCreate):
    id: int


class InventoryCreate(BaseModel):
    store_id: int
    product_id: int
    price: float
    currency: str = "PEN"
    stock: Optional[int] = None


class InventoryOut(InventoryCreate):
    id: int


class PriceComparison(BaseModel):
    """Comparativa de precios del mismo producto en diferentes tiendas"""
    product_name: str
    brand: Optional[str]
    stores: List[ProductResult]
    cheapest: ProductResult
    most_expensive: ProductResult
    price_difference: float
    average_price: float
    savings_percentage: float


class ProductRecommendation(BaseModel):
    """Recomendación inteligente de producto"""
    product: ProductResult
    reason: str
    score: float  # 0-100


class RecommendationResponse(BaseModel):
    """Respuesta de recomendaciones"""
    recommendations: List[ProductRecommendation]
    total: int
    message: str


class PriceAlert(BaseModel):
    """Alerta de precio para un producto"""
    id: Optional[int] = None
    product_name: str
    target_price: float
    user_email: Optional[str] = None
    active: bool = True
    created_at: Optional[str] = None


class PriceStatistics(BaseModel):
    """Estadísticas de precios para un producto"""
    product_name: str
    count: int
    min_price: float
    max_price: float
    average_price: float
    median_price: float
    stores: dict  # {store_name: price}


# ========= UTILS =========

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distancia aproximada en km entre dos puntos lat/lon.
    """
    R = 6371.0  # radio Tierra en km
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


def normalize_text(text: str) -> str:
    """
    Pasa a minúsculas y elimina tildes para comparar texto.
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


# ========= FUNCIONES DE IA Y BÚSQUEDA MEJORADA =========

def correct_search_query(query: str, suggestions: Optional[List[str]] = None) -> str:
    """
    Corrige errores de ortografía en la búsqueda usando fuzzy matching.
    Si hay sugerencias, intenta hacer match.
    """
    if not suggestions:
        # Sugerencias comunes de productos
        suggestions = [
            "iphone", "samsung", "huawei", "xiaomi", "motorola", "nokia",
            "sony", "lg", "panasonic", "tcl", "acer", "asus", "hp", "lenovo",
            "celular", "smartphone", "tablet", "laptop", "televisor", "tv",
            "auriculares", "headphones", "smartwatch", "watch", "mica", "protector",
            "cargador", "cable", "bateria", "funda", "case",
            "pura", "pro", "ultra", "max", "plus", "lite", "se"
        ]
    
    # Si la query está muy bien escrita, no hacer nada
    if query.lower() in [s.lower() for s in suggestions]:
        return query
    
    # Buscar la sugerencia más similar
    best_match = process.extractOne(query.lower(), suggestions, scorer=fuzz.token_set_ratio)
    if best_match and best_match[1] > 80:
        return best_match[0]
    
    return query


def smart_search_filter(products: List['ProductResult'], query: str) -> List['ProductResult']:
    """
    Filtra inteligentemente productos según la query.
    Puede entender intenciones como "barato", "premium", etc.
    """
    query_lower = normalize_text(query)
    
    # Intenciones de precio
    if any(word in query_lower for word in ["barato", "economico", "oferta", "descuento", "rebajado"]):
        # Ordenar por precio ascendente
        products.sort(key=lambda p: p.price)
        return products[:min(len(products), 10)]
    
    if any(word in query_lower for word in ["premium", "caro", "lujo", "top", "mejor"]):
        # Filtrar productos caros
        threshold = sum(p.price for p in products) / len(products) if products else 0
        products = [p for p in products if p.price >= threshold]
        products.sort(key=lambda p: p.price, reverse=True)
        return products[:min(len(products), 10)]
    
    # Intenciones de marca
    brand_keywords = {
        "apple": "Apple",
        "samsung": "Samsung",
        "huawei": "Huawei",
        "xiaomi": "Xiaomi",
        "sony": "Sony"
    }
    
    for keyword, brand in brand_keywords.items():
        if keyword in query_lower:
            products = [p for p in products if p.brand and brand.lower() in p.brand.lower()]
            return products
    
    return products


def get_price_comparison(products: List[ProductResult], product_name: str) -> Optional[PriceComparison]:
    """
    Compara precios del mismo producto en diferentes tiendas.
    """
    if not products:
        return None
    
    # Agrupar por nombre normalizado
    norm_name = normalize_text(product_name)
    matching_products = [
        p for p in products 
        if normalize_text(p.name) == norm_name or normalize_text(f"{p.name} {p.brand or ''}") == norm_name
    ]
    
    if len(matching_products) < 2:
        return None
    
    prices = [p.price for p in matching_products]
    cheapest = min(matching_products, key=lambda p: p.price)
    most_expensive = max(matching_products, key=lambda p: p.price)
    average_price = sum(prices) / len(prices)
    price_difference = most_expensive.price - cheapest.price
    savings_percentage = (price_difference / most_expensive.price) * 100 if most_expensive.price > 0 else 0
    
    return PriceComparison(
        product_name=product_name,
        brand=matching_products[0].brand,
        stores=matching_products,
        cheapest=cheapest,
        most_expensive=most_expensive,
        price_difference=price_difference,
        average_price=average_price,
        savings_percentage=round(savings_percentage, 2)
    )


def get_price_statistics(products: List[ProductResult], product_name: str) -> Optional[PriceStatistics]:
    """
    Calcula estadísticas de precios para un producto.
    """
    if not products:
        return None
    
    norm_name = normalize_text(product_name)
    matching_products = [
        p for p in products 
        if normalize_text(p.name) == norm_name or normalize_text(f"{p.name} {p.brand or ''}") == norm_name
    ]
    
    if not matching_products:
        return None
    
    prices = sorted([p.price for p in matching_products])
    count = len(prices)
    min_price = min(prices)
    max_price = max(prices)
    average_price = sum(prices) / count
    median_price = prices[count // 2] if count % 2 == 1 else (prices[count // 2 - 1] + prices[count // 2]) / 2
    
    stores_dict = {}
    for p in matching_products:
        stores_dict[p.store_name] = p.price
    
    return PriceStatistics(
        product_name=product_name,
        count=count,
        min_price=min_price,
        max_price=max_price,
        average_price=round(average_price, 2),
        median_price=round(median_price, 2),
        stores=stores_dict
    )


def generate_recommendations(products: List[ProductResult], query: str) -> List[ProductRecommendation]:
    """
    Genera recomendaciones inteligentes basadas en la búsqueda.
    """
    recommendations = []
    
    if not products:
        return recommendations
    
    # Calcular scores para cada producto
    for idx, product in enumerate(products[:10]):  # Top 10
        score = 100
        reason = []
        
        # Puntos por precio
        avg_price = sum(p.price for p in products) / len(products)
        if product.price < avg_price * 0.8:
            score += 20
            reason.append("Muy buen precio")
        elif product.price > avg_price * 1.2:
            score -= 15
            reason.append("Precio elevado")
        
        # Puntos por tienda confiable
        trusted_stores = ["Hiraoka Online", "Falabella Online"]
        if product.store_name in trusted_stores:
            score += 15
            reason.append(f"Vendido por {product.store_name}")
        
        # Puntos por posición (primeros son mejores)
        score += (10 - idx)
        
        recommendations.append(
            ProductRecommendation(
                product=product,
                reason="; ".join(reason) if reason else "Producto relevante",
                score=min(100, score)
            )
        )
    
    # Ordenar por score
    recommendations.sort(key=lambda r: r.score, reverse=True)
    return recommendations


# ========= SCRAPER HIRAOKA (LIVE, SIN BD) =========

def scrape_hiraoka_live(
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
) -> List[ProductResult]:
    """
    Llama a la web de Hiraoka en tiempo real y devuelve productos tal cual,
    sin aplicar todavía el filtro estricto de texto.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    params = {"q": query}

    resp = requests.get(HIRAOKA_BASE_URL, params=params, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Cada producto está en:
    # <div class="product-item-info" data-container="product-grid">
    cards = soup.select("div.product-item-info[data-container='product-grid']")

    results: List[ProductResult] = []

    for idx, card in enumerate(cards, start=1):
        # ===== Nombre =====
        name_el = card.select_one(
            "strong.product.name.product-item-name a.product-item-link"
        )
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        href = name_el.get("href") if hasattr(name_el, "get") else None
        if href and isinstance(href, str):
            href = href.strip()
        if href and href.startswith("/"):
            product_url = f"https://hiraoka.com.pe{href}"
        else:
            product_url = href if href else None

        # ===== Marca =====
        brand_el = card.select_one(
            "strong.product.brand.product-item-brand a.product-item-link"
        )
        brand = brand_el.get_text(strip=True) if brand_el else None

        # ===== Precio =====
        price_span = card.select_one("div.price-box [data-price-type='finalPrice']")
        amount_str = None

        if price_span and price_span.get("data-price-amount"):
            amount_str = price_span["data-price-amount"].strip()
        else:
            price_text_el = card.select_one("div.price-box span.price")
            if not price_text_el:
                continue
            price_text = price_text_el.get_text(strip=True)
            digits = (
                price_text.replace("S/", "")
                .replace("S/.", "")
                .replace("s/", "")
                .replace("\xa0", " ")
                .replace(" ", "")
                .replace(",", "")
            )
            amount_str = digits

        try:
            price = float(Decimal(amount_str))
        except Exception:
            continue

        # ===== Imagen =====
        img_el = card.select_one("img.product-image-photo")
        image_url = img_el["src"] if img_el and img_el.get("src") else None

        # ===== Filtros simples por precio y marca (si vienen) =====
        if filters:
            if filters.max_price is not None and price > filters.max_price:
                continue
            if filters.brand:
                if not brand or filters.brand.lower() not in brand.lower():
                    continue

        # ===== Distancia (opcional) =====
        if user_location:
            distance = haversine_km(
                user_location.lat,
                user_location.lon,
                HIRAOKA_LAT,
                HIRAOKA_LON,
            )
            distance_km = round(distance, 3)
        else:
            distance_km = None

        payment_methods = ["tarjeta", "efectivo"]

        results.append(
            ProductResult(
                product_id=idx,
                name=name,
                brand=brand,
                category=None,
                image_url=image_url,
                product_url=product_url,
                price=price,
                currency="PEN",
                store_id=1,
                store_name="Hiraoka Online",
                store_location=Location(lat=HIRAOKA_LAT, lon=HIRAOKA_LON),
                distance_km=distance_km,
                payment_methods=payment_methods,
            )
        )

    # Orden básico
    if user_location:
        results.sort(
            key=lambda r: (
                r.distance_km if r.distance_km is not None else 999999,
                r.price,
            )
        )
    else:
        results.sort(key=lambda r: r.price)

    return results

def scrape_falabella_live(
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
) -> List[ProductResult]:
    """
    Scraper en vivo para Falabella Perú (estructura nueva 2025).
    Usa la estructura actual de los pods:
      - Producto en div.pod (con clase pod-2_GRID, pod-3_GRID, etc.)
      - Marca en b.pod-title
      - Nombre en b.pod-subTitle
      - Precio en li[data-event-price]
    NO toca la BD.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    # Falabella usa 'Ntt' como parámetro de texto
    params = {"Ntt": query}

    resp = requests.get(FALABELLA_BASE_URL, params=params, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Seleccionar todos los pods de productos (nueva estructura)
    product_pods = soup.select("a[data-pod='catalyst-pod']")

    results: List[ProductResult] = []

    for idx, pod in enumerate(product_pods, start=1):
        href = pod.get("href") if hasattr(pod, "get") else None
        if href and isinstance(href, str):
            href = href.strip()
        if href and href.startswith("/"):
            product_url = f"https://www.falabella.com.pe{href}"
        else:
            product_url = href if href else None
        # ========= MARCA =========
        brand_el = pod.select_one("b.pod-title")
        brand = brand_el.get_text(strip=True) if brand_el else None

        # ========= NOMBRE (subtítulo) =========
        name_el = pod.select_one("b.pod-subTitle")
        if not name_el:
            # sin nombre, no tiene sentido
            continue
        name = name_el.get_text(strip=True)

        # ========= FILTRO ESTRICTO POR PALABRAS DE LA QUERY =====
        # Unimos nombre + marca y normalizamos (minúsculas, sin tildes)
        full_name = f"{name} {brand or ''}"
        norm_full_name = normalize_text(full_name)

        # Partimos la query en palabras
        query_tokens = [
            t for t in normalize_text(query).split()
        ]

        # Si quieres que TODAS las palabras de la query aparezcan como palabras EXACTAS en el nombre+marca:
        full_name_words = norm_full_name.split()
        if query_tokens and not all(tok in full_name_words for tok in query_tokens):
            # Este producto no cumple con la búsqueda estricta, lo saltamos
            continue

        # ========= PRECIO =========
        # <li data-event-price="2,499" class="... prices-0">...</li>
        price_li = pod.select_one("li[data-event-price]")
        if not price_li:
            continue

        amount_str = price_li.get("data-event-price", "").strip()
        if not amount_str:
            # fallback: leer texto S/  2,499
            price_span = price_li.select_one("span")
            if not price_span:
                continue
            price_text = price_span.get_text(strip=True)
            digits = (
                price_text.replace("S/", "")
                .replace("S/.", "")
                .replace("s/", "")
                .replace("\xa0", " ")
                .replace(" ", "")
                .replace(",", "")
            )
            amount_str = digits

        try:
            price = float(Decimal(amount_str.replace(",", "")))
        except Exception:
            continue

        # ========= IMAGEN =========
        # <img src="..." alt="...">
        img_el = pod.select_one("img[alt]")
        image_url = img_el["src"] if img_el and img_el.get("src") else None

        # ========= FILTROS SIMPLES (precio/marca) =========
        if filters:
            if filters.max_price is not None and price > filters.max_price:
                continue
            if filters.brand:
                if not brand or filters.brand.lower() not in brand.lower():
                    continue

        # ========= DISTANCIA AL USUARIO (opcional) =========
        if user_location:
            distance = haversine_km(
                user_location.lat,
                user_location.lon,
                FALABELLA_LAT,
                FALABELLA_LON,
            )
            distance_km = round(distance, 3)
        else:
            distance_km = None

        payment_methods = ["tarjeta", "efectivo"]

        results.append(
            ProductResult(
                product_id=idx,  # id artificial para esta respuesta
                name=name,
                brand=brand,
                category=None,
                image_url=image_url,
                product_url=product_url,
                price=price,
                currency="PEN",
                store_id=2,
                store_name="Falabella Online",
                store_location=Location(lat=FALABELLA_LAT, lon=FALABELLA_LON),
                distance_km=distance_km,
                payment_methods=payment_methods,
            )
        )

    # Orden básico
    if user_location:
        results.sort(
            key=lambda r: (
                r.distance_km if r.distance_km is not None else 999999,
                r.price,
            )
        )
    else:
        results.sort(key=lambda r: r.price)

    return results



# ========= ENDPOINTS: TIENDAS =========

@app.post("/stores", response_model=StoreOut)
def create_store(store: StoreCreate, db: Session = Depends(get_db)):
    payment_methods_str = ",".join(store.payment_methods) if store.payment_methods else None

    db_store = Store(
        name=store.name,
        address=store.address,
        district=store.district,
        city=store.city,
        latitude=store.latitude,
        longitude=store.longitude,
        payment_methods=payment_methods_str,
    )
    db.add(db_store)
    db.commit()
    db.refresh(db_store)

    methods = db_store.payment_methods.split(",") if db_store.payment_methods else None

    return StoreOut(
        id=db_store.id,
        name=db_store.name,
        address=db_store.address,
        district=db_store.district,
        city=db_store.city,
        latitude=db_store.latitude,
        longitude=db_store.longitude,
        payment_methods=methods,
    )


@app.get("/stores", response_model=List[StoreOut])
def list_stores(db: Session = Depends(get_db)):
    stores = db.query(Store).all()
    if not stores:
        try:
            inserted = _seed_default_stores(db)
            if inserted:
                stores = db.query(Store).all()
        except Exception:
            logger.exception("Seed en /stores falló")
    out: List[StoreOut] = []
    for s in stores:
        methods = s.payment_methods.split(",") if s.payment_methods else None
        out.append(
            StoreOut(
                id=s.id,
                name=s.name,
                code=s.code,
                address=s.address,
                district=s.district,
                city=s.city,
                latitude=s.latitude,
                longitude=s.longitude,
                payment_methods=methods,
            )
        )
    return out


# ========= ENDPOINTS: PRODUCTOS =========

@app.post("/products", response_model=ProductOut)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = Product(
        name=product.name,
        brand=product.brand,
        category=product.category,
        description=product.description,
        image_url=product.image_url,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return ProductOut(
        id=db_product.id,
        name=db_product.name,
        brand=db_product.brand,
        category=db_product.category,
        description=db_product.description,
        image_url=db_product.image_url,
    )


@app.get("/products", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    items = db.query(Product).all()
    return [
        ProductOut(
            id=p.id,
            name=p.name,
            brand=p.brand,
            category=p.category,
            description=p.description,
            image_url=p.image_url,
        )
        for p in items
    ]


# ========= ENDPOINTS: INVENTARIO =========

@app.post("/inventory-items", response_model=InventoryOut)
def create_inventory_item(item: InventoryCreate, db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == item.store_id).first()
    if not store:
        raise HTTPException(status_code=400, detail="La tienda no existe")

    product = db.query(Product).filter(Product.id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=400, detail="El producto no existe")

    db_item = InventoryItem(
        store_id=item.store_id,
        product_id=item.product_id,
        price=item.price,
        currency=item.currency,
        stock=item.stock,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    return InventoryOut(
        id=db_item.id,
        store_id=db_item.store_id,
        product_id=db_item.product_id,
        price=float(db_item.price),
        currency=db_item.currency,
        stock=db_item.stock,
    )


@app.get("/inventory-items", response_model=List[InventoryOut])
def list_inventory_items(db: Session = Depends(get_db)):
    items = db.query(InventoryItem).all()
    return [
        InventoryOut(
            id=i.id,
            store_id=i.store_id,
            product_id=i.product_id,
            price=float(i.price),
            currency=i.currency,
            stock=i.stock,
        )
        for i in items
    ]


# ========= ENDPOINT: BÚSQUEDA SOBRE BD =========

@app.post("/search", response_model=SearchResponse)
def search_products(payload: SearchRequest, db: Session = Depends(get_db)):
    """
    Búsqueda directa sobre la BD local (productos que tú hayas cargado).
    """
    q = (
        db.query(InventoryItem, Product, Store)
        .join(Product, InventoryItem.product_id == Product.id)
        .join(Store, InventoryItem.store_id == Store.id)
    )

    if payload.query:
        pattern = f"%{payload.query}%"
        q = q.filter(
            or_(
                Product.name.ilike(pattern),
                Product.brand.ilike(pattern),
                Product.category.ilike(pattern),
            )
        )

    if payload.filters:
        f = payload.filters
        if f.category:
            q = q.filter(Product.category == f.category)
        if f.brand:
            q = q.filter(Product.brand == f.brand)
        if f.max_price is not None:
            q = q.filter(InventoryItem.price <= f.max_price)
        if f.payment_method:
            pattern_pm = f"%{f.payment_method}%"
            q = q.filter(Store.payment_methods.ilike(pattern_pm))

    rows = q.all()

    results: List[ProductResult] = []
    for inv, prod, store in rows:
        if payload.user_location:
            distance = haversine_km(
                payload.user_location.lat,
                payload.user_location.lon,
                store.latitude,
                store.longitude,
            )
            distance_km = round(distance, 3)
        else:
            distance_km = None

        methods = store.payment_methods.split(",") if store.payment_methods else []

        results.append(
            ProductResult(
                product_id=prod.id,
                name=prod.name,
                brand=prod.brand,
                category=prod.category,
                image_url=prod.image_url,
                price=float(inv.price),
                currency=inv.currency,
                store_id=store.id,
                store_name=store.name,
                store_location=Location(lat=store.latitude, lon=store.longitude),
                distance_km=distance_km,
                payment_methods=methods,
            )
        )

    if payload.user_location:
        results.sort(
            key=lambda r: (
                r.distance_km if r.distance_km is not None else 999999,
                r.price,
            )
        )
    else:
        results.sort(key=lambda r: r.price)

    message = "OK" if results else "Sin resultados para esta búsqueda"

    return SearchResponse(results=results, total=len(results), message=message)


# ========= ENDPOINT: BÚSQUEDA HIRAOKA EN VIVO (CON FILTRO ESTRICTO) =========

@app.post("/search/hiraoka-live", response_model=SearchResponse)
def search_hiraoka_live(payload: SearchRequest):
    """
    Búsqueda en tiempo real en Hiraoka (sin usar la base de datos),
    con filtro ESTRICTO por las palabras que escribió el usuario.
    """
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en Hiraoka.",
        )

    # 1) Scraping crudo (trae todo lo que devuelve Hiraoka para ese q)
    raw_results = scrape_hiraoka_live(
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    # 2) Normalizamos la query y la rompemos en palabras (ignorando palabras muy cortas)
    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    # 3) Filtro estricto: TODAS las palabras deben aparecer en (nombre + marca)
    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en Hiraoka"

    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/falabella-live", response_model=SearchResponse)
def search_falabella_live_endpoint(payload: SearchRequest):
    """
    Búsqueda en tiempo real en Falabella (sin usar la base),
    con el mismo filtro ESTRICTO de palabras que usamos en Hiraoka.
    """
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en Falabella.",
        )

    # 1) Scraping crudo de Falabella
    raw_results = scrape_falabella_live(
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    # 2) Filtro estricto por las palabras escritas por el usuario
    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en Falabella"

    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/inkafarma-live", response_model=SearchResponse)
def search_inkafarma_live_endpoint(payload: SearchRequest):
    """Búsqueda en tiempo real en Inkafarma (sin usar la base), con filtro ESTRICTO."""
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en Inkafarma.",
        )

    try:
        from inkafarma_scraper import scrape_inkafarma_live
    except ImportError:
        raise HTTPException(status_code=503, detail="Scraper de Inkafarma no disponible")

    raw_results = scrape_inkafarma_live(
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en Inkafarma"
    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/mifarma-live", response_model=SearchResponse)
def search_mifarma_live_endpoint(payload: SearchRequest):
    """Búsqueda en tiempo real en Mifarma (Algolia), con filtro ESTRICTO."""
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en Mifarma.",
        )

    try:
        from mifarma_scraper import scrape_mifarma_live
    except ImportError:
        raise HTTPException(status_code=503, detail="Scraper de Mifarma no disponible")

    raw_results = scrape_mifarma_live(
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en Mifarma"
    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/promart-live", response_model=SearchResponse)
def search_promart_live_endpoint(payload: SearchRequest):
    """Búsqueda en tiempo real en Promart (API VTEX catalog_system), con filtro ESTRICTO."""
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en Promart.",
        )

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        raise HTTPException(status_code=503, detail="Scraper VTEX no disponible")

    raw_results = scrape_vtex_catalog_live(
        store_name="Promart",
        store_id=5,
        base_origin="https://www.promart.pe",
        store_lat=-12.06,
        store_lon=-77.04,
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en Promart"
    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/oechsle-live", response_model=SearchResponse)
def search_oechsle_live_endpoint(payload: SearchRequest):
    """Búsqueda en tiempo real en Oechsle (API VTEX catalog_system), con filtro ESTRICTO."""
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en Oechsle.",
        )

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        raise HTTPException(status_code=503, detail="Scraper VTEX no disponible")

    raw_results = scrape_vtex_catalog_live(
        store_name="Oechsle",
        store_id=6,
        base_origin="https://www.oechsle.pe",
        store_lat=-12.06,
        store_lon=-77.04,
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en Oechsle"
    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/plazavea-live", response_model=SearchResponse)
def search_plazavea_live_endpoint(payload: SearchRequest):
    """Búsqueda en tiempo real en PlazaVea (API VTEX catalog_system), con filtro ESTRICTO."""
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="Por ahora 'query' es obligatorio para la búsqueda en PlazaVea.",
        )

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        raise HTTPException(status_code=503, detail="Scraper VTEX no disponible")

    raw_results = scrape_vtex_catalog_live(
        store_name="PlazaVea",
        store_id=7,
        base_origin="https://www.plazavea.com.pe",
        store_lat=-12.06,
        store_lon=-77.04,
        query=payload.query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    norm_query = normalize_text(payload.query)
    tokens = [t for t in norm_query.split() if len(t) > 2]

    if tokens:
        filtered_results: List[ProductResult] = []
        for r in raw_results:
            full_name = f"{r.name} {r.brand or ''}"
            norm_name = normalize_text(full_name)
            if all(tok in norm_name for tok in tokens):
                filtered_results.append(r)
        results = filtered_results
    else:
        results = raw_results

    message = "OK" if results else "Sin resultados para esta búsqueda en PlazaVea"
    return SearchResponse(results=results, total=len(results), message=message)


@app.post("/search/all-stores", response_model=SearchResponse)
def search_all_stores(payload: SearchRequest):
    """
    Búsqueda combinada en TODAS las tiendas:
    - Hiraoka
    - Falabella
    - Promart
    - Oechsle
    - PlazaVea
    - Inkafarma
    
    Con corrección automática y filtrado inteligente.
    """
    if not payload.query:
        raise HTTPException(
            status_code=400,
            detail="'query' es obligatorio",
        )

    # 1) Corregir query automáticamente
    corrected_query = correct_search_query(payload.query)
    
    # 2) Buscar en todas las tiendas

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        print("Advertencia: VTEX scraper no disponible")
        promart_results = []
        oechsle_results = []
        plazavea_results = []
    else:
        promart_results = scrape_vtex_catalog_live(
            store_name="Promart",
            store_id=5,
            base_origin="https://www.promart.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        oechsle_results = scrape_vtex_catalog_live(
            store_name="Oechsle",
            store_id=6,
            base_origin="https://www.oechsle.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        plazavea_results = scrape_vtex_catalog_live(
            store_name="PlazaVea",
            store_id=7,
            base_origin="https://www.plazavea.com.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )

    # Hiraoka y Falabella siempre disponibles
    hiraoka_results = scrape_hiraoka_live(
        query=corrected_query,
        user_location=payload.user_location,
        filters=payload.filters,
    )
    
    falabella_results = scrape_falabella_live(
        query=corrected_query,
        user_location=payload.user_location,
        filters=payload.filters,
    )

    # Inkafarma
    try:
        from inkafarma_scraper import scrape_inkafarma_live
    except ImportError:
        print("Advertencia: Inkafarma scraper no disponible")
        inkafarma_results = []
    else:
        inkafarma_results = scrape_inkafarma_live(
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )

    # 3) Combinar resultados
    all_results = (
        hiraoka_results
        + falabella_results
        + promart_results
        + oechsle_results
        + plazavea_results
        + inkafarma_results
    )

    # 4) Aplicar filtrado inteligente
    if all_results:
        all_results = smart_search_filter(all_results, corrected_query)

    # 5) Ordenar por precio si no hay ubicación del usuario
    if not payload.user_location:
        all_results.sort(key=lambda r: (r.price, r.store_name))

    # 6) Eliminar duplicados (por nombre + marca similar)
    seen = set()
    unique_results = []
    for r in all_results:
        key = normalize_text(f"{r.name} {r.brand or ''}")
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    # Limitar a 50 resultados
    unique_results = unique_results[:50]

    message = f"Búsqueda en {len(set(r.store_name for r in unique_results))} tiendas: {len(unique_results)} productos encontrados"
    if corrected_query != payload.query:
        message += f" (búsqueda corregida: '{corrected_query}')"

    return SearchResponse(results=unique_results, total=len(unique_results), message=message)


@app.post("/search/recommendations", response_model=RecommendationResponse)
def get_recommendations(payload: SearchRequest):
    """
    Obtiene recomendaciones inteligentes basadas en una búsqueda.
    Analiza precios, tiendas confiables y relevancia.
    """
    if not payload.query:
        raise HTTPException(status_code=400, detail="'query' es obligatorio")

    # Buscar en todas las tiendas
    corrected_query = correct_search_query(payload.query)
    

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        promart_results = []
        oechsle_results = []
        plazavea_results = []
    else:
        promart_results = scrape_vtex_catalog_live(
            store_name="Promart",
            store_id=5,
            base_origin="https://www.promart.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        oechsle_results = scrape_vtex_catalog_live(
            store_name="Oechsle",
            store_id=6,
            base_origin="https://www.oechsle.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        plazavea_results = scrape_vtex_catalog_live(
            store_name="PlazaVea",
            store_id=7,
            base_origin="https://www.plazavea.com.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )

    hiraoka_results = scrape_hiraoka_live(corrected_query, payload.user_location, payload.filters)
    falabella_results = scrape_falabella_live(corrected_query, payload.user_location, payload.filters)
    
    all_results = (
        hiraoka_results
        + falabella_results
        
        + promart_results
        + oechsle_results
        + plazavea_results
    )

    # Generar recomendaciones
    recommendations = generate_recommendations(all_results, corrected_query)
    
    message = f"Se generaron {len(recommendations)} recomendaciones basadas en {corrected_query}"
    
    return RecommendationResponse(
        recommendations=recommendations,
        total=len(recommendations),
        message=message
    )


@app.post("/search/compare-prices")
def compare_prices(payload: SearchRequest):
    """
    Compara precios del mismo producto en diferentes tiendas.
    Muestra ahorros potenciales.
    """
    if not payload.query:
        raise HTTPException(status_code=400, detail="'query' es obligatorio")

    corrected_query = correct_search_query(payload.query)
    
    # Obtener productos de todas las tiendas
    

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        promart_results = []
        oechsle_results = []
        plazavea_results = []
    else:
        promart_results = scrape_vtex_catalog_live(
            store_name="Promart",
            store_id=5,
            base_origin="https://www.promart.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        oechsle_results = scrape_vtex_catalog_live(
            store_name="Oechsle",
            store_id=6,
            base_origin="https://www.oechsle.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        plazavea_results = scrape_vtex_catalog_live(
            store_name="PlazaVea",
            store_id=7,
            base_origin="https://www.plazavea.com.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )

    hiraoka_results = scrape_hiraoka_live(corrected_query, payload.user_location, payload.filters)
    falabella_results = scrape_falabella_live(corrected_query, payload.user_location, payload.filters)
    
    all_results = (
        hiraoka_results
        + falabella_results
        
        + promart_results
        + oechsle_results
        + plazavea_results
    )

    # Generar comparativas
    comparisons = []
    
    # Agrupar por nombre normalizado
    products_by_name = {}
    for product in all_results:
        norm_name = normalize_text(product.name)
        if norm_name not in products_by_name:
            products_by_name[norm_name] = []
        products_by_name[norm_name].append(product)
    
    # Crear comparativas
    for product_name, products in products_by_name.items():
        if len(products) > 1:
            comparison = get_price_comparison(products, product_name)
            if comparison:
                comparisons.append(comparison)
    
    # Ordenar por ahorro potencial
    comparisons.sort(key=lambda c: c.savings_percentage, reverse=True)
    
    return {
        "comparisons": comparisons[:10],
        "total": len(comparisons),
        "message": f"Se encontraron {len(comparisons)} productos en múltiples tiendas"
    }


@app.post("/search/statistics")
def get_statistics(payload: SearchRequest):
    """
    Obtiene estadísticas de precios para los productos encontrados.
    """
    if not payload.query:
        raise HTTPException(status_code=400, detail="'query' es obligatorio")

    corrected_query = correct_search_query(payload.query)
    
    # Obtener productos
    

    try:
        from vtex_scraper import scrape_vtex_catalog_live
    except ImportError:
        promart_results = []
        oechsle_results = []
        plazavea_results = []
    else:
        promart_results = scrape_vtex_catalog_live(
            store_name="Promart",
            store_id=5,
            base_origin="https://www.promart.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        oechsle_results = scrape_vtex_catalog_live(
            store_name="Oechsle",
            store_id=6,
            base_origin="https://www.oechsle.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )
        plazavea_results = scrape_vtex_catalog_live(
            store_name="PlazaVea",
            store_id=7,
            base_origin="https://www.plazavea.com.pe",
            store_lat=-12.06,
            store_lon=-77.04,
            query=corrected_query,
            user_location=payload.user_location,
            filters=payload.filters,
        )

    hiraoka_results = scrape_hiraoka_live(corrected_query, payload.user_location, payload.filters)
    falabella_results = scrape_falabella_live(corrected_query, payload.user_location, payload.filters)
    
    all_results = (
        hiraoka_results
        + falabella_results
        
        + promart_results
        + oechsle_results
        + plazavea_results
    )

    # Generar estadísticas
    statistics = []
    
    products_by_name = {}
    for product in all_results:
        norm_name = normalize_text(product.name)
        if norm_name not in products_by_name:
            products_by_name[norm_name] = []
        products_by_name[norm_name].append(product)
    
    for product_name, products in products_by_name.items():
        stats = get_price_statistics(products, product_name)
        if stats:
            statistics.append(stats)
    
    # Ordenar por cantidad de tiendas
    statistics.sort(key=lambda s: s.count, reverse=True)
    
    return {
        "statistics": statistics[:10],
        "total": len(statistics),
        "message": f"Estadísticas de {len(statistics)} productos encontrados"
    }


# ========= ENDPOINT: CHAT (STUB) =========

@app.post("/chat", response_model=ChatResponse)
async def chat_with_ai(payload: ChatMessage):
    answer = (
        "Este es un stub de demo. Cuando conectemos la IA, "
        "podrás escribir o hablar y Simple interpretará la intención, "
        "buscará productos reales y te explicará las opciones."
    )

    dummy_search = SearchResponse(results=[], total=0, message="Sin resultados (demo).")

    return ChatResponse(
        answer=answer,
        suggestions=[
            "Búscame una laptop para oficina",
            "Encuentra un antigripal cerca de mí",
            "Muéstrame televisores Samsung de 55 pulgadas",
        ],
        attached_results=dummy_search,
    )


# ========= ENDPOINT: BÚSQUEDA POR IMAGEN (STUB) =========

@app.post("/image-search", response_model=SearchResponse)
async def image_search(
    file: UploadFile = File(...),
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    db: Session = Depends(get_db),
):
    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="Formato de imagen no soportado")

    return SearchResponse(
        results=[], total=0, message="Búsqueda por imagen aún no implementada (demo)"
    )
