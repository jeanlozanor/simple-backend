import os
import json

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("No se encontró OPENAI_API_KEY")

client = OpenAI(api_key=api_key)

BASE_URL = "http://127.0.0.1:8000"  # FastAPI local


def call_simple_search(query: str):
    """
    Llama a tu endpoint /search de SimPLE y devuelve el JSON.
    """
    resp = requests.get(f"{BASE_URL}/search", params={"q": query}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def ai_verify_results(query: str, products_json):
    """
    Usa gpt-5.1 para revisar los resultados de SimPLE y detectar problemas.
    """
    instructions = """
Eres un verificador de calidad para la app SimPLE.

SimPLE recibe una búsqueda (por ejemplo 'celular samsung')
y devuelve una lista de productos en formato JSON con:
- name
- brand
- price
- currency
- store_name
- product_url
- image_url

Tu tarea:
1. Revisar si los productos devueltos tienen sentido para la búsqueda del usuario.
2. Detectar errores o anomalías, por ejemplo:
   - precios = 0 o negativos
   - currency distinta de 'PEN'
   - image_url vacía o sospechosa
   - productos que no coinciden con la marca o categoría pedida
3. Responder en español, con:
   - Un resumen general (OK / problemas)
   - Lista de problemas concretos (si los hay)
   - Recomendaciones para mejorar el scraper o los filtros.
"""

    user_content = (
        "Consulta del usuario:\n"
        f"{query}\n\n"
        "JSON devuelto por SimPLE:\n"
        f"{json.dumps(products_json, ensure_ascii=False, indent=2)}"
    )

    response = client.responses.create(
        model="gpt-5.1",
        instructions=instructions,
        input=user_content,
    )

    print(response.output_text)


if __name__ == "__main__":
    # Cambia la query para probar distintos casos
    query = "celular samsung entre 800 y 1500 soles"

    # 1. Llamamos a tu backend SimPLE
    products = call_simple_search(query)

    # 2. Pedimos a gpt-5.1 que revise esos resultados
    ai_verify_results(query, products)
