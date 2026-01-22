import logging
import os
import asyncio
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta

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
from telegram.error import TelegramError

from config import Config
from database import db

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
        # Initialize bot with your token
        self.token = Config.BOT_TOKEN
        if not self.token:
            raise ValueError("BOT_TOKEN not found in environment variables!")
        
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        logger.info("Bot initialized successfully")

    def setup_handlers(self):
        """Setup all command and message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("add", self.add_channel))
        self.application.add_handler(CommandHandler("list", self.list_channels))
        self.application.add_handler(CommandHandler("addsudo", self.add_sudo))
        self.application.add_handler(CommandHandler("removesudo", self.remove_sudo))
        self.application.add_handler(CommandHandler("sudo", self.list_sudo))
        
        # Callback query handlers
        self.application.add_handler(CallbackQueryHandler(self.callback_handler, pattern="^(remove_|send_now|schedule|cancel_post).*"))
        
        # Conversation handler for posting
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("post", self.post_command)],
            states={
                WAITING_FOR_POSTS: [
                    MessageHandler(filters.ALL & ~filters.COMMAND, self.receive_posts)
                ],
                WAITING_FOR_SCHEDULE: [
                    CallbackQueryHandler(self.handle_schedule_choice, pattern="^(send_now|schedule|cancel_post)$")
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
        )
        self.application.add_handler(conv_handler)
        
        # Error handler
        self.application.add_error_handler(self.error_handler)

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
            "/post - Start posting to channels\n"
            "/help - Show this help message\n\n"
            "Bot developed for channel management"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "🤖 **Bot Help Guide**\n\n"
            "📌 **Commands:**\n"
            "• /add <channel_id> - Add a channel (Bot must be admin)\n"
            "• /list - Show all channels with remove option\n"
            "• /addsudo <user_id> - Add sudo user (Owner only)\n"
            "• /removesudo <user_id> - Remove sudo user (Owner only)\n"
            "• /sudo - List all sudo users\n"
            "• /post - Start posting to all channels\n"
            "• /cancel - Cancel current operation\n\n"
            "⚙️ **How to get Channel ID:**\n"
            "1. Forward a message from your channel to @username_to_id_bot\n"
            "2. Or use @getidsbot to get channel ID\n"
            "3. Channel ID format: -100xxxxxxxxxx\n\n"
            "📝 **Posting Guide:**\n"
            "1. Use /post to start\n"
            "2. Send exact number of posts as channels\n"
            "3. Choose to send now or schedule\n"
            "4. Each post goes to a different channel\n"
            "5. Supports text, photos, videos, documents"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

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
                "Usage: `/add <channel_id>`\n"
                "Example: `/add -1001234567890`\n\n"
                "Get channel ID from @username_to_id_bot",
                parse_mode='Markdown'
            )
            return

        channel_id = context.args[0]
        
        # Validate channel ID format
        if not re.match(r"^-100\d+$", channel_id):
            await update.message.reply_text(
                "❌ Invalid channel ID format!\n"
                "Channel ID should start with -100 followed by numbers.\n"
                "Example: `-1001234567890`\n\n"
                "Use @getidsbot to get correct channel ID",
                parse_mode='Markdown'
            )
            return

        try:
            # Check if bot is admin in channel
            bot = context.bot
            chat_member = await bot.get_chat_member(channel_id, bot.id)
            
            if chat_member.status not in ["administrator", "creator"]:
                await update.message.reply_text(
                    "❌ Bot is not admin in this channel!\n"
                    "Please make bot admin with post permissions first."
                )
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
                f"✅ **Channel added successfully!**\n\n"
                f"📢 **Channel:** {channel_title}\n"
                f"🆔 **ID:** `{channel_id}`\n"
                f"👤 **Added by:** {update.effective_user.first_name}\n"
                f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                parse_mode='Markdown'
            )
            
        except TelegramError as e:
            logger.error(f"Telegram error adding channel: {e}")
            await update.message.reply_text(
                "❌ **Failed to add channel!**\n\n"
                "**Possible reasons:**\n"
                "1. Bot is not in the channel\n"
                "2. Invalid channel ID\n"
                "3. Channel is private and bot not added\n"
                "4. Bot doesn't have admin permissions"
            )
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await update.message.reply_text("❌ An unexpected error occurred!")

    async def list_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list command to show all channels"""
        user_id = update.effective_user.id
        
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return

        channels = db.get_all_channels()
        
        if not channels:
            await update.message.reply_text("📭 No channels added yet! Use `/add` to add channels.", parse_mode='Markdown')
            return

        # Create inline keyboard with remove buttons
        keyboard = []
        for channel in channels:
            # Truncate long channel names
            display_name = channel['channel_title'][:30] + "..." if len(channel['channel_title']) > 30 else channel['channel_title']
            button = InlineKeyboardButton(
                f"🗑️ {display_name}",
                callback_data=f"remove_{channel['channel_id']}"
            )
            keyboard.append([button])
        
        # Add a cancel button
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        channels_text = "\n".join([f"• {ch['channel_title']} (`{ch['channel_id']}`)" for ch in channels])
        
        await update.message.reply_text(
            f"📋 **Total Channels: {len(channels)}**\n\n"
            f"{channels_text}\n\n"
            f"Click on any channel to remove it:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
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
                "⚠️ Please provide user ID!\n"
                "Usage: `/addsudo <user_id>`\n\n"
                "Get user ID from @userinfobot",
                parse_mode='Markdown'
            )
            return

        try:
            target_user_id = int(context.args[0])
            
            # Check if user exists (try to get user info)
            try:
                user = await context.bot.get_chat(target_user_id)
                username = user.username or user.first_name
            except:
                username = str(target_user_id)
            
            # Check if already sudo
            if db.is_sudo_user(target_user_id):
                await update.message.reply_text("⚠️ User is already a sudo user!")
                return
            
            # Add to database
            db.add_sudo_user(target_user_id, username, user_id)
            await update.message.reply_text(
                f"✅ **User added as sudo!**\n\n"
                f"👤 User: {username}\n"
                f"🆔 ID: `{target_user_id}`\n"
                f"👑 Added by: {update.effective_user.first_name}",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID! User ID must be a number.")
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
                "Usage: `/removesudo <user_id>`",
                parse_mode='Markdown'
            )
            return

        try:
            target_user_id = int(context.args[0])
            
            # Check if user exists in sudo list
            if not db.is_sudo_user(target_user_id):
                await update.message.reply_text("⚠️ User is not in sudo list!")
                return
            
            # Remove from database
            db.remove_sudo_user(target_user_id)
            await update.message.reply_text(f"✅ User `{target_user_id}` removed from sudo!", parse_mode='Markdown')
            
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID! User ID must be a number.")
        except Exception as e:
            logger.error(f"Error removing sudo: {e}")
            await update.message.reply_text("❌ Failed to remove sudo user!")

    async def list_sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sudo command to list all sudo users"""
        user_id = update.effective_user.id
        
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return

        sudo_users = db.get_all_sudo_users()
        
        if not sudo_users:
            await update.message.reply_text("👥 No sudo users added! Use `/addsudo` to add users.", parse_mode='Markdown')
            return

        text = "👑 **Sudo Users List:**\n\n"
        for i, user in enumerate(sudo_users, 1):
            username = user.get('username', 'N/A')
            added_by = user.get('added_by', 'Unknown')
            added_date = user.get('added_date', datetime.now())
            
            if isinstance(added_date, datetime):
                date_str = added_date.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = str(added_date)
            
            text += f"{i}. **User:** {username}\n"
            text += f"   **ID:** `{user['user_id']}`\n"
            text += f"   **Added by:** {added_by}\n"
            text += f"   **Date:** {date_str}\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')

    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /post command to start posting"""
        user_id = update.effective_user.id
        
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await update.message.reply_text("❌ You are not authorized to use this command!")
            return ConversationHandler.END

        channels = db.get_all_channels()
        
        if not channels:
            await update.message.reply_text("❌ No channels added! Use `/add` first.", parse_mode='Markdown')
            return ConversationHandler.END

        # Store channel info in user data
        context.user_data['channels'] = channels
        context.user_data['posts_received'] = []
        context.user_data['channel_count'] = len(channels)
        
        channel_list = "\n".join([f"{i+1}. {ch['channel_title']}" for i, ch in enumerate(channels)])
        
        await update.message.reply_text(
            f"📝 **Posting Setup**\n\n"
            f"📢 **Total Channels:** {len(channels)}\n"
            f"📨 **Required Posts:** {len(channels)}\n\n"
            f"**Channels:**\n{channel_list}\n\n"
            f"**Please send {len(channels)} posts now.**\n"
            f"Each post will be sent to a different channel in order.\n\n"
            f"📤 **Supported content:** Text, Photos, Videos, Documents\n"
            f"⏱️ **Status:** Waiting for post 1/{len(channels)}\n\n"
            f"Type `/cancel` to stop anytime.",
            parse_mode='Markdown'
        )
        
        return WAITING_FOR_POSTS

    async def receive_posts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive posts from user"""
        # Check if we're in the right state
        if 'channels' not in context.user_data:
            await update.message.reply_text("❌ Session expired. Use `/post` to start again.", parse_mode='Markdown')
            return ConversationHandler.END
        
        # Store the post
        if 'posts_received' not in context.user_data:
            context.user_data['posts_received'] = []
        
        # Store post data
        post_data = {
            'message_id': update.message.message_id,
            'chat_id': update.message.chat_id,
            'text': update.message.text or update.message.caption or '',
            'media_type': None,
            'file_id': None,
            'has_media': False
        }
        
        # Handle different media types
        if update.message.photo:
            post_data['media_type'] = 'photo'
            post_data['file_id'] = update.message.photo[-1].file_id
            post_data['has_media'] = True
        elif update.message.video:
            post_data['media_type'] = 'video'
            post_data['file_id'] = update.message.video.file_id
            post_data['has_media'] = True
        elif update.message.document:
            post_data['media_type'] = 'document'
            post_data['file_id'] = update.message.document.file_id
            post_data['has_media'] = True
        elif update.message.text:
            post_data['media_type'] = 'text'
            post_data['has_media'] = False
        
        context.user_data['posts_received'].append(post_data)
        
        received = len(context.user_data['posts_received'])
        required = context.user_data['channel_count']
        
        if received < required:
            # Show what type of content was received
            content_type = "📝 Text"
            if post_data['media_type'] == 'photo':
                content_type = "🖼️ Photo"
            elif post_data['media_type'] == 'video':
                content_type = "🎥 Video"
            elif post_data['media_type'] == 'document':
                content_type = "📎 Document"
            
            await update.message.reply_text(
                f"✅ **Post {received} received!** ({content_type})\n"
                f"📨 Need {required - received} more posts.\n"
                f"⏱️ **Status:** Waiting for post {received + 1}/{required}",
                parse_mode='Markdown'
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
            
            # Show summary of what was received
            summary = []
            for i, post in enumerate(context.user_data['posts_received'], 1):
                if post['media_type'] == 'text':
                    summary.append(f"{i}. 📝 Text (length: {len(post['text'])} chars)")
                elif post['media_type'] == 'photo':
                    summary.append(f"{i}. 🖼️ Photo with caption")
                elif post['media_type'] == 'video':
                    summary.append(f"{i}. 🎥 Video with caption")
                elif post['media_type'] == 'document':
                    summary.append(f"{i}. 📎 Document with caption")
            
            summary_text = "\n".join(summary)
            
            await update.message.reply_text(
                f"✅ **All {required} posts received!**\n\n"
                f"**Posts Summary:**\n{summary_text}\n\n"
                f"**Choose an option:**",
                reply_markup=reply_markup,
                parse_mode='Markdown'
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
        elif query.data == "cancel":
            await query.message.delete()

    async def send_posts_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send posts immediately"""
        query = update.callback_query
        await query.edit_message_text("🚀 **Sending posts to channels...**\n\nPlease wait...", parse_mode='Markdown')
        
        channels = context.user_data['channels']
        posts = context.user_data['posts_received']
        
        success_count = 0
        failed_channels = []
        
        # Send posts one by one
        for i, (channel, post) in enumerate(zip(channels, posts)):
            try:
                success = await self.send_post_to_channel(context.bot, channel['channel_id'], post)
                if success:
                    success_count += 1
                    logger.info(f"Successfully sent post {i+1} to {channel['channel_title']}")
                else:
                    failed_channels.append(channel['channel_title'])
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to send to {channel['channel_title']}: {e}")
                failed_channels.append(channel['channel_title'])
        
        # Send report
        report = f"📊 **Posting Report**\n\n"
        report += f"✅ **Successfully sent:** {success_count}/{len(channels)}\n"
        
        if failed_channels:
            report += f"❌ **Failed channels:** {', '.join(failed_channels[:5])}"
            if len(failed_channels) > 5:
                report += f" and {len(failed_channels) - 5} more..."
        
        # Clear user data
        context.user_data.clear()
        
        await query.message.reply_text(report, parse_mode='Markdown')
        return ConversationHandler.END

    async def send_post_to_channel(self, bot, channel_id, post):
        """Send a post to a specific channel"""
        try:
            if post['media_type'] == 'photo' and post['file_id']:
                await bot.send_photo(
                    chat_id=channel_id,
                    photo=post['file_id'],
                    caption=post['text'][:1024] if post['text'] else None,
                    parse_mode='Markdown'
                )
            elif post['media_type'] == 'video' and post['file_id']:
                await bot.send_video(
                    chat_id=channel_id,
                    video=post['file_id'],
                    caption=post['text'][:1024] if post['text'] else None,
                    parse_mode='Markdown'
                )
            elif post['media_type'] == 'document' and post['file_id']:
                await bot.send_document(
                    chat_id=channel_id,
                    document=post['file_id'],
                    caption=post['text'][:1024] if post['text'] else None,
                    parse_mode='Markdown'
                )
            elif post['text']:
                await bot.send_message(
                    chat_id=channel_id,
                    text=post['text'][:4096],
                    parse_mode='Markdown'
                )
            else:
                logger.warning(f"No content to send for post: {post}")
                return False
            return True
        except TelegramError as e:
            logger.error(f"Telegram error sending to {channel_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending post to {channel_id}: {e}")
            return False

    async def ask_schedule_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask for schedule time"""
        query = update.callback_query
        
        # For now, implement simple scheduling options
        keyboard = [
            [
                InlineKeyboardButton("⏰ In 1 hour", callback_data="schedule_1"),
                InlineKeyboardButton("⏰ In 3 hours", callback_data="schedule_3")
            ],
            [
                InlineKeyboardButton("⏰ In 6 hours", callback_data="schedule_6"),
                InlineKeyboardButton("⏰ In 12 hours", callback_data="schedule_12")
            ],
            [
                InlineKeyboardButton("⏰ Tomorrow same time", callback_data="schedule_24"),
                InlineKeyboardButton("🚀 Send Now Instead", callback_data="send_now")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⏰ **Schedule Posts**\n\n"
            "Choose when to send the posts:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return WAITING_FOR_SCHEDULE

    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the conversation"""
        if context.user_data:
            context.user_data.clear()
        
        await update.message.reply_text("❌ **Operation cancelled!**\n\nAll data cleared.", parse_mode='Markdown')
        return ConversationHandler.END

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        # Handle channel removal
        if query.data.startswith("remove_"):
            await self.handle_channel_removal(update, context)
        
        # Handle post scheduling choices
        elif query.data.startswith("schedule_"):
            await self.handle_scheduled_time(update, context)
        
        # Handle other callbacks
        elif query.data in ["send_now", "schedule", "cancel_post", "cancel"]:
            await self.handle_schedule_choice(update, context)

    async def handle_channel_removal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle channel removal callback"""
        query = update.callback_query
        
        # Check if user is authorized
        user_id = query.from_user.id
        if not (db.is_sudo_user(user_id) or user_id == Config.OWNER_ID):
            await query.message.reply_text("❌ You are not authorized!")
            return
        
        channel_id = query.data.replace("remove_", "")
        
        try:
            # Get channel info before removal
            channel = db.get_channel_by_id(channel_id)
            if not channel:
                await query.answer("Channel not found!", show_alert=True)
                return
            
            # Remove channel from database
            db.remove_channel(channel_id)
            
            # Update message
            new_text = query.message.text + f"\n\n✅ **Removed:** {channel['channel_title']}"
            
            # Update or delete the message
            try:
                await query.edit_message_text(
                    new_text,
                    parse_mode='Markdown',
                    reply_markup=None  # Remove buttons
                )
            except:
                await query.edit_message_text(
                    f"✅ **Channel removed successfully!**\n\n"
                    f"📢 **Channel:** {channel['channel_title']}\n"
                    f"🆔 **ID:** `{channel_id}`",
                    parse_mode='Markdown'
                )
            
            await query.answer(f"Removed {channel['channel_title']}!", show_alert=False)
            
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await query.answer("Failed to remove channel!", show_alert=True)

    async def handle_scheduled_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle scheduled time selection"""
        query = update.callback_query
        
        # Extract hours from callback data (schedule_1, schedule_3, etc.)
        try:
            hours = int(query.data.split("_")[1])
        except:
            hours = 1
        
        await query.edit_message_text(
            f"⏰ **Posts scheduled!**\n\n"
            f"Your posts will be sent in {hours} hour{'s' if hours > 1 else ''}.\n"
            f"Please note: Full scheduling requires additional setup with APScheduler.\n\n"
            f"For now, posts are marked as scheduled in database.",
            parse_mode='Markdown'
        )
        
        # Store scheduled post in database
        channels = context.user_data.get('channels', [])
        posts = context.user_data.get('posts_received', [])
        
        scheduled_time = datetime.now() + timedelta(hours=hours)
        
        for i, (channel, post) in enumerate(zip(channels, posts)):
            scheduled_post = {
                'channel_id': channel['channel_id'],
                'channel_title': channel['channel_title'],
                'post_data': post,
                'scheduled_time': scheduled_time,
                'sent': False,
                'added_by': query.from_user.id,
                'added_date': datetime.now()
            }
            db.add_scheduled_post(scheduled_post)
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        try:
            # Notify user about error
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ An error occurred! Please try again."
                )
        except:
            pass
        
        return

    def run(self):
        """Run the bot"""
        logger.info("Starting bot...")
        self.application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == "__main__":
    # Check for required environment variables
    required_vars = ['BOT_TOKEN', 'OWNER_ID']
    missing_vars = [var for var in required_vars if not getattr(Config, var, None)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please check your .env file")
        exit(1)
    
    try:
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
