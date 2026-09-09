import os
import threading
import asyncio
import re
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

# Funzione per calcolare il rincaro sul prezzo trovato nel testo
def apply_markup(match):
    price_str = match.group(1).replace(',', '.')
    try:
        price = float(price_str)
        
        # Tabella dei rincari
        if 1 <= price < 15:
            price += 3
        elif 15 <= price < 50:
            price += 5
        elif 50 <= price < 150:
            price += 10
        elif 150 <= price < 300:
            price += 20
        elif price >= 300:
            price += 30
            
        # Restituisce il nuovo prezzo formattato con la virgola (stile italiano)
        return f"{price:.2f}".replace('.', ',') + " €"
    except ValueError:
        return match.group(0)

# Funzione per pulire il testo, applicare il rincaro e formattare
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
            
        # Cerca e aggiorna il prezzo nella riga (es. "22,00 €" diventerà "27,00 €" ecc.)
        updated_line = re.sub(r'(\d+[\.,]\d{2})\s*€', apply_markup, line_str)
        cleaned_lines.append(updated_line)
    
    # Unisce il testo pulito
    result = "\n".join(cleaned_lines).strip()
    
    # Aggiunge la riga divisoria alla fine del prodotto
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
    
    # 1. Invia prima le immagini come album
    if files:
        requests.post(webhook_url, files=files)
        await asyncio.sleep(1.5) 
        
    # 2. Invia il testo pulito con prezzo ricaricato DOPO le immagini
    cleaned = clean_message_text(text)
    if cleaned:
        requests.post(webhook_url, json={"content": cleaned})
        await asyncio.sleep(1)

# Gestione Messaggi Singoli (Testo o una sola foto)
@client.on(events.NewMessage(chats=target_channel))
async def single_handler(event):
    if event.grouped_id:
        return
        
    text = event.raw_text or ""
    cleaned = clean_message_text(text)
    
    if event.photo:
        # 1. Invia prima la foto singola
        photo_bytes = await event.download_media(file=bytes)
        if photo_bytes:
            files = {'file': ('image.jpg', photo_bytes, 'image/jpeg')}
            requests.post(webhook_url, files=files)
            await asyncio.sleep(1.5)
            
        # 2. Invia il testo DOPO la foto
        if cleaned:
            requests.post(webhook_url, json={"content": cleaned})
            
    elif cleaned:
        # Se è solo testo
        requests.post(webhook_url, json={"content": cleaned})
        
    await asyncio.sleep(1)

print("Userbot avviato e in ascolto (immagini prime + rincaro prezzi attivo)...")
client.start()
client.run_until_disconnected()
