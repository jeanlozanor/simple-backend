"""
Scraper para Mifarma (Perú) usando API de Algolia.
Mifarma es parte del grupo Intercorp (mismo grupo que Inkafarma).
"""
import json
from decimal import Decimal
from typing import List, Optional

import requests

from main import normalize_text, haversine_km, Location, ProductResult, SearchFilters

# API de Algolia para Mifarma
ALGOLIA_APP_ID = "O74E6QKJ1F"
ALGOLIA_API_KEY = "b65e33077a0664869c7f2544d5f1e332"
ALGOLIA_INDEX = "products"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"

MIFARMA_LAT = -12.06
MIFARMA_LON = -77.04
IMAGE_BASE_URL = "https://dcuk1cxrnzjkh.cloudfront.net/imagesproducto/"


def scrape_mifarma_live(
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
) -> List[ProductResult]:
    """
    Scraper en vivo para Mifarma (Perú) usando API de Algolia.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": ALGOLIA_API_KEY,
    }

    body = {
        "query": query,
        "hitsPerPage": 50,
    }

    try:
        resp = requests.post(ALGOLIA_URL, json=body, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error al conectar con Mifarma (Algolia): {e}")
        return []

    hits = data.get("hits", [])

    results: List[ProductResult] = []

    for idx, hit in enumerate(hits, start=1):
        try:
            # ========= NOMBRE =========
            name = hit.get("name", "")
            if not name or len(name) < 3:
                continue

            # ========= PRESENTACIÓN (agregar al nombre) =========
            presentation = hit.get("presentation", "")
            if presentation:
                name = f"{name} - {presentation}"

            # ========= MARCA =========
            brand = hit.get("brand", None)

            # ========= FILTRO POR PALABRAS (menos estricto, Algolia ya filtra bien) =====
            full_name = f"{name} {brand or ''}"
            norm_full_name = normalize_text(full_name)

            query_tokens = [t for t in normalize_text(query).split() if len(t) > 2]

            # Verificar que cada token esté contenido en el nombre (no como palabra exacta)
            if query_tokens and not all(tok in norm_full_name for tok in query_tokens):
                continue

            # ========= PRECIO =========
            # Usar precio con promoción si existe, sino precio normal
            price_promo = hit.get("pricePromo", 0)
            price_list = hit.get("priceList", 0)
            price = price_promo if price_promo and price_promo > 0 else price_list

            if not price or price <= 0:
                continue

            price = float(price)

            # ========= IMAGEN =========
            image_url = hit.get("image", None)
            if not image_url:
                object_id = hit.get("objectID", "")
                if object_id:
                    image_url = f"{IMAGE_BASE_URL}{object_id}X.jpg"

            # ========= URL DEL PRODUCTO =========
            uri = hit.get("uri", "")
            product_url = f"https://www.mifarma.com.pe/producto/{uri}" if uri else None

            # ========= FILTROS SIMPLES =========
            if filters:
                if filters.max_price is not None and price > filters.max_price:
                    continue
                if filters.min_price is not None and price < filters.min_price:
                    continue

            # ========= DISTANCIA =========
            distance_km = None
            if user_location and user_location.lat and user_location.lon:
                distance_km = haversine_km(
                    user_location.lat, user_location.lon,
                    MIFARMA_LAT, MIFARMA_LON
                )

            # ========= INFORMACIÓN ADICIONAL =========
            category = hit.get("category", [])
            category_str = category[0] if category else None
            
            sub_category = hit.get("subCategory", [])
            sub_category_str = sub_category[0] if sub_category else None

            # ========= CREAR RESULTADO =========
            results.append(ProductResult(
                product_id=str(hit.get("objectID", f"mifarma_{idx}")),
                name=name.strip(),
                brand=brand,
                price=price,
                currency="PEN",
                image_url=image_url,
                product_url=product_url,
                store_name="Mifarma",
                store_code="mifarma",
                store_address="Lima, Perú",
                store_lat=MIFARMA_LAT,
                store_lon=MIFARMA_LON,
                distance_km=distance_km,
                category=category_str,
                subcategory=sub_category_str,
                availability="in_stock" if hit.get("validPrice", True) else "unknown",
                rating=None,
                reviews_count=None,
                discount_percent=hit.get("discountRate", None),
                original_price=price_list if price_promo and price_promo > 0 else None,
            ))

        except Exception as e:
            print(f"Error procesando producto Mifarma: {e}")
            continue

    return results


if __name__ == "__main__":
    # Prueba rápida
    results = scrape_mifarma_live("paracetamol")
    print(f"Total resultados: {len(results)}")
    for r in results[:5]:
        print(f"  - {r.name}: S/ {r.price}")
