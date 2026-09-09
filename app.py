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

# Funzione per pulire il testo rimuovendo claim, offerte e hashtag
def clean_message_text(text):
    if not text:
        return ""
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_str = line.strip()
        # Salta le righe indesiderate (claim, offerte, hashtag)
        if (
            "Per prenotare" in line_str or 
            "/claim" in line_str or 
            "Offerto da" in line_str or 
            line_str.startswith("#")
        ):
            continue
        cleaned_lines.append(line)
    
    # Rimette insieme il testo pulito eliminando spazi vuoti superflui
    result = "\n".join(cleaned_lines).strip()
    
    # Aggiunge la riga sotto per dividere i prodotti
    if result:
        result = f"{result}\n──────────────────────────────"
        
    return result

# Gestione Album (Post con più foto insieme)
@client.on(events.Album(chats=target_channel))
async def album_handler(event):
    text = ""
    for message in event.messages:
        if message.raw_text:
            text = message.raw_text
            break
    
    files = []
    for i, message in enumerate(event.messages):
        if message.photo:
            photo_bytes = await message.download_media(file=bytes)
            if photo_bytes:
                files.append((f'files[{i}]', (f'image_{i}.jpg', photo_bytes, 'image/jpeg')))
    
    if files:
        data = {}
        cleaned = clean_message_text(text)
        if cleaned:
            data['content'] = cleaned
        
        requests.post(webhook_url, data=data, files=files)
        await asyncio.sleep(1)

# Gestione Messaggi Singoli (Testo o una sola foto)
@client.on(events.NewMessage(chats=target_channel))
async def single_handler(event):
    if event.grouped_id:
        return
        
    text = event.raw_text or ""
    cleaned = clean_message_text(text)
    
    if event.photo:
        photo_bytes = await event.download_media(file=bytes)
        if photo_bytes:
            files = {'file': ('image.jpg', photo_bytes, 'image/jpeg')}
            data = {}
            if cleaned:
                data['content'] = cleaned
            requests.post(webhook_url, data=data, files=files)
    elif cleaned:
        requests.post(webhook_url, json={"content": cleaned})
        
    await asyncio.sleep(1)

print("Userbot avviato e in ascolto (testo pulito + immagini raggruppate)...")
client.start()
client.run_until_disconnected()
