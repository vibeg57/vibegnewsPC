import os
import json
import requests
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ВЕРСИЯ 5.0 (Региональные зеркала)
VERSION = "5.0 (USA/Singapore)"

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
    data = {"chat_id": chat_id, "text": text, **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})}
    try:
        requests.post(url, json=data, timeout=5)
    except: pass

def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY: return "❌ Нет ключа API"
    
    # 🌍 СПИСОК ЗЕРКАЛ (Если главное не работает, пробуем их)
    endpoints = [
        "https://openapi-us.gptbots.ai/v1/chat",  # Зеркало США
        "https://openapi-sg.gptbots.ai/v1/chat",  # Зеркало Сингапур
        "https://openapi.gptbots.ai/v1/chat",     # Главный (на всякий случай)
    ]
    
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
    
    errors = []

    for url in endpoints:
        try:
            # Пробуем подключиться (5 сек на попытку)
            resp = requests.post(url, headers=headers, json=data, timeout=5)
            
            if resp.status_code == 200:
                raw = resp.json()
                reply = raw.get('data', {}).get('reply') or raw.get('message')
                if reply:
                    return reply
                else:
                    return f"✅ Подключился к {url}, но ответ пуст: {json.dumps(raw, ensure_ascii=False)}"
            
            # Если ошибка 404/500/401 - запоминаем и идем дальше
            errors.append(f"{url} -> {resp.status_code}")
            
        except Exception as e:
            # Если ошибка DNS или таймаут - запоминаем и идем дальше
            errors.append(f"{url} -> {str(e)[:40]}...")

    # Если ни одно зеркало не сработало
    return f"❌ Все зеркала недоступны:\n" + "\n".join(errors)

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
                send_message(chat_id, f"Версия: {VERSION}. Ищу зеркала...", menu_markup)
            else:
                send_message(chat_id, "Соединяюсь...")
                reply = gptbots_generate(text, user_id)
                send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)