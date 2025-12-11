import re
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
        "cable",
        "funda",
        "case",
        "protector",
        "mica",
        "cover",
        "soporte",
        "auricular",
        "audifono",
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

def search_hiraoka(query: str, brand_filter: Optional[str] = None) -> List[Product]:
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

        # Sólo nos quedamos con cosas tipo CELULAR / SMARTPHONE
        if not _is_probably_phone(name, query):
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

from playwright.sync_api import sync_playwright

def _fetch_falabella_html(query: str) -> str:
    """
    Usa un navegador Chromium headless (Playwright) para cargar
    la página de búsqueda de Falabella y devolver el HTML renderizado.

    Se hace robusto frente a timeouts: si el goto demora mucho, igual
    devolvemos el HTML que se tenga hasta ese momento.
    """
    search_url = f"https://www.falabella.com.pe/falabella-pe/search?Ntt={query}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])

        try:
            # Mucho más seguro que "networkidle"
            page.goto(
                search_url,
                wait_until="domcontentloaded",  # o "load"
                timeout=60000  # 60s
            )
        except Exception as e:
            # No rompemos el scraping por timeout, solo lo registramos
            print(f"Advertencia: timeout o error en Falabella.goto: {e}")

        # Damos un pequeño margen para que terminen de pintar los pods
        page.wait_for_timeout(3000)  # 3 segundos

        html = page.content()
        browser.close()

    return html



def search_falabella(query: str, brand_filter: Optional[str] = None) -> List[Product]:
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

        # Sólo celulares / smartphones (no fundas, parlantes, etc.)
        if not _is_probably_phone(name, query):
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
        results.extend(search_hiraoka(query, brand_filter))
    except Exception as e:
        print(f"Error buscando en Hiraoka: {e}")

    # Falabella
    try:
        results.extend(search_falabella(query, brand_filter))
    except Exception as e:
        print(f"Error buscando en Falabella: {e}")

    # Filtrado por precio si aplica
    if filters.min_price is not None:
        results = [p for p in results if p.price >= filters.min_price]
    if filters.max_price is not None:
        results = [p for p in results if p.price <= filters.max_price]

    return results
