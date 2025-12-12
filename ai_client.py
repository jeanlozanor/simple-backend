import os
import json

from dotenv import load_dotenv
from openai import OpenAI

from models import SearchFilters

# Carga variables del .env (incluida OPENAI_API_KEY)
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("No se encontró OPENAI_API_KEY en el .env")

# Cliente de OpenAI - inicialización simple
try:
    client = OpenAI(api_key=api_key)
except Exception as e:
    print(f"Warning: Error inicializando OpenAI client: {e}")
    client = None

SYSTEM_PROMPT = """
Eres un asistente para la app SimPLE. Lee la búsqueda y devuelve SOLO un JSON válido.

Objetivo: clasificar bien la categoría para evitar mezclar celulares con TV u otros.

Usa SOLO estas categorías (en minúsculas):
- "celular"
- "televisor"
- "laptop"
- "tablet"
- "audifonos"
- "monitor"
- "reloj"
- "accesorio"

Si no está claro, deja "category": null.

Si el usuario menciona un modelo específico (p. ej. "s24", "iPhone 15", "Galaxy A54"), ponlo en normalized_query junto con la marca para buscar algo preciso.

Estructura de salida (solo JSON, sin texto extra):
{
    "normalized_query": "...",
    "brand": "..." o null,
    "category": "..." o null,
    "min_price": number o null,
    "max_price": number o null
}

Ejemplos:
Usuario: "celular samsung s24 buena cámara"
{
    "normalized_query": "celular samsung s24",
    "brand": "Samsung",
    "category": "celular",
    "min_price": null,
    "max_price": null
}

Usuario: "tv lg 55 pulgadas 4k entre 1500 y 2500"
{
    "normalized_query": "televisor lg 55 4k",
    "brand": "LG",
    "category": "televisor",
    "min_price": 1500.0,
    "max_price": 2500.0
}

Usuario: "audífonos sony baratos"
{
    "normalized_query": "audifonos sony",
    "brand": "Sony",
    "category": "audifonos",
    "min_price": null,
    "max_price": null
}
"""


def interpret_query(user_query: str) -> SearchFilters:
    """
    Usa GPT-4 para interpretar la búsqueda del usuario
    y devolver filtros estructurados (marca, categoría, rango de precios).
    """
    if not client:
        return SearchFilters(
            raw_query=user_query,
            normalized_query=user_query,
            brand=None,
            category=None,
            min_price=None,
            max_price=None,
        )

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Búsqueda del usuario: {user_query}\nRecuerda: responde solo el JSON."}
            ],
            temperature=0.3,
            max_tokens=200
        )

        raw_text = response.choices[0].message.content or ""
    except Exception as e:
        print(f"Error llamando a OpenAI: {e}")
        raw_text = ""

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Si algo sale mal, usamos la query tal cual como fallback
        data = {
            "normalized_query": user_query,
            "brand": None,
            "category": None,
            "min_price": None,
            "max_price": None,
        }

    # Post-procesamos para asegurar categoría cuando sea obvia
    normalized = data.get("normalized_query", user_query)
    brand = data.get("brand")
    category = data.get("category")

    lower_q = (user_query or "").lower()
    if category is None:
        if any(w in lower_q for w in ["celular", "telefono", "smartphone", "phone"]):
            category = "celular"
        elif "tv" in lower_q or "televisor" in lower_q:
            category = "televisor"
        elif "laptop" in lower_q or "notebook" in lower_q or "macbook" in lower_q:
            category = "laptop"
        elif "tablet" in lower_q or "ipad" in lower_q:
            category = "tablet"
        elif "audifono" in lower_q or "aud\u00edfono" in lower_q or "audifonos" in lower_q or "auricular" in lower_q:
            category = "audifonos"

    return SearchFilters(
        raw_query=user_query,
        normalized_query=normalized,
        brand=brand,
        category=category,
        min_price=data.get("min_price"),
        max_price=data.get("max_price"),
    )
