import os
import json
import requests
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Включаем логирование на полную
logging.basicConfig(level=logging.INFO)
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

def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # ⚠️ УБРАЛИ parse_mode="Markdown", чтобы сообщение точно дошло!
    data = {
        "chat_id": chat_id, 
        "text": text, 
        **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})
    }
    
    try:
        r = requests.post(url, json=data, timeout=5)
        # Если ошибка отправки - пишем в лог Vercel
        if r.status_code != 200:
            logger.error(f"TG Send Error: {r.text}")
    except Exception as e:
        logger.error(f"TG Connection Error: {e}")

def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY: return "❌ Ошибка: Нет ключа API"
    
    endpoint = "https://api.gptbots.ai/v1/chat"
    
    headers = {
        "Authorization": f"Bearer {GPTBOTS_API_KEY.strip()}",
        "Content-Type": "application/json"
    }
    
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "stream": False
    }
    
    try:
        logger.info(f"Sending to GPT: {data}") # Пишем в лог, что отправляем
        resp = requests.post(endpoint, headers=headers, json=data, timeout=9)
        logger.info(f"GPT Response Code: {resp.status_code}") # Пишем код ответа
        logger.info(f"GPT Body: {resp.text}") # Пишем тело ответа
        
        if resp.status_code == 200:
            raw_json = resp.json()
            # Пытаемся достать ответ разными способами
            reply = raw_json.get('data', {}).get('reply')
            if not reply:
                reply = raw_json.get('message')
            
            if reply:
                return reply
            else:
                # Если ответа нет, возвращаем ВЕСЬ JSON
                return f"🔍 ОТЛАДКА: {json.dumps(raw_json, ensure_ascii=False)}"
        else:
            return f"Ошибка GPT {resp.status_code}: {resp.text}"
            
    except Exception as e:
        logger.error(f"Global Error: {e}")
        return f"Критическая ошибка: {str(e)}"

@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")
            user_id = data["message"].get("from", {}).get("id")

            if not text: return JSONResponse(content={"status": "ignored"})

            if text == "/start":
                send_message(chat_id, "Режим полной отладки.", menu_markup)
            else:
                send_message(chat_id, "Думаю...")
                reply = gptbots_generate(text, user_id)
                send_message(chat_id, reply) # Теперь это сообщение точно дойдет

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook Fatal: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)