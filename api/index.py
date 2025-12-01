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

# --- Получаем переменные окружения ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
MESSAGE_LIMIT_PER_DAY = int(os.getenv("MESSAGE_LIMIT_PER_DAY", 30))

# --- Клавиатура меню ---
MENU_OPTIONS = [
    "Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"
]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

# --- Системное сообщение для GPTBots ---
SYSTEM_PROMPT = (
    "Вы — экспертный помощник по компьютерной грамотности для начинающих. "
    "Отвечайте понятно, дружелюбно и по существу. Избегайте сложных терминов, если не попросили. "
    "Помогайте с вопросами по работе с компьютером, смартфоном, интернетом, программами и настройкам. "
    "Если вопрос выходит за рамки — вежливо сообщайте об этом."
)

def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
        logging.error("GPTBOTS_API_KEY или GPTBOTS_AGENT_ID не установлены.")
        return "К сожалению, я не могу обработать ваш запрос, так как не настроены ключи для сервиса GPT."

    endpoint = "https://openapi.gptbots.ai/v1/chat"
    headers = {
        "X-API-Key": GPTBOTS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "agent_id": GPTBOTS_AGENT_ID,
        "user_id": str(user_id),
        "query": text,
        "system_prompt": SYSTEM_PROMPT
    }
    try:
        response = requests.post(endpoint, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        resp = response.json()
        return resp.get('data', {}).get('reply', 'Сервис GPTBots не ответил.')
    except Exception as e:
        logging.error(f"Ошибка GPTBots: {e}")
        return "Сервис временно недоступен. Попробуйте позже."

def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN не установлен.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    try:
        requests.post(url, json=data, timeout=10)
        return True
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        return False

def handle_menu_option(chat_id, option):
    messages = {
        "Компьютер": "В этом разделе вы найдете советы по работе с компьютером...",
        "Смартфон": "Здесь вы узнаете, как пользоваться смартфоном...",
        "Интернет": "В этом разделе вы найдете информацию о безопасном использовании интернета...",
        "Программы": "Здесь вы найдете советы по выбору и использованию программ...",
        "FAQ": "В этом разделе собраны ответы на часто задаваемые вопросы.",
        "О боте": f"Бот является помощником сайта vibegnews.tilda.ws. Лимит: {MESSAGE_LIMIT_PER_DAY} сообщений."
    }
    send_message(chat_id, messages.get(option, "Раздел недоступен."), reply_markup=menu_markup)

app = FastAPI()

# ЭТО ВАЖНОЕ ИЗМЕНЕНИЕ:
# Мы слушаем корневой путь "/", потому что файл уже называется webhook.py
@app.post("/") 
async def webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Received data: {json.dumps(data, ensure_ascii=False)}")
        
        message = data.get("message")
        if not message:
            return JSONResponse({"ok": True})

        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")

        if text == "/start":
            send_message(chat_id, "Привет! Я помощник по компьютерной грамотности. Выберите раздел:", menu_markup)
        elif text in MENU_OPTIONS:
            handle_menu_option(chat_id, text)
        else:
            response_text = gptbots_generate(text, user_id)
            send_message(chat_id, response_text, reply_markup=menu_markup)

        return JSONResponse({"ok": True})

    except Exception as e:
        logging.error(f"Error: {e}")
        return JSONResponse({"ok": True}) # Всегда отвечаем OK телеграму, чтобы он не спамил повторами

@app.get("/")
async def read_root():
    return {"message": "Бот работает! (Файл api/webhook.py)"}