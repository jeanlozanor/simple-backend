from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("No se encontró OPENAI_API_KEY")

client = OpenAI(api_key=api_key)

resp = client.responses.create(
    model="gpt-5.1",
    input="Responde solo esta frase: 'SimPLE está conectado correctamente'."
)

print(resp.output_text)
