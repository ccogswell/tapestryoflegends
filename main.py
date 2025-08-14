import discord
from discord.ext import commands
import os
import asyncio
import time
import logging
from bot.commands import RPCommands
from bot.session_manager import SessionManager
from bot.reward_calculator import RewardCalculator
from bot.achievement_system import AchievementSystem
from bot.achievement_commands import AchievementCommands
from bot.alias_manager import AliasManager
from bot.alias_commands import AliasCommands
from bot.stats_commands import StatsCommands
from database import DatabaseManager

# Configure logging for the bot
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # Privileged intent - enabled in Discord developer portal
intents.message_content = True  # Required for alias system to read message content

bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize managers
session_manager = SessionManager()
reward_calculator = RewardCalculator()
db_manager = DatabaseManager()
achievement_system = AchievementSystem(db_manager)
alias_manager = AliasManager(db_manager)

# Initialize stats system
try:
    from bot.stats_system import StatsSystem
    stats_system = StatsSystem(db_manager)
    logger.info("Stats system initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize stats system: {e}")
    stats_system = None

# Global bot instance for web interface access
bot_instance = None

@bot.event
async def on_ready():
    """Event triggered when bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    
    # Update bot status to indicate successful connection
    try:
        from run import bot_status
        bot_status["running"] = True
        bot_status["error"] = None
    except ImportError:
        pass  # bot_status not available (running standalone)
    
    # Store bot instance globally for web interface access
    global bot_instance
    bot_instance = bot
    
    # Start the participant table update task
    try:
        from bot.views import start_participant_update_task
        start_participant_update_task()
        logger.info("Started participant table update task")
    except Exception as e:
        logger.warning(f"Failed to start participant update task: {e}")
    
    # Start periodic session backup task
    try:
        async def periodic_session_backup():
            while True:
                await asyncio.sleep(300)  # Save every 5 minutes
                try:
                    session_manager.save_session_state()
                    logger.debug("Periodic session backup completed")
                except Exception as e:
                    logger.warning(f"Periodic session backup failed: {e}")
        
        asyncio.create_task(periodic_session_backup())
        logger.info("Started periodic session backup task")
    except Exception as e:
        logger.warning(f"Failed to start session backup task: {e}")
    
    # Start connection health monitoring
    try:
        async def connection_health_monitor():
            while True:
                await asyncio.sleep(60)  # Check every minute
                try:
                    if bot.is_closed():
                        logger.warning("Bot connection is closed, attempting reconnect...")
                    else:
                        logger.debug("Bot connection healthy")
                except Exception as e:
                    logger.warning(f"Connection health check failed: {e}")
        
        asyncio.create_task(connection_health_monitor())
        logger.info("Started connection health monitoring")
    except Exception as e:
        logger.warning(f"Failed to start connection monitoring: {e}")
    
    # Start guild member cache service
    try:
        from bot.guild_member_cache import start_guild_member_cache
        start_guild_member_cache(bot)
        logger.info("Started guild member cache service")
    except Exception as e:
        logger.warning(f"Failed to start guild member cache: {e}")
    
    # Initialize achievement system first
    try:
        await achievement_system.initialize()
        logger.info("Achievement system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize achievement system: {e}", exc_info=True)
    
    # Add cogs
    try:
        # Load RP Commands cog with achievement system and stats system
        rp_cog = RPCommands(bot, session_manager, reward_calculator, achievement_system, stats_system)
        await bot.add_cog(rp_cog)
        logger.info("Successfully loaded RPCommands cog")
        
        # Load Achievement Commands cog
        achievement_cog = AchievementCommands(bot, achievement_system)
        await bot.add_cog(achievement_cog)
        logger.info("Successfully loaded AchievementCommands cog")
        
        # Load Alias Commands cog
        alias_cog = AliasCommands(bot, alias_manager)
        await bot.add_cog(alias_cog)
        logger.info("Successfully loaded AliasCommands cog")
        
        # Load Stats Commands cog
        if stats_system:
            stats_cog = StatsCommands(bot, stats_system)
            await bot.add_cog(stats_cog)
            logger.info("Successfully loaded StatsCommands cog")
        
        # Add the context menu command manually since it's defined outside the class
        from bot.alias_commands import view_character_profile
        bot.tree.add_command(view_character_profile)
        logger.info("Successfully added character profile context menu")
        
        # Explicitly copy app commands from all cogs to bot tree
        all_cogs = [rp_cog, achievement_cog, alias_cog]
        if stats_system:
            all_cogs.append(stats_cog)
        total_commands = 0
        
        for cog in all_cogs:
            cog_commands = getattr(cog, '__cog_app_commands__', [])
            total_commands += len(cog_commands)
            logger.info(f"Cog {cog.__class__.__name__} has {len(cog_commands)} app commands")
            
            for command in cog_commands:
                logger.info(f"Copying command: {command.name}")
                # Remove from tree first if it exists
                existing = bot.tree.get_command(command.name)
                if existing:
                    bot.tree.remove_command(command.name)
                bot.tree.add_command(command)
        
        logger.info(f"Total commands copied: {total_commands}")
        
    except Exception as e:
        logger.error(f"Failed to load cogs: {e}", exc_info=True)
        return
    
    # Sync slash commands with force refresh
    try:
        # Check if we have commands to sync BEFORE clearing
        all_commands = bot.tree.get_commands()
        logger.info(f"Commands in tree before clear: {len(all_commands)}")
        for cmd in all_commands:
            desc = getattr(cmd, 'description', 'No description')
            logger.info(f"  - {cmd.name}: {desc}")
        
        # Clear and re-sync to force Discord to update command signatures
        bot.tree.clear_commands(guild=None)
        
        # Re-add commands from all cogs after clearing
        for cog_name in ["RPCommands", "AchievementCommands", "AliasCommands", "StatsCommands"]:
            cog = bot.get_cog(cog_name)
            if cog:
                logger.info(f"Re-adding {len(cog.__cog_app_commands__)} commands from {cog_name} after clear")
                for command in cog.__cog_app_commands__:
                    bot.tree.add_command(command)
        
        # Re-add the context menu command after clearing
        from bot.alias_commands import view_character_profile
        bot.tree.add_command(view_character_profile)
        logger.info("Re-added character profile context menu after clear")
        
        # Check commands after re-adding
        final_commands = bot.tree.get_commands()
        logger.info(f"Commands in tree after re-adding: {len(final_commands)}")
        
        synced = await bot.tree.sync()
        logger.info(f"Force-synced {len(synced)} command(s) - Discord will update signatures")
        
        # List synced commands
        for cmd in synced:
            logger.info(f"  Synced: {cmd.name}")
            
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}", exc_info=True)

@bot.event
async def on_member_join(member):
    """Handle when a member joins a guild"""
    try:
        from bot.guild_member_cache import handle_member_join
        await handle_member_join(member)
    except Exception as e:
        logger.error(f"Error in on_member_join: {e}")

@bot.event
async def on_member_remove(member):
    """Handle when a member leaves a guild"""
    try:
        from bot.guild_member_cache import handle_member_remove
        await handle_member_remove(member)
    except Exception as e:
        logger.error(f"Error in on_member_remove: {e}")

@bot.event
async def on_member_update(before, after):
    """Handle when a member's information is updated"""
    try:
        from bot.guild_member_cache import handle_member_update
        await handle_member_update(before, after)
    except Exception as e:
        logger.error(f"Error in on_member_update: {e}")

