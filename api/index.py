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
    
    # 🔍 СПИСОК АДРЕСОВ ДЛЯ ПРОВЕРКИ
    # Мы попробуем их по очереди, пока один не сработает
    possible_endpoints = [
        "https://api.gptbots.ai/openapi/v1/chat",  # Самый вероятный (путь openapi на домене api)
        "https://api.gptbots.ai/v1/chat",          # Стандартный
        "https://www.gptbots.ai/api/v1/chat",      # Альтернативный
    ]
    
    # Заголовки (шлем всё сразу, чтобы наверняка)
    headers = {
        "X-API-Key": GPTBOTS_API_KEY.strip(),
        "Authorization": f"Bearer {GPTBOTS_API_KEY.strip()}",
        "Content-Type": "application/json"
    }
    
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "stream": False
    }
    
    last_error = ""

    # 🔄 ЦИКЛ ПОДБОРА АДРЕСА
    for url in possible_endpoints:
        try:
            # Короткий таймаут для перебора (4 сек на попытку)
            resp = requests.post(url, headers=headers, json=data, timeout=4)
            
            # Если успех (200) - сразу возвращаем ответ
            if resp.status_code == 200:
                raw = resp.json()
                reply = raw.get('data', {}).get('reply') or raw.get('message')
                if reply:
                    return reply  # УРА, НАШЛИ!
                else:
                    return f"Ответ пустой (JSON): {json.dumps(raw, ensure_ascii=False)}"
            
            # Если 404 - значит адрес не тот, пробуем следующий
            elif resp.status_code == 404:
                last_error = f"404 на {url}"
                continue 
            
            # Если другая ошибка (например 401 или 500) - возвращаем её
            else:
                return f"Ошибка {resp.status_code} на {url}: {resp.text[:100]}"
                
        except Exception as e:
            last_error = str(e)
            continue # Пробуем следующий адрес

    # Если ничего не подошло
    return f"❌ Не удалось подобрать адрес сервера. Последняя ошибка: {last_error}"

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
                send_message(chat_id, "Ищу рабочий сервер...", menu_markup)
            else:
                send_message(chat_id, "Думаю...")
                reply = gptbots_generate(text, user_id)
                send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)