import os
import re
import sqlite3
from telethon import TelegramClient, events
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

# Configurazioni da variabili d'ambiente o dirette
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "IL_TUO_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "IL_TUO_API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING", "LA_TUA_SESSION_STRING")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "IL_TUO_DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "ID_CANALE_DISCORD"))

from telethon.sessions import StringSession
tg_client = TelegramClient(StringSession(SESSION_STRING), TELEGRAM_API_ID, TELEGRAM_API_HASH)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Database setup
def init_db():
    conn = sqlite3.connect('preorders.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS preorders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            price REAL,
            markup_price REAL,
            hashtag TEXT,
            claimed_by TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def is_valid_product_message(text):
    if not text:
        return False
    has_hashtag = bool(re.search(r'#\w+', text))
    has_price = bool(re.search(r'\d+([.,]\d{2})?\s*€', text))
    return has_hashtag and has_price

def calculate_markup(price):
    # Esempio di markup del 10%
    return round(price * 1.10, 2)

class ClaimView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id

    @discord.ui.button(label="Claim Prodotto", style=discord.ButtonStyle.green, custom_id="claim_button")
    async def claim_callback(self, interaction: discord.Interaction, button: Button):
        user_name = interaction.user.name
        conn = sqlite3.connect('preorders.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE preorders SET claimed_by = ? WHERE id = ?", (user_name, self.product_id))
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(f"Prodotto reclamato con successo da {user_name}!", ephemeral=True)

@tg_client.on(events.NewMessage)
async def handle_telegram_message(event):
    chat = await event.get_chat()
    chat_id = event.chat_id
    text = event.raw_text
    
    print(f"DEBUG - Messaggio ricevuto da chat ID: {chat_id} | Testo: {text}", flush=True)

    if is_valid_product_message(text):
        # Estrai prezzo base
        price_match = re.search(r'(\d+([.,]\d{2})?)\s*€', text.replace(',', '.'))
        base_price = float(price_match.group(1)) if price_match else 0.0
        markup_price = calculate_markup(base_price)
        
        hashtag_match = re.search(r'#\w+', text)
        hashtag = hashtag_match.group(0) if hashtag_match else "#generico"

        # Salva su DB
        conn = sqlite3.connect('preorders.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO preorders (product_name, price, markup_price, hashtag) VALUES (?, ?, ?, ?)",
                       (text, base_price, markup_price, hashtag))
        product_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Invia su Discord
        discord_channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if discord_channel:
            embed = discord.Embed(title="Nuovo Preorder Disponibile!", description=text, color=discord.Color.blue())
            embed.add_field(name="Prezzo Originale", value=f"{base_price:.2f} €", inline=True)
            embed.add_field(name="Prezzo con Markup", value=f"{markup_price:.2f} €", inline=True)
            embed.add_field(name="Hashtag", value=hashtag, inline=False)
            
            view = ClaimView(product_id)
            await discord_channel.send(embed=embed, view=view)

@bot.event
async def on_ready():
    print(f"Bot Discord avviato come {bot.user}", flush=True)
    
    # Avvia Telethon se non è già connesso
    if not tg_client.is_connected():
        await tg_client.start()
        print("Client Telethon avviato con successo!", flush=True)
        
        # Stampa l'ID corretto di tutti i canali/gruppi per trovare quello giusto
        async for dialog in tg_client.iter_dialogs():
            print(f"Chat trovata -> Nome: {dialog.name} | ID: {dialog.id}", flush=True)

# Avvio combinato
async def main():
    await tg_client.connect()
    # Esegui il client Discord e Telethon insieme
    await discord.BasesClient.start(bot, DISCORD_TOKEN) if hasattr(discord, 'BasesClient') else await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.start(DISCORD_TOKEN))
    except KeyboardInterrupt:
        loop.run_until_complete(tg_client.disconnect())
        loop.run_until_complete(bot.close())