@bot.event
async def on_message(message):
    """Handle character alias messages"""
    # Skip if message is from a bot or webhook
    if message.author.bot:
        return
    
    # Skip if message is in DMs
    if not message.guild:
        return
    
    # Skip if message is empty
    if not message.content.strip():
        return
    
    try:
        # Prevent duplicate processing using message ID
        message_id = message.id
        if message_id in alias_manager.processing_messages:
            logger.warning(f"Message {message_id} already being processed, skipping duplicate")
            return
        
        # Add to processing set immediately to prevent race conditions
        alias_manager.processing_messages.add(message_id)
        logger.debug(f"Processing message {message_id}: '{message.content[:50]}...'")
        
        # First, check if this is a multi-line message with multiple different character triggers
        multiline_aliases = alias_manager.parse_multiline_aliases(message)
        if multiline_aliases and len(multiline_aliases) > 1:
            # Only process as multi-line if we have DIFFERENT characters
            unique_characters = set(alias.name for alias, _ in multiline_aliases)
            if len(unique_characters) > 1:
                # Handle multi-line message with multiple character triggers
                logger.info(f"Processing {len(multiline_aliases)} multi-line aliases from message")
                try:
                    await message.delete()
                    logger.debug(f"Deleted original multi-line message")
                    
                    # Send each character message separately
                    for alias, content in multiline_aliases:
                        try:
                            await alias_manager.send_as_character(message.channel, alias, content)
                            logger.info(f"Successfully posted multi-line message as {alias.name}")
                        except Exception as e:
                            logger.error(f"Failed to post multi-line message as {alias.name}: {e}")
                            
                except discord.Forbidden:
                    logger.warning(f"No permission to delete message in {message.channel.name}")
                except discord.NotFound:
                    logger.debug("Message already deleted")
                except Exception as e:
                    logger.error(f"Error processing multi-line aliases: {e}")
                finally:
                    # Always clean up and return - multi-line processing is complete
                    alias_manager.processing_messages.discard(message_id)
            
            # Multi-line processing complete - exit the function completely
            return
        
        # Single line processing - check if message matches any alias trigger
        alias_match = alias_manager.check_message_for_alias(message)
        logger.info(f"Message '{message.content[:30]}...' alias_match: {alias_match is not None}")
        
        # If no alias trigger, check if this should be added to existing consolidation  
        if not alias_match:
            # Additional check: make sure the message doesn't contain any other alias triggers
            contains_trigger = alias_manager.contains_any_alias_trigger(message.content, message.author.id, message.guild.id)
            logger.info(f"Message '{message.content[:30]}...' contains_trigger: {contains_trigger}")
            
            # No consolidation caching - just ignore non-trigger messages
            if not contains_trigger:
                logger.debug(f"Non-trigger message ignored: '{message.content[:30]}...'")
                return
        
        # Process single alias trigger messages
        if alias_match:
            alias, content = alias_match
            
            # Check if this should be consolidated with other messages from the same character
            should_consolidate = await alias_manager.handle_potential_consolidation(message, alias, content)
            
            if should_consolidate:
                # Message was queued for consolidation, delete the original
                try:
                    await message.delete()
                    logger.debug(f"Deleted original message for consolidation: {content[:50]}...")
                except discord.Forbidden:
                    logger.warning(f"No permission to delete message in {message.channel.name}")
                except discord.NotFound:
                    logger.debug("Message already deleted")
                except Exception as e:
                    logger.error(f"Error deleting message for consolidation: {e}")
                finally:
                    # Always clean up and return - consolidation processing is complete
                    alias_manager.processing_messages.discard(message_id)
                
                return
            
            logger.info(f"Processing alias message from {message.author.display_name} as {alias.name}: '{message.content}' -> '{content}'")
            
            try:
                # Delete the original message FIRST to prevent multiple processing
                await message.delete()
                logger.debug(f"Deleted original message from {message.author.display_name}")
                
                # Send message as character using webhook
                await alias_manager.send_as_character(message.channel, alias, content)
                logger.info(f"Successfully posted message as {alias.name} in {message.channel.name}")
                
            except discord.Forbidden:
                logger.warning(f"No permission to delete message in {message.channel.name}")
            except discord.NotFound:
                # Message already deleted
                logger.debug("Message already deleted")
            except Exception as e:
                logger.error(f"Failed to process alias message: {e}")
                # Try to notify user about the error
                try:
                    await message.channel.send(
                        f"❌ {message.author.mention} Failed to post as {alias.name}: {str(e)}",
                        delete_after=10
                    )
                except:
                    pass
                    
    except Exception as e:
        logger.error(f"Error processing alias message: {e}", exc_info=True)
    finally:
        # Always remove from processing set
        alias_manager.processing_messages.discard(message_id)

