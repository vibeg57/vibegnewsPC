import os
import requests
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import sqlite3
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
MESSAGE_LIMIT_PER_DAY = int(os.getenv("MESSAGE_LIMIT_PER_DAY", 30))

# База данных для хранения счетчиков сообщений
DB_PATH = "messages.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_messages (
            user_id INTEGER PRIMARY KEY,
            date TEXT,
            count INTEGER
        )
    """)
    conn.commit()
    conn.close()

def check_limit(user_id):
    today = datetime.utcnow().date()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT date, count FROM user_messages WHERE user_id = ?", (user_id,))
    record = cursor.fetchone()
    if not record or record[0] != str(today):
        cursor.execute("REPLACE INTO user_messages (user_id, date, count) VALUES (?, ?, 0)", (user_id, str(today)))
        conn.commit()
        conn.close()
        return True
    return record[1] < MESSAGE_LIMIT_PER_DAY

def increment_limit(user_id):
    today = datetime.utcnow().date()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE user_messages SET count = count + 1 WHERE user_id = ? AND date = ?", (user_id, str(today)))
    conn.commit()
    conn.close()

# Клавиатура меню
MENU_OPTIONS = [
    "Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"
]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

# Системное сообщение для GPTBots
SYSTEM_PROMPT = (
    "Вы — экспертный помощник по компьютерной грамотности для начинающих. "
    "Отвечайте понятно, дружелюбно и по существу. Избегайте сложных терминов, если не попросили. "
    "Помогайте с вопросами по работе с компьютером, смартфоном, интернетом, программами и настройкам. "
    "Если вопрос выходит за рамки — вежливо сообщайте об этом."
)

def gptbots_generate(text, user_id):
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
        response = requests.post(endpoint, headers=headers, json=data, timeout=12)
        response.raise_for_status()
        resp = response.json()
        return resp.get('data', {}).get('reply', 'Сервис GPTBots не ответил.')
    except requests.exceptions.Timeout:
        logging.error("Таймаут при запросе к GPTBots API")
        return "Сервис временно недоступен. Попробуйте позже."
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к GPTBots API: {e}")
        return "Произошла ошибка при обращении к сервису GPTBots."

def send_message(chat_id, text, reply_markup=menu_markup):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка отправки сообщения в Telegram: {e}")
        return False

def send_inline(chat_id, text, button_text, button_url):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    reply_markup = {
        "inline_keyboard": [
            [{"text": button_text, "url": button_url}]
        ]
    }
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка отправки inline-сообщения в Telegram: {e}")
        return False

# Инициализация базы данных
init_db()

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not user_id:
        logging.warning("Не удалось получить chat_id или user_id")
        return JSONResponse({"ok": True})

    if not check_limit(user_id):
        send_message(chat_id, f"Достигнут лимит ({MESSAGE_LIMIT_PER_DAY}) сообщений на сегодня. Попробуйте завтра!")
        return JSONResponse({"ok": True})
    increment_limit(user_id)

    try:
        if text == "/start":
            send_message(chat_id, "Привет! Я помощник по компьютерной грамотности для новичков. Выберите раздел меню:")
        elif text in MENU_OPTIONS:
            handle_menu_option(chat_id, text)
        else:
            response = gptbots_generate(text, user_id)
            send_message(chat_id, response)
    except Exception as e:
        logging.error(f"Произошла ошибка: {e}")

    return JSONResponse({"ok": True})

def handle_menu_option(chat_id, option):
    messages = {
        "Компьютер": "В этом разделе вы найдете советы по работе с компьютером...",
        "Смартфон": "Здесь вы узнаете, как пользоваться смартфоном...",
        "Интернет": "В этом разделе вы найдете информацию о безопасном использовании интернета...",
        "Программы": "Здесь вы найдете советы по выбору и использованию программ...",
        "FAQ": "В этом разделе собраны ответы на часто задаваемые вопросы.",
        "О боте": ("Бот является помощником сайта [vibegnews.tilda.ws](https://vibegnews.tilda.ws/) и даёт ответы по его темам и другим вопросам.\n\n"
                   f"*Основные возможности:*\n- Лимит сообщений: {MESSAGE_LIMIT_PER_DAY} в сутки.\n- Сброс лимита: раз в день.\n- Ведение статистики использования для улучшения сервиса.\n\n"
                   "*Конфиденциальность:*\nВсе ваши данные и сообщения обрабатываются с соблюдением конфиденциальности и не передаются третьим лицам.")
    }
    send_message(chat_id, messages.get(option, "Выбранный раздел недоступен."))
