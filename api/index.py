import os
import requests
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# --- Переменные ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
MESSAGE_LIMIT_PER_DAY = int(os.getenv("MESSAGE_LIMIT_PER_DAY", 30))

# --- Клавиатура ---
MENU_OPTIONS = ["Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

# --- GPTBots Логика ---
SYSTEM_PROMPT = "Отвечай кратко, понятно и дружелюбно, как эксперт для новичков."

def gptbots_generate(text, user_id):
    # Проверка ключей
    if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
        logging.error("Нет ключей GPTBots!")
        return "Ошибка настройки бота (нет ключей)."

    # Точная ссылка (проверь, чтобы было /chat в конце)
    endpoint = "https://openapi.gptbots.ai/v1/chat"
    
    headers = {
        "X-API-Key": GPTBOTS_API_KEY.strip(), # strip() убирает случайные пробелы
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
        logging.info(f"Отправка запроса в GPTBots: {endpoint}")
        # Таймаут 9 секунд (важно для Vercel!)
        response = requests.post(endpoint, headers=headers, json=data, timeout=9)
        
        if response.status_code == 200:
            resp_json = response.json()
            # Пытаемся достать ответ из разных возможных полей
            return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Пустой ответ от GPT."
        else:
            logging.error(f"Ошибка GPTBots {response.status_code}: {response.text}")
            return "Сервис сейчас перегружен, попробуйте через минуту."
            
    except Exception as e:
        logging.error(f"Сбой подключения к GPTBots: {e}")
        return "Сервис временно недоступен (ошибка связи)."

# --- Отправка сообщений ---
def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown",
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    try:
        requests.post(url, json=data, timeout=5)
        return True
    except:
        return False

# --- Сервер ---
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
            send_message(chat_id, "Привет! Я готов помочь. Выбери тему:", menu_markup)
        elif text in MENU_OPTIONS:
            # Тут простая заглушка для примера
            answers = {"Компьютер": "Советы по ПК...", "О боте": "Я помощник vibegnews."}
            send_message(chat_id, answers.get(text, "Раздел в разработке."), reply_markup=menu_markup)
        else:
            # Запрос к GPT
            reply = gptbots_generate(text, user_id)
            send_message(chat_id, reply, menu_markup)

        return JSONResponse({"ok": True})
    except Exception as e:
        logging.error(f"Critical Error: {e}")
        return JSONResponse({"ok": True})

@app.get("/")
async def root():
    return {"status": "active"}