@bot.event
async def on_guild_join(guild):
    """Event triggered when bot joins a new guild"""
    try:
        # Initialize session storage for new guild
        session_manager.initialize_guild(guild.id)
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
    except Exception as e:
        logger.error(f"Error initializing guild {guild.name}: {e}", exc_info=True)

async def main():
    """Main function to start the bot with comprehensive error handling"""
    try:
        logger.info("Initializing Discord bot...")
        
        # Cog loading happens in on_ready event
        logger.info("RPCommands cog will be loaded in on_ready")
        
        # Get token from environment
        token = os.getenv('DISCORD_BOT_TOKEN')
        if not token:
            error_msg = "DISCORD_BOT_TOKEN environment variable not set"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Validate token format (should start with Bot or be just the token)
        token = token.strip()
        if not token:
            error_msg = "DISCORD_BOT_TOKEN is empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Token configured (length: {len(token)})")
        
        # Start bot with proper error handling
        try:
            logger.info("Connecting to Discord...")
            await bot.start(token)
        except discord.LoginFailure as e:
            logger.error(f"Discord login failed - invalid token: {e}")
            raise
        except discord.HTTPException as e:
            logger.error(f"Discord HTTP error: {e}")
            raise
        except discord.ConnectionClosed as e:
            logger.error(f"Discord connection closed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting bot: {type(e).__name__}: {e}", exc_info=True)
            raise
            
    except Exception as e:
        logger.error(f"Bot initialization failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
