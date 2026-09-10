import os
import threading
import asyncio
import re
import sqlite3
from datetime import datetime, time, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
import discord
from discord.ext import commands, tasks

# 1. Server web per Render
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

# 2. Configurazione Credenziali e ID Canali Discord
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
TELEGRAM_CHANNEL = "https://t.me/+tNa5JDiCTVQ1ZDk0"
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')

# ID Canali Discord ufficiali
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
            timestamp TEXT,
            status TEXT DEFAULT 'Ordinato'
        )
    ''')
    try:
        cursor.execute("ALTER TABLE ordini ADD COLUMN status TEXT DEFAULT 'Ordinato'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

init_db()

def save_order(user_id, username, product_name, price, quantity):
    conn = sqlite3.connect('ordini.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ordini (user_id, username, product_name, price, quantity, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Ordinato')
    ''', (str(user_id), str(username), product_name, price, int(quantity), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

# 3. Configurazione Bot Discord e View per Admin
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class AdminActionView(discord.ui.View):
    def __init__(self, order_id):
        super().__init__(timeout=None)
        self.order_id = order_id

    @discord.ui.button(label="💳 Segna come Pagato", style=discord.ButtonStyle.primary, custom_id="btn_pagato")
    async def segna_pagato(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect('ordini.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE ordini SET status = 'Pagato' WHERE id = ?", (self.order_id,))
        conn.commit()
        conn.close()
        
        button.label = "✅ Pagato"
        button.style = discord.ButtonStyle.success
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"💳 L'ordine **#{self.order_id}** è stato segnato come **PAGATO**.", ephemeral=True)

    @discord.ui.button(label="🚚 Segna come Consegnato", style=discord.ButtonStyle.secondary, custom_id="btn_consegnato")
    async def segna_consegnato(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect('ordini.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE ordini SET status = 'Consegnato' WHERE id = ?", (self.order_id,))
        conn.commit()
        conn.close()
        
        button.label = "📦 Consegnato"
        button.style = discord.ButtonStyle.success
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🚚 L'ordine **#{self.order_id}** è stato segnato come **CONSEGNATO**.", ephemeral=True)

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

        order_id = save_order(interaction.user.id, interaction.user.name, self.product_name, self.price, qty)

        await interaction.response.send_message(
            f"✅ **Ordine registrato con successo!** (ID: #{order_id})\n📦 Prodotto: {self.product_name}\n🔢 Quantità: {qty}\n💰 Prezzo unitario: {self.price}",
            ephemeral=True
        )

        admin_channel = bot.get_channel(CHANNEL_ADMIN_LOGS)
        if admin_channel:
            embed = discord.Embed(title=f"🛒 Nuovo Claim Ricevuto! (ID #{order_id})", color=discord.Color.gold())
            embed.add_field(name="Utente", value=f"{interaction.user.mention} ({interaction.user.name})", inline=False)
            embed.add_field(name="Prodotto", value=self.product_name, inline=False)
            embed.add_field(name="Quantità", value=str(qty), inline=True)
            embed.add_field(name="Prezzo Unitario", value=self.price, inline=True)
            embed.add_field(name="Stato Attuale", value="⏳ `Ordinato`", inline=False)
            embed.timestamp = datetime.now()
            
            view = AdminActionView(order_id)
            await admin_channel.send(embed=embed, view=view)

class ClaimView(discord.ui.View):
    def __init__(self, product_name, price):
        super().__init__(timeout=None)
        self.product_name = product_name
        self.price = price

    @discord.ui.button(label="🛒 CLAIM", style=discord.ButtonStyle.success, custom_id="claim_button")
    async def claim_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ClaimModal(self.product_name, self.price)
        await interaction.response.send_modal(modal)

# 4. Logica di Smistamento
def get_discord_channel_id(text):
    if not text:
        return CHANNEL_ALTRO
    
    if "#Pokemon" in text:
        return CHANNEL_POKEMON
    elif "#OnePiece" in text:
        return CHANNEL_ONEPIECE
    elif "#DragonBall" in text:
        return CHANNEL_DRAGONBALL
    elif "#Altro" in text:
        return CHANNEL_ALTRO
    else:
        text_lower = text.lower()
        if "#pokemon" in text_lower:
            return CHANNEL_POKEMON
        elif "#onepiece" in text_lower:
            return CHANNEL_ONEPIECE
        elif "#dragonball" in text_lower:
            return CHANNEL_DRAGONBALL
        else:
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

# Task Giornaliera per il Recap degli Ordini (Esegue ogni giorno alle ore 09:00 UTC)
@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def recap_giornaliero():
    admin_channel = bot.get_channel(CHANNEL_ADMIN_LOGS)
    if not admin_channel:
        return

    conn = sqlite3.connect('ordini.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, product_name, price, quantity, status, timestamp FROM ordini WHERE status != 'Consegnato' ORDER BY id DESC LIMIT 25")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        embed = discord.Embed(title="📊 Recap Giornaliero Ordini", description="Ottimo! Non ci sono ordini in sospeso (tutti consegnati).", color=discord.Color.green())
        await admin_channel.send(embed=embed)
        return

    embed = discord.Embed(title="📊 Recap Giornaliero Ordini in Sospeso", color=discord.Color.orange(), timestamp=datetime.now())
    for row in rows:
        oid, username, product, price, qty, status, timestamp = row
        status_icon = "⏳" if status == "Ordinato" else "💳"
        embed.add_field(
            name=f"ID #{oid} - {product} (x{qty})",
            value=f"👤 {username} | 💰 {price}\nStato: {status_icon} **{status}** | 🕒 {timestamp}",
            inline=False
        )
    await admin_channel.send(embed=embed)

# Comandi Admin Gestione Ordini
@bot.command(name="ordini")
@commands.has_permissions(administrator=True)
async def mostra_ordini(ctx, stato: str = None):
    conn = sqlite3.connect('ordini.db')
    cursor = conn.cursor()
    
    if stato:
        cursor.execute('SELECT id, username, product_name, price, quantity, timestamp, status FROM ordini WHERE status LIKE ? ORDER BY id DESC LIMIT 15', (f"%{stato}%",))
        title = f"📋 Ordini filtrati per: {stato.capitalize()}"
    else:
        cursor.execute('SELECT id, username, product_name, price, quantity, timestamp, status FROM ordini ORDER BY id DESC LIMIT 15')
        title = "📋 Ultimi 15 Ordini Totali"
        
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await ctx.send("📭 Nessun ordine trovato.")
        return

    embed = discord.Embed(title=title, color=discord.Color.blue())
    for row in rows:
        oid, username, product, price, qty, timestamp, current_status = row
        icon = "⏳" if current_status == "Ordinato" else ("💳" if current_status == "Pagato" else "🚚")
        embed.add_field(
            name=f"ID #{oid} - {product} (x{qty})",
            value=f"👤 **Utente:** {username}\n💰 **Prezzo:** {price}\n{icon} **Stato:** `{current_status}`\n🕒 {timestamp}",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="stato")
@commands.has_permissions(administrator=True)
async def cambia_stato(ctx, order_id: int, nuovo_stato: str):
    nuovo_stato_cap = nuovo_stato.capitalize()
    if nuovo_stato_cap not in ["Ordinato", "Pagato", "Consegnato"]:
        await ctx.send("❌ Stato non valido. Usa: `Ordinato`, `Pagato` o `Consegnato`.")
        return

    conn = sqlite3.connect('ordini.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE ordini SET status = ? WHERE id = ?", (nuovo_stato_cap, order_id))
    conn.commit()
    conn.close()

    await ctx.send(f"✅ L'ordine **#{order_id}** è stato aggiornato a: `{nuovo_stato_cap}`")

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

# 5. Avvio simultaneo
@bot.event
async def on_ready():
    print(f"Bot Discord connesso come {bot.user}", flush=True)
    if not recap_giornaliero.is_running():
        recap_giornaliero.start()
    await tg_client.start()
    print("Userbot Telegram avviato e in ascolto...", flush=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Errore: DISCORD_TOKEN non trovato nelle variabili d'ambiente!", flush=True)
    else:
        bot.run(DISCORD_TOKEN)
