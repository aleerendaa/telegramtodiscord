import os
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
import requests

# 1. Piccolo server web finto per mantenere felice Render
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web, daemon=True).start()

# 2. Configurazione Telegram
api_id = int(os.environ.get('API_ID', 0))
api_hash = os.environ.get('API_HASH', '')
webhook_url = os.environ.get('WEBHOOK_URL', '')
target_channel = "pokemonpreorder"

# Usa il file di sessione che hai caricato
client = TelegramClient('bot_session', api_id, api_hash)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    text = event.raw_text
    if text:
        requests.post(webhook_url, json={"content": text})
        # Pausa di 1 secondo per evitare il blocco di Discord in caso di messaggi multipli
        await asyncio.sleep(1)

print("Userbot avviato e in ascolto sul canale...")
client.start()
client.run_until_disconnected()
