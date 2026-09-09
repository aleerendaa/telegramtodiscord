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
    
    # Controlla se il messaggio contiene una foto/media
    if event.photo:
        # Scarica l'immagine in memoria dal messaggio di Telegram
        photo_bytes = await event.download_media(file=bytes)
        
        if photo_bytes:
            # Invia l'immagine e l'eventuale testo a Discord tramite file multipart
            files = {
                'file': ('image.jpg', photo_bytes, 'image/jpeg')
            }
            data = {
                'content': text
            }
            requests.post(webhook_url, data=data, files=files)
    elif text:
        # Se è solo testo senza immagini
        requests.post(webhook_url, json={"content": text})

    # Pausa di 1 secondo per evitare blocchi (Rate Limit) di Discord
    await asyncio.sleep(1)

print("Userbot avviato e in ascolto (con supporto immagini)...")
client.start()
client.run_until_disconnected()
