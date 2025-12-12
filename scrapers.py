import os
import re
import json
from urllib.parse import quote_plus
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from models import Product, SearchFilters

# =====================================================================
# CONFIGURACIÓN GENERAL
# =====================================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _vtex_headers(origin: str, referer: str) -> dict:
    """Headers extra para endpoints VTEX que suelen bloquear bots."""
    return {
        **HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        "Origin": origin,
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    }

# Activar Playwright solo si está disponible y si la variable lo permite (para Render evitamos fallos)
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "true").lower() == "true"

# Incluir Falabella en el agregado (por defecto OFF para evitar JS/Playwright en entornos locales)
INCLUDE_FALABELLA = os.getenv("INCLUDE_FALABELLA", "false").lower() == "true"


# =====================================================================
# UTILIDADES COMUNES
# =====================================================================

def _parse_price(text: str) -> float:
    """
    Extrae un número decimal de un texto de precio.

    Ejemplos:
    - 'S/ 1,299.00' -> 1299.0
    - 'S/ 449'      -> 449.0
    - '1,199'       -> 1199.0
    """
    if not text:
        return 0.0

    tmp = re.sub(r"[^\d,\.]", "", text)
    if not tmp:
        return 0.0

    if "," in tmp and "." in tmp:
        tmp = tmp.replace(",", "")
    elif "," in tmp and "." not in tmp:
        tmp = tmp.replace(",", "")

    try:
        return float(tmp)
    except ValueError:
        return 0.0


def _infer_brand(name: str, brand_filter: Optional[str] = None) -> Optional[str]:
    """
    Detecta la marca a partir del texto del producto.
    Sólo usa brand_filter como respaldo si también aparece en el nombre.
    """
    upper = name.upper()

    if "REDMI" in upper:
        return "Redmi"
    if "XIAOMI" in upper:
        return "Xiaomi"
    if "SAMSUNG" in upper:
        return "Samsung"
    if "HUAWEI" in upper:
        return "Huawei"
    if "MOTOROLA" in upper:
        return "Motorola"
    if "HONOR" in upper:
        return "Honor"
    if "OPPO" in upper:
        return "Oppo"
    if "ZTE" in upper:
        return "ZTE"
    if "TCL" in upper:
        return "TCL"
    if "DJI" in upper:
        return "DJI"
    if "MIRAY" in upper:
        return "Miray"

    # Solo usamos brand_filter si realmente aparece en el texto
    if brand_filter and brand_filter.upper() in upper:
        return brand_filter.strip().title()

    return None


def _is_probably_phone(name: str, original_query: str) -> bool:
    """
    Heurística para decidir si un producto es un CELULAR / SMARTPHONE
    y no un accesorio (parlante, estabilizador, tablet, power bank, batería, etc.).
    """
    ln = name.lower()

    # Señales fuertes de que SÍ es un celular
    is_phone_signal = False

    core_words = ["celular", "smartphone", "phone"]
    if any(w in ln for w in core_words):
        is_phone_signal = True

    phone_markers = [
        "redmi",
        "poco",
        "galaxy",
        "iphone",
        "moto ",
        "moto g",
        "note 11",
        "note 12",
        "note 13",
        "note 14",
        "note 15",
        "a05",
        "a07",
        "a15",
        "a16",
        "a26",
        "a34",
        "a35",
    ]
    if any(w in ln for w in phone_markers):
        is_phone_signal = True

    # Specs típicos de ficha de celular
    if re.search(r"\b\d+\s*gb\b", ln) and ("ram" in ln or "almacen" in ln or "almacenamiento" in ln):
        is_phone_signal = True
    # Tamaño en pulgadas: teléfonos suelen estar ~4" a ~8"; TVs son > 20".
    m_inches = re.search(r"\b(\d+(?:\.\d+)?)\s*\"", ln)
    if m_inches:
        try:
            inches = float(m_inches.group(1))
            if 3.5 <= inches <= 8.2:
                is_phone_signal = True
        except Exception:
            pass

    if "celular" in (original_query or "").lower():
        is_phone_signal = True

    # Palabras que indican que NO es un celular (accesorios, baterías, etc.)
    accessories_words = [
        "parlante",
        "parlantes",
        "amplificador",
        "estabilizador",
        "gimbal",
        "tablet",
        "ipad",
        "pad ",
        "smartwatch",
        "reloj",
        "cargador",
        "funda",
        "case",
        "protector",
        "mica",
        "cover",
        "soporte",
        "audífono",
        "audifonos",
        "audífonos",
        "altavoz",
        # 🔋 cosas de batería / powerbank
        "power bank",
        "powerbank",
        "power-bank",
        "bateria",
        "batería",
        "battery",
        "baterias",
        "baterías",
        "bank 20000",
        "bank 10000",
    ]
    if any(w in ln for w in accessories_words) and not is_phone_signal:
        return False

    return is_phone_signal


