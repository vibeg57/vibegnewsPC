import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

# Отключаем предупреждения SSL (хотя на проде лучше так не делать)
import urllib3
urllib3.disable_warnings()

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

async def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Нет токена телеграм!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", 
            **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=data, timeout=5.0)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")

async def gptbots_generate(text, user_id):
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
        async with httpx.AsyncClient(verify=False) as client:
            # Увеличиваем таймаут, GPT может думать долго
            response = await client.post(endpoint, headers=headers, json=data, timeout=25.0)
            
            if response.status_code == 200:
                resp_json = response.json()
                # Логируем ответ для отладки
                logger.info(f"GPT Response: {resp_json}")
                return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Пустой ответ от GPT"
            else:
                logger.error(f"GPT Error {response.status_code}: {response.text}")
                return f"Ошибка API GPT: {response.status_code}"
    except Exception as e:
        logger.error(f"Exception GPT: {e}")
        return "Бот сейчас недоступен (таймаут)."

@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Incoming Update: {json.dumps(data)}") # Увидим в логах Vercel

        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            user_id = data["message"]["from"]["id"]
            text = data["message"].get("text", "")

            if not text:
                return JSONResponse(content={"status": "ignored"})

            if text == "/start":
                await send_message(chat_id, "Привет! Я готов помочь.", menu_markup)
            else:
                # Отправляем "печатает..."
                async with httpx.AsyncClient() as client:
                    await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction", 
                                      json={"chat_id": chat_id, "action": "typing"})
                
                # Запрос к GPT
                reply = await gptbots_generate(text, user_id)
                await send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.get("/")
async def root():
    return {"status": "Bot is running"}