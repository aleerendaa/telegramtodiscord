import os
from telethon import TelegramClient, events
import requests

# Inserisci qui direttamente i tuoi dati per evitare errori di lettura su Render
api_id = 30476464          # <-- Sostituisci con il tuo API_ID numerico (senza virgolette)
api_hash = "a649bf57ad8523670eb38c547cc8bea1"  # <-- Sostituisci con il tuo API_HASH tra virgolette
webhook_url = "https://discord.com/api/webhooks/1546517396116865194/UwM6WTilUEQRBwL6ZAbYm9VbUGKqM8utxO_Ta6-yxBDvW5Oi1h7SB8XbukfrQwj-LrF1" # <-- Sostituisci con l'URL del webhook
target_channel = "pokemonpreorder"

client = TelegramClient('session_string', api_id, api_hash)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    text = event.raw_text
    if text:
        requests.post(webhook_url, json={"content": text})

client.start()
client.run_until_disconnected()
