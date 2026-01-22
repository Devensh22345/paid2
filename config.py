
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
    
    # Logging level
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Webhook settings (for production)
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    PORT = int(os.getenv("PORT", 8443))
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        
        if cls.OWNER_ID == 0:
            errors.append("OWNER_ID is required and must be a number")
        
        return errors
