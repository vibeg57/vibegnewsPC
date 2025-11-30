import os
import requests
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import logging
import uvicorn # Импортируем uvicorn для запуска

# --- Настройка логирования ---
# Используем StreamHandler, чтобы логи выводились в stdout/stderr, что Vercel будет собирать
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# --- Получаем переменные окружения ---
# Vercel автоматически подставит эти переменные, если они настроены в проекте
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
# Устанавливаем значение по умолчанию, если переменная не найдена
MESSAGE_LIMIT_PER_DAY = int(os.getenv("MESSAGE_LIMIT_PER_DAY", 30))

# --- Проверка обязательных переменных окружения при старте ---
if not TELEGRAM_BOT_TOKEN:
    logging.error("TELEGRAM_BOT_TOKEN не установлен. Бот не будет работать.")
if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
    logging.warning("GPTBOTS_API_KEY или GPTBOTS_AGENT_ID не установлены. Функционал GPT будет недоступен.")

# --- Клавиатура меню ---
MENU_OPTIONS = [
    "Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"
]

def generate_menu_keyboard():
    # Создаем клавиатуру с двумя кнопками в ряду
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
    # Проверяем наличие ключей перед запросом
    if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
        logging.error("GPTBOTS_API_KEY или GPTBOTS_AGENT_ID не установлены. Невозможно сгенерировать ответ.")
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
        # Увеличим таймаут, так как запросы к внешним API могут занимать время
        response = requests.post(endpoint, headers=headers, json=data, timeout=15) # Увеличил таймаут до 15 секунд
        response.raise_for_status() # Проверяем на ошибки HTTP (4xx, 5xx)
        resp = response.json()
        return resp.get('data', {}).get('reply', 'Сервис GPTBots не ответил.')
    except requests.exceptions.Timeout:
        logging.error("Таймаут при запросе к GPTBots API")
        return "Сервис временно недоступен. Попробуйте позже."
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к GPTBots API: {e}")
        return "Произошла ошибка при обращении к сервису GPTBots."

def send_message(chat_id, text, reply_markup=None): # reply_markup теперь опционален
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN не установлен. Невозможно отправить сообщение.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        # Если reply_markup передан, используем его, иначе не добавляем в JSON
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка отправки сообщения в Telegram: {e}")
        return False

def send_inline(chat_id, text, button_text, button_url):
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN не установлен. Невозможно отправить inline-сообщение.")
        return False

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

app = FastAPI()

@app.get("/") # Добавляем корневой маршрут для проверки работы сервера
async def read_root():
    return {"message": "Бот запущен и работает!"}

@app.post("/webhook")
async def webhook(request: Request):
    chat_id = None # Инициализируем chat_id, чтобы он был доступен в блоке except
    try:
        # Логируем входящий запрос
        body = await request.body()
        try:
            data = await request.json()
            # ensure_ascii=False для корректного отображения кириллицы в логах
            logging.info(f"Received webhook data: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            logging.error("Некорректный JSON в запросе")
            return JSONResponse({"error": "Invalid JSON data"}, status_code=400)

        message = data.get("message")
        if not message:
            logging.warning("В запросе отсутствует поле 'message'")
            return JSONResponse({"ok": True}) # Отвечаем OK, чтобы Telegram не повторял запрос

        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")

        if not chat_id or not user_id:
            logging.warning(f"Не удалось получить chat_id или user_id из сообщения: {message}")
            return JSONResponse({"ok": True})

        # Обработка команды /start
        if text == "/start":
            # Отправляем приветственное сообщение с клавиатурой меню
            send_message(chat_id, "Привет! Я помощник по компьютерной грамотности для новичков. Выберите раздел меню:", menu_markup)
        # Обработка пунктов меню
        elif text in MENU_OPTIONS:
            handle_menu_option(chat_id, text)
        # Обработка текстовых запросов через GPTBots
        else:
            # Проверяем, установлен ли токен Telegram перед отправкой ответа
            if not TELEGRAM_BOT_TOKEN:
                logging.error("TELEGRAM_BOT_TOKEN не установлен. Невозможно отправить ответ пользователю.")
                return JSONResponse({"error": "Telegram bot token is missing"}, status_code=500)

            response_text = gptbots_generate(text, user_id)
            # Возвращаем клавиатуру меню после ответа GPT
            send_message(chat_id, response_text, reply_markup=menu_markup)

        return JSONResponse({"ok": True})

    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка в webhook: {e}", exc_info=True) # exc_info=True для полного стека ошибок
        # Пытаемся отправить сообщение об ошибке пользователю, если это возможно
        if chat_id and TELEGRAM_BOT_TOKEN:
            send_message(chat_id, "Произошла внутренняя ошибка. Попробуйте позже.", reply_markup=menu_markup)
        return JSONResponse({"error": "Internal Server Error"}, status_code=500)

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
    # Отправляем сообщение с клавиатурой меню
    send_message(chat_id, messages.get(option, "Выбранный раздел недоступен."), reply_markup=menu_markup)

# --- Запуск приложения FastAPI ---
# Этот блок будет выполняться, когда контейнер запускается
if __name__ == "__main__":
    # Получаем порт из переменной окружения PORT, если она есть, иначе используем 8080
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Запуск FastAPI приложения на порту {port}")
    # Важно: host='0.0.0.0' чтобы приложение было доступно извне контейнера
    # Vercel будет использовать порт, переданный в переменной окружения PORT
    # Поэтому мы запускаемся на 0.0.0.0 и используем этот порт
    uvicorn.run(app, host="0.0.0.0", port=port)
