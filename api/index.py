import os
import json
import requests
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Импорты для Telegram бота и кнопок
from telebot import TeleBot, types
from telebot.apihelper import ApiTelegramException

# --- Конфигурация ---
# ВЕРСИЯ (для информации)
VERSION = "5.0 (USA/Singapore)"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Получаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")
VERCEL_URL = os.environ.get("VERCEL_URL") # URL твоего проекта на Vercel

# Проверяем, что все необходимые переменные окружения установлены
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения.")
if not GPTBOTS_API_KEY:
    logger.error("GPTBOTS_API_KEY не установлен в переменных окружения.")
if not GPTBOTS_AGENT_ID:
    logger.error("GPTBOTS_AGENT_ID не установлен в переменных окружения.")

# --- Настройки GPTBots API ---
# Рекомендованный эндпоинт для Conversation API
# Замени 'sg' на свой дата-центр, если нужно (например, 'th')
GPTBOTS_BASE_URL = "https://api-sg.gptbots.ai/v2/conversation"

# --- Меню для Telegram бота ---
MENU_OPTIONS = ["Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"]

def generate_menu_keyboard():
    """Создает клавиатуру с кнопками меню."""
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    # Используем ReplyKeyboardMarkup для кнопок, которые появляются под полем ввода
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

menu_markup = generate_menu_keyboard()

