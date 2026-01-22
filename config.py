import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot Token
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # MongoDB Configuration
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "telegram_bot_db")
    
    # Bot Owner ID (for initial setup)
    OWNER_ID = int(os.getenv("OWNER_ID", 0))
    
    # Timezone for scheduling
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    
    # Maximum channels that can be added
    MAX_CHANNELS = 100
