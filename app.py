from telethon import TelegramClient, events
import requests

# Inserisci i tuoi dati presi da my.telegram.org
api_id = 30476464          # <-- Il tuo API_ID numerico
api_hash = "a649bf57ad8523670eb38c547cc8bea1"  # <-- Il tuo API_HASH

# Inserisci il Token del bot preso da @BotFather su Telegram
bot_token = "8579978474:AAHyJH68Jdah1CHn8XIL9M1Uzk2t76-X3ok" 

webhook_url = "https://discord.com/api/webhooks/1546517396116865194/UwM6WTilUEQRBwL6ZAbYm9VbUGKqM8utxO_Ta6-yxBDvW5Oi1h7SB8XbukfrQwj-LrF1"
target_channel = "pokemonpreorder"

# Avvia il client come Bot (nessuna richiesta di login interattiva!)
client = TelegramClient('bot_session', api_id, api_hash).start(bot_token=bot_token)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    text = event.raw_text
    if text:
        requests.post(webhook_url, json={"content": text})

print("Bot avviato e in ascolto...")
client.run_until_disconnected()
