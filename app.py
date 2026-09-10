import os
import sqlite3
import logging
import asyncio
from telethon import TelegramClient, events
import discord
from discord.ui import Button, View

# Configurazione logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ================= CONFIGURAZIONE CREDENZIALI =================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# ================= ID CANALI DISCORD UFFICIALI (HARDCODED) =================
CHANNEL_IDS = {
    "pokemon": 1547376481477459988,
    "onepiece": 1532111869832069242,
    "dragonball": 1532112469567471938,
    "altro": 1532112759490351244,
    "admin_logs": 1533540767396794479
}

# ================= INIZIALIZZAZIONE DATABASE SQLITE =================
def init_db():
    conn = sqlite3.connect("ordini.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            username TEXT,
            item_text TEXT,
            quantity INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ================= SETUP CLIENTS =================
# Telethon Userbot (usa la sessione salvata senza chiedere input)
client = TelegramClient('session_name', API_ID, API_HASH)

# Discord Client
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
discord_client = discord.Client(intents=intents)

# ================= INTERFACCIA CLAIM DISCORD =================
class ClaimView(View):
    def __init__(self, item_description):
        super().__init__(timeout=None)
        self.item_description = item_description

    @discord.ui.button(label="CLAIM", style=discord.ButtonStyle.green, custom_id="claim_button")
    async def claim_callback(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        username = interaction.user.name
        
        try:
            conn = sqlite3.connect("ordini.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO claims (user_id, username, item_text, quantity) VALUES (?, ?, ?, ?)",
                (user_id, username, self.item_description, 1)
            )
            conn.commit()
            conn.close()
            
            await interaction.response.send_message(
                f"✅ Claim registrato con successo per {interaction.user.mention}!", ephemeral=True
            )
            logging.info(f"💾 [DATABASE] Salvato claim da {username} ({user_id})")
        except Exception as e:
            logging.error(f"❌ [ERRORE DB] {e}")
            await interaction.response.send_message(
                "❌ Si è verificato un errore durante la registrazione del claim.", ephemeral=True
            )

# ================= LOGICA DI SMISTAMENTO =================
def get_target_channel_id(text):
    if not text:
        return CHANNEL_IDS["altro"]
    
    text_lower = text.lower()
    
    if "#pokemon" in text_lower:
        return CHANNEL_IDS["pokemon"]
    elif "#onepiece" in text_lower:
        return CHANNEL_IDS["onepiece"]
    elif "#dragonball" in text_lower:
        return CHANNEL_IDS["dragonball"]
    else:
        return CHANNEL_IDS["altro"]

# ================= EVENTO RICEZIONE TELEGRAM =================
@client.on(events.NewMessage)
async def handle_telegram_message(event):
    message_text = event.raw_text
    logging.info(f"📩 [TELEGRAM] Messaggio intercettato: {message_text[:50]}...")
    
    # 1. Determina l'ID di destinazione
    target_id = get_target_channel_id(message_text)
    
    # 2. Recupera il canale da Discord
    channel = discord_client.get_channel(target_id)
    if not channel:
        try:
            channel = await discord_client.fetch_channel(target_id)
        except Exception as e:
            logging.error(f"❌ [DISCORD] Impossibile trovare il canale ID {target_id}: {e}")
            return
            
    # 3. Invia il messaggio con il bottone Claim
    try:
        view = ClaimView(item_description=message_text[:100])
        await channel.send(content=message_text, view=view)
        logging.info(f"✨ [DISCORD] Inoltrato con successo nel canale: #{channel.name} (ID: {target_id})")
    except Exception as e:
        logging.error(f"❌ [DISCORD] Errore di invio: {e}")

# ================= EVENTO PRONTEZZA DISCORD =================
@discord_client.event
async def on_ready():
    logging.info(f"🤖 Bot Discord connesso come {discord_client.user}")

# ================= MAIN ASINCRONO UNIFICATO =================
async def main():
    # Avvia Discord client in background
    await discord_client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    # Avvia Telethon e Discord in modo sicuro
    loop = asyncio.get_event_loop()
    
    # Connetti Telethon senza bloccare con l'input
    client.connect()
    if not client.is_user_authorized():
        logging.error("❌ [TELEGRAM] Userbot non autorizzato! Controlla la sessione.")
    else:
        logging.info("🚀 [TELEGRAM] Userbot connesso e pronto!")

    # Esegui i client in parallelo nel loop
    try:
        loop.run_until_complete(asyncio.gather(
            discord_client.start(DISCORD_TOKEN),
            client.run_until_disconnected()
        ))
    except KeyboardInterrupt:
        logging.info("🛑 Arresto del sistema in corso...")
    finally:
        loop.close()
