import time
from decimal import Decimal
from typing import List, Optional

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from db import SessionLocal
from main import normalize_text, haversine_km, Location, ProductResult, SearchFilters

# Endpoint de búsqueda de Alkosto
BASE_SEARCH_URL = "https://www.alkosto.com/search"
BASE_ORIGIN = "https://www.alkosto.com"

ALKOSTO_LAT = -12.06
ALKOSTO_LON = -77.04

def scrape_alkosto_live(
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
) -> List[ProductResult]:
    """
    Scraper en vivo para Alkosto (Perú).
    Alkosto usa estructura con contenedores de producto.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    params = {"query": query}

    try:
        resp = requests.get(BASE_SEARCH_URL, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error al conectar con Alkosto: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Alkosto usa estructura: div con clase "producto"
    product_cards = soup.select("div[class*='producto'], article[class*='producto']")

    results: List[ProductResult] = []

    for idx, card in enumerate(product_cards, start=1):
        try:
            # ========= MARCA =========
            brand_el = card.select_one("[class*='brand'], [class*='marca'], .brand")
            brand = brand_el.get_text(strip=True) if brand_el else None

            # ========= NOMBRE =========
            name_el = card.select_one("[class*='product-name'], [class*='titulo'], .product-name, h2, h3")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)

            # ========= FILTRO ESTRICTO POR PALABRAS =====
            full_name = f"{name} {brand or ''}"
            norm_full_name = normalize_text(full_name)

            query_tokens = [t for t in normalize_text(query).split()]
            full_name_words = norm_full_name.split()
            
            if query_tokens and not all(tok in full_name_words for tok in query_tokens):
                continue

            # ========= PRECIO =========
            price_el = card.select_one("[class*='price'], [class*='precio'], .price, .precio")
            if not price_el:
                continue

            price_text = price_el.get_text(strip=True)
            digits = (
                price_text.replace("S/", "")
                .replace("S/.", "")
                .replace("s/", "")
                .replace("\xa0", " ")
                .replace(" ", "")
                .replace(",", "")
            )

            try:
                price = float(Decimal(digits))
            except Exception:
                continue

            # ========= IMAGEN =========
            img_el = card.select_one("img")
            image_url = img_el["src"] if img_el and img_el.get("src") else None

            # ========= URL DEL PRODUCTO =========
            link_el = card.select_one("a[href]")
            href = link_el.get("href") if link_el else None
            product_url = urljoin(BASE_ORIGIN, href) if href else None

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
                    ALKOSTO_LAT,
                    ALKOSTO_LON,
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
                    store_id=4,
                    store_name="Alkosto Online",
                    store_location=Location(lat=ALKOSTO_LAT, lon=ALKOSTO_LON),
                    distance_km=distance_km,
                    payment_methods=payment_methods,
                )
            )

        except Exception as e:
            print(f"Error procesando producto de Alkosto: {e}")
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
