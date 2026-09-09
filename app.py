import os
from telethon import TelegramClient, events
import requests

# Prende i dati dalle variabili d'ambiente del pannello
api_id = int(os.environ.get('30476464', 0))
api_hash = os.environ.get('a649bf57ad8523670eb38c547cc8bea1', '')
webhook_url = os.environ.get('https://discord.com/api/webhooks/1546517396116865194/UwM6WTilUEQRBwL6ZAbYm9VbUGKqM8utxO_Ta6-yxBDvW5Oi1h7SB8XbukfrQwj-LrF1', '')
target_channel = 'pokemonpreorder'

client = TelegramClient('session_string', api_id, api_hash)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    text = event.raw_text
    if text:
        requests.post(webhook_url, json={"content": text})

client.start()
client.run_until_disconnected()