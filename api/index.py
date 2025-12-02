import os
import json
import httpx
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализация приложения
app = FastAPI()

# Получение переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")

MENU_OPTIONS = ["Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

async def send_message(chat_id, text, reply_markup=None):
    """Отправка сообщения в Telegram"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Ошибка: Не задан TELEGRAM_BOT_TOKEN")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown", 
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=data, timeout=5.0)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")

async def gptbots_generate(text, user_id):
    """Запрос к GPTBots"""
    if not GPTBOTS_API_KEY: 
        return "❌ Ошибка: Не задан GPTBOTS_API_KEY"
    
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
        # Убрали verify=False для исправления ошибки [Errno 16]
        async with httpx.AsyncClient() as client:
            # Таймаут 20 сек. Если GPT думает дольше, Vercel может убить процесс (лимит 10с на Hobby тарифе)
            response = await client.post(endpoint, headers=headers, json=data, timeout=20.0)
            
            if response.status_code == 200:
                resp_json = response.json()
                logger.info(f"GPT Success: {resp_json}")
                return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Ответ пуст."
            else:
                logger.error(f"GPT Error Status {response.status_code}: {response.text}")
                return f"Произошла ошибка на сервере ИИ (код {response.status_code})."
                
    except httpx.TimeoutException:
        logger.error("GPT Timeout")
        return "ИИ думает слишком долго, попробуйте спросить проще."
    except Exception as e:
        logger.error(f"Exception GPT: {e}")
        return "Временная ошибка соединения с ИИ."

@app.post("/api/webhook")
async def webhook(request: Request):
    """Обработчик входящих сообщений от Telegram"""
    try:
        data = await request.json()
        
        # Проверяем, есть ли сообщение
        if "message" not in data:
            return JSONResponse(content={"status": "ignored"})
            
        chat_id = data["message"]["chat"]["id"]
        # Безопасное получение user_id и текста
        user_id = data["message"].get("from", {}).get("id", 0)
        text = data["message"].get("text", "")

        if not text:
            logger.info("Получено сообщение без текста (фото или стикер)")
            return JSONResponse(content={"status": "no_text"})

        logger.info(f"User: {user_id} | Text: {text}")

        # Обработка команды /start
        if text == "/start":
            await send_message(chat_id, "Привет! Я твой помощник. Задай вопрос или выбери тему в меню.", menu_markup)
        else:
            # Отправляем статус "печатает...", чтобы пользователь видел активность
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction", 
                        json={"chat_id": chat_id, "action": "typing"},
                        timeout=2.0
                    )
                except:
                    pass # Если не удалось отправить "печатает", не страшно

            # Запрос к GPT и ответ
            reply = await gptbots_generate(text, user_id)
            await send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Critical Webhook Error: {e}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.get("/")
async def root():
    """Проверка работоспособности"""
    return {"status": "Bot is running", "version": "1.0.1"}