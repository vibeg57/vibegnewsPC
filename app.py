import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
from datetime import datetime
from collections import defaultdict

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
MESSAGE_LIMIT_PER_DAY = 30

# Счетчик сообщений
user_message_count = defaultdict(lambda: {"date": datetime.utcnow().date(), "count": 0})
ignore_list = set()

# Клавиатура меню
menu_keyboard = [
    ["Компьютер", "Смартфон"],
    ["Интернет", "Программы"],
    ["FAQ", "О боте"]
]
menu_markup = {
    "keyboard": menu_keyboard,
    "resize_keyboard": True
}

# Системное сообщение для GPTBots — роль и стиль агента
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
        r = requests.post(endpoint, headers=headers, json=data, timeout=12)
        r.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        resp = r.json()
        return resp.get('data', {}).get('reply', 'Сервис GPTBots не ответил.')
    except requests.exceptions.RequestException as e:
        print(f"Error with GPTBots API: {e}")
        return "Не удалось связаться с сервисом GPTBots. Попробуйте позже."

def check_limit(user_id):
    today = datetime.utcnow().date()
    record = user_message_count[user_id]
    if record["date"] != today:
        user_message_count[user_id] = {"date": today, "count": 0}
        return True
    return record["count"] < MESSAGE_LIMIT_PER_DAY

def increment_limit(user_id):
    today = datetime.utcnow().date()
    record = user_message_count[user_id]
    if record["date"] != today:
        user_message_count[user_id] = {"date": today, "count": 1}
    else:
        record["count"] += 1

def send_message(chat_id, text, reply_markup=menu_markup):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

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
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Error sending inline message to Telegram: {e}")

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not user_id:
        return JSONResponse({"ok": True})

    if user_id in ignore_list:
        return JSONResponse({"ok": True})

    if not check_limit(user_id):
        send_message(chat_id, f"Достигнут лимит ({MESSAGE_LIMIT_PER_DAY}) сообщений на сегодня. Попробуйте завтра!")
        return JSONResponse({"ok": True})
    increment_limit(user_id)

    try:
        if text == "/start":
            send_message(chat_id, "Привет! Я помощник по компьютерной грамотности для новичков. Выберите раздел меню:")

        elif text == "Компьютер":
            send_message(chat_id, "В этом разделе вы найдете советы по работе с компьютером, настройке операционной системы и решению распространенных проблем.")
        elif text == "Смартфон":
            send_message(chat_id, "Здесь вы узнаете, как пользоваться смартфоном, устанавливать приложения и настраивать параметры.")
        elif text == "Интернет":
            send_message(chat_id, "В этом разделе вы найдете информацию о безопасном использовании интернета, поисковых системах и социальных сетях.")
        elif text == "Программы":
            send_message(chat_id, "Здесь вы найдете советы по выбору и использованию различных программ для работы, учебы и развлечений.")
        elif text == "FAQ":
            send_message(chat_id, "В этом разделе собраны ответы на часто задаваемые вопросы.")
        elif text == "О боте":
            send_inline(chat_id,
                        ("Бот является помощником сайта [vibegnews.tilda.ws](https://vibegnews.tilda.ws/) и даёт ответы по его темам и другим вопросам.\n\n"
                         f"*Основные возможности:*\n- Лимит сообщений: {MESSAGE_LIMIT_PER_DAY} в сутки.\n- Сброс лимита: раз в день.\n- Ведение статистики использования для улучшения сервиса.\n\n"
                         "*Конфиденциальность:*\nВсе ваши данные и сообщения обрабатываются с соблюдением конфиденциальности и не передаются третьим лицам."),
                        "Перейти на сайт", "https://vibegnews.tilda.ws/")

        else:
            response = gptbots_generate(text, user_id)
            send_message(chat_id, response)

    except Exception as e:
        print(f"An error occurred: {e}")  # Log the error for debugging

    return JSONResponse({"ok": True})
