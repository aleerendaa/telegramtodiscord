import os
import threading
import asyncio
import re
import random
import uuid
import sqlite3
from datetime import datetime, time, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import discord
from discord.ext import commands, tasks

# Gestione Database (Supporta sia SQLite locale che PostgreSQL esterno come Supabase)
DATABASE_URL = os.environ.get('DATABASE_URL')
is_postgres = bool(DATABASE_URL)

if is_postgres:
    import psycopg2
    import io

# Dizionario globale per tracciare l'ultima versione attiva di ciascun prodotto
active_product_versions = {}

# Set per evitare la duplicazione dei messaggi appartenenti agli album (grouped_id)
processed_grouped_ids = set()

# Lock per sequenziare l'invio dei messaggi Telegram ed evitare sovrapposizioni su Discord
processing_lock = asyncio.Lock()

# Fuso orario italiano (UTC+2 / CEST)
ITALY_TZ = timezone(timedelta(hours=2))

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
SESSION_STRING = os.environ.get('SESSION_STRING', '')
TELEGRAM_CHANNEL = -1003944376038
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')

CHANNEL_ADMIN_LOGS = 1533540767396794479
CHANNEL_ORDINI = 1558069027329540156
CHANNEL_POKEMON = 1557072021215776768
CHANNEL_ONEPIECE = 1532111869832069242
CHANNEL_DRAGONBALL = 1532112469567471938
CHANNEL_PREORDER = 1532029845481984260
CHANNEL_ALTRO = 1532112759490351244

def get_db_connection():
    if is_postgres:
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect('ordini.db')

