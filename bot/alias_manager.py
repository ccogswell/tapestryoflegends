import asyncio
import re
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from models import CharacterAlias
from database import DatabaseManager
import discord

logger = logging.getLogger(__name__)

class AliasManager:
    """Manages character aliases and webhook posting"""
    
    def __init__(self, database_manager: DatabaseManager):
        self.db_manager = database_manager
        self.webhook_cache: Dict[int, discord.Webhook] = {}  # channel_id -> webhook
        self.processing_messages: set = set()  # Track messages being processed to prevent duplicates
        self.auto_proxy: Dict[int, Dict] = {}  # user_id -> {'guild_id': int, 'alias': CharacterAlias}
        self.pending_messages: Dict[str, Dict] = {}  # channel_id+user_id -> {'alias': CharacterAlias, 'content': List[str], 'last_time': float}
        self.consolidation_delay = 3.0  # Wait 3 seconds before sending consolidated message
        
    def get_user_aliases(self, user_id: int, guild_id: int) -> List[CharacterAlias]:
        """Get all aliases for a user in a guild"""
        db = self.db_manager.get_session()
        try:
            aliases = db.query(CharacterAlias).filter(
                CharacterAlias.user_id == str(user_id),
                CharacterAlias.guild_id == str(guild_id)
            ).all()
            return aliases
        except Exception as e:
            logger.error(f"Database error getting user aliases: {e}")
            db.rollback()
            return []
        finally:
            db.close()
    
    def get_alias_by_name(self, user_id: int, guild_id: int, name: str) -> Optional[CharacterAlias]:
        """Get a specific alias by name"""
        db = self.db_manager.get_session()
        try:
            alias = db.query(CharacterAlias).filter(
                CharacterAlias.user_id == str(user_id),
                CharacterAlias.guild_id == str(guild_id),
                CharacterAlias.name.ilike(name)  # Case insensitive
            ).first()
            return alias
        finally:
            db.close()
    
    def create_alias(self, user_id: int, guild_id: int, name: str, trigger: str, avatar_url: str, group_name: str = None, **kwargs) -> CharacterAlias:
        """Create a new character alias"""
        # Ensure guild exists first
        self.db_manager.ensure_guild_exists(guild_id)
        
        max_retries = 3
        for attempt in range(max_retries):
            db = None
            try:
                db = self.db_manager.get_session()
                
                # Check if name already exists for this user in this guild
                existing = db.query(CharacterAlias).filter(
                    CharacterAlias.user_id == str(user_id),
                    CharacterAlias.guild_id == str(guild_id),
                    CharacterAlias.name.ilike(name)
                ).first()
                
                if existing:
                    raise ValueError(f"You already have a character named '{name}'")
                
                # Build alias data with extended character information
                # Ensure avatar_url is never None due to database constraint
                default_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"
                alias_data = {
                    'user_id': str(user_id),
                    'guild_id': str(guild_id),
                    'name': name,
                    'trigger': trigger,
                    'avatar_url': avatar_url if avatar_url else default_avatar,
                    'group_name': group_name
                }
                
                # Add optional extended character information
                for field in ['character_class', 'race', 'pronouns', 'age', 'alignment', 
                             'description', 'personality', 'backstory', 'goals', 'notes', 'dndbeyond_url']:
                    if field in kwargs and kwargs[field]:
                        alias_data[field] = kwargs[field]
                
                alias = CharacterAlias(**alias_data)
                
                db.add(alias)
                db.commit()
                db.refresh(alias)
                return alias
                
            except ValueError:
                if db:
                    db.rollback()
                raise  # Re-raise ValueError as is
            except Exception as e:
                if db:
                    db.rollback()
                
                if attempt < max_retries - 1:
                    logger.warning(f"Database operation attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"All database operation attempts failed: {e}")
                    raise RuntimeError("Database connection issue. Please try again in a moment.")
            finally:
                if db:
                    db.close()
    
    def update_alias(self, user_id: int, guild_id: int, name: str, 
                    new_name: str = "", new_trigger: str = "", new_avatar: str = "", new_group: str = "") -> CharacterAlias:
        """Update an existing alias"""
        db = self.db_manager.get_session()
        try:
            alias = db.query(CharacterAlias).filter(
                CharacterAlias.user_id == str(user_id),
                CharacterAlias.guild_id == str(guild_id),
                CharacterAlias.name.ilike(name)
            ).first()
            
            if not alias:
                raise ValueError(f"No character named '{name}' found")
            
            # Check if new name conflicts with existing
            if new_name and new_name.lower() != alias.name.lower():
                existing = db.query(CharacterAlias).filter(
                    CharacterAlias.user_id == str(user_id),
                    CharacterAlias.guild_id == str(guild_id),
                    CharacterAlias.name.ilike(new_name)
                ).first()
                
                if existing:
                    raise ValueError(f"You already have a character named '{new_name}'")
            
            # Update fields
            if new_name and new_name.strip():
                setattr(alias, 'name', new_name)
            if new_trigger and new_trigger.strip():
                setattr(alias, 'trigger', new_trigger)
            if new_avatar and new_avatar.strip():
                setattr(alias, 'avatar_url', new_avatar)
            if new_group is not None:  # Allow setting to None/empty to remove group
                setattr(alias, 'group_name', new_group.strip() if new_group.strip() else None)
            
            db.commit()
            db.refresh(alias)
            return alias
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()
    
    def delete_alias(self, user_id: int, guild_id: int, name: str) -> bool:
        """Delete an alias"""
        db = self.db_manager.get_session()
        try:
            alias = db.query(CharacterAlias).filter(
                CharacterAlias.user_id == str(user_id),
                CharacterAlias.guild_id == str(guild_id),
                CharacterAlias.name.ilike(name)
            ).first()
            
            if not alias:
                return False
            
            db.delete(alias)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()
    
    def check_message_for_alias(self, message: discord.Message) -> Optional[Tuple[CharacterAlias, str]]:
        """Check if a message matches any of the user's alias triggers (own + shared) or auto-proxy"""
        if not message.guild or message.author.bot:
            return None
        
        # Get user's own aliases
        user_aliases = self.get_user_aliases(message.author.id, message.guild.id)
        
        # Get shared aliases accessible to this user
        shared_aliases = self._get_shared_aliases_for_user(message.author.id, message.guild.id)
        
        # Get personal trigger overrides
        overrides = self._get_user_overrides(message.author.id, message.guild.id)
        
        # Combine both lists - prioritize user's own aliases over shared ones
        all_aliases = user_aliases + [shared_data["alias"] for shared_data in shared_aliases]
        
        message_content = message.content
        
        # Check for personal trigger overrides first (highest priority)
        for override_data in overrides:
            override_trigger = str(override_data['personal_trigger'])
            if self._matches_trigger(message_content, override_trigger):
                alias = override_data['alias']
                actual_content = self._extract_content(message_content, override_trigger)
                
                # Update auto-proxy if enabled
                if message.author.id in self.auto_proxy:
                    auto_data = self.auto_proxy[message.author.id]
                    if auto_data['guild_id'] == message.guild.id:
                        old_alias = auto_data.get('alias')
                        old_name = old_alias.name if old_alias else "None"
                        self.auto_proxy[message.author.id]['alias'] = alias
                        logger.info(f"Override trigger matched: {alias.name} with personal trigger {override_trigger}")
                
                return alias, actual_content
        
        # Check for explicit trigger patterns (own aliases + shared aliases)
        for alias in all_aliases:
            trigger = str(alias.trigger)
            
            # Handle different trigger patterns
            if self._matches_trigger(message_content, trigger):
                # Extract the actual message content
                actual_content = self._extract_content(message_content, trigger)
                
                # If auto-proxy is enabled, update the current character (sticky behavior)
                if message.author.id in self.auto_proxy:
                    auto_data = self.auto_proxy[message.author.id]
                    if auto_data['guild_id'] == message.guild.id:
                        # Update auto-proxy to this new character (sticky behavior)
                        old_alias = auto_data.get('alias')
                        old_name = old_alias.name if old_alias else "None"
                        self.auto_proxy[message.author.id]['alias'] = alias
                        logger.info(f"Sticky auto-proxy switched from {old_name} to {alias.name} for user {message.author.display_name} ({message.author.id})")
                
                return alias, actual_content
        
        # Check for auto-proxy if no trigger matched
        if message.author.id in self.auto_proxy:
            auto_data = self.auto_proxy[message.author.id]
            if auto_data['guild_id'] == message.guild.id and auto_data['alias']:
                # User has auto-proxy enabled for this guild - use their current auto alias
                logger.debug(f"Using sticky auto-proxy character {auto_data['alias'].name} for {message.author.display_name}")
                return auto_data['alias'], message.content
        
        return None
    
    def parse_multiline_aliases(self, message: discord.Message) -> Optional[List[Tuple[CharacterAlias, str]]]:
        """Parse a message for multiple alias triggers on different lines"""
        if not message.guild or message.author.bot:
            return None
        
        lines = message.content.split('\n')
        if len(lines) <= 1:
            return None  # Single line message, use regular parsing
        
        # Get user's own aliases, shared aliases, and overrides
        user_aliases = self.get_user_aliases(message.author.id, message.guild.id)
        shared_aliases = self._get_shared_aliases_for_user(message.author.id, message.guild.id)
        overrides = self._get_user_overrides(message.author.id, message.guild.id)
        all_aliases = user_aliases + [shared_data["alias"] for shared_data in shared_aliases]
        
        parsed_messages = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            
            # Check for personal trigger overrides first
            matched = False
            for override_data in overrides:
                override_trigger = str(override_data['personal_trigger'])
                if self._matches_trigger(line, override_trigger):
                    alias = override_data['alias']
                    actual_content = self._extract_content(line, override_trigger)
                    if actual_content.strip():
                        parsed_messages.append((alias, actual_content))
                        matched = True
                        
                        # Update auto-proxy if enabled
                        if message.author.id in self.auto_proxy:
                            auto_data = self.auto_proxy[message.author.id]
                            if auto_data['guild_id'] == message.guild.id:
                                old_alias = auto_data.get('alias')
                                old_name = old_alias.name if old_alias else "None"
                                self.auto_proxy[message.author.id]['alias'] = alias
                                logger.debug(f"Multi-line override trigger matched: {alias.name}")
                        break
            
            # If no override matched, check regular aliases
            if not matched:
                for alias in all_aliases:
                    trigger = str(alias.trigger)
                    
                    if self._matches_trigger(line, trigger):
                        # Extract the actual message content
                        actual_content = self._extract_content(line, trigger)
                        if actual_content.strip():  # Only add if there's actual content
                            parsed_messages.append((alias, actual_content))
                            matched = True
                            
                            # Update auto-proxy if enabled (sticky behavior)
                            if message.author.id in self.auto_proxy:
                                auto_data = self.auto_proxy[message.author.id]
                                if auto_data['guild_id'] == message.guild.id:
                                    old_alias = auto_data.get('alias')
                                    old_name = old_alias.name if old_alias else "None"
                                    self.auto_proxy[message.author.id]['alias'] = alias
                                    logger.debug(f"Multi-line sticky auto-proxy switched from {old_name} to {alias.name}")
                            break
            
            # If no trigger matched for this line, check auto-proxy
            if not matched and message.author.id in self.auto_proxy:
                auto_data = self.auto_proxy[message.author.id]
                if auto_data['guild_id'] == message.guild.id and auto_data['alias']:
                    # Use current auto-proxy character
                    logger.debug(f"Using auto-proxy character {auto_data['alias'].name} for line: {line[:30]}...")
                    parsed_messages.append((auto_data['alias'], line))
        
        # Only return if we found at least one valid alias message
        if parsed_messages:
            logger.info(f"Parsed {len(parsed_messages)} alias messages from multi-line input")
            return parsed_messages
        
        return None
    
    def _matches_trigger(self, message: str, trigger: str) -> bool:
        """Check if message matches the trigger pattern (case insensitive)"""
        if not message or not trigger:
            return False
        
        # Convert both to lowercase for case insensitive matching
        message_lower = message.lower()
        trigger_lower = trigger.lower()
        
        # Handle bracket patterns like [text] or (text) - these need special content extraction
        if trigger_lower.startswith('[') and trigger_lower.endswith(']'):
            return message_lower.startswith('[') and message_lower.endswith(']') and len(message) > 2
        elif trigger_lower.startswith('(') and trigger_lower.endswith(')'):
            return message_lower.startswith('(') and message_lower.endswith(')') and len(message) > 2
        
        # For any other trigger, check if message starts with it (most common case)
        elif message_lower.startswith(trigger_lower):
            return True
        
        # Handle exact match (trigger is the entire message)
        elif trigger_lower == message_lower:
            return True
            
        return False
    
    def _extract_content(self, message: str, trigger: str) -> str:
        """Extract the actual content from a triggered message (case insensitive matching)"""
        if not message or not trigger:
            return message
        
        # Convert to lowercase for comparison but preserve original case for content
        message_lower = message.lower()
        trigger_lower = trigger.lower()
        
        # Handle bracket patterns like [text] - extract content between brackets
        if trigger_lower.startswith('[') and trigger_lower.endswith(']'):
            if message_lower.startswith('[') and message_lower.endswith(']'):
                return message[1:-1].strip()
        
        # Handle parentheses patterns like (text) - extract content between parentheses  
        elif trigger_lower.startswith('(') and trigger_lower.endswith(')'):
            if message_lower.startswith('(') and message_lower.endswith(')'):
                return message[1:-1].strip()
        
        # Handle exact match - return empty content
        elif trigger_lower == message_lower:
            return ""
        
        # For any prefix trigger, remove the trigger from the beginning
        elif message_lower.startswith(trigger_lower):
            return message[len(trigger):].strip()
        
        # Fallback - return original message
        return message
    
    async def get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook:
        """Get or create a webhook for the channel with cleanup if limit reached"""
        if channel.id in self.webhook_cache:
            webhook = self.webhook_cache[channel.id]
            try:
                # Test if webhook still exists
                await webhook.fetch()
                return webhook
            except discord.NotFound:
                # Webhook was deleted, remove from cache
                del self.webhook_cache[channel.id]
        
        # Try to find existing Quest Keeper webhook first
        try:
            webhooks = await channel.webhooks()
            for webhook in webhooks:
                if webhook.name in ["Quest Keeper RP", "Character Alias Bot"]:
                    self.webhook_cache[channel.id] = webhook
                    return webhook
        except Exception:
            pass
        
        # Create new webhook
        try:
            webhook = await channel.create_webhook(
                name="Quest Keeper RP",
                reason="Character alias system"
            )
            self.webhook_cache[channel.id] = webhook
            return webhook
        except discord.HTTPException as e:
            if e.code == 30007:  # Maximum webhooks reached
                # Try to clean up old webhooks and retry
                try:
                    await self._cleanup_old_webhooks(channel)
                    webhook = await channel.create_webhook(
                        name="Quest Keeper RP",
                        reason="Character alias system"
                    )
                    self.webhook_cache[channel.id] = webhook
                    return webhook
                except Exception as cleanup_error:
                    raise Exception(f"Failed to create webhook after cleanup: {cleanup_error}")
            else:
                raise Exception(f"Failed to create webhook: {e}")
        except discord.Forbidden:
            raise ValueError("Bot doesn't have permission to create webhooks in this channel")
        except Exception as e:
            raise Exception(f"Failed to create webhook: {e}")
    
    async def _cleanup_old_webhooks(self, channel: discord.TextChannel):
        """Clean up old Quest Keeper webhooks to make room for new ones"""
        try:
            webhooks = await channel.webhooks()
            quest_keeper_webhooks = [w for w in webhooks if w.name in ["Quest Keeper RP", "Character Alias Bot"]]
            
            # Delete all but keep space for one new one
            if len(quest_keeper_webhooks) > 1:
                for webhook in quest_keeper_webhooks[1:]:  # Keep the first one
                    try:
                        await webhook.delete(reason="Cleaning up duplicate webhooks")
                        logger.info(f"Cleaned up old webhook in {channel.name}")
                    except Exception:
                        pass
                        
            # If we still have too many webhooks, delete some non-Quest Keeper ones
            if len(webhooks) >= 15:
                other_webhooks = [w for w in webhooks if w.name not in ["Quest Keeper RP", "Character Alias Bot"]][:5]
                for webhook in other_webhooks:
                    try:
                        await webhook.delete(reason="Making room for Quest Keeper webhooks")
                        logger.info(f"Deleted other webhook '{webhook.name}' in {channel.name}")
                    except Exception:
                        pass
                        
        except Exception as e:
            logger.error(f"Error during webhook cleanup: {e}")
            raise
    
    async def handle_potential_consolidation(self, message: discord.Message, alias: CharacterAlias, content: str) -> bool:
        """Simple consolidation check - always send immediately, no caching.
        Returns False to indicate message should be sent immediately."""
        
        logger.debug(f"Processing message from {alias.name}: '{content[:50]}...' (sending immediately)")
        return False  # Always send immediately, no consolidation caching
    
    async def _send_consolidated_after_delay(self, channel: discord.TextChannel, channel_user_key: str, original_message: discord.Message):
        """Send the consolidated message after the delay period"""
        try:
            # Wait for the consolidation delay
            await asyncio.sleep(self.consolidation_delay)
            
            # Check if the pending message still exists
            if channel_user_key not in self.pending_messages:
                return
            
            pending = self.pending_messages[channel_user_key]
            
            # Combine all content parts with line breaks
            consolidated_content = '\n'.join(pending['content'])
            
            # Send the consolidated message
            try:
                await self.send_as_character(channel, pending['alias'], consolidated_content)
                logger.info(f"Sent consolidated message as {pending['alias'].name} with {len(pending['content'])} parts: '{consolidated_content[:100]}...'")
            except Exception as e:
                logger.error(f"Failed to send consolidated message as {pending['alias'].name}: {e}")
                # Send an error message
                try:
                    await channel.send(
                        f"❌ Failed to post consolidated message as **{pending['alias'].name}**: {str(e)}",
                        delete_after=10
                    )
                except:
                    pass
            
            # Clean up the pending message
            del self.pending_messages[channel_user_key]
            
        except asyncio.CancelledError:
            # Timer was cancelled because a new message came in
            logger.debug(f"Consolidation timer cancelled for {channel_user_key}")
        except Exception as e:
            logger.error(f"Error in consolidated message timer: {e}")
            # Clean up on error
            if channel_user_key in self.pending_messages:
                del self.pending_messages[channel_user_key]
    
    def contains_any_alias_trigger(self, content: str, user_id: int, guild_id: int) -> bool:
        """Check if content starts with any alias trigger for this user"""
        try:
            # Get user's own aliases
            user_aliases = self.get_user_aliases(user_id, guild_id)
            
            # Get shared aliases accessible to this user
            shared_aliases = self._get_shared_aliases_for_user(user_id, guild_id)
            
            # Get personal trigger overrides
            overrides = self._get_user_overrides(user_id, guild_id)
            
            # Combine all aliases
            all_aliases = user_aliases + [shared_data["alias"] for shared_data in shared_aliases]
            
            # Check overrides first
            for override_data in overrides:
                override_trigger = str(override_data['personal_trigger'])
                if self._matches_trigger(content, override_trigger):
                    logger.debug(f"Found override trigger match: '{override_trigger}' in '{content}'")
                    return True
            
            # Check regular triggers
            for alias in all_aliases:
                if alias.trigger and self._matches_trigger(content, alias.trigger):
                    logger.debug(f"Found regular trigger match: '{alias.trigger}' in '{content}'")
                    return True
            
            logger.debug(f"No trigger found in '{content}' for user {user_id}")
            return False
        except Exception as e:
            logger.error(f"Error checking for alias triggers: {e}")
            return False
    
    async def send_as_character(self, channel: discord.TextChannel, alias: CharacterAlias, content: str):
        """Send a message as a character using webhooks"""
        try:
            # If we're in a thread, use the parent channel for webhook creation
            webhook_channel = channel
            if hasattr(channel, 'parent') and channel.parent:
                webhook_channel = channel.parent
            
            webhook = await self.get_or_create_webhook(webhook_channel)
            
            logger.debug(f"Sending webhook message as {alias.name}: {content[:50]}...")
            
            # Send message with thread parameter if we're in a thread
            webhook_kwargs = {
                'content': content,
                'username': str(alias.name),
                'avatar_url': str(alias.avatar_url),
                'wait': True
            }
            
            # If original channel is a thread, specify it in the webhook send
            if hasattr(channel, 'parent') and channel.parent:
                webhook_kwargs['thread'] = channel
            
            await webhook.send(**webhook_kwargs)
            
            # Update message usage statistics
            self.increment_message_count(alias.user_id, alias.guild_id, alias.name)
            
            logger.debug(f"Webhook message sent successfully as {alias.name}")
            
        except Exception as e:
            logger.error(f"Failed to send webhook message: {e}")
            raise
    
    def enable_auto_proxy(self, user_id: int, guild_id: int, alias_name: str = "") -> bool:
        """Enable auto-proxy (sticky mode) for a user"""
        if alias_name:
            alias = self.get_alias_by_name(user_id, guild_id, alias_name)
            if not alias:
                return False
        else:
            # Start without a specific character - will be set on first trigger
            alias = None
        
        self.auto_proxy[user_id] = {
            'guild_id': guild_id,
            'alias': alias
        }
        return True
    
    def disable_auto_proxy(self, user_id: int) -> bool:
        """Disable auto-proxy for a user"""
        if user_id in self.auto_proxy:
            del self.auto_proxy[user_id]
            return True
        return False
    
    def get_auto_proxy_status(self, user_id: int, guild_id: int) -> Optional[CharacterAlias]:
        """Get the current auto-proxy character for a user in this guild"""
        if user_id in self.auto_proxy:
            auto_data = self.auto_proxy[user_id]
            if auto_data['guild_id'] == guild_id:
                return auto_data['alias']
        return None
    
    def increment_message_count(self, user_id: int, guild_id: int, alias_name: str):
        """Increment the message count for a character alias"""
        db = self.db_manager.get_session()
        try:
            alias = db.query(CharacterAlias).filter(
                CharacterAlias.user_id == str(user_id),
                CharacterAlias.guild_id == str(guild_id),
                CharacterAlias.name.ilike(alias_name)
            ).first()
            
            if alias:
                alias.message_count = (alias.message_count or 0) + 1
                alias.last_used = datetime.utcnow()
                db.commit()
                logger.debug(f"Updated message count for {alias_name}: {alias.message_count}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update message count for {alias_name}: {e}")
        finally:
            db.close()
    
    def get_alias_stats(self, user_id: int, guild_id: int) -> List[Dict]:
        """Get usage statistics for all user's aliases"""
        aliases = self.get_user_aliases(user_id, guild_id)
        stats = []
        
        for alias in aliases:
            stats.append({
                'name': alias.name,
                'trigger': alias.trigger,
                'message_count': alias.message_count or 0,
                'last_used': alias.last_used,
                'created_at': alias.created_at
            })
        
        # Sort by message count (most used first)
        stats.sort(key=lambda x: x['message_count'], reverse=True)
        return stats
    
    def _get_shared_aliases_for_user(self, user_id: int, guild_id: int):
        """Get all aliases shared with a specific user"""
        try:
            db = self.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission, CharacterAlias
                
                user_id_str = str(user_id)
                guild_id_str = str(guild_id)
                
                # Query for shared groups that this user has access to
                shared_groups = db.query(SharedGroup, SharedGroupPermission).join(
                    SharedGroupPermission, SharedGroup.id == SharedGroupPermission.shared_group_id
                ).filter(
                    SharedGroupPermission.user_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.is_active == True
                ).all()
                
                shared_aliases = []
                
                for shared_group, permission in shared_groups:
                    if shared_group.is_single_alias and shared_group.single_alias_id:
                        # Handle single alias shares
                        alias = db.query(CharacterAlias).filter(
                            CharacterAlias.id == shared_group.single_alias_id
                        ).first()
                        
                        if alias:
                            shared_aliases.append({
                                "alias": alias,
                                "permission": permission.permission_level,
                                "shared_group": shared_group
                            })
                    else:
                        # Handle group/subgroup shares
                        query = db.query(CharacterAlias).filter(
                            CharacterAlias.user_id == shared_group.owner_id,
                            CharacterAlias.guild_id == guild_id_str,
                            CharacterAlias.group_name == shared_group.group_name
                        )
                        
                        if shared_group.subgroup_name:
                            query = query.filter(CharacterAlias.subgroup == shared_group.subgroup_name)
                        
                        aliases = query.all()
                        
                        for alias in aliases:
                            shared_aliases.append({
                                "alias": alias,
                                "permission": permission.permission_level,
                                "shared_group": shared_group
                            })
                
                return shared_aliases
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting shared aliases for user in alias_manager: {e}")
            return []
    
    def _get_user_overrides(self, user_id: int, guild_id: int):
        """Get all personal trigger overrides for a user"""
        try:
            db = self.db_manager.get_session()
            try:
                from models import AliasOverride, CharacterAlias
                
                user_id_str = str(user_id)
                guild_id_str = str(guild_id)
                
                overrides = db.query(AliasOverride, CharacterAlias).join(
                    CharacterAlias, AliasOverride.original_alias_id == CharacterAlias.id
                ).filter(
                    AliasOverride.user_id == user_id_str,
                    AliasOverride.guild_id == guild_id_str,
                    AliasOverride.is_active == True
                ).all()
                
                override_list = []
                for override, alias in overrides:
                    override_list.append({
                        'personal_trigger': override.personal_trigger,
                        'alias': alias,
                        'override': override
                    })
                
                return override_list
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting user overrides in alias_manager: {e}")
            return []