import os
import json
import requests
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Логирование
logging.basicConfig(level=logging.INFO)
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
    
    # Мы убрали parse_mode, чтобы Markdown не ломал сообщения с спецсимволами
    data = {
        "chat_id": chat_id, 
        "text": text, 
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"TG Error: {e}")

def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY: return "❌ Ошибка: Нет ключа API"
    
    # ✅ Используем api.gptbots.ai (он отвечает 401, значит сервер живой)
    endpoint = "https://api.gptbots.ai/v1/chat"
    
    # ✅ Используем Bearer токен (исправляет ошибку 401)
    headers = {
        "Authorization": f"Bearer {GPTBOTS_API_KEY.strip()}",
        "Content-Type": "application/json"
    }
    
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "stream": False
    }
    
    try:
        # Таймаут 9 сек (Vercel Free лимит ~10 сек)
        resp = requests.post(endpoint, headers=headers, json=data, timeout=9)
        
        if resp.status_code == 200:
            raw = resp.json()
            # Пытаемся найти ответ в разных полях JSON
            reply = raw.get('data', {}).get('reply') or raw.get('message')
            if reply:
                return reply
            else:
                return f"Ответ получен, но пустой: {json.dumps(raw, ensure_ascii=False)}"
        else:
            # Выводим код ошибки и начало текста ошибки
            return f"Ошибка GPT {resp.status_code}: {resp.text[:300]}"
            
    except requests.exceptions.Timeout:
        return "⏱ ИИ думает слишком долго (больше 9 сек)."
    except Exception as e:
        return f"Ошибка соединения: {str(e)}"

@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")
            user_id = data["message"].get("from", {}).get("id")

            if not text: return JSONResponse(content={"status": "ignored"})

            if text == "/start":
                send_message(chat_id, "Привет! Я готов. Задай вопрос.", menu_markup)
            else:
                send_message(chat_id, "Думаю...")
                reply = gptbots_generate(text, user_id)
                send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)