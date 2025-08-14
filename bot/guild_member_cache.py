"""
Guild Member Cache Service
Periodically fetches and caches Discord guild member information for web app usage
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from database import get_db_session
from models import Guild, GuildMember

logger = logging.getLogger(__name__)

class GuildMemberCache:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.sync_interval_hours = 6  # Sync every 6 hours
        self.is_running = False
        
    async def start_periodic_sync(self):
        """Start the periodic member sync task"""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info("Starting guild member cache sync task")
        
        while self.is_running:
            try:
                await self.sync_all_guilds()
                await asyncio.sleep(self.sync_interval_hours * 3600)  # Convert hours to seconds
            except Exception as e:
                logger.error(f"Error in periodic guild member sync: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retry on error
    
    async def sync_all_guilds(self):
        """Sync member data for all guilds the bot is in"""
        if not self.bot.is_ready():
            logger.warning("Bot not ready, skipping guild member sync")
            return
            
        guilds_synced = 0
        for guild in self.bot.guilds:
            try:
                await self.sync_guild_members(guild)
                guilds_synced += 1
                # Small delay between guilds to avoid rate limits
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed to sync members for guild {guild.name} ({guild.id}): {e}")
        
        logger.info(f"Completed guild member sync for {guilds_synced} guilds")
    
    async def sync_guild_members(self, guild: discord.Guild):
        """Sync member data for a specific guild"""
        logger.debug(f"Syncing members for guild: {guild.name} ({guild.id})")
        
        db = get_db_session()
        if not db:
            logger.error("Failed to get database session for member sync")
            return
            
        try:
            # Ensure guild exists in database
            guild_record = db.query(Guild).filter(Guild.id == str(guild.id)).first()
            if not guild_record:
                guild_record = Guild(
                    id=str(guild.id),
                    name=guild.name,
                    created_at=datetime.utcnow()
                )
                db.add(guild_record)
                db.commit()
            
            # Update guild name if changed
            if guild_record.name != guild.name:
                guild_record.name = guild.name
            
            # Mark start of sync
            sync_time = datetime.utcnow()
            guild_record.last_member_sync = sync_time
            
            # Get current member IDs to track who's still in the guild
            current_member_ids = set()
            
            # Sync each member
            members_processed = 0
            async for member in guild.fetch_members(limit=None):
                try:
                    await self.sync_guild_member(db, guild, member, sync_time)
                    current_member_ids.add(str(member.id))
                    members_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to sync member {member.id} in guild {guild.id}: {e}")
            
            # Mark members who left as inactive
            db.query(GuildMember).filter(
                GuildMember.guild_id == str(guild.id),
                ~GuildMember.user_id.in_(current_member_ids),
                GuildMember.is_active == True
            ).update({
                'is_active': False,
                'updated_at': sync_time
            }, synchronize_session=False)
            
            db.commit()
            logger.info(f"Synced {members_processed} members for guild {guild.name}")
            
        except Exception as e:
            logger.error(f"Error syncing guild {guild.id}: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def sync_guild_member(self, db, guild: discord.Guild, member: discord.Member, sync_time: datetime):
        """Sync a specific guild member"""
        # Check if member record exists
        member_record = db.query(GuildMember).filter(
            GuildMember.guild_id == str(guild.id),
            GuildMember.user_id == str(member.id)
        ).first()
        
        # Prepare member data
        avatar_url = None
        if member.avatar:
            avatar_url = str(member.avatar.url)
        elif member.default_avatar:
            avatar_url = str(member.default_avatar.url)
        
        # Get role IDs as JSON
        role_ids = [str(role.id) for role in member.roles if role.id != guild.id]  # Exclude @everyone
        roles_json = json.dumps(role_ids) if role_ids else None
        
        if member_record:
            # Update existing record
            member_record.username = member.name
            member_record.display_name = member.display_name
            member_record.discriminator = member.discriminator if hasattr(member, 'discriminator') else None
            member_record.avatar_url = avatar_url
            member_record.joined_at = member.joined_at
            member_record.roles = roles_json
            member_record.updated_at = sync_time
            member_record.is_active = True
        else:
            # Create new record
            member_record = GuildMember(
                guild_id=str(guild.id),
                user_id=str(member.id),
                username=member.name,
                display_name=member.display_name,
                discriminator=member.discriminator if hasattr(member, 'discriminator') else None,
                avatar_url=avatar_url,
                joined_at=member.joined_at,
                roles=roles_json,
                cached_at=sync_time,
                updated_at=sync_time,
                is_active=True
            )
            db.add(member_record)
    
    def stop(self):
        """Stop the periodic sync task"""
        self.is_running = False
        logger.info("Stopped guild member cache sync task")

# Global instance
_guild_member_cache: Optional[GuildMemberCache] = None

def get_guild_member_cache() -> Optional[GuildMemberCache]:
    """Get the global guild member cache instance"""
    return _guild_member_cache

def start_guild_member_cache(bot: discord.Client):
    """Start the guild member cache service"""
    global _guild_member_cache
    if _guild_member_cache is None:
        _guild_member_cache = GuildMemberCache(bot)
        asyncio.create_task(_guild_member_cache.start_periodic_sync())
        logger.info("Guild member cache service started")
    return _guild_member_cache

async def sync_guild_members_now(guild_id: Optional[str] = None):
    """Manually trigger a guild member sync"""
    if _guild_member_cache is None:
        logger.warning("Guild member cache not initialized")
        return
        
    if guild_id:
        # Sync specific guild
        guild = _guild_member_cache.bot.get_guild(int(guild_id))
        if guild:
            await _guild_member_cache.sync_guild_members(guild)
        else:
            logger.warning(f"Guild {guild_id} not found")
    else:
        # Sync all guilds
        await _guild_member_cache.sync_all_guilds()

async def handle_member_join(member: discord.Member):
    """Handle when a member joins a guild"""
    if _guild_member_cache is None:
        logger.warning("Guild member cache not initialized")
        return
        
    try:
        db = get_db_session()
        if not db:
            logger.error("Failed to get database session for member join")
            return
            
        sync_time = datetime.utcnow()
        await _guild_member_cache.sync_guild_member(db, member.guild, member, sync_time)
        db.commit()
        logger.info(f"Added new member {member.name} to cache for guild {member.guild.name}")
        
    except Exception as e:
        logger.error(f"Error handling member join for {member.name}: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()

async def handle_member_remove(member: discord.Member):
    """Handle when a member leaves a guild"""
    if _guild_member_cache is None:
        logger.warning("Guild member cache not initialized")
        return
        
    try:
        db = get_db_session()
        if not db:
            logger.error("Failed to get database session for member remove")
            return
            
        from models import GuildMember
        
        # Mark member as inactive
        member_record = db.query(GuildMember).filter(
            GuildMember.guild_id == str(member.guild.id),
            GuildMember.user_id == str(member.id)
        ).first()
        
        if member_record:
            member_record.is_active = False
            member_record.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Marked member {member.name} as inactive in cache for guild {member.guild.name}")
        else:
            logger.warning(f"Member {member.name} not found in cache for guild {member.guild.name}")
            
    except Exception as e:
        logger.error(f"Error handling member remove for {member.name}: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()

async def handle_member_update(before: discord.Member, after: discord.Member):
    """Handle when a member's information is updated"""
    if _guild_member_cache is None:
        logger.warning("Guild member cache not initialized")
        return
        
    # Check if relevant information changed
    if (before.name == after.name and 
        before.display_name == after.display_name and
        before.avatar == after.avatar and
        before.roles == after.roles):
        return  # No relevant changes
        
    try:
        db = get_db_session()
        if not db:
            logger.error("Failed to get database session for member update")
            return
            
        sync_time = datetime.utcnow()
        await _guild_member_cache.sync_guild_member(db, after.guild, after, sync_time)
        db.commit()
        logger.debug(f"Updated member {after.name} in cache for guild {after.guild.name}")
        
    except Exception as e:
        logger.error(f"Error handling member update for {after.name}: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()