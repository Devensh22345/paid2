from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from config import Config
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        try:
            self.client = MongoClient(Config.MONGO_URI)
            self.db = self.client[Config.DATABASE_NAME]
            self.channels = self.db["channels"]
            self.sudo_users = self.db["sudo_users"]
            self.scheduled_posts = self.db["scheduled_posts"]
            logger.info("Database connection established")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    # Channel Management
    def add_channel(self, channel_id, channel_title, added_by):
        channel_data = {
            "channel_id": channel_id,
            "channel_title": channel_title,
            "added_by": added_by,
            "added_date": datetime.utcnow(),
            "active": True
        }
        return self.channels.insert_one(channel_data)

    def get_all_channels(self):
        return list(self.channels.find({"active": True}))

    def get_channel_count(self):
        return self.channels.count_documents({"active": True})

    def remove_channel(self, channel_id):
        return self.channels.delete_one({"channel_id": channel_id})

    def get_channel_by_id(self, channel_id):
        return self.channels.find_one({"channel_id": channel_id})

    # Sudo Users Management
    def add_sudo_user(self, user_id, username, added_by):
        sudo_data = {
            "user_id": user_id,
            "username": username,
            "added_by": added_by,
            "added_date": datetime.utcnow()
        }
        return self.sudo_users.insert_one(sudo_data)

    def remove_sudo_user(self, user_id):
        return self.sudo_users.delete_one({"user_id": user_id})

    def get_all_sudo_users(self):
        return list(self.sudo_users.find())

    def is_sudo_user(self, user_id):
        return self.sudo_users.find_one({"user_id": user_id}) is not None

    # Scheduled Posts Management
    def add_scheduled_post(self, post_data):
        return self.scheduled_posts.insert_one(post_data)

    def get_scheduled_posts(self):
        return list(self.scheduled_posts.find({"sent": False}))

    def mark_post_as_sent(self, post_id):
        return self.scheduled_posts.update_one(
            {"_id": post_id},
            {"$set": {"sent": True, "sent_date": datetime.utcnow()}}
        )

db = Database()
