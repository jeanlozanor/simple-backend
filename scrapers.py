import os
import re
import json
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

# Activar Playwright solo si está disponible y si la variable lo permite (para Render evitamos fallos)
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "true").lower() == "true"


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
    if any(w in ln for w in accessories_words):
        return False

    # Palabras que claramente son de celular
    core_words = ["celular", "smartphone", "phone"]
    if any(w in ln for w in core_words):
        return True


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

    # Palabras típicas de modelos de celular
    phone_markers = [
        "redmi",
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
        return True

    # Si en la query pusiste "celular" y el producto no parece accesorio
    if "celular" in original_query.lower():
        return True

    return False



def _clean_url(url: str) -> str:
    """
    Elimina parámetros de tracking (?foo=...) para usar la URL limpia
    como identificador de producto (y también mostrarla más bonita).
    """
    return url.split("?", 1)[0]


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
    base_url = "https://www.oechsle.pe/catalogsearch/result/"
    params = {"q": query}

    try:
        resp = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error cargando Oechsle: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    products: List[Product] = []
    seen_urls: set[str] = set()

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

        name = alt_text if alt_text and len(alt_text) > len(raw_name) else raw_name

        if not _passes_category(name, category, query):
            continue

        price_text = price_tag.get_text(strip=True)
        price = _parse_price(price_text)
        if price <= 0:
            continue

        href = link_tag.get("href") or ""
        if href and href.startswith("/"):
            href = "https://www.oechsle.pe" + href
        href_clean = _clean_url(href)
        if not href_clean or href_clean in seen_urls:
            continue
        seen_urls.add(href_clean)

        img_url = img_tag.get("src") if img_tag and img_tag.get("src") else None

        brand = _infer_brand(name, brand_filter)
        if brand_filter:
            if brand is None:
                continue
            if brand.strip().lower() != brand_filter.strip().lower():
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
    search_url = f"https://www.plazavea.com.pe/search?q={query}"

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error cargando PlazaVea: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Intentar parsear ld+json con ItemList
    products: List[Product] = []
    seen_urls: set[str] = set()

    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    items = []
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
        # fallback básico: tarjetas en HTML
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
        brand = _infer_brand(name, brand_filter)
        if brand_filter:
            if brand is None:
                continue
            if brand.strip().lower() != brand_filter.strip().lower():
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

    # Falabella (Playwright opcional)
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
