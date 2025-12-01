import os
import json
import httpx # Используем современную библиотеку вместо requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
MESSAGE_LIMIT_PER_DAY = int(os.getenv("MESSAGE_LIMIT_PER_DAY", 30))

MENU_OPTIONS = ["Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

SYSTEM_PROMPT = "Отвечай кратко, понятно и дружелюбно, как эксперт для новичков."

# --- АСИНХРОННАЯ функция запроса к GPT ---
async def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
        logging.error("Нет ключей GPTBots")
        return "Ошибка настроек: нет ключей."

    endpoint = "https://openapi.gptbots.ai/v1/chat"
    
    headers = {
        "Authorization": f"Bearer {GPTBOTS_API_KEY.strip()}", # Пробуем Bearer (стандарт)
        # Если Bearer не сработает, можно раскомментировать строку ниже:
        # "X-API-Key": GPTBOTS_API_KEY.strip(), 
        "Content-Type": "application/json"
    }
    
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "system_prompt": SYSTEM_PROMPT,
        "stream": False
    }
    
    try:
        # Используем httpx для асинхронного запроса
        # timeout=20.0 дает боту больше времени на раздумья
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(endpoint, headers=headers, json=data, timeout=20.0)
            
            if response.status_code == 200:
                resp_json = response.json()
                return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Пустой ответ."
            else:
                logging.error(f"GPTBots Error {response.status_code}: {response.text}")
                return f"Ошибка сервиса ({response.status_code})."
            
    except httpx.TimeoutException:
        logging.error("GPTBots timeout")
        return "Нейросеть долго думает и не успела ответить."
    except Exception as e:
        logging.error(f"Connect Error: {e}")
        return "Не удалось соединиться с сервером GPT."

# --- Функция отправки в Telegram (тоже переделаем на httpx для надежности) ---
async def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN: return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, "text": text, "parse_mode": "Markdown",
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=data, timeout=5.0)
        return True
    except Exception as e:
        logging.error(f"TG Send Error: {e}")
        return False

app = FastAPI()

@app.post("/")
async def webhook(request: Request):
    try:
        data = await request.json()
        message = data.get("message")
        if not message: return JSONResponse({"ok": True})

        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")

        if text == "/start":
            await send_message(chat_id, "Привет! Я готов помочь. Задай вопрос:", menu_markup)
        elif text in MENU_OPTIONS:
            answers = {"О боте": "Я умный помощник.", "FAQ": "Тут будут ответы."}
            await send_message(chat_id, answers.get(text, "Раздел в разработке."), reply_markup=menu_markup)
        else:
            # Сразу говорим пользователю, что приняли запрос (чтобы он не ждал в тишине)
            await send_message(chat_id, "⏳ Думаю...", reply_markup=menu_markup)
            
            # Делаем запрос к GPT
            reply = await gptbots_generate(text, user_id)
            
            # Отправляем ответ
            await send_message(chat_id, reply, reply_markup=menu_markup)

        return JSONResponse({"ok": True})
    except Exception as e:
        logging.error(f"Global Error: {e}")
        return JSONResponse({"ok": True})

@app.get("/")
async def root():
    return {"status": "Active with httpx"}