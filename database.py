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
            self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
            self.db = self.client[Config.DATABASE_NAME]
            self.channels = self.db["channels"]
            self.sudo_users = self.db["sudo_users"]
            self.scheduled_posts = self.db["scheduled_posts"]
            
            # Create indexes
            self.channels.create_index("channel_id", unique=True)
            self.sudo_users.create_index("user_id", unique=True)
            self.scheduled_posts.create_index("scheduled_time")
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("✅ Database connection established successfully")
            
        except ConnectionFailure as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
            raise

    # Channel Management
    def add_channel(self, channel_id, channel_title, added_by):
        try:
            channel_data = {
                "channel_id": str(channel_id),
                "channel_title": str(channel_title),
                "added_by": added_by,
                "added_date": datetime.utcnow(),
                "active": True
            }
            result = self.channels.insert_one(channel_data)
            logger.info(f"Channel added: {channel_title} ({channel_id})")
            return result
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            return None

    def get_all_channels(self):
        try:
            return list(self.channels.find({"active": True}).sort("added_date", -1))
        except Exception as e:
            logger.error(f"Error getting channels: {e}")
            return []

    def get_channel_count(self):
        try:
            return self.channels.count_documents({"active": True})
        except Exception as e:
            logger.error(f"Error counting channels: {e}")
            return 0

    def remove_channel(self, channel_id):
        try:
            result = self.channels.delete_one({"channel_id": str(channel_id)})
            logger.info(f"Channel removed: {channel_id}")
            return result
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            return None

    def get_channel_by_id(self, channel_id):
        try:
            return self.channels.find_one({"channel_id": str(channel_id)})
        except Exception as e:
            logger.error(f"Error getting channel: {e}")
            return None

    # Sudo Users Management
    def add_sudo_user(self, user_id, username, added_by):
        try:
            sudo_data = {
                "user_id": user_id,
                "username": str(username),
                "added_by": added_by,
                "added_date": datetime.utcnow()
            }
            result = self.sudo_users.insert_one(sudo_data)
            logger.info(f"Sudo user added: {username} ({user_id})")
            return result
        except Exception as e:
            logger.error(f"Error adding sudo user: {e}")
            return None

    def remove_sudo_user(self, user_id):
        try:
            result = self.sudo_users.delete_one({"user_id": user_id})
            logger.info(f"Sudo user removed: {user_id}")
            return result
        except Exception as e:
            logger.error(f"Error removing sudo user: {e}")
            return None

    def get_all_sudo_users(self):
        try:
            return list(self.sudo_users.find().sort("added_date", -1))
        except Exception as e:
            logger.error(f"Error getting sudo users: {e}")
            return []

    def is_sudo_user(self, user_id):
        try:
            return self.sudo_users.find_one({"user_id": user_id}) is not None
        except Exception as e:
            logger.error(f"Error checking sudo user: {e}")
            return False

    # Scheduled Posts Management
    def add_scheduled_post(self, post_data):
        try:
            result = self.scheduled_posts.insert_one(post_data)
            logger.info(f"Scheduled post added: {post_data.get('channel_title')}")
            return result
        except Exception as e:
            logger.error(f"Error adding scheduled post: {e}")
            return None

    def get_scheduled_posts(self, limit=100):
        try:
            return list(self.scheduled_posts.find({"sent": False})
                       .sort("scheduled_time", 1)
                       .limit(limit))
        except Exception as e:
            logger.error(f"Error getting scheduled posts: {e}")
            return []

    def mark_post_as_sent(self, post_id):
        try:
            return self.scheduled_posts.update_one(
                {"_id": post_id},
                {"$set": {"sent": True, "sent_date": datetime.utcnow()}}
            )
        except Exception as e:
            logger.error(f"Error marking post as sent: {e}")
            return None

    def delete_scheduled_post(self, post_id):
        try:
            return self.scheduled_posts.delete_one({"_id": post_id})
        except Exception as e:
            logger.error(f