def init_db():
    if is_postgres:
        return
     
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordini (
            id TEXT PRIMARY KEY,
            cliente TEXT,
            prodotto TEXT,
            quantita INTEGER,
            prezzo_unitario NUMERIC,
            stato TEXT DEFAULT 'in_arrivo',
            messaggio TEXT,
            created_at TIMESTAMPTZ,
            "Acquisto" TEXT DEFAULT 'Discord'
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def trova_o_genera_codice_cliente(input_cliente):
    conn = get_db_connection()
    cursor = conn.cursor()
     
    input_pulito = input_cliente.strip()
     
    if re.match(r'^CLI-\d+$', input_pulito, re.IGNORECASE):
        cursor.execute("SELECT cliente FROM ordini WHERE cliente ILIKE %s LIMIT 1" if is_postgres else "SELECT cliente FROM ordini WHERE cliente LIKE ? LIMIT 1", (input_pulito,))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        if res:
            return res[0].upper()
        return input_pulito.upper()

    if is_postgres:
        cursor.execute("SELECT cliente FROM ordini WHERE messaggio ILIKE %s OR cliente ILIKE %s LIMIT 1", (f"[user:{input_pulito}]", input_pulito))
    else:
        cursor.execute("SELECT cliente FROM ordini WHERE messaggio LIKE ? OR cliente LIKE ? LIMIT 1", (f"[user:{input_pulito}]", input_pulito))
     
    row = cursor.fetchone()
    if row and row[0]:
        codice_esistente = row[0]
        cursor.close()
        conn.close()
        return codice_esistente

    while True:
        nuovo_codice = f"CLI-{random.randint(1000, 9999)}"
        if is_postgres:
            cursor.execute("SELECT 1 FROM ordini WHERE cliente = %s LIMIT 1", (nuovo_codice,))
        else:
            cursor.execute("SELECT 1 FROM ordini WHERE cliente = ? LIMIT 1", (nuovo_codice,))
        if not cursor.fetchone():
            break

    cursor.close()
    conn.close()
    return nuovo_codice

def save_order(input_cliente, product_name, price, quantity, initial_status='in_arrivo'):
    conn = get_db_connection()
    cursor = conn.cursor()
     
    codice_cliente = trova_o_genera_codice_cliente(input_cliente)
     
    try:
        numeric_price = float(str(price).replace('€', '').strip().replace(',', '.'))
    except ValueError:
        numeric_price = 0.0

    timestamp = datetime.now(timezone.utc).isoformat()
    messaggio_str = f"[user:{input_cliente.strip()}]"
    
    if is_postgres:
        cursor.execute('''
            INSERT INTO ordini (cliente, prodotto, quantita, prezzo_unitario, stato, messaggio, created_at, "Acquisto")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (codice_cliente, product_name, int(quantity), numeric_price, initial_status, messaggio_str, timestamp, 'Discord'))
        order_id = cursor.fetchone()[0]
    else:
        order_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO ordini (id, cliente, prodotto, quantita, prezzo_unitario, stato, messaggio, created_at, "Acquisto")
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, codice_cliente, product_name, int(quantity), numeric_price, initial_status, messaggio_str, timestamp, 'Discord'))
         
    conn.commit()
    cursor.close()
    conn.close()
    return order_id, codice_cliente

async def invia_recap_giornaliero_logic(target_channel):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if is_postgres:
            cursor.execute('''
                SELECT id, cliente, prodotto, quantita, prezzo_unitario, stato, messaggio, created_at 
                FROM ordini 
                WHERE created_at >= NOW() - INTERVAL '24 hours' 
                  AND ("Acquisto"::text ILIKE 'discord' OR "Acquisto" IS NULL)
                ORDER BY created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT id, cliente, prodotto, quantita, prezzo_unitario, stato, messaggio, created_at 
                FROM ordini 
                WHERE datetime(created_at) >= datetime('now', '-1 day') 
                  AND (LOWER("Acquisto") = 'discord' OR "Acquisto" IS NULL)
                ORDER BY created_at DESC
            ''')
            
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            embed = discord.Embed(
                title="📊 Recap Giornaliero Ordini Discord", 
                description="Nessun nuovo ordine ricevuto da Discord nelle ultime 24 ore.", 
                color=discord.Color.green()
            )
            await target_channel.send(embed=embed)
            return

        embed = discord.Embed(
            title="📊 Recap Giornaliero Ordini Discord (Ultime 24h)", 
            color=discord.Color.orange(), 
            timestamp=datetime.now()
        )
        for row in rows:
            oid, cliente, prodotto, quantita, prezzo_unitario, stato, messaggio, created_at = row
            status_icon = "⏳" if stato == "in_arrivo" else ("💳" if stato == "pagato" else "🚚")
            embed.add_field(
                name=f"{prodotto} (x{quantita})",
                value=f"👤 Cliente: {cliente} | 💰 Unitario: {prezzo_unitario} €\nStato: {status_icon} **{stato}** | 🕒 {created_at}",
                inline=False
            )
        await target_channel.send(embed=embed)
    except Exception as e:
        print(f"Errore generazione recap: {e}", flush=True)
        await target_channel.send(f"❌ Si è verificato un errore durante la generazione del recap: {e}")

@tasks.loop(time=time(hour=0, minute=0, tzinfo=timezone.utc))
async def recap_giornaliero():
    admin_channel = bot.get_channel(CHANNEL_ORDINI)
    if not admin_channel:
        return
    await invia_recap_giornaliero_logic(admin_channel)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class OrderApprovalView(discord.ui.View):
    def __init__(self, discord_user=None, nome_inserito="", codice_cliente="", product_name="", qty=1, price="0", total_str=""):
        super().__init__(timeout=None)
        self.discord_user = discord_user
        self.nome_inserito = nome_inserito
        self.codice_cliente = codice_cliente
        self.product_name = product_name
        self.qty = qty
        self.price = price
        self.total_str = total_str

    @discord.ui.button(label="Conferma Pagamento", style=discord.ButtonStyle.success, emoji="✅", custom_id="order_confirm_payment")
    async def confirm_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if not self.nome_inserito and interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                for field in embed.fields:
                    if field.name == "Cliente / Codice":
                        self.nome_inserito = field.value.split(" (`")[0]
                    elif field.name == "Prodotto":
                        self.product_name = field.value
                    elif field.name == "Quantità":
                        self.qty = int(field.value)
                    elif field.name == "Prezzo Unitario":
                        self.price = field.value

            order_id, _ = save_order(self.nome_inserito, self.product_name, self.price, self.qty, initial_status='pagato')
            
            for child in self.children:
                child.disabled = True
                
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_field_at(index=6, name="Stato Attuale", value="💳 `pagato` (Confermato)", inline=False)
            
            await interaction.message.edit(embed=embed, view=self)
            await interaction.followup.send(f"✅ Pagamento confermato e ordine salvato nel database per {self.nome_inserito}.", ephemeral=True)
        except Exception as e:
            print(f"Errore conferma pagamento: {e}", flush=True)
            await interaction.followup.send(f"❌ Errore nella conferma del pagamento: {e}", ephemeral=True)

    @discord.ui.button(label="Annulla Ordine", style=discord.ButtonStyle.danger, emoji="❌", custom_id="order_cancel_order")
    async def cancel_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            for child in self.children:
                child.disabled = True
                
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.set_field_at(index=6, name="Stato Attuale", value="❌ `annullato` (Non disponibile / Scaduto)", inline=False)
            
            await interaction.message.edit(embed=embed, view=self)
            await interaction.followup.send("❌ Ordine annullato con successo.", ephemeral=True)
        except Exception as e:
            print(f"Errore annullamento ordine: {e}", flush=True)
            await interaction.followup.send(f"❌ Errore durante l'annullamento: {e}", ephemeral=True)

class ClaimView(discord.ui.View):
    def __init__(self, product_name="", price="", start_time=None, end_time=None, post_token=None):
        super().__init__(timeout=None)
        self.product_name = product_name
        self.price = price
        self.start_time = start_time
        self.end_time = end_time
        self.post_token = post_token

    @discord.ui.button(label="🛒 CLAIM", style=discord.ButtonStyle.success, custom_id="claim_button_persistent")
    async def claim_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.post_token and active_product_versions.get(self.product_name) != self.post_token:
            await interaction.response.send_message("❌ Questo annuncio è stato aggiornato o ripostato con nuovi dettagli! Usa il pulsante nel messaggio più recente.", ephemeral=True)
            return

        now = datetime.now(ITALY_TZ)
        
        if self.start_time and now < self.start_time:
            await interaction.response.send_message(f"⏳ I preordini per questo prodotto non sono ancora aperti!\nInizio previsto: {self.start_time.strftime('%d/%m/%Y alle %H:%M')}", ephemeral=True)
            return
            
        if self.end_time and now > self.end_time:
            await interaction.response.send_message(f"❌ I claim per questo prodotto sono chiusi, scadenza {self.end_time.strftime('%d/%m/%Y alle %H:%M')}, richiedi questo prodotto in <#1531772977073356881> e se disponibile sarà postato", ephemeral=True)
            return

        modal = ClaimModal(self.product_name, self.price)
        await interaction.response.send_modal(modal)

class ClaimModal(discord.ui.Modal, title="Conferma Preordine"):
    cliente_input = discord.ui.TextInput(
        label="Nome e Cognome o Codice Cliente",
        placeholder="Es. Mario Rossi oppure CLI-1719",
        min_length=2,
        max_length=50,
        required=True
    )
     
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
        await interaction.response.defer(ephemeral=True)
        try:
            try:
                qty = int(self.quantita.value)
                if qty <= 0:
                    raise ValueError()
            except ValueError:
                await interaction.followup.send("❌ Inserisci una quantità valida maggiore di 0.", ephemeral=True)
                return

            nome_inserito = self.cliente_input.value.strip()

            try:
                numeric_price = float(str(self.price).replace('€', '').strip().replace(',', '.'))
                total_price = numeric_price * qty
                total_str = f"{total_price:.2f}".replace('.', ',') + " €"
            except ValueError:
                total_str = "N/D"

            codice_cliente = trova_o_genera_codice_cliente(nome_inserito)

            await interaction.followup.send(
                f"✅ **Ordine registrato con successo!**\n\n"
                f"👤 **Cliente:** {nome_inserito} (Codice: `{codice_cliente}`)\n"
                f"📦 **Prodotto:** {self.product_name}\n"
                f"🔢 **Quantità:** {qty}\n"
                f"💰 **Prezzo unitario:** {self.price}\n"
                f"💵 **Totale da pagare:** {total_str}\n\n"
                f"💳 **Metodi di pagamento:**\n"
                f"• **PayPal:** `@aleerendaa`",
                ephemeral=True
            )

            ordini_channel = bot.get_channel(CHANNEL_ORDINI)
            if ordini_channel:
                embed = discord.Embed(title=f"🛒 Nuovo Claim Ricevuto!", color=discord.Color.orange())
                embed.add_field(name="Discord User", value=f"{interaction.user.mention} ({interaction.user.name})", inline=False)
                embed.add_field(name="Cliente / Codice", value=f"{nome_inserito} (`{codice_cliente}`)", inline=False)
                embed.add_field(name="Prodotto", value=self.product_name, inline=False)
                embed.add_field(name="Quantità", value=str(qty), inline=True)
                embed.add_field(name="Prezzo Unitario", value=self.price, inline=True)
                embed.add_field(name="Totale", value=total_str, inline=True)
                embed.add_field(name="Stato Attuale", value="⏳ `Da pagare`", inline=False)
                embed.timestamp = datetime.now()
                 
                approval_view = OrderApprovalView(interaction.user, nome_inserito, codice_cliente, self.product_name, qty, self.price, total_str)
                await ordini_channel.send(embed=embed, view=approval_view)

        except Exception as e:
            print(f"ERRORE CRITICO durante il claim: {e}", flush=True)
            try:
                await interaction.followup.send(f"❌ Si è verificato un errore interno durante la registrazione dell'ordine.", ephemeral=True)
            except:
                pass

class ModaleCreaProdottoStandard(discord.ui.Modal, title="Crea Nuovo Prodotto"):
    titolo = discord.ui.TextInput(
        label="Nome Prodotto", 
        placeholder="Es. 30th Celebration Booster Box", 
        required=True
    )
    descrizione = discord.ui.TextInput(
        label="Descrizione e Prezzo", 
        placeholder="Es. Sealed / Box da 30 Buste\n205,00 € • 15 disponibili", 
        style=discord.TextStyle.paragraph, 
        required=True
    )
    hashtag = discord.ui.TextInput(
        label="Canale (#pokemon #onepiece #dragonball)", 
        placeholder="Es. #pokemon", 
        required=True
    )
    date_validita = discord.ui.TextInput(
        label="Periodo Validità", 
        placeholder="dal 10/10/2026, 12:00 fino al 15/10/2026, 23:00", 
        required=True
    )
    foto_url = discord.ui.TextInput(
        label="Link Foto Prodotto (Opzionale)", 
        placeholder="Es. https://i.imgur.com/immagine.jpg (Opzionale)", 
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            full_text = (
                f"{self.titolo.value.strip()}\n\n"
                f"{self.descrizione.value.strip()}\n\n"
                f"Ordinazioni aperte {self.date_validita.value.strip()}\n\n"
                f"{self.hashtag.value.strip()}"
            )
            
            target_channel_id = get_discord_channel_id(full_text)
            channel = bot.get_channel(target_channel_id)
            
            if not channel:
                await interaction.followup.send("❌ Canale Discord di destinazione non trovato per l'hashtag inserito.", ephemeral=True)
                return

            cleaned, title, price_formatted = clean_message_text(full_text)
            start_dt, end_dt = extract_dates(full_text)
            
            post_token = str(uuid.uuid4())
            active_product_versions[title] = post_token
            
            view = ClaimView(title, price_formatted, start_dt, end_dt, post_token)
            
            url_immagine = self.foto_url.value.strip() if self.foto_url.value else None
            if url_immagine and (url_immagine.startswith("http://") or url_immagine.startswith("https://")):
                await channel.send(content=url_immagine)
                await asyncio.sleep(0.5)

            if cleaned:
                await channel.send(content=cleaned, view=view)
                await interaction.followup.send(f"✅ Prodotto creato e pubblicato con successo in <#{target_channel_id}>!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Errore nella formattazione del testo del prodotto.", ephemeral=True)
        except Exception as e:
            print(f"Errore creazione prodotto: {e}", flush=True)
            await interaction.followup.send(f"❌ Si è verificato un errore durante la pubblicazione: {e}", ephemeral=True)

class OrdiniAdminMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Crea Nuovo Prodotto", style=discord.ButtonStyle.success, custom_id="menu_crea_prodotto")
    async def crea_prodotto_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ModaleCreaProdottoStandard()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📊 Genera Recap Ora", style=discord.ButtonStyle.primary, emoji="🕒", custom_id="menu_genera_recap")
    async def manual_recap_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await invia_recap_giornaliero_logic(interaction.channel)
        await interaction.followup.send("✅ Recap generato con successo!", ephemeral=True)

@bot.command(name="menu")
@commands.has_permissions(administrator=True)
async def menu_ordini(ctx):
    embed = discord.Embed(
        title="⚙️ Pannello Gestione Ordini & Preorder", 
        description="Utilizza i pulsanti sottostanti per creare un nuovo annuncio/prodotto oppure per generare manualmente il riepilogo degli ordini Discord delle ultime 24 ore.", 
        color=discord.Color.blue()
    )
    view = OrdiniAdminMenuView()
    await ctx.send(embed=embed, view=view)

def get_discord_channel_id(text):
    if not text:
        return CHANNEL_ALTRO
     
    text_lower = text.lower()
    
    # 1. Controlla prima se ci sono hashtag espliciti
    if "#pokemon" in text_lower:
        return CHANNEL_POKEMON
    elif "#onepiece" in text_lower or "#one-piece" in text_lower:
        return CHANNEL_ONEPIECE
    elif "#dragonball" in text_lower or "#dragon-ball" in text_lower:
        return CHANNEL_DRAGONBALL
    elif "#preorder" in text_lower or "#pre-order" in text_lower:
        return CHANNEL_PREORDER

    # 2. Riconoscimento intelligente tramite parole chiave specifiche per Brand:
    
    # ONE PIECE
    parole_onepiece = [
        "one piece", "onepiece", "op-", "op0", "eb-", "luffy", "zoro", "nami", 
        "shanks", "law", "kid", "romance dawn", "paramount", "pillars", "flame", 
        "500 years", "wings of captain", "extra booster", "flagship", "card game"
    ]
    if any(p in text_lower for p in parole_onepiece):
        return CHANNEL_ONEPIECE

    # DRAGON BALL
    parole_dragonball = [
        "dragon ball", "dragonball", "dbs", "dbz", "fusion world", "awakened", 
        "goku", "vegeta", "gohan", "piccolo", "frieza", "broly", "saiyan"
    ]
    if any(p in text_lower for p in parole_dragonball):
        return CHANNEL_DRAGONBALL

    # POKÉMON
    parole_pokemon = [
        "pokemon", "pokémon", "booster box", "booster", "pikachu", "charizard", 
        "eevee", "mew", "cinese", "giapponese", "sv", "s8a", "promo", "pack"
    ]
    if any(p in text_lower for p in parole_pokemon):
        return CHANNEL_POKEMON

    # Se non trova corrispondenze specifiche ma è un preordine generale
    if "preorder" in text_lower or "pre-order" in text_lower or "prenotare" in text_lower:
        return CHANNEL_PREORDER

    return CHANNEL_ALTRO

def is_valid_product_message(text):
    if not text:
        return False
    
    text_lower = text.lower()
    
    # 1. Verifica che ci sia un'indicazione di prezzo (cerca il simbolo € seguito o preceduto da cifre)
    ha_prezzo = bool(re.search(r'€\s*\d+', text) or re.search(r'\d+\s*€', text))
    
    # 2. Verifica che contenga parole chiave tipiche di un prodotto/preorder
    parole_chiave_prodotto = [
        "booster", "box", "sealed", "preorder", "pre-order", "disponibili", 
        "pokemon", "pokémon", "one piece", "dragon ball", "cinese", "giapponese"
    ]
    ha_parole_chiave = any(p in text_lower for p in parole_chiave_prodotto)
    
    return ha_prezzo and ha_parole_chiave

def extract_dates(text):
    # Cerca date del tipo "dal 21/10/2026 al 23/10/2026" oppure con orari "dal 21/10/2026, 12:00 fino al 23/10/2026, 23:00"
    match = re.search(
        r'dal\s+(\d{2}/\d{2}/\d{4})(?:,\s*(\d{2}:\d{2}))?\s+(?:fino\s+)?al\s+(\d{2}/\d{2}/\d{4})(?:,\s*(\d{2}:\d{2}))?', 
        text, 
        re.IGNORECASE
    )
    
    start_dt, end_dt = None, None
    if match:
        try:
            d_start, t_start, d_end, t_end = match.groups()
            
            # Se l'orario manca, imposta 00:00 per l'inizio e 23:59 per la fine del giorno
            t_start = t_start if t_start else "00:00"
            t_end = t_end if t_end else "23:59"
            
            start_dt = datetime.strptime(f"{d_start}, {t_start}", '%d/%m/%Y, %H:%M').replace(tzinfo=ITALY_TZ)
            end_dt = datetime.strptime(f"{d_end}, {t_end}", '%d/%m/%Y, %H:%M').replace(tzinfo=ITALY_TZ)
        except ValueError as e:
            print(f"Errore parsing date: {e}", flush=True)
            
    return start_dt, end_dt

def clean_message_text(text):
    if not text:
        return "", "", ""
     
    lines = text.split('\n')
    cleaned_lines = []
    product_title = "Prodotto Preorder"
    product_price = "N/D"
     
    for i, line in enumerate(lines):
        line_str = re.sub(r'#\w+', '', line)
        line_str = re.sub(r'🇯🇵', '', line_str).strip()
         
        if line.strip() == "🇯🇵" or line.strip() == "#giapponese":
            continue
         
        if not line_str:
            cleaned_lines.append("")
            continue
             
        if (
            "Per prenotare" in line_str or 
            "/claim" in line_str or 
            "Offerto da" in line_str or
            "Come prenotare" in line_str or
            "Rispondi a questo post" in line_str or
            "Esempio: /claim" in line_str or
            "Preorder inviato da" in line_str
        ):
            continue
             
        if i == 0 and line_str:
            product_title = line_str

        def replace_price(match):
            nonlocal product_price
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
                 
                formatted_price = f"{price:.2f}".replace('.', ',') + " €"
                if product_price == "N/D":
                    product_price = formatted_price
                return formatted_price
            except ValueError:
                return match.group(0)

        updated_line = re.sub(r'(\d+([.,]\d{2})?)\s*€', replace_price, line_str)
        updated_line = re.sub(r'€\s*(\d+([.,]\d{2})?)', replace_price, updated_line)
        cleaned_lines.append(updated_line)
     
    result = "\n".join(cleaned_lines).strip()
    if result:
        result = f"{result}\n──────────────────────────────"
         
    return result, product_title, product_price

# Avvio dello Userbot Telegram con gestione sequenziale
tg_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@tg_client.on(events.NewMessage)
async def debug_all_messages(event):
    if event.chat_id != TELEGRAM_CHANNEL:
        return

    # Utilizziamo un lock per elaborare ciascun post/album uno alla volta
    async with processing_lock:
        text = event.raw_text or ""
        
        # Gestione Album Telegram (grouped_id)
        if event.grouped_id:
            if event.grouped_id in processed_grouped_ids:
                return
            processed_grouped_ids.add(event.grouped_id)
            
            album_messages = await tg_client.get_messages(event.chat_id, ids=list(range(event.id - 10, event.id + 10)))
            group_msgs = [m for m in album_messages if m and m.grouped_id == event.grouped_id]
            
            main_text = ""
            for m in group_msgs:
                if m.raw_text and is_valid_product_message(m.raw_text):
                    main_text = m.raw_text
                    break
            
            if not main_text:
                return

            target_channel_id = get_discord_channel_id(main_text)
            channel = bot.get_channel(target_channel_id)
            if not channel:
                return

            cleaned, title, price = clean_message_text(main_text)
            start_dt, end_dt = extract_dates(main_text)
            post_token = str(uuid.uuid4())
            active_product_versions[title] = post_token
            view = ClaimView(title, price, start_dt, end_dt, post_token)

            for m in group_msgs:
                if m.photo:
                    file_path = f"temp_{m.id}.jpg"
                    path = await m.download_media(file=file_path)
                    if path:
                        await channel.send(file=discord.File(path))
                        await asyncio.sleep(1.0)
                        if os.path.exists(path):
                            os.remove(path)

            if cleaned:
                await channel.send(content=cleaned, view=view)
                await asyncio.sleep(1.5)

        else:
            # Gestione messaggio singolo normale
            if is_valid_product_message(text):
                target_channel_id = get_discord_channel_id(text)
                channel = bot.get_channel(target_channel_id)
                if channel:
                    cleaned, title, price = clean_message_text(text)
                    start_dt, end_dt = extract_dates(text)
                    
                    post_token = str(uuid.uuid4())
                    active_product_versions[title] = post_token
                    
                    view = ClaimView(title, price, start_dt, end_dt, post_token)
                     
                    if event.photo:
                        file_path = f"temp_{event.id}.jpg"
                        path = await event.download_media(file=file_path)
                        if path:
                            await channel.send(file=discord.File(path))
                            await asyncio.sleep(1.0)
                            if os.path.exists(path):
                                os.remove(path)
                      
                    if cleaned:
                        await channel.send(content=cleaned, view=view)
                        await asyncio.sleep(1.5)

@bot.event
async def on_ready():
    print(f"Bot Discord connesso come {bot.user}", flush=True)
    
    bot.add_view(OrdiniAdminMenuView())
    bot.add_view(OrderApprovalView())
    bot.add_view(ClaimView())
    
    if not recap_giornaliero.is_running():
        recap_giornaliero.start()
        
    if not tg_client.is_connected():
        try:
            await tg_client.start()
            print("Userbot Telegram avviato e in ascolto...", flush=True)
        except Exception as e:
            print(f"Errore nell'avvio dello userbot Telegram: {e}", flush=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Errore: DISCORD_TOKEN non trovato nelle variabili d'ambiente!", flush=True)
    else:
        bot.run(DISCORD_TOKEN)
