import time
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from db import SessionLocal
from main import normalize_text
from models import Store, Product, InventoryItem

# Endpoint de búsqueda de Hiraoka
BASE_SEARCH_URL = "https://hiraoka.com.pe/gpsearch/"

def get_session() -> Session:
    return SessionLocal()

def get_or_create_hiraoka_store(db: Session) -> Store:
    store = db.query(Store).filter(Store.name == "Hiraoka Online").first()
    if store:
        return store

    store = Store(
        name="Hiraoka Online",
        address="Tienda online",
        district="Lima",
        city="Lima",
        latitude=-12.06,   # aproximado solo para pruebas
        longitude=-77.04,
        payment_methods="tarjeta,efectivo"
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store

def upsert_product_and_inventory(
    db: Session,
    store: Store,
    name: str,
    brand: str | None,
    category: str | None,
    price: Decimal,
    image_url: str | None,
):
    # 1. Buscar si ya existe el producto (nombre + marca)
    q = db.query(Product).filter(Product.name == name)
    if brand:
        q = q.filter(Product.brand == brand)
    product = q.first()

    if not product:
        product = Product(
            name=name,
            brand=brand,
            category=category,
            description=None,
            image_url=image_url,
        )
        db.add(product)
        db.commit()
        db.refresh(product)

    # 2. Buscar/crear inventario para esa tienda + producto
    inv = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.store_id == store.id,
            InventoryItem.product_id == product.id,
        )
        .first()
    )

    if not inv:
        inv = InventoryItem(
            store_id=store.id,
            product_id=product.id,
            price=price,
            currency="PEN",
            stock=None,
        )
        db.add(inv)
    else:
        # Actualizar precio si ya existe
        inv.price = price

    db.commit()

def scrape_hiraoka_search(db: Session, query: str, category: str | None = None):
    store = get_or_create_hiraoka_store(db)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    params = {"q": query}
    print(f"Buscando en Hiraoka: {BASE_SEARCH_URL} con q={query}")
    resp = requests.get(BASE_SEARCH_URL, params=params, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Cada producto está en un <div class="product-item-info" data-container="product-grid">
    product_cards = soup.select("div.product-item-info[data-container='product-grid']")
    print(f"Productos encontrados en HTML: {len(product_cards)}")

    for card in product_cards:
        # ===== NOMBRE =====
        # <strong class="product name product-item-name"> <a class="product-item-link">Nombre</a> ...
        name_el = card.select_one("strong.product.name.product-item-name a.product-item-link")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        # ===== MARCA =====
        # <strong class="product brand product-item-brand"> <a class="product-item-link">HUAWEI</a> ...
        brand_el = card.select_one("strong.product.brand.product-item-brand a.product-item-link")
        brand = brand_el.get_text(strip=True) if brand_el else None

                # ===== FILTRO ESTRICTO POR PALABRAS DE LA QUERY =====
        # Unimos nombre + marca y normalizamos (minúsculas, sin tildes)
        full_name = f"{name} {brand or ''}"
        norm_full_name = normalize_text(full_name)

        # Partimos la query en palabras
        query_tokens = [
            t for t in normalize_text(query).split()
        ]

        # Si quieres que TODAS las palabras de la query aparezcan como palabras EXACTAS en el nombre+marca:
        full_name_words = norm_full_name.split()
        print(f"DEBUG: query_tokens={query_tokens}, full_name_words={full_name_words}")
        if query_tokens and not all(tok in full_name_words for tok in query_tokens):
            # Este producto no cumple con la búsqueda estricta, lo saltamos
            print(f"FILTRADO: {name} {brand} - no contiene todas las palabras")
            continue


        # ===== PRECIO =====
        # Dentro de <div class="price-box ...">
        # Hay un <span id="product-price-85072" data-price-amount="3699" data-price-type="finalPrice" ...>
        price_wrapper = card.select_one("div.price-box [data-price-type='finalPrice']")
        if not price_wrapper:
            # fallback: buscar el texto de la clase .price
            price_text_el = card.select_one("div.price-box span.price")
            if not price_text_el:
                print(f"Sin precio para producto: {name}")
                continue
            price_text = price_text_el.get_text(strip=True)
            digits = (
                price_text.replace("S/", "")
                .replace("S/.", "")
                .replace("s/", "")
                .replace(" ", "")
                .replace(",", "")
            )
            try:
                price = Decimal(digits)
            except Exception:
                print(f"No pude convertir el precio (texto): {price_text}")
                continue
        else:
            # Mejor: usar el atributo data-price-amount="3699"
            price_amount = price_wrapper.get("data-price-amount")
            try:
                price = Decimal(price_amount)
            except Exception:
                print(f"No pude convertir el precio (data-price-amount): {price_amount}")
                continue

        # ===== IMAGEN =====
        # <img class="product-image-photo" src="...">
        img_el = card.select_one("img.product-image-photo")
        image_url = img_el["src"] if img_el and img_el.has_attr("src") else None

        # ===== CATEGORÍA =====
        # Por ahora puedes pasarla como parámetro según lo que estás buscando
        cat_value = category

        print(f"- {name} | {brand} | {price} | {image_url}")

        upsert_product_and_inventory(
            db=db,
            store=store,
            name=name,
            brand=brand,
            category=cat_value,
            price=price,
            image_url=image_url,
        )

        # Para no abusar del sitio
        time.sleep(0.2)

def main():
    db = get_session()
    try:
        # Aquí defines qué quieres traer de Hiraoka.
        # Por ejemplo: celulares, TVs, lavadoras, etc.
        scrape_hiraoka_search(db, "huawei pura 70", category="celular")
        scrape_hiraoka_search(db, "televisor 55", category="televisor")
        scrape_hiraoka_search(db, "lavadora", category="lavadora")
    finally:
        db.close()

if __name__ == "__main__":
    main()
