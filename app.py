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
target_channel = "https://t.me/+tNa5JDiCTVQ1ZDk0"

# Mappa dei webhook in base agli hashtag
WEBHOOKS = {
    "pokemon": "https://discord.com/api/webhooks/1547376609642942486/Wy4CtOMOpOTmPO7Z5TjIZoEuYjV6UFSlzTaI6k35dc_ZZ1gEehVgkUwlqdKMZtTYbGNP",
    "onepiece": "https://discord.com/api/webhooks/1541457812733952110/ae90a97cwBxOqrKR1HvpL9uo8D3wYsQcFTdXPEv8M10Wasl0iCI1B8zTgI2nctg2ozW8",
    "dragonball": "https://discord.com/api/webhooks/1532483075303276675/5BKO9qohcH1cXu4KEMoUApMvd71QA6S4LxN2U7Acmt1AEVoV9fDLr0izQqMkXZu7Jh07",
    "altro": "https://discord.com/api/webhooks/1534305426706006047/RWumSsDuJ3nJ07ssqBJuMaq1rbu8yTVhs5J3QJDr7iGliNJxokXzVUPoxCtGXOB-eHnI"
}

# Usa il file di sessione che hai caricato
client = TelegramClient('bot_session', api_id, api_hash)

# Funzione per determinare il webhook giusto in base al testo/hashtag
def get_webhook_url(text):
    if not text:
        return WEBHOOKS["altro"]
    
    text_lower = text.lower()
    if "#pokemon" in text_lower:
        return WEBHOOKS["pokemon"]
    elif "#onepiece" in text_lower:
        return WEBHOOKS["onepiece"]
    elif "#dragonball" in text_lower:
        return WEBHOOKS["dragonball"]
    else:
        return WEBHOOKS["altro"]

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
            
        # Cerca e aggiorna il prezzo nella riga
        updated_line = re.sub(r'(\d+[\.,]\d{2})\s*€', apply_markup, line_str)
        cleaned_lines.append(updated_line)
    
    result = "\n".join(cleaned_lines).strip()
    
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
    
    # Sceglie il webhook in base al testo originale (prima che venga ripulito degli hashtag)
    current_webhook = get_webhook_url(text)
    
    files = []
    for i, message in enumerate(event.messages):
        if message.photo:
            photo_bytes = await message.download_media(file=bytes)
            if photo_bytes:
                files.append((f'files[{i}]', (f'image_{i}.jpg', photo_bytes, 'image/jpeg')))
    
    # 1. Invia prima le immagini al webhook corretto
    if files:
        requests.post(current_webhook, files=files)
        await asyncio.sleep(1.5) 
        
    # 2. Invia il testo pulito con prezzo ricaricato DOPO le immagini
    cleaned = clean_message_text(text)
    if cleaned:
        requests.post(current_webhook, json={"content": cleaned})
        await asyncio.sleep(1)

# Gestione Messaggi Singoli (Testo o una sola foto)
@client.on(events.NewMessage(chats=target_channel))
async def single_handler(event):
    if event.grouped_id:
        return
        
    text = event.raw_text or ""
    current_webhook = get_webhook_url(text)
    cleaned = clean_message_text(text)
    
    if event.photo:
        # 1. Invia prima la foto singola al webhook corretto
        photo_bytes = await message_bytes = await event.download_media(file=bytes) if hasattr(event, 'download_media') else await event.download_media(file=bytes)
        # Nota: usiamo download_media standard
        photo_bytes = await event.download_media(file=bytes)
        if photo_bytes:
            files = {'file': ('image.jpg', photo_bytes, 'image/jpeg')}
            requests.post(current_webhook, files=files)
            await asyncio.sleep(1.5)
            
        # 2. Invia il testo DOPO la foto
        if cleaned:
            requests.post(current_webhook, json={"content": cleaned})
            
    elif cleaned:
        # Se è solo testo
        requests.post(current_webhook, json={"content": cleaned})
        
    await asyncio.sleep(1)

print("Userbot avviato e in ascolto (smistamento webhook per categoria attivo)...")
client.start()
client.run_until_disconnected()
