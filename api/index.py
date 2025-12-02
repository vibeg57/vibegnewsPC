import os
import json
import requests
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Настройка логирования
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
    """Отправка сообщения в Telegram (через requests)"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Нет токена телеграм!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown", 
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    
    try:
        # Используем requests с таймаутом
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Telegram Send Error: {e}")

def gptbots_generate(text, user_id):
    """Запрос к GPTBots (через requests)"""
    if not GPTBOTS_API_KEY: 
        return "❌ Ошибка: Нет GPTBOTS_API_KEY"
    
    endpoint = "https://openapi.gptbots.ai/v1/chat"
    
    headers = {
        "X-API-Key": GPTBOTS_API_KEY.strip(),
        "Content-Type": "application/json"
    }
    
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "stream": False
    }
    
    try:
        # requests работает стабильнее на Vercel
        response = requests.post(endpoint, headers=headers, json=data, timeout=25)
        
        if response.status_code == 200:
            resp_json = response.json()
            return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Пустой ответ"
        else:
            logger.error(f"GPT Error {response.status_code}: {response.text}")
            return f"Ошибка API GPT: {response.status_code}"
            
    except Exception as e:
        logger.error(f"GPT Connection Error: {e}")
        return "Бот сейчас недоступен (ошибка соединения)."

@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        
        if "message" not in data:
            return JSONResponse(content={"status": "ignored"})

        chat_id = data["message"]["chat"]["id"]
        user_id = data["message"].get("from", {}).get("id", 0)
        text = data["message"].get("text", "")

        if not text:
            return JSONResponse(content={"status": "no_text"})

        if text == "/start":
            send_message(chat_id, "Привет! Я готов помочь.", menu_markup)
        else:
            # Отправляем "печатает..."
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction", 
                    json={"chat_id": chat_id, "action": "typing"},
                    timeout=2
                )
            except: 
                pass

            # Получаем ответ от GPT
            reply = gptbots_generate(text, user_id)
            send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.get("/")
async def root():
    return {"status": "Bot is running on Requests"}