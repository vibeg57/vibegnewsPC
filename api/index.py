import os
import json
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", 
            **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})}
    try:
        requests.post(url, json=data, timeout=5)
    except: pass

def gptbots_generate(text, user_id):
    # 1. Проверка наличия ключей
    if not GPTBOTS_API_KEY: return "❌ Ошибка: В Vercel не добавлен GPTBOTS_API_KEY"
    if not GPTBOTS_AGENT_ID: return "❌ Ошибка: В Vercel не добавлен GPTBOTS_AGENT_ID"
    
    endpoint = "https://openapi.gptbots.ai/v1/chat"
    headers = {"X-API-Key": GPTBOTS_API_KEY.strip(), "Content-Type": "application/json"}
    data = {
        "agent_id": GPTBOTS_AGENT_ID.strip(),
        "user_id": str(user_id),
        "query": text,
        "stream": False
    }
    
    try:
        # Уменьшил таймаут до 9 секунд, так как Vercel убивает процесс на 10-й секунде
        resp = requests.post(endpoint, headers=headers, json=data, timeout=9)
        
        if resp.status_code == 200:
            return resp.json().get('data', {}).get('reply') or "GPT прислал пустой ответ"
        else:
            # Возвращаем код ошибки и текст от сервера GPT
            return f"⚠️ Ошибка API {resp.status_code}: {resp.text[:100]}"
            
    except requests.exceptions.Timeout:
        return "⏱ GPT думал дольше 9 секунд (Таймаут Vercel)."
    except Exception as e:
        # ВОТ ЭТО САМОЕ ВАЖНОЕ: Бот пришлет саму ошибку
        return f"🔥 CRITICAL ERROR: {str(e)}"

@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            
            if not text: return JSONResponse(content={"status": "ignored"})

            if text == "/start":
                send_message(chat_id, "Режим отладки. Напиши любой вопрос.", menu_markup)
            else:
                send_message(chat_id, "Думаю...")
                reply = gptbots_generate(text, msg.get("from", {}).get("id"))
                send_message(chat_id, reply)

        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)