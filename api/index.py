import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

# Отключаем предупреждения SSL
import urllib3
urllib3.disable_warnings()

logging.basicConfig(level=logging.INFO)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPTBOTS_API_KEY = os.getenv("GPTBOTS_API_KEY")
GPTBOTS_AGENT_ID = os.getenv("GPTBOTS_AGENT_ID")

MENU_OPTIONS = ["Компьютер", "Смартфон", "Интернет", "Программы", "FAQ", "О боте"]

def generate_menu_keyboard():
    keyboard = [MENU_OPTIONS[i:i+2] for i in range(0, len(MENU_OPTIONS), 2)]
    return {"keyboard": keyboard, "resize_keyboard": True}

menu_markup = generate_menu_keyboard()

async def send_message(chat_id, text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", 
            **({"reply_markup": json.dumps(reply_markup)} if reply_markup else {})}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=data, timeout=5.0)

async def gptbots_generate(text, user_id):
    if not GPTBOTS_API_KEY: return "❌ Ошибка: Нет GPTBOTS_API_KEY"
    
    endpoint = "https://openapi.gptbots.ai/v1/chat"
    
    # Вернулись к X-API-Key (это чаще работает для GPTBots)
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
        async with httpx.AsyncClient(verify=False) as client:
            # Таймаут 15 сек
            response = await client.post(endpoint, headers=headers, json=data, timeout=15.0)
            
            if response.status_code == 200:
                resp_json = response.json()
                return resp_json.get('data', {}).get('reply') or resp_json.get('message') or "Пустой ответ"
            else: