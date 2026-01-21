import time
from typing import Any, Dict, List, Optional

import requests
from urllib.parse import urljoin

from main import haversine_km, Location, normalize_text, ProductResult, SearchFilters

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def _safe_get(dct: Any, path: List[Any]) -> Any:
    cur = dct
    for key in path:
        if cur is None:
            return None
        try:
            if isinstance(key, int):
                if not isinstance(cur, list) or len(cur) <= key:
                    return None
                cur = cur[key]
            else:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(key)
        except Exception:
            return None
    return cur


def scrape_vtex_catalog_live(
    *,
    store_name: str,
    store_id: int,
    base_origin: str,
    store_lat: float,
    store_lon: float,
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
    limit: int = 25,
    payment_methods: Optional[List[str]] = None,
) -> List[ProductResult]:
    """Scraper en vivo para tiendas VTEX via `api/catalog_system`.

    Usa el endpoint público:
    `GET {base_origin}/api/catalog_system/pub/products/search/?ft=<query>&_from=0&_to=N`

    Retorna resultados normalizados a `ProductResult`.
    """

    endpoint = f"{base_origin.rstrip('/')}/api/catalog_system/pub/products/search/"

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json",
        "Accept-Language": "es-PE,es;q=0.9",
    }

    safe_limit = max(1, min(int(limit), 50))
    params = {
        "ft": query,
        "_from": 0,
        "_to": safe_limit - 1,
    }

    try:
        resp = requests.get(endpoint, params=params, headers=headers, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error al conectar con {store_name}: {e}")
        return []

    if not isinstance(data, list):
        return []

    query_tokens = [t for t in normalize_text(query).split() if t]

    results: List[ProductResult] = []

    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue

        name = item.get("productName")
        if not name:
            continue
        name_str = str(name).strip()

        brand = item.get("brand")
        brand_str = str(brand).strip() if brand else None

        full_name = f"{name_str} {brand_str or ''}".strip()
        norm_full = normalize_text(full_name)
        full_words = norm_full.split()
        if query_tokens and not all(tok in full_words for tok in query_tokens):
            continue

        product_id_raw = item.get("productId")
        try:
            product_id = int(product_id_raw)
        except Exception:
            product_id = idx

        price = _safe_get(item, ["items", 0, "sellers", 0, "commertialOffer", "Price"])
        try:
            price_f = float(price)
        except Exception:
            continue
        if price_f <= 0:
            continue

        if filters:
            if filters.max_price is not None and price_f > filters.max_price:
                continue
            if filters.brand:
                if not brand_str or filters.brand.lower() not in brand_str.lower():
                    continue

        image_url = _safe_get(item, ["items", 0, "images", 0, "imageUrl"])
        image_url_str = str(image_url).strip() if image_url else None

        link = item.get("link")
        link_text = item.get("linkText")
        product_url = None
        if isinstance(link, str) and link.strip():
            product_url = urljoin(base_origin.rstrip("/") + "/", link.strip())
        elif isinstance(link_text, str) and link_text.strip():
            product_url = f"{base_origin.rstrip('/')}/{link_text.strip()}/p"

        if user_location:
            distance = haversine_km(
                user_location.lat,
                user_location.lon,
                store_lat,
                store_lon,
            )
            distance_km = round(distance, 3)
        else:
            distance_km = None

        results.append(
            ProductResult(
                product_id=product_id,
                name=name_str,
                brand=brand_str,
                category=None,
                image_url=image_url_str,
                product_url=product_url,
                price=price_f,
                currency="PEN",
                store_id=store_id,
                store_name=store_name,
                store_location=Location(lat=store_lat, lon=store_lon),
                distance_km=distance_km,
                payment_methods=payment_methods or ["tarjeta", "efectivo"],
            )
        )

        time.sleep(0.03)

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
