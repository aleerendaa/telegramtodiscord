import os
import sqlite3
import logging
from telethon import TelegramClient, events
import discord
from discord.ui import Button, View

# Configurazione logging
logging.basicConfig(level=logging.INFO)

# ================= CONFIGURAZIONE CREDENZIALI =================
API_ID = int(os.getenv("API_ID", "IL_TUO_API_ID"))
API_HASH = os.getenv("API_HASH", "IL_TUO_API_HASH")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "IL_TUO_DISCORD_TOKEN")

# ================= ID CANALI DISCORD UFFICIALI =================
CHANNEL_POKEMON = 1547376481477459988
CHANNEL_ONEPIECE = 1532111869832069242
CHANNEL_DRAGONBALL = 1532112469567471938
CHANNEL_ALTRO = 1532112759490351244
CHANNEL_ADMIN_LOGS = 1533540767396794479

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

# ================= CONFIGURAZIONE CLIENT TELEGRAM & DISCORD =================
client = TelegramClient('session_name', API_ID, API_HASH)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
discord_client = discord.Client(intents=intents)

# ================= FUNZIONE DI SMISTAMENTO INTELLIGENTE =================
def get_discord_channel_id(text):
    if not text:
        print("⚠️ [SMISTAMENTO] Testo vuoto -> Canale ALTRO", flush=True)
        return CHANNEL_ALTRO
    
    text_lower = text.lower()
    print(f"🔍 [SMISTAMENTO] Testo ricevuto: {text_lower}", flush=True)
    
    if "#pokemon" in text_lower:
        print("✅ [SMISTAMENTO] Trovato #pokemon -> ID POKEMON", flush=True)
        return CHANNEL_POKEMON
    elif "#onepiece" in text_lower:
        print("✅ [SMISTAMENTO] Trovato #onepiece -> ID ONE PIECE", flush=True)
        return CHANNEL_ONEPIECE
    elif "#dragonball" in text_lower:
        print("✅ [SMISTAMENTO] Trovato #dragonball -> ID DRAGON BALL", flush=True)
        return CHANNEL_DRAGONBALL
    else:
        print("⚠️ [SMISTAMENTO] Nessun hashtag corrispondente -> Canale ALTRO", flush=True)
        return CHANNEL_ALTRO

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
            print(f"💾 [DATABASE] Salvato claim da {username} ({user_id})", flush=True)
            
        except Exception as e:
            print(f"❌ [ERRORE DB] {e}", flush=True)
            await interaction.response.send_message(
                "❌ Si è verificato un errore durante la registrazione del claim.", ephemeral=True
            )

# ================= ASCOLTO MESSAGGI TELEGRAM =================
@client.on(events.NewMessage)
async def my_event_handler(event):
    message_text = event.raw_text
    print(f"\n--------------------------------------------------", flush=True)
    print(f"📩 [TELEGRAM] Messaggio ricevuto!", flush=True)
    
    target_channel_id = get_discord_channel_id(message_text)
    
    channel = discord_client.get_channel(target_channel_id)
    if not channel:
        try:
            channel = await discord_client.fetch_channel(target_channel_id)
        except Exception as e:
            print(f"❌ [ERRORE] Impossibile trovare il canale su Discord: {e}", flush=True)
            return

    print(f"🎯 [INVIO] Destinazione canale: #{channel.name} (ID: {target_channel_id})", flush=True)
    
    try:
        view = ClaimView(item_description=message_text[:100])
        await channel.send(content=message_text, view=view)
        print(f"✨ [SUCCESSO] Messaggio spedito correttamente!", flush=True)
    except Exception as e:
        print(f"❌ [ERRORE INVIO] {e}", flush=True)
    print(f"--------------------------------------------------", flush=True)

# ================= EVENTO AVVIO DISCORD =================
@discord_client.event
async def on_ready():
    print(f"🤖 Bot Discord connesso come {discord_client.user}", flush=True)

# ================= AVVIAMENTO SISTEMA =================
if __name__ == "__main__":
    import threading
    import asyncio
    
    def run_discord():
        discord_client.run(DISCORD_TOKEN)
        
    discord_thread = threading.Thread(target=run_discord)
    discord_thread.start()
    
    print("🚀 Userbot Telegram avviato e in ascolto...", flush=True)
    
    # Avvio sicuro di Telethon che non crasha su Render
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(client.start())
        client.run_until_disconnected()
    except Exception as e:
        print(f"❌ Errore critico Telegram: {e}", flush=True)
