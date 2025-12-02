import os
import json
import requests  # Мы используем requests вместо httpx
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")

MENU_OPTIONS = ["Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown", 
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    try:
        # Синхронный запрос
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Telegram Send Error: {e}")

def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY: return "Нет ключа API"
    
    endpoint = "https://openapi.gptbots.ai/v1/chat"
    headers = {"X-API-Key": GPTBOTS_API_KEY.strip(), "Content-Type": "application/json"}
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "stream": False
    }
    
    try:
        # Синхронный запрос (requests не вызывает Errno 16)
        response = requests.post(endpoint, headers=headers, json=data, timeout=20)
        if response.status_code == 200:
            return response.json().get('data', {}).get('reply') or "Пустой ответ"
        return f"Ошибка GPT: {response.status_code}"
    except Exception as e:
        logger.error(f"GPT Error: {e}")
        return "Бот недоступен (ошибка соединения)"

@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            user_id = data["message"]["from"]["id"]
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Привет! Я на связи.", menu_markup)
            else:
                # Имитация печати
                try:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction", 
                                  json={"chat_id": chat_id, "action": "typing"}, timeout=1)
                except: pass
                
                reply = gptbots_generate(text, user_id)
                send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return JSONResponse(content={"status": "error"}, status_code=500)