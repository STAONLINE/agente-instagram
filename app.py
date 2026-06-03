import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ─────────────────────────────────────────────
#  CONFIGURA TU NEGOCIO AQUÍ
# ─────────────────────────────────────────────
BUSINESS_CONTEXT = """
Eres la asistente virtual de "Soy Tu Administrativa", un servicio de administración
y gestión para autónomos y pequeñas empresas en España.

SERVICIOS QUE OFRECEMOS:
- Gestión de facturación y contabilidad básica
- Presentación de impuestos (IVA, IRPF, modelo 303, 130...)
- Alta y baja como autónomo
- Gestión de presupuestos y contratos
- Atención al correo y agenda
- Soporte administrativo puntual o mensual

TARIFAS (ejemplo, ajusta con las tuyas reales):
- Pack Básico: desde 60€/mes (facturación + 1 impuesto trimestral)
- Pack Completo: desde 120€/mes (todo incluido)
- Consulta puntual: 30€/hora

ZONA DE TRABAJO:
- Trabajo 100% en remoto, atiendo a toda España.

CONTACTO Y CITAS:
- Para contratar o pedir más info, pide que te dejen su email o número
  y les contactarás en menos de 24h.
- No gestiones pagos ni contratos por Instagram.

TONO:
- Cercano, profesional y claro. Tutéales salvo que el cliente use usted.
- Respuestas cortas (máximo 3-4 líneas). Si necesitan más detalle, ofrece una llamada.
- No inventes precios ni servicios que no estén aquí.
- Si no sabes algo, di que lo consultarás y pedirás contacto.
"""

# Historial de conversaciones en memoria (se reinicia si el servidor se reinicia)
# Para producción real, usa una base de datos (Redis, SQLite, etc.)
conversations = {}

# ─────────────────────────────────────────────
#  INSTAGRAM / META WEBHOOK
# ─────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta llama a este endpoint para verificar el webhook."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == os.environ["VERIFY_TOKEN"]:
        print("Webhook verificado correctamente")
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    """Recibe los DMs de Instagram y responde con el agente."""
    data = request.get_json()
    print("Evento recibido:", json.dumps(data, indent=2))

    try:
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging["sender"]["id"]
                message = messaging.get("message", {})
                text = message.get("text")

                # Ignorar mensajes del propio bot y mensajes sin texto
                if not text or messaging["sender"]["id"] == messaging["recipient"]["id"]:
                    continue

                reply = get_ai_reply(sender_id, text)
                send_instagram_message(sender_id, reply)

    except Exception as e:
        print(f"Error procesando mensaje: {e}")

    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
#  LÓGICA DEL AGENTE IA
# ─────────────────────────────────────────────

def get_ai_reply(user_id: str, user_message: str) -> str:
    """Genera una respuesta usando Gemini REST API con historial de conversación."""
    if user_id not in conversations:
        conversations[user_id] = []

    # Guardar mensaje del usuario
    conversations[user_id].append({"role": "user", "content": user_message})

    # Construir historial en formato Gemini REST
    contents = []
    for msg in conversations[user_id][-10:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    api_key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    payload = {
        "system_instruction": {"parts": [{"text": BUSINESS_CONTEXT}]},
        "contents": contents
    }

    r = requests.post(url, json=payload)
    r.raise_for_status()
    reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]

    # Guardar respuesta en historial
    conversations[user_id].append({"role": "model", "content": reply})

    return reply


# ─────────────────────────────────────────────
#  ENVÍO DE MENSAJES A INSTAGRAM
# ─────────────────────────────────────────────

def send_instagram_message(recipient_id: str, text: str):
    """Envía un mensaje de vuelta al usuario por Instagram."""
    url = f"https://graph.facebook.com/v19.0/me/messages"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    params = {"access_token": os.environ["INSTAGRAM_ACCESS_TOKEN"]}

    r = requests.post(url, json=payload, headers=headers, params=params)
    if r.status_code != 200:
        print(f"Error enviando mensaje: {r.status_code} {r.text}")


# ─────────────────────────────────────────────
#  INICIO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