# --- Функция отправки сообщений Telegram ---
def send_telegram_message(chat_id: int, text: str, reply_markup=None):
    """Отправляет сообщение пользователю Telegram через API."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен. Невозможно отправить сообщение.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        # "parse_mode": "HTML" # Можно добавить, если хочешь использовать форматирование
    }
    if reply_markup:
        # ReplyKeyboardMarkup нужно передавать как объект, а не JSON строку в payload
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status() # Проверяем на ошибки HTTP
        logger.info(f"Сообщение успешно отправлено в чат {chat_id}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при отправке сообщения в Telegram (чат {chat_id}): {e}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при отправке сообщения в Telegram (чат {chat_id}): {e}")

# --- Функция для генерации ответа от GPTBots ---
def gptbots_generate(query: str, user_id: int) -> str:
    """
    Отправляет запрос к Conversation API GPTBots и возвращает ответ.
    """
    if not GPTBOTS_API_KEY or not GPTBOTS_AGENT_ID:
        logger.error("GPTBOTS_API_KEY или GPTBOTS_AGENT_ID не установлены.")
        return "❌ Настройка GPTBots API не завершена."

    headers = {
        "Authorization": f"Bearer {GPTBOTS_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    payload = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id), # user_id должен быть строкой
        "query": query,
        # "stream": False # Если API поддерживает stream, можно его включить
        # Дополнительные параметры, если они есть в документации GPTBots:
        # "history": [], # Для поддержания истории диалога
        # "temperature": 0.7,
        # "max_tokens": 150
    }

    try:
        logger.info(f"Отправка запроса к GPTBots API: {GPTBOTS_BASE_URL}")
        response = requests.post(GPTBOTS_BASE_URL, headers=headers, json=payload, timeout=15) # Увеличили таймаут до 15 секунд
        response.raise_for_status() # Вызовет исключение для плохих статусов (4xx или 5xx)

        response_data = response.json()
        logger.info(f"Получен ответ от GPTBots API: {json.dumps(response_data, ensure_ascii=False)}")

        # --- Обработка ответа от GPTBots ---
        # Структура ответа может отличаться. Проверяем по коду и наличию данных.
        # Пример: {"code": 0, "message": "Success", "data": {"response": "Текст ответа"}}
        if response_data.get("code") == 0 and "data" in response_data and "response" in response_data["data"]:
            return response_data["data"]["response"]
        elif response_data.get("code") == 40127: # Developer authentication failed
            logger.error("Ошибка аутентификации GPTBots API (40127). Проверьте API ключ и его настройки.")
            return "❌ Ошибка аутентификации. Проверьте настройки API ключа."
        elif response_data.get("code") == 40400: # Not Found
            logger.error("Эндпоинт GPTBots API не найден (40400). Проверьте URL.")
            return "❌ Эндпоинт GPTBots API не найден. Проверьте настройки URL."
        elif response_data.get("code") == 20059: # Agent not found
            logger.error("Агент GPTBots API не найден (20059). Проверьте Agent ID.")
            return "❌ Агент GPTBots API не найден. Проверьте Agent ID."
        else:
            # Обработка других кодов ошибок или неожиданной структуры ответа
            error_message = response_data.get("message", "Неизвестная ошибка ответа от GPTBots.")
            logger.error(f"GPTBots API вернул ошибку: {error_message} (Код: {response_data.get('code')})")
            return f"Произошла ошибка при получении ответа от GPTBots. Пожалуйста, попробуйте позже. ({error_message})"

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP ошибка при запросе к GPTBots API: {e}")
        logger.error(f"Статус код: {e.response.status_code}")
        try:
            logger.error(f"Ответ сервера: {e.response.json()}")
        except json.JSONDecodeError:
            logger.error(f"Ответ сервера (текст): {e.response.text}")
        return "Произошла ошибка сети при обращении к GPTBots. Попробуйте позже."
    except requests.exceptions.RequestException as e:
        logger.error(f"Общая ошибка при запросе к GPTBots API: {e}")
        return "Произошла ошибка сети при обращении к GPTBots. Попробуйте позже."
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в gptbots_generate: {e}", exc_info=True) # Логируем стек вызовов
        return "Произошла непредвиденная ошибка. Попробуйте еще раз."

# --- Обработка Webhook ---
@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Получено сообщение от Telegram: {json.dumps(data, indent=2, ensure_ascii=False)}")

        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            user_id = message["from"]["id"] # ID пользователя Telegram

            if not text:
                logger.info("Получено пустое сообщение, игнорируем.")
                return JSONResponse(content={"status": "ignored", "reason": "empty message"})

            # Обработка команды /start
            if text == "/start":
                greeting_message = f"Привет! Я твой бот. Я могу помочь тебе с вопросами по IT. Выбери тему ниже или задай свой вопрос."
                # Отправляем приветственное сообщение с меню
                send_telegram_message(chat_id, greeting_message, reply_markup=menu_markup)
                logger.info(f"Отправлено приветственное сообщение с меню пользователю {chat_id}.")
                return JSONResponse(content={"status": "ok", "action": "start_message_sent"})

            # Обработка других сообщений (свободный диалог или кнопки меню)
            else:
                # Проверяем, не является ли сообщение одной из кнопок меню
                if text in MENU_OPTIONS:
                    # Если это кнопка меню, отправляем ее как запрос к GPTBots.
                    # Ты можешь изменить эту логику, если хочешь предопределенный ответ.
                    logger.info(f"Получена кнопка меню '{text}' от пользователя {user_id} (чат {chat_id}). Отправляем как запрос к GPTBots.")
                    # Отправляем сообщение пользователю, что обрабатываем запрос
                    send_telegram_message(chat_id, "Думаю...")
                    # Получаем ответ от GPTBots
                    reply = gptbots_generate(text, user_id)
                    # Отправляем ответ пользователю
                    send_telegram_message(chat_id, reply)
                    logger.info(f"Ответ от GPTBots отправлен пользователю {chat_id}.")
                    return JSONResponse(content={"status": "ok", "action": "gptbots_response_sent"})
                else:
                    # Если это обычный текст, обрабатываем как свободный диалог
                    logger.info(f"Получен запрос от пользователя {user_id} (чат {chat_id}): '{text[:50]}...'")
                    # Отправляем сообщение пользователю, что обрабатываем запрос
                    send_telegram_message(chat_id, "Думаю...")
                    # Получаем ответ от GPTBots
                    reply = gptbots_generate(text, user_id)
                    # Отправляем ответ пользователю
                    send_telegram_message(chat_id, reply)
                    logger.info(f"Ответ от GPTBots отправлен пользователю {chat_id}.")
                    return JSONResponse(content={"status": "ok", "action": "gptbots_response_sent"})

        elif "callback_query" in data:
            # Обработка нажатий на Inline кнопки (если они будут добавлены)
            logger.info("Получен Callback Query, но он не обрабатывается.")
            return JSONResponse(content={"status": "ignored", "reason": "callback_query not handled"})

        else:
            logger.warning("Получено сообщение, которое не является сообщением пользователя или командой.")
            return JSONResponse(content={"status": "ignored", "reason": "unhandled message type"})

    except Exception as e:
        logger.error(f"Ошибка в обработчике Webhook: {e}", exc_info=True) # Логируем стек вызовов
        return JSONResponse(content={"error": str(e)}, status_code=500)

# --- Корневой маршрут для проверки работоспособности ---
@app.get("/")
async def root():
    return {"message": "Бот работает!", "version": VERSION}

# --- Важно: Установка Webhook ---
# На Vercel автоматическая установка Webhook может быть ненадежной.
# Лучше всего установить его один раз вручную через Telegram BotFather или API.
# Пример команды для установки Webhook:
# curl -X POST "https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<YOUR_VERCEL_URL>/api/webhook"
# Замените <YOUR_TELEGRAM_BOT_TOKEN> и <YOUR_VERCEL_URL> на ваши реальные значения.
