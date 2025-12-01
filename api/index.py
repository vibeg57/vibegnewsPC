import os
import requests
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import urllib3

# Отключаем предупреждения о небезопасном соединении (так как мы используем verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
        return "Ошибка: Нет ключей доступа."

    endpoint = "https://openapi.gptbots.ai/v1/chat"
    
    # ИСПРАВЛЕНИЕ: Добавляем User-Agent (маскируемся под браузер) и возвращаем X-API-Key
    headers = {
        "X-API-Key": GPTBOTS_API_KEY.strip(),
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "system_prompt": SYSTEM_PROMPT,
        "stream": False
    }
    
    try:
        # ИСПРАВЛЕНИЕ: verify=False отключает строгую проверку SSL (помогает от ConnectionError)
        response = requests.post(endpoint, headers=headers, json=data, timeout=15, verify=False)
        
        if response.status_code == 200:
            resp_json = response.json()
            return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Пустой ответ."
        elif response.status_code == 401:
             return "Ошибка ключа (401). Проверьте API Key."
        elif response.status_code == 404:
             return "Ошибка агента (404). Проверьте Agent ID."
        else:
            logging.error(f"GPTBots Error {response.status_code}: {response.text}")
            return f"Ошибка сервиса: {response.status_code}"
            
    except Exception as e:
        logging.error(f"Connect Error: {e}")
        return "Не удалось соединиться с сервером GPT."

def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN: return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, "text": text, "parse_mode": "Markdown",
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    try: requests.post(url, json=data, timeout=5)
    except: pass

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
            send_message(chat_id, "Привет! Я готов помочь. Задай вопрос:", menu_markup)
        elif text in MENU_OPTIONS:
            answers = {"О боте": "Помощник vibegnews.", "Компьютер": "Советы..."}
            send_message(chat_id, answers.get(text, "Раздел в разработке."), reply_markup=menu_markup)
        else:
            send_message(chat_id, "Запрос отправлен...", reply_markup=menu_markup)
            reply = gptbots_generate(text, user_id)
            send_message(chat_id, reply, reply_markup=menu_markup)

        return JSONResponse({"ok": True})
    except:
        return JSONResponse({"ok": True})

@app.get("/")
async def root():
    return {"status": "Running"}