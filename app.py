import os
from telethon import TelegramClient, events
import requests

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

client.run_until_disconnected()