def _passes_category(name: str, category: Optional[str], original_query: str) -> bool:
    """
    Filtro por categoría para no mezclar celulares con TV u otros.
    - Si category es None: aceptar todo.
    - "celular": aplicar heurística de celular.
    - "televisor": debe contener tv/televisor/4k/fhd/uhd y no parecer celular.
    - Para otras categorías simples, solo validar que el texto contenga la palabra.
    """
    if category is None:
        return True

    cat = category.lower()
    ln = name.lower()

    if cat == "celular":
        return _is_probably_phone(name, original_query)

    if cat == "televisor":
        if any(word in ln for word in ["televisor", "smart tv", "tv", "uhd", "oled", "qled", "4k", "8k"]):
            # descartar si parece celular
            return not _is_probably_phone(name, original_query)
        return False

    if cat == "laptop":
        return any(w in ln for w in ["laptop", "notebook", "thinkpad", "ideapad", "macbook", "vivobook", "inspiron", "pavilion"])

    if cat == "tablet":
        return any(w in ln for w in ["tablet", "ipad", "galaxy tab", "tab "])

    if cat == "audifonos":
        return any(w in ln for w in ["audifono", "audífono", "audifonos", "audífonos", "earbud", "earbuds", "headset", "headphone", "diadema"])

    if cat == "monitor":
        return any(w in ln for w in ["monitor", "gaming monitor", "ips", "va", "hz", "curvo", "curved"])

    if cat == "reloj":
        return any(w in ln for w in ["reloj", "smartwatch", "watch"])

    if cat == "accesorio":
        # accesorios genéricos
        return any(w in ln for w in ["cargador", "cable", "case", "funda", "protector", "power bank", "bateria", "batería"])

    return True



def _clean_url(url: str) -> str:
    """
    Elimina parámetros de tracking (?foo=...) para usar la URL limpia
    como identificador de producto (y también mostrarla más bonita).
    """
    return url.split("?", 1)[0]


def _vtex_query_candidates(query: str, brand_filter: Optional[str] = None) -> List[str]:
    """VTEX en algunos sitios bloquea búsquedas con espacios; probamos tokens individuales."""
    candidates: List[str] = []

    if brand_filter:
        bf = brand_filter.strip()
        if bf:
            candidates.append(bf)

    q = (query or "").strip()
    if not q:
        return candidates

    # Si no hay espacios, úsalo tal cual
    if " " not in q:
        candidates.append(q)
        return list(dict.fromkeys(candidates))

    stop = {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "para",
        "con",
        "y",
        "en",
        "un",
        "una",
        "por",
        "smart",
        "tv",
        "televisor",
        "celular",
        "laptop",
        "notebook",
    }
    tokens = re.findall(r"[a-zA-Z0-9]+", q.lower())
    tokens = [t for t in tokens if len(t) >= 3 and t not in stop]

    # Preferir tokens largos/modelos (ej: 65v6c, redmi13, etc.)
    tokens = sorted(dict.fromkeys(tokens), key=len, reverse=True)
    candidates.extend(tokens[:4])

    return list(dict.fromkeys(candidates))


# =====================================================================
# HIRAOKA
# =====================================================================

