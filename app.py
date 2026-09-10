import os
import threading
import asyncio
import re
import sqlite3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
import requests
import discord
from discord.ext import commands

# 1. Server web finto per mantenere felice Render
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

# 2. Configurazione Credenziali e ID Canali Discord (ordinati correttamente)
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
TELEGRAM_CHANNEL = "https://t.me/+tNa5JDiCTVQ1ZDk0"

DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
CHANNEL_ADMIN_LOGS = 1547376481477459988
CHANNEL_POKEMON = 1532111869832069242
CHANNEL_ONEPIECE = 1532112469567471938
CHANNEL_DRAGONBALL = 1532112759490351244
CHANNEL_ALTRO = 1533540767396794479

# Inizializzazione Database SQLite locale
def init_db():
    conn = sqlite3.connect('ordini.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordini (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            username TEXT,
            product_name TEXT,
            price TEXT,
            quantity INTEGER,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Funzione per salvare l'ordine nel database
def save_order(user_id, username, product_name, price, quantity):
    conn = sqlite3.connect('ordini.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ordini (user_id, username, product_name, price, quantity, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(user_id), str(username), product_name, price, int(quantity), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# 3. Configurazione Bot Discord con Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Modale per inserire la quantità quando si clicca "Claim"
class ClaimModal(discord.ui.Modal, title="Conferma Preordine"):
    quantita = discord.ui.TextInput(
        label="Quantità desiderata",
        placeholder="Es. 1, 2, 3...",
        min_length=1,
        max_length=3,
        required=True
    )

    def __init__(self, product_name, price):
        super().__init__()
        self.product_name = product_name
        self.price = price

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantita.value)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Inserisci un numero valido maggiore di 0.", ephemeral=True)
            return

        # Salva nel database SQLite
        save_order(interaction.user.id, interaction.user.name, self.product_name, self.price, qty)

        # Risposta privata all'utente
        await interaction.response.send_message(
            f"✅ **Ordine registrato con successo!**\n📦 Prodotto: {self.product_name}\n🔢 Quantità: {qty}\n💰 Prezzo unitario: {self.price}",
            ephemeral=True
        )

        # Invia notifica nel canale admin
        admin_channel = bot.get_channel(CHANNEL_ADMIN_LOGS)
        if admin_channel:
            embed = discord.Embed(title="🛒 Nuovo Claim Ricevuto!", color=discord.Color.green())
            embed.add_field(name="Utente", value=f"{interaction.user.mention} ({interaction.user.name})", inline=False)
            embed.add_field(name="Prodotto", value=self.product_name, inline=False)
            embed.add_field(name="Quantità", value=str(qty), inline=True)
            embed.add_field(name="Prezzo Unitario", value=self.price, inline=True)
            embed.timestamp = datetime.now()
            await admin_channel.send(embed=embed)

# View con il pulsante Claim
class ClaimView(discord.ui.View):
    def __init__(self, product_name, price):
        super().__init__(timeout=None) # Il pulsante non scade mai
        self.product_name = product_name
        self.price = price

    @discord.ui.button(label="🛒 CLAIM", style=discord.ButtonStyle.success, custom_id="claim_button")
    async def claim_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ClaimModal(self.product_name, self.price)
        await interaction.response.send_modal(modal)

# 4. Logica Telegram & Smistamento Rigido
def get_discord_channel_id(text):
    if not text:
        print("⚠️ [SMISTAMENTO] Testo vuoto o assente -> Assegnato a ALTRO")
        return CHANNEL_ALTRO
    
    text_lower = text.lower()
    print(f"🔍 [SMISTAMENTO] Testo ricevuto da Telegram: {text_lower}")
    
    if "#pokemon" in text_lower:
        print("✅ [SMISTAMENTO] Rilevato #pokemon -> Canale POKEMON")
        return CHANNEL_POKEMON
    elif "#onepiece" in text_lower:
        print("✅ [SMISTAMENTO] Rilevato #onepiece -> Canale ONE PIECE")
        return CHANNEL_ONEPIECE
    elif "#dragonball" in text_lower:
        print("✅ [SMISTAMENTO] Rilevato #dragonball -> Canale DRAGON BALL")
        return CHANNEL_DRAGONBALL
    else:
        print("⚠️ [SMISTAMENTO] Nessun hashtag valido trovato -> Canale ALTRO")
        return CHANNEL_ALTRO

def apply_markup(match):
    price_str = match.group(1).replace(',', '.')
    try:
        price = float(price_str)
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

def clean_message_text(text):
    if not text:
        return "", "", ""
    
    lines = text.split('\n')
    cleaned_lines = []
    product_title = "Prodotto Preorder"
    product_price = "N/D"
    
    for i, line in enumerate(lines):
        line_str = line.strip()
        if (
            "Per prenotare" in line_str or 
            "/claim" in line_str or 
            "Offerto da" in line_str or 
            line_str.startswith("#")
        ):
            continue
            
        if i == 0 and line_str:
            product_title = line_str

        updated_line = re.sub(r'(\d+[\.,]\d{2})\s*€', apply_markup, line_str)
        if "€" in updated_line and product_price == "N/D":
            product_price = updated_line

        cleaned_lines.append(updated_line)
    
    result = "\n".join(cleaned_lines).strip()
    if result:
        result = f"{result}\n──────────────────────────────"
        
    return result, product_title, product_price

# Avvio del client Telegram
tg_client = TelegramClient('bot_session', API_ID, API_HASH)

@tg_client.on(events.Album(chats=TELEGRAM_CHANNEL))
async def album_handler(event):
    text = ""
    for message in event.messages:
        if message.raw_text:
            text = message.raw_text
            break
    
    target_channel_id = get_discord_channel_id(text)
    channel = bot.get_channel(target_channel_id)
    if not channel:
        return

    discord_files = []
    for i, message in enumerate(event.messages):
        if message.photo:
            path = await message.download_media(file=f'temp_img_{i}.jpg')
            if path:
                discord_files.append(discord.File(path))
    
    cleaned, title, price = clean_message_text(text)

    if discord_files:
        await channel.send(files=discord_files)
        await asyncio.sleep(1.5)
        for f in discord_files:
            try:
                os.remove(f.fp.name)
            except:
                pass
        
    if cleaned:
        view = ClaimView(title, price)
        await channel.send(content=cleaned, view=view)

@tg_client.on(events.NewMessage(chats=TELEGRAM_CHANNEL))
async def single_handler(event):
    if event.grouped_id:
        return
        
    text = event.raw_text or ""
    target_channel_id = get_discord_channel_id(text)
    channel = bot.get_channel(target_channel_id)
    if not channel:
        return

    cleaned, title, price = clean_message_text(text)
    
    if event.photo:
        path = await event.download_media(file='temp_single.jpg')
        if path:
            file = discord.File(path)
            await channel.send(file=file)
            await asyncio.sleep(1.5)
            try:
                os.remove(path)
            except:
                pass
            
        if cleaned:
            view = ClaimView(title, price)
            await channel.send(content=cleaned, view=view)
    elif cleaned:
        view = ClaimView(title, price)
        await channel.send(content=cleaned, view=view)

# 5. Avvio simultaneo di Telegram e Discord
@bot.event
async def on_ready():
    print(f"Bot Discord connesso come {bot.user}")
    await tg_client.start()
    print("Userbot Telegram avviato e in ascolto...")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Errore: DISCORD_TOKEN non trovato nelle variabili d'ambiente!")
    else:
        bot.run(DISCORD_TOKEN)
