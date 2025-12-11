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
Eres un asistente para una app de comparación de precios llamada SimPLE.
Tu tarea es leer la búsqueda del usuario y devolver un JSON con filtros estructurados.

Responde SIEMPRE SOLO un JSON válido, sin texto adicional, con este esquema:
{
  "normalized_query": "...",
  "brand": "... o null",
  "category": "... o null",
  "min_price": ... o null,
  "max_price": ... o null
}
Ejemplos:

Usuario: "zapatillas adidas para correr talla 42 baratas"
Respuesta:
{
  "normalized_query": "zapatillas adidas running",
  "brand": "Adidas",
  "category": "zapatillas",
  "min_price": null,
  "max_price": 350.0
}

Usuario: "celular samsung entre 800 y 1200 soles"
Respuesta:
{
  "normalized_query": "celular samsung",
  "brand": "Samsung",
  "category": "celular",
  "min_price": 800.0,
  "max_price": 1200.0
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

    return SearchFilters(
        raw_query=user_query,
        normalized_query=data.get("normalized_query", user_query),
        brand=data.get("brand"),
        category=data.get("category"),
        min_price=data.get("min_price"),
        max_price=data.get("max_price"),
    )
