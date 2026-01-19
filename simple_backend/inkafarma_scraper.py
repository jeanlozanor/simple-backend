import time
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from main import normalize_text, haversine_km, Location, ProductResult, SearchFilters

# Endpoint de búsqueda de Inkafarma
BASE_SEARCH_URL = "https://www.inkafarma.com.pe/buscar"

INKAFARMA_LAT = -12.06
INKAFARMA_LON = -77.04


def scrape_inkafarma_live(
    query: str,
    user_location: Optional[Location] = None,
    filters: Optional[SearchFilters] = None,
) -> List[ProductResult]:
    """
    Scraper en vivo para Inkafarma (Perú).
    Inkafarma es un sitio de farmacias con búsqueda de productos.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    params = {"q": query}

    try:
        resp = requests.get(BASE_SEARCH_URL, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error al conectar con Inkafarma: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Inkafarma típicamente usa divs de productos con clases como "product", "item", "producto"
    # Intentamos varios selectores comunes
    product_cards = soup.select(
        "div[class*='product'], article[class*='product'], "
        "div[class*='item'], li[class*='product'], "
        "div.producto, div.item-producto"
    )

    results: List[ProductResult] = []

    for idx, card in enumerate(product_cards, start=1):
        try:
            # ========= NOMBRE =========
            name_el = card.select_one(
                "[class*='product-name'], [class*='titulo'], "
                ".product-name, h2, h3, .name, .titulo"
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            # ========= MARCA (opcional) =========
            brand_el = card.select_one("[class*='brand'], [class*='marca'], .brand, .marca")
            brand = brand_el.get_text(strip=True) if brand_el else None

            # ========= FILTRO ESTRICTO POR PALABRAS =====
            full_name = f"{name} {brand or ''}"
            norm_full_name = normalize_text(full_name)

            query_tokens = [t for t in normalize_text(query).split()]
            full_name_words = norm_full_name.split()

            if query_tokens and not all(tok in full_name_words for tok in query_tokens):
                continue

            # ========= PRECIO =========
            price_el = card.select_one(
                "[class*='price'], [class*='precio'], .price, .precio, "
                "[data-price], .product-price"
            )
            if not price_el:
                continue

            price_text = price_el.get_text(strip=True)
            # Limpiar: "S/ 123.45" -> "123.45"
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

            if price <= 0:
                continue

            # ========= IMAGEN =========
            img_el = card.select_one("img")
            image_url = None
            if img_el:
                src = img_el.get("src") or img_el.get("data-src")
                if src:
                    image_url = src.strip()

            # ========= URL DEL PRODUCTO =========
            link_el = card.select_one("a[href]")
            href = link_el.get("href") if link_el else None
            product_url = urljoin(BASE_SEARCH_URL.rsplit("/", 1)[0], href) if href else None

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
                    category=None,
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

        time.sleep(0.03)

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
