import os
import json
import requests
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Версия для проверки обновления
VERSION = "4.0 (Обход DNS)"

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
    
    # 🛠 СТРАТЕГИЯ ОБХОДА
    # Мы используем api.gptbots.ai (так как он доступен), но меняем ПУТЬ
    
    attempts = [
        # Попытка 1: Вложенный путь openapi
        "https://api.gptbots.ai/openapi/v1/chat",
        
        # Попытка 2: Альтернативный путь bot
        "https://api.gptbots.ai/bot/v1/chat",
        
        # Попытка 3: "Подмена хоста" (Стучимся в api, но представляемся как openapi)
        # Это хакерский трюк, который часто срабатывает на Cloudflare
        {"url": "https://api.gptbots.ai/v1/chat", "host_header": "openapi.gptbots.ai"}
    ]
    
    base_headers = {
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

    for attempt in attempts:
        try:
            # Настройка URL и Заголовков
            if isinstance(attempt, dict):
                url = attempt["url"]
                headers = base_headers.copy()
                headers["Host"] = attempt["host_header"] # Подменяем заголовок
                debug_info = f"Подмена Host на {attempt['host_header']}"
            else:
                url = attempt
                headers = base_headers
                debug_info = url

            # Запрос
            resp = requests.post(url, headers=headers, json=data, timeout=5)
            
            if resp.status_code == 200:
                raw = resp.json()
                reply = raw.get('data', {}).get('reply') or raw.get('message')
                if reply:
                    return reply
                else:
                    return f"Пустой ответ ({debug_info}): {json.dumps(raw, ensure_ascii=False)}"
            elif resp.status_code == 404:
                last_error += f"\n❌ {debug_info} -> 404"
                continue # Ищем дальше
            else:
                # Если 401 или 500 - значит мы нашли сервер, но другая ошибка
                return f"⚠️ Ошибка на {debug_info}: {resp.status_code} {resp.text[:100]}"
                
        except Exception as e:
            last_error += f"\n🔥 {url} -> {str(e)[:50]}"

    return f"Все попытки провалились:{last_error}"

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
                send_message(chat_id, f"Версия: {VERSION}. Пробую обход DNS...", menu_markup)
            else:
                send_message(chat_id, "Подбираю ключи...")
                reply = gptbots_generate(text, user_id)
                send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)