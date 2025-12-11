# SimPLE Backend

Backend de SimPLE - Asistente de compras inteligente con IA.

## Características

- API REST con FastAPI
- Integración con OpenAI GPT
- Web scraping de tiendas
- Búsqueda inteligente de productos

## Requisitos

- Python 3.11+
- pip

## Instalación Local

1. Clona el repositorio:
```bash
git clone <repository-url>
cd simple-backend
```

2. Crea un entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instala las dependencias:
```bash
pip install -r requirements.txt
```

4. Crea un archivo `.env` con tus credenciales:
```
OPENAI_API_KEY=tu_api_key_aqui
```

5. Ejecuta el servidor:
```bash
uvicorn main:app --reload
```

El servidor estará disponible en `http://localhost:8000`

## Endpoints

- `GET /search?q=<query>` - Busca productos basado en la query
- `GET /chat?question=<question>` - Chat con IA para búsqueda de productos
- `GET /docs` - Documentación interactiva (Swagger UI)

## Despliegue en Render

1. Sube el código a GitHub
2. Ve a https://render.com
3. Crea un nuevo "Web Service"
4. Conecta tu repositorio de GitHub
5. Configura las variables de entorno:
   - `OPENAI_API_KEY`: Tu API key de OpenAI
6. Deploy

## Desarrollo

Para contribuir:
1. Haz fork del repositorio
2. Crea una rama para tu feature
3. Haz commit de tus cambios
4. Push a la rama
5. Abre un Pull Request

## Licencia

MIT
