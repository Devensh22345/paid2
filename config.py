import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot Token
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8446660054:AAEZbyTPJtZbe7XdIMJJc5w8Pk2Har0P5QE")
    
    # MongoDB Configuration
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://6:6@cluster0.ne91zzc.mongodb.net/?appName=Cluster0")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "telegram_bot_db")
    
    # Bot Owner ID (for initial setup)
    OWNER_ID = int(os.getenv("OWNER_ID", "6872968794"))
    
    # Timezone for scheduling
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    
    # Maximum channels that can be added
    MAX_CHANNELS = 100
