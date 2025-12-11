from typing import List

import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from models import Product, ChatResponse
from ai_client import interpret_query, client  # client es el de OpenAI que ya usamos
from scrapers import search_all_stores

app = FastAPI(
    title="SimPLE Backend",
    description="Backend de SimPLE para búsqueda de productos con soporte de IA.",
    version="0.1.0",
)

# Habilitamos CORS básico, por si luego conectas un front (web / móvil)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en prod lo puedes restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/search", response_model=List[Product])
def search(q: str = Query(..., description="Texto de búsqueda del usuario")):
    """
    Endpoint básico de búsqueda:
    - Usa GPT-5.1 para interpretar la búsqueda (ai_client.interpret_query)
    - Llama a search_all_stores() para obtener productos
    - Devuelve solo la lista de productos (JSON)
    """
    filters = interpret_query(q)
    products = search_all_stores(filters)
    return products


@app.get("/chat", response_model=ChatResponse)
def chat(question: str = Query(..., description="Mensaje del usuario para el asistente SimPLE")):
    """
    Endpoint conversacional:
    - Interpreta la búsqueda con GPT (mismo interpret_query)
    - Busca productos
    - Llama a GPT otra vez para que genere una respuesta en texto,
      explicando qué opciones hay y recomendando algunas.
    - Devuelve texto + lista de productos.
    """
    # 1. Interpretar búsqueda y obtener productos
    filters = interpret_query(question)
    products = search_all_stores(filters)

    # Preparamos los productos como JSON puro para dárselos al modelo
    products_json = [p.model_dump() for p in products]

    # 2. Llamar a GPT-5.1 para que analice y responda
    instructions = """
Eres un asistente de compras para la app SimPLE.

Tu tarea:
- Leer la consulta del usuario.
- Leer la lista de productos devueltos por el backend (en JSON).
- Responder en ESPAÑOL, de forma clara y breve (máx. 2–3 párrafos).
- Menciona 2 o 3 productos recomendados con su precio aproximado y alguna diferencia importante.
- Si hay muy pocos productos, dilo.
- Si no hay productos, explícalo y sugiere cómo reformular la búsqueda.

NO inventes productos que no estén en la lista JSON.
"""

    user_content = (
        "Consulta del usuario:\n"
        f"{q}\n\n"
        "Filtros interpretados (marca, categoría, rango de precios):\n"
        f"{filters.model_dump()}\n\n"
        "Lista de productos devueltos por el backend SimPLE (JSON):\n"
        f"{json.dumps(products_json, ensure_ascii=False, indent=2)}"
    )

    resp = client.responses.create(
        model="gpt-5.1",
        instructions=instructions,
        input=user_content,
    )

    answer = resp.output_text or "No pude generar una respuesta."

    return ChatResponse(answer=answer, products=products)
