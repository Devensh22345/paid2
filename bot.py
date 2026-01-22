import logging
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    BotCommand,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from config import Config
from database import db
from datetime import datetime, timedelta
import asyncio
from typing import Dict, List, Tuple
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_CHANNEL_ID, WAITING_FOR_POSTS, WAITING_FOR_SCHEDULE = range(3)

class TelegramBot:
    def __init__(self):
        self.application = Application.builder().token(Config.BOT_TOKEN).build()
        self.user_data: Dict[int, Dict] = {}
        self.setup_handlers()

    def setup_handlers(self):
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("add", self.add_channel))
        self.application.add_handler(CommandHandler("list", self.list_channels))
        self.application.add_handler(CommandHandler("addsudo", self.add_sudo))
        self.application.add_handler(CommandHandler("removesudo", self.remove_sudo))
        self.application.add_handler(CommandHandler("sudo", self.list_sudo))
        self.application.add_handler(CommandHandler("post", self.post_command))
        
        # Callback query handlers
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Conversation handler for posting
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("post", self.post_command)],
            states={
                WAITING_FOR_POSTS: [
                    MessageHandler(filters.ALL & ~filters.COMMAND, self.receive_posts)
                ],
                WAITING_FOR_SCHEDULE: [
                    CallbackQueryHandler(self.handle_schedule_choice)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
        )
        self.application.add_handler(conv_handler)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        welcome_text = (
            f"👋 Welcome {user.first_name}!\n\n"
            "📋 **Available Commands:**\n"
            "/add - Add a post channel\n"
            "/list - List all channels\n"
            "/addsudo - Add sudo user\n"
            "/removesudo - Remove sudo user\n"
            "/sudo - List sudo users\n"
            "/post - Start posting to channels\n\n"
            "Bot developed for channel management"
        )
        await update.message.reply_text(welcome_text)

    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add command to add channels"""
        user_id = update.effective_user.id
        
        # Check if user is sudo or owner
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ Please provide channel ID!\n"
                "Usage: /add <channel_id>\n"
                "Example: /add -1001234567890"
            )
            return

        channel_id = context.args[0]
        
        # Validate channel ID format
        if not re.match(r"^-100\d+$", channel_id):
            await update.message.reply_text(
                "❌ Invalid channel ID format!\n"
                "Channel ID should start with -100 followed by numbers.\n"
                "Example: -1001234567890"
            )
            return

        try:
            # Check if bot is admin in channel
            bot = context.bot
            chat_member = await bot.get_chat_member(channel_id, bot.id)
            
            if chat_member.status not in ["administrator", "creator"]:
                await update.message.reply_text("❌ Bot is not admin in this channel!")
                return
            
            # Get channel info
            chat = await bot.get_chat(channel_id)
            channel_title = chat.title
            
            # Check if channel already exists
            if db.get_channel_by_id(channel_id):
                await update.message.reply_text("⚠️ This channel is already added!")
                return
            
            # Add to database
            db.add_channel(channel_id, channel_title, user_id)
            
            await update.message.reply_text(
                f"✅ Channel added successfully!\n"
                f"📢 Channel: {channel_title}\n"
                f"🆔 ID: {channel_id}"
            )
            
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await update.message.reply_text("❌ Failed to add channel. Make sure:\n"
                                           "1. Bot is admin in the channel\n"
                                           "2. Channel ID is correct\n"
                                           "3. Bot has proper permissions")

    async def list_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list command to show all channels"""
        user_id = update.effective_user.id
        
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return

        channels = db.get_all_channels()
        
        if not channels:
            await update.message.reply_text("📭 No channels added yet!")
            return

        keyboard = []
        for channel in channels:
            button = InlineKeyboardButton(
                f"❌ {channel['channel_title']}",
                callback_data=f"remove_{channel['channel_id']}"
            )
            keyboard.append([button])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"📋 **Total Channels: {len(channels)}**\n"
            "Click on any channel to remove it:",
            reply_markup=reply_markup
        )

    async def add_sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsudo command"""
        user_id = update.effective_user.id
        
        # Only owner can add sudo users
        if user_id != Config.OWNER_ID:
            await update.message.reply_text("❌ Only bot owner can add sudo users!")
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ Please provide user ID or username!\n"
                "Usage: /addsudo <user_id or @username>"
            )
            return

        target = context.args[0]
        
        try:
            # Try to get user info
            if target.startswith("@"):
                # Get user by username (requires user to have started the bot)
                # This is simplified - in production you might need a different approach
                target_user_id = int(target.replace("@", ""))
            else:
                target_user_id = int(target)
            
            # Check if already sudo
            if db.is_sudo_user(target_user_id):
                await update.message.reply_text("⚠️ User is already a sudo user!")
                return
            
            # Add to database
            db.add_sudo_user(target_user_id, target, user_id)
            await update.message.reply_text(f"✅ User {target} added as sudo!")
            
        except Exception as e:
            logger.error(f"Error adding sudo: {e}")
            await update.message.reply_text("❌ Failed to add sudo user!")

    async def remove_sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /removesudo command"""
        user_id = update.effective_user.id
        
        if user_id != Config.OWNER_ID:
            await update.message.reply_text("❌ Only bot owner can remove sudo users!")
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ Please provide user ID!\n"
                "Usage: /removesudo <user_id>"
            )
            return

        target_user_id = int(context.args[0])
        db.remove_sudo_user(target_user_id)
        await update.message.reply_text(f"✅ User {target_user_id} removed from sudo!")

    async def list_sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sudo command to list all sudo users"""
        user_id = update.effective_user.id
        
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return

        sudo_users = db.get_all_sudo_users()
        
        if not sudo_users:
            await update.message.reply_text("👥 No sudo users added!")
            return

        text = "👑 **Sudo Users List:**\n\n"
        for i, user in enumerate(sudo_users, 1):
            text += f"{i}. User ID: `{user['user_id']}`\n"
            text += f"   Added by: {user['added_by']}\n"
            text += f"   Date: {user['added_date'].strftime('%Y-%m-%d %H:%M')}\n\n"
        
        await update.message.reply_text(text)

    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /post command to start posting"""
        user_id = update.effective_user.id
        
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return ConversationHandler.END

        channels = db.get_all_channels()
        
        if not channels:
            await update.message.reply_text("❌ No channels added! Use /add first.")
            return ConversationHandler.END

        # Store channel info in user data
        context.user_data['channels'] = channels
        context.user_data['posts_received'] = []
        context.user_data['channel_count'] = len(channels)
        
        await update.message.reply_text(
            f"📝 **Posting Setup**\n\n"
            f"📢 Total Channels: {len(channels)}\n"
            f"📨 Required Posts: {len(channels)}\n\n"
            f"Please send {len(channels)} posts now.\n"
            f"Each post will be sent to a different channel.\n\n"
            f"⚠️ **Note:** You can send text, photos, videos, or documents.\n"
            f"Type /cancel to stop."
        )
        
        return WAITING_FOR_POSTS

    async def receive_posts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive posts from user"""
        user_id = update.effective_user.id
        
        # Store the post
        if 'posts_received' not in context.user_data:
            context.user_data['posts_received'] = []
        
        # Store post data
        post_data = {
            'message_id': update.message.message_id,
            'chat_id': update.message.chat_id,
            'text': update.message.text if update.message.text else update.message.caption,
            'media_type': None,
            'file_id': None
        }
        
        # Handle different media types
        if update.message.photo:
            post_data['media_type'] = 'photo'
            post_data['file_id'] = update.message.photo[-1].file_id
        elif update.message.video:
            post_data['media_type'] = 'video'
            post_data['file_id'] = update.message.video.file_id
        elif update.message.document:
            post_data['media_type'] = 'document'
            post_data['file_id'] = update.message.document.file_id
        
        context.user_data['posts_received'].append(post_data)
        
        received = len(context.user_data['posts_received'])
        required = context.user_data['channel_count']
        
        if received < required:
            await update.message.reply_text(
                f"✅ Post {received} received!\n"
                f"📨 Need {required - received} more posts."
            )
            return WAITING_FOR_POSTS
        elif received == required:
            # All posts received, show options
            keyboard = [
                [
                    InlineKeyboardButton("🚀 Send Now", callback_data="send_now"),
                    InlineKeyboardButton("⏰ Schedule", callback_data="schedule")
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ All {required} posts received!\n\n"
                f"Choose an option:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_SCHEDULE
        else:
            await update.message.reply_text("⚠️ You've sent more posts than required!")
            return WAITING_FOR_POSTS

    async def handle_schedule_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle schedule choice"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "send_now":
            await self.send_posts_now(update, context)
        elif query.data == "schedule":
            await self.ask_schedule_time(update, context)
        elif query.data == "cancel_post":
            await query.edit_message_text("❌ Posting cancelled!")
            return ConversationHandler.END

    async def send_posts_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send posts immediately"""
        query = update.callback_query
        await query.edit_message_text("🚀 Sending posts to channels...")
        
        channels = context.user_data['channels']
        posts = context.user_data['posts_received']
        
        success_count = 0
        failed_channels = []
        
        for i, (channel, post) in enumerate(zip(channels, posts)):
            try:
                await self.send_post_to_channel(context.bot, channel['channel_id'], post)
                success_count += 1
                await asyncio.sleep(0.5)  # Rate limiting
            except Exception as e:
                logger.error(f"Failed to send to {channel['channel_title']}: {e}")
                failed_channels.append(channel['channel_title'])
        
        # Send report
        report = f"📊 **Posting Report**\n\n"
        report += f"✅ Successfully sent: {success_count}/{len(channels)}\n"
        
        if failed_channels:
            report += f"❌ Failed channels: {', '.join(failed_channels)}"
        
        await query.message.reply_text(report)
        return ConversationHandler.END

    async def send_post_to_channel(self, bot, channel_id, post):
        """Send a post to a specific channel"""
        try:
            if post['media_type'] == 'photo':
                await bot.send_photo(
                    chat_id=channel_id,
                    photo=post['file_id'],
                    caption=post['text']
                )
            elif post['media_type'] == 'video':
                await bot.send_video(
                    chat_id=channel_id,
                    video=post['file_id'],
                    caption=post['text']
                )
            elif post['media_type'] == 'document':
                await bot.send_document(
                    chat_id=channel_id,
                    document=post['file_id'],
                    caption=post['text']
                )
            else:
                await bot.send_message(
                    chat_id=channel_id,
                    text=post['text']
                )
            return True
        except Exception as e:
            logger.error(f"Error sending post to {channel_id}: {e}")
            return False

    async def ask_schedule_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask for schedule time (simplified version)"""
        query = update.callback_query
        await query.edit_message_text(
            "⏰ Scheduling feature will be implemented in the next version!\n"
            "For now, please use 'Send Now' option."
        )
        return ConversationHandler.END

    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the conversation"""
        await update.message.reply_text("❌ Operation cancelled!")
        return ConversationHandler.END

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        # Handle channel removal
        if query.data.startswith("remove_"):
            channel_id = query.data.replace("remove_", "")
            
            # Check if user is authorized
            user_id = query.from_user.id
            if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
                await query.message.reply_text("❌ You are not authorized!")
                return
            
            # Remove channel from database
            db.remove_channel(channel_id)
            
            # Update message
            await query.edit_message_text("✅ Channel removed successfully!")
        
        # Handle post scheduling choices
        elif query.data in ["send_now", "schedule", "cancel_post"]:
            await self.handle_schedule_choice(update, context)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        # This can be expanded for other message handling
        pass

    def run(self):
        """Run the bot"""
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
