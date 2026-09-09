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
target_channel = "https://t.me/+tNa5JDiCTVQ1ZDk0"

# Usa il file di sessione che hai caricato
client = TelegramClient('bot_session', api_id, api_hash)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    text = event.raw_text or ""
    
    # 1. Se c'è una foto, la scarichiamo e la inviamo per PRIMA
    if event.photo:
        photo_bytes = await event.download_media(file=bytes)
        if photo_bytes:
            files = {'file': ('image.jpg', photo_bytes, 'image/jpeg')}
            requests.post(webhook_url, files=files)
            # Breve pausa per garantire che l'immagine arrivi prima del testo
            await asyncio.sleep(0.5)
            
    # 2. Se c'è del testo, lo formattiamo in modo pulito e strutturato
    if text:
        formatted_text = (
            f"📦 **NUOVO PREORDINE DISPONIBILE**\n"
            f"──────────────────────────────\n"
            f"{text}\n"
            f"──────────────────────────────"
        )
        requests.post(webhook_url, json={"content": formatted_text})

    # Pausa finale per evitare il blocco (Rate Limit) di Discord
    await asyncio.sleep(1)

print("Userbot avviato e in ascolto (immagini prima + struttura pulita)...")
client.start()
client.run_until_disconnected()
