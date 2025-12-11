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
    - Interpreta la búsqueda con GPT
    - Busca productos
    - Llama a GPT otra vez para que genere una respuesta en texto
    """
    try:
        # 1. Interpretar búsqueda y obtener productos
        filters = interpret_query(question)
        products = search_all_stores(filters)

        # Preparamos los productos como JSON puro
        products_json = [p.model_dump() for p in products]

        # 2. Llamar a GPT para que analice y responda
        instructions = """Eres un asistente de compras para la app SimPLE.
Tu tarea:
- Leer la consulta del usuario
- Leer la lista de productos devueltos
- Responder en ESPAÑOL, de forma clara y breve (2-3 párrafos)
- Menciona 2 o 3 productos recomendados con precio
- Si hay pocos/sin productos, dilo
NO inventes productos que no estén en la lista."""

        user_message = (
            f"Consulta: {question}\n\n"
            f"Filtros: {filters.model_dump()}\n\n"
            f"Productos encontrados:\n{json.dumps(products_json, ensure_ascii=False, indent=2)}"
        )

        resp = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=500
        )

        answer = resp.choices[0].message.content or "No pude generar una respuesta."
        
        return ChatResponse(answer=answer, products=products)
    
    except Exception as e:
        # Devolver un error controlado en lugar de crash
        error_msg = f"Error en el backend: {str(e)}"
        print(f"ERROR: {error_msg}")
        return ChatResponse(
            answer=f"Disculpa, hubo un error: {str(e)}",
            products=[]
        )
