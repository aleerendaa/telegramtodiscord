import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
import requests

# 1. Piccolo server web finto per soddisfare Render
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

# Avvia il server web in un "thread" separato
threading.Thread(target=run_web, daemon=True).start()

# 2. Il tuo codice Telegram originale
api_id = int(os.environ.get('API_ID', 0))
api_hash = os.environ.get('API_HASH', '')
bot_token = os.environ.get('BOT_TOKEN', '')
webhook_url = os.environ.get('WEBHOOK_URL', '')
target_channel = "pokemonpreorder"

client = TelegramClient('bot_session', api_id, api_hash).start(bot_token=bot_token)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    text = event.raw_text
    if text:
        requests.post(webhook_url, json={"content": text})

print("Bot avviato e in ascolto...")
client.run_until_disconnected()