def search_hiraoka(query: str, brand_filter: Optional[str] = None, category: Optional[str] = None) -> List[Product]:
    """
    Busca productos en Hiraoka usando la página pública de búsqueda.
    """
    base_url = "https://hiraoka.com.pe/catalogsearch/result/"
    params = {"q": query}

    resp = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    products: List[Product] = []
    seen_urls: set[str] = set()  # para eliminar duplicados

    for card in soup.select(".product-item-info, .product-item"):
        name_tag = card.select_one(".product-item-link")
        price_tag = card.select_one(".price")
        img_tag = card.select_one("img")
        link_tag = card.select_one("a.product-item-link")

        if not (name_tag and price_tag and link_tag):
            continue

        raw_name = name_tag.get_text(strip=True)

        alt_text = ""
        if img_tag and img_tag.get("alt"):
            alt_text = img_tag["alt"].strip()

        if alt_text and len(alt_text) > len(raw_name):
            name = alt_text
        else:
            name = raw_name

        # Filtrar por categoría si aplica
        if not _passes_category(name, category, query):
            continue

        price_text = price_tag.get_text(strip=True)
        price = _parse_price(price_text)

        href = link_tag.get("href")
        if href and href.startswith("/"):
            href = "https://hiraoka.com.pe" + href
        if not href:
            continue

        href_clean = _clean_url(href)
        if href_clean in seen_urls:
            continue
        seen_urls.add(href_clean)

        img_url = None
        if img_tag and img_tag.get("src"):
            img_url = img_tag["src"]

        brand = _infer_brand(name, brand_filter)

        # Si hay filtro de marca (ej. "Redmi"), filtramos
        if brand_filter:
            if brand is None:
                continue
            if brand.strip().lower() != brand_filter.strip().lower():
                continue

        if price <= 0:
            continue

        products.append(
            Product(
                name=name,
                brand=brand,
                price=price,
                currency="PEN",
                store_name="Hiraoka Online",
                product_url=href_clean,
                image_url=img_url,
            )
        )

    return products


# =====================================================================
# FALABELLA (Playwright)
# =====================================================================

def _fetch_falabella_html(query: str) -> str:
    """
    Si USE_PLAYWRIGHT=true: usar Playwright siempre (necesario porque Falabella carga vía JS).
    Si USE_PLAYWRIGHT=false: intentar requests (sin garantías).
    """
    search_url = f"https://www.falabella.com.pe/falabella-pe/search?Ntt={query}"

    if not USE_PLAYWRIGHT:
        try:
            resp = requests.get(search_url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"Falabella sin Playwright error: {e}")
            return ""

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"No se pudo importar Playwright: {e}")
        return ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(3500)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"Error usando Playwright en Falabella: {e}")
        return ""



def search_falabella(query: str, brand_filter: Optional[str] = None, category: Optional[str] = None) -> List[Product]:
    """
    Busca productos en Falabella Perú usando el HTML renderizado
    por Playwright. Estructura típica:

    <div data-testid="ssr-pod" ...>
      <a ... class="pod pod-4_GRID pod-link" href=".../product/...">
        <b class="pod-title">XIAOMI</b>
        <b class="pod-subTitle">Redmi13blue8gb256gb</b>
        <div id="testId-pod-prices-...">
          <span> S/  449 </span>
        </div>
      </a>
    </div>
    """
    try:
        html = _fetch_falabella_html(query)
    except Exception as e:
        print(f"Error cargando Falabella con Playwright: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")

    products: List[Product] = []
    seen_urls: set[str] = set()

    containers = soup.select("div[data-testid='ssr-pod']")
    cards = []
    for cont in containers:
        cards.extend(cont.select("a.pod-link[href*='/product/']"))

    # Fallback: por si cambia la clase
    if not cards:
        cards = soup.select("a[href*='/falabella-pe/product/']")

    for card in cards:
        # Marca y modelo
        brand_tag = card.select_one(".pod-title")
        subtitle_tag = card.select_one(".pod-subTitle")

        brand_text = brand_tag.get_text(strip=True) if brand_tag else ""
        subtitle_text = subtitle_tag.get_text(strip=True) if subtitle_tag else ""

        if brand_text and subtitle_text:
            name = f"{brand_text} {subtitle_text}"
        else:
            name = (subtitle_text or brand_text).strip()

        # Filtrar por categoría si aplica
        if not _passes_category(name, category, query):
            continue

        # Precio: primer span dentro del contenedor de precios
        price_container = card.select_one("div[id^='testId-pod-prices']")
        price_span = price_container.select_one("span") if price_container else None
        price_text = price_span.get_text(strip=True) if price_span else ""
        price = _parse_price(price_text)

        href = card.get("href")
        if href and href.startswith("/"):
            href = "https://www.falabella.com.pe" + href
        if not href:
            continue

        href_clean = _clean_url(href)
        if href_clean in seen_urls:
            continue
        seen_urls.add(href_clean)

        img_tag = card.select_one("img")
        img_url = img_tag.get("src") if img_tag and img_tag.get("src") else None

        brand = _infer_brand(name, brand_filter)

        if brand_filter:
            if brand is None:
                continue
            if brand.strip().lower() != brand_filter.strip().lower():
                continue

        if price <= 0:
            continue

        products.append(
            Product(
                name=name,
                brand=brand,
                price=price,
                currency="PEN",
                store_name="Falabella",
                product_url=href_clean,
                image_url=img_url,
            )
        )

    return products


# =====================================================================
# OECHSLE (HTML)
# =====================================================================

def search_oechsle(query: str, brand_filter: Optional[str] = None, category: Optional[str] = None) -> List[Product]:
    """Busca en Oechsle. Primero intenta el API VTEX; si falla, cae a HTML."""

    products: List[Product] = []
    seen_urls: set[str] = set()

    # 1) API VTEX (más estable que el HTML)
    api_url = "https://www.oechsle.pe/api/catalog_system/pub/products/search/"
    try:
        for ft in _vtex_query_candidates(query, brand_filter):
            qref = quote_plus(ft)
            api_resp = requests.get(
                api_url,
                params={"ft": ft, "sc": 1},
                headers=_vtex_headers(
                    origin="https://www.oechsle.pe",
                    referer=f"https://www.oechsle.pe/busca/?ft={qref}",
                ),
                timeout=15,
            )
            if not api_resp.ok:
                continue

            data = api_resp.json()
            for item in data:
                name = (item.get("productName") or "").strip()
                if not name:
                    continue
                if not _passes_category(name, category, query):
                    continue

                sellers = item.get("items", [{}])[0].get("sellers", []) if item.get("items") else []
                price = 0.0
                if sellers:
                    offer = sellers[0].get("commertialOffer", {})
                    price = float(offer.get("Price") or 0)

                if price <= 0:
                    continue

                link = (item.get("link") or "").strip()
                if not link:
                    link_text = (item.get("linkText") or "").strip()
                    if link_text:
                        link = f"https://www.oechsle.pe/{link_text}/p"
                if link and link.startswith("/"):
                    link = "https://www.oechsle.pe" + link
                href_clean = _clean_url(link)
                if not href_clean or href_clean in seen_urls:
                    continue
                seen_urls.add(href_clean)

                images = item.get("items", [{}])[0].get("images", []) if item.get("items") else []
                img_url = images[0].get("imageUrl") if images else None

                brand = _infer_brand(name, brand_filter)
                if brand_filter:
                    if brand is None or brand.strip().lower() != brand_filter.strip().lower():
                        continue

                products.append(
                    Product(
                        name=name,
                        brand=brand,
                        price=price,
                        currency="PEN",
                        store_name="Oechsle",
                        product_url=href_clean,
                        image_url=img_url,
                    )
                )

            if products:
                break
    except Exception as e:
        print(f"Oechsle API fallback a HTML por error: {e}")

    if products:
        return products

    # 2) Fallback HTML (VTEX). Oechsle suele renderizar resultados como div.resultItem
    search_urls = [
        "https://www.oechsle.pe/busca/",
        "https://www.oechsle.pe/catalogsearch/result/",
    ]

    html = ""
    for url in search_urls:
        try:
            if url.endswith("/busca/"):
                resp = requests.get(url, params={"ft": query}, headers=HEADERS, timeout=15)
            else:
                resp = requests.get(url, params={"q": query}, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text
            if html:
                break
        except Exception as e:
            print(f"Error cargando Oechsle HTML ({url}): {e}")

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    for card in soup.select("div.resultItem"):
        name = (card.get("data-product-name") or "").strip()
        if not name:
            name_tag = card.select_one(".resultItem__detail--name")
            name = name_tag.get_text(strip=True) if name_tag else ""
        if not name:
            continue

        if not _passes_category(name, category, query):
            continue

        price_text = (card.get("data-product-price") or "").strip()
        if not price_text:
            price_tag = card.select_one(".resultItem__detail--price .price .value")
            price_text = price_tag.get_text(strip=True) if price_tag else ""
        price = _parse_price(price_text)
        if price <= 0:
            continue

        a = card.select_one("a.resultItem__link[href]")
        href = a.get("href") if a else ""
        if href and href.startswith("/"):
            href = "https://www.oechsle.pe" + href
        href_clean = _clean_url(href)
        if not href_clean or href_clean in seen_urls:
            continue
        seen_urls.add(href_clean)

        img = card.select_one("img.resultItem__image")
        img_url = img.get("src") if img and img.get("src") else None

        brand_hint = (card.get("data-product-brand") or "").strip()
        brand = _infer_brand(name, brand_filter) or (brand_hint.title() if brand_hint else None)
        if brand_filter:
            if brand is None or brand.strip().lower() != brand_filter.strip().lower():
                continue

        products.append(
            Product(
                name=name,
                brand=brand,
                price=price,
                currency="PEN",
                store_name="Oechsle",
                product_url=href_clean,
                image_url=img_url,
            )
        )

    return products


# =====================================================================
# PLAZAVEA (HTML / ld+json)
# =====================================================================

def search_plazavea(query: str, brand_filter: Optional[str] = None, category: Optional[str] = None) -> List[Product]:
    """Busca en PlazaVea. Usa API VTEX; si falla, cae a HTML/ld+json."""

    products: List[Product] = []
    seen_urls: set[str] = set()

    # 1) API VTEX (estable y con precios correctos)
    api_url = "https://www.plazavea.com.pe/api/catalog_system/pub/products/search/"
    try:
        for ft in _vtex_query_candidates(query, brand_filter):
            qref = quote_plus(ft)
            api_resp = requests.get(
                api_url,
                params={"ft": ft, "sc": 1},
                headers=_vtex_headers(
                    origin="https://www.plazavea.com.pe",
                    referer=f"https://www.plazavea.com.pe/search?q={qref}",
                ),
                timeout=15,
            )
            if not api_resp.ok:
                continue

            data = api_resp.json()
            for item in data:
                name = (item.get("productName") or "").strip()
                if not name:
                    continue
                if not _passes_category(name, category, query):
                    continue

                sellers = item.get("items", [{}])[0].get("sellers", []) if item.get("items") else []
                price = 0.0
                if sellers:
                    offer = sellers[0].get("commertialOffer", {})
                    price = float(offer.get("Price") or 0)

                if price <= 0:
                    continue

                link = (item.get("link") or "").strip()
                if not link:
                    link_text = (item.get("linkText") or "").strip()
                    if link_text:
                        link = f"https://www.plazavea.com.pe/{link_text}/p"
                if link and link.startswith("/"):
                    link = "https://www.plazavea.com.pe" + link
                href_clean = _clean_url(link)
                if not href_clean or href_clean in seen_urls:
                    continue
                seen_urls.add(href_clean)

                images = item.get("items", [{}])[0].get("images", []) if item.get("items") else []
                img_url = images[0].get("imageUrl") if images else None

                brand = _infer_brand(name, brand_filter)
                if brand_filter:
                    if brand is None or brand.strip().lower() != brand_filter.strip().lower():
                        continue

                products.append(
                    Product(
                        name=name,
                        brand=brand,
                        price=price,
                        currency="PEN",
                        store_name="PlazaVea",
                        product_url=href_clean,
                        image_url=img_url,
                    )
                )

            if products:
                break
    except Exception as e:
        print(f"PlazaVea API fallback a HTML por error: {e}")

    if products:
        return products

    # 2) Fallback HTML + ld+json (PlazaVea renderiza tarjetas Showcase)
    search_url = f"https://www.plazavea.com.pe/search?q={query}"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error cargando PlazaVea: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    items = []

    # 2.1) Tarjetas Showcase (rápido y estable)
    for card in soup.select("div.Showcase"):
        name = (card.get("data-ga-name") or "").strip()
        brand = (card.get("data-ga-brand") or "").strip()

        a = card.select_one("a.Showcase__link[href]")
        href = a.get("href") if a else ""

        img = card.select_one("img")
        img_url = img.get("src") if img and img.get("src") else None

        price_text = (card.get("data-ga-price") or "").strip()
        if not price_text:
            sale = card.select_one(".Showcase__salePrice")
            price_text = (sale.get("data-price") if sale else "") or ""

        if name and href:
            items.append(
                {
                    "name": name,
                    "brand": brand,
                    "url": href,
                    "image": img_url,
                    "price": price_text,
                    "currency": "PEN",
                }
            )

    # 2.2) ld+json (fallback)
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for sc in scripts:
        try:
            data = json.loads(sc.string or "")
        except Exception:
            continue

        if isinstance(data, dict) and data.get("@type") == "ItemList" and isinstance(data.get("itemListElement"), list):
            for el in data["itemListElement"]:
                item = el.get("item") if isinstance(el, dict) else None
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or ""
                url = item.get("url") or ""
                image = item.get("image") or None
                offers = item.get("offers") or {}
                price = offers.get("price") if isinstance(offers, dict) else None
                currency = offers.get("priceCurrency") if isinstance(offers, dict) else "PEN"
                items.append({"name": name, "url": url, "image": image, "price": price, "currency": currency})

    if not items:
        cards = soup.select("[data-pvsnid] a[href*='/p']")
        for a in cards:
            url = a.get("href") or ""
            name = a.get_text(strip=True)
            items.append({"name": name, "url": url, "image": None, "price": None, "currency": "PEN"})

    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            continue

        if not _passes_category(name, category, query):
            continue

        price = _parse_price(str(it.get("price") or ""))
        if price <= 0:
            continue

        href = it.get("url") or ""
        if href and href.startswith("/"):
            href = "https://www.plazavea.com.pe" + href
        href_clean = _clean_url(href)
        if not href_clean or href_clean in seen_urls:
            continue
        seen_urls.add(href_clean)

        img_url = it.get("image")

        brand_hint = (it.get("brand") or "").strip()
        brand = _infer_brand(name, brand_filter) or (brand_hint.title() if brand_hint else None)
        if brand_filter:
            if brand is None or brand.strip().lower() != brand_filter.strip().lower():
                continue

        products.append(
            Product(
                name=name,
                brand=brand,
                price=price,
                currency=it.get("currency") or "PEN",
                store_name="PlazaVea",
                product_url=href_clean,
                image_url=img_url,
            )
        )

    return products


# =====================================================================
# AGREGADOR MULTI-TIENDA
# =====================================================================

def search_all_stores(filters: SearchFilters) -> List[Product]:
    """
    Busca en todas las tiendas soportadas usando:
    - normalized_query
    - brand sugerida por la IA (si existe)
    - rango de precios (min_price, max_price)
    """
    query = filters.normalized_query
    brand_filter = filters.brand

    results: List[Product] = []

    # Hiraoka
    try:
        results.extend(search_hiraoka(query, brand_filter, filters.category))
    except Exception as e:
        print(f"Error buscando en Hiraoka: {e}")

    # Falabella (opt-in)
    if INCLUDE_FALABELLA:
        try:
            results.extend(search_falabella(query, brand_filter, filters.category))
        except Exception as e:
            print(f"Error buscando en Falabella: {e}")

    # Oechsle
    try:
        results.extend(search_oechsle(query, brand_filter, filters.category))
    except Exception as e:
        print(f"Error buscando en Oechsle: {e}")

    # PlazaVea
    try:
        results.extend(search_plazavea(query, brand_filter, filters.category))
    except Exception as e:
        print(f"Error buscando en PlazaVea: {e}")

    # Filtrado por precio si aplica
    if filters.min_price is not None:
        results = [p for p in results if p.price >= filters.min_price]
    if filters.max_price is not None:
        results = [p for p in results if p.price <= filters.max_price]

    return results
