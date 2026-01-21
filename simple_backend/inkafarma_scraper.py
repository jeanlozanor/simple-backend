import json
from decimal import Decimal
from typing import List, Optional

import requests

from main import normalize_text, haversine_km, Location, ProductResult, SearchFilters

# API de Algolia para Inkafarma
ALGOLIA_APP_ID = "15W622LAQ4"
ALGOLIA_API_KEY = "eb3261874e9b933efab019b04acff834"
ALGOLIA_INDEX = "products"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"

INKAFARMA_LAT = -12.06
INKAFARMA_LON = -77.04
IMAGE_BASE_URL = "https://dcuk1cxrnzjkh.cloudfront.net/imagesproducto/"


def scrape_inkafarma_live(
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
) -> List[ProductResult]:
    """
    Scraper en vivo para Inkafarma (Perú) usando API de Algolia.
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
        print(f"Error al conectar con Inkafarma (Algolia): {e}")
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

            # ========= FILTRO ESTRICTO POR PALABRAS =====
            full_name = f"{name} {brand or ''}"
            norm_full_name = normalize_text(full_name)

            query_tokens = [t for t in normalize_text(query).split()]
            full_name_words = norm_full_name.split()

            if query_tokens and not all(tok in full_name_words for tok in query_tokens):
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
            product_url = f"https://inkafarma.pe/producto/{uri}" if uri else None

            # ========= FILTROS SIMPLES =========
            if filters:
                if filters.max_price is not None and price > filters.max_price:
                    continue
                if filters.brand:
                    if not brand or filters.brand.lower() not in brand.lower():
                        continue

            # ========= DISTANCIA =========
            if user_location:
                distance = haversine_km(
                    user_location.lat,
                    user_location.lon,
                    INKAFARMA_LAT,
                    INKAFARMA_LON,
                )
                distance_km = round(distance, 3)
            else:
                distance_km = None

            payment_methods = ["tarjeta", "efectivo", "online"]

            results.append(
                ProductResult(
                    product_id=idx,
                    name=name,
                    brand=brand,
                    category=hit.get("category", [None])[0] if hit.get("category") else None,
                    image_url=image_url,
                    product_url=product_url,
                    price=price,
                    currency="PEN",
                    store_id=10,
                    store_name="Inkafarma Online",
                    store_location=Location(lat=INKAFARMA_LAT, lon=INKAFARMA_LON),
                    distance_km=distance_km,
                    payment_methods=payment_methods,
                )
            )

        except Exception as e:
            print(f"Error procesando producto de Inkafarma: {e}")
            continue

    # Ordenar resultados
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
