import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_, or_
import discord
from database import DatabaseManager
from models import Achievement, PlayerAchievement, PlayerStats, Milestone, PlayerMilestone, Base
import logging

logger = logging.getLogger(__name__)

class AchievementSystem:
    """Manages player achievements, milestones, and statistics"""
    
    def __init__(self, database_manager: DatabaseManager):
        self.db_manager = database_manager
        self.achievement_cache = {}
        self.milestone_cache = {}
        
    async def initialize(self):
        """Initialize achievement system with default achievements"""
        try:
            # Create achievement tables
            from models.achievement_models import Base
            from models import Base as ModelsBase
            Base.metadata.create_all(self.db_manager.engine)
            
            # Populate default achievements if empty
            await self._populate_default_achievements()
            logger.info("Achievement system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize achievement system: {e}")
            
    async def _populate_default_achievements(self):
        """Add default achievements to the database"""
        db = self.db_manager.get_session()
        try:
            # Check if achievements exist
            existing_count = db.query(Achievement).count()
            if existing_count > 0:
                return
            
            # Session Participation Achievements
            session_achievements = [
                {
                    'key': 'first_steps',
                    'name': 'First Steps',
                    'description': 'Join your first roleplay session',
                    'category': 'session',
                    'icon': '👣',
                    'points': 10,
                    'requirement_type': 'sessions_count',
                    'requirement_value': 1
                },
                {
                    'key': 'regular_adventurer', 
                    'name': 'Regular Adventurer',
                    'description': 'Participate in 5 roleplay sessions',
                    'category': 'session',
                    'icon': '🎒',
                    'points': 25,
                    'requirement_type': 'sessions_count',
                    'requirement_value': 5
                },
                {
                    'key': 'veteran_adventurer',
                    'name': 'Veteran Adventurer', 
                    'description': 'Participate in 25 roleplay sessions',
                    'category': 'session',
                    'icon': '⚔️',
                    'points': 75,
                    'requirement_type': 'sessions_count',
                    'requirement_value': 25
                },
                {
                    'key': 'legendary_adventurer',
                    'name': 'Legendary Adventurer',
                    'description': 'Participate in 100 roleplay sessions',
                    'category': 'session', 
                    'icon': '🏆',
                    'points': 200,
                    'requirement_type': 'sessions_count',
                    'requirement_value': 100
                },
                {
                    'key': 'marathon_session',
                    'name': 'Marathon Runner',
                    'description': 'Participate in a session lasting 6+ hours',
                    'category': 'session',
                    'icon': '🏃‍♀️',
                    'points': 50,
                    'requirement_type': 'session_duration',
                    'requirement_value': 360  # 6 hours in minutes
                },
            ]
            
            # Character Development Achievements  
            character_achievements = [
                {
                    'key': 'level_up',
                    'name': 'Level Up!',
                    'description': 'Reach character level 5',
                    'category': 'character',
                    'icon': '📈',
                    'points': 20,
                    'requirement_type': 'character_level',
                    'requirement_value': 5
                },
                {
                    'key': 'seasoned_hero',
                    'name': 'Seasoned Hero',
                    'description': 'Reach character level 10',
                    'category': 'character',
                    'icon': '🛡️',
                    'points': 40,
                    'requirement_type': 'character_level',
                    'requirement_value': 10
                },
                {
                    'key': 'epic_hero',
                    'name': 'Epic Hero',
                    'description': 'Reach character level 15',
                    'category': 'character',
                    'icon': '⭐',
                    'points': 75,
                    'requirement_type': 'character_level',
                    'requirement_value': 15
                },
                {
                    'key': 'legendary_hero',
                    'name': 'Legendary Hero', 
                    'description': 'Reach character level 20',
                    'category': 'character',
                    'icon': '👑',
                    'points': 150,
                    'requirement_type': 'character_level',
                    'requirement_value': 20
                },
                {
                    'key': 'wealthy_adventurer',
                    'name': 'Wealthy Adventurer',
                    'description': 'Earn 1000 total gold pieces',
                    'category': 'character',
                    'icon': '💰',
                    'points': 30,
                    'requirement_type': 'total_gold',
                    'requirement_value': 1000
                },
            ]
            
            # DM/Community Achievements
            community_achievements = [
                {
                    'key': 'first_dm',
                    'name': 'First Time DM',
                    'description': 'Host your first roleplay session',
                    'category': 'community',
                    'icon': '🎭',
                    'points': 30,
                    'requirement_type': 'dm_sessions',
                    'requirement_value': 1
                },
                {
                    'key': 'master_storyteller',
                    'name': 'Master Storyteller',
                    'description': 'Host 10 roleplay sessions as DM',
                    'category': 'community', 
                    'icon': '📖',
                    'points': 100,
                    'requirement_type': 'dm_sessions',
                    'requirement_value': 10
                },
                {
                    'key': 'guild_mentor',
                    'name': 'Guild Mentor',
                    'description': 'Help 5 new players in their first sessions',
                    'category': 'community',
                    'icon': '🤝',
                    'points': 60,
                    'requirement_type': 'players_helped',
                    'requirement_value': 5,
                    'is_hidden': True
                },
                {
                    'key': 'dedication',
                    'name': 'Dedication',
                    'description': 'Play for 50 total hours',
                    'category': 'community',
                    'icon': '⏰',
                    'points': 80,
                    'requirement_type': 'total_playtime',
                    'requirement_value': 50
                },
            ]
            
            # Special/Hidden Achievements
            special_achievements = [
                {
                    'key': 'early_bird',
                    'name': 'Early Bird',
                    'description': 'Join a session within the first 5 minutes',
                    'category': 'special',
                    'icon': '🐦',
                    'points': 15,
                    'requirement_type': 'quick_join',
                    'requirement_value': 5,
                    'is_hidden': True
                },
                {
                    'key': 'night_owl',
                    'name': 'Night Owl',
                    'description': 'Play a session starting after midnight',
                    'category': 'special',
                    'icon': '🦉',
                    'points': 15,
                    'requirement_type': 'late_night_session',
                    'requirement_value': 1,
                    'is_hidden': True
                },
                {
                    'key': 'completionist',
                    'name': 'Completionist',
                    'description': 'Unlock 20 different achievements',
                    'category': 'meta',
                    'icon': '💯',
                    'points': 100,
                    'requirement_type': 'achievements_count',
                    'requirement_value': 20
                },
            ]
            
            # Add all achievements to database
            all_achievements = session_achievements + character_achievements + community_achievements + special_achievements
            
            for ach_data in all_achievements:
                achievement = Achievement(**ach_data)
                db.add(achievement)
            
            db.commit()
            logger.info(f"Populated {len(all_achievements)} default achievements")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to populate default achievements: {e}")
        finally:
            db.close()
    
    async def update_player_stats(self, user_id: str, guild_id: str, stat_updates: Dict):
        """Update player statistics and check for achievement unlocks"""
        db = self.db_manager.get_session()
        try:
            # Get or create player stats
            stats = db.query(PlayerStats).filter(
                and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
            ).first()
            
            if not stats:
                stats = PlayerStats(user_id=user_id, guild_id=guild_id)
                db.add(stats)
            
            # Update stats - handle SQLAlchemy attribute access properly
            for stat_name, value in stat_updates.items():
                if hasattr(stats, stat_name):
                    if stat_name in ['total_sessions', 'sessions_as_dm', 'players_helped', 'achievements_unlocked']:
                        # Increment counters
                        current_value = getattr(stats, stat_name, None)
                        current_value = current_value if current_value is not None else 0
                        setattr(stats, stat_name, current_value + value)
                    elif stat_name in ['highest_character_level', 'longest_session_minutes']:
                        # Update if higher
                        current_value = getattr(stats, stat_name, None)
                        current_value = current_value if current_value is not None else 0
                        if value > current_value:
                            setattr(stats, stat_name, value)
                    else:
                        # Direct update or accumulate
                        if stat_name in ['total_playtime_hours', 'total_xp_earned', 'total_gold_earned']:
                            current_value = getattr(stats, stat_name, None)
                            current_value = current_value if current_value is not None else 0
                            setattr(stats, stat_name, current_value + value)
                        else:
                            setattr(stats, stat_name, value)
            
            db.commit()
            
            # Check for achievement unlocks
            new_achievements = await self._check_achievement_unlocks(user_id, guild_id, stats)
            return stats, new_achievements
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update player stats: {e}")
            return None, []
        finally:
            db.close()
    
    async def _check_achievement_unlocks(self, user_id: str, guild_id: str, stats: PlayerStats) -> List[Achievement]:
        """Check if player has unlocked any new achievements"""
        db = self.db_manager.get_session()
        new_achievements = []
        
        try:
            # Get all achievements
            all_achievements = db.query(Achievement).filter(Achievement.is_active == True).all()
            
            # Get player's current achievements
            current_achievements = db.query(PlayerAchievement).filter(
                and_(
                    PlayerAchievement.user_id == user_id,
                    PlayerAchievement.guild_id == guild_id,
                    PlayerAchievement.is_completed == True
                )
            ).all()
            
            achieved_ids = {pa.achievement_id for pa in current_achievements}
            
            for achievement in all_achievements:
                if achievement.id in achieved_ids:
                    continue
                    
                # Check if achievement requirements are met
                if await self._is_achievement_unlocked(achievement, stats):
                    # Create achievement unlock record
                    player_achievement = PlayerAchievement(
                        user_id=user_id,
                        guild_id=guild_id,
                        achievement_id=achievement.id,
                        current_progress=achievement.requirement_value,
                        is_completed=True,
                        completed_at=datetime.utcnow()
                    )
                    db.add(player_achievement)
                    new_achievements.append(achievement)
                    
                    # Update stats
                    current_achievements = getattr(stats, 'achievements_unlocked', None)
                    current_achievements = current_achievements if current_achievements is not None else 0
                    stats.achievements_unlocked = current_achievements + 1
                    
                    current_points = getattr(stats, 'total_achievement_points', None)
                    current_points = current_points if current_points is not None else 0
                    stats.total_achievement_points = current_points + achievement.points
            
            db.commit()
            return new_achievements
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to check achievement unlocks: {e}")
            return []
        finally:
            db.close()
    
    async def _is_achievement_unlocked(self, achievement: Achievement, stats: PlayerStats) -> bool:
        """Check if specific achievement requirements are met"""
        req_type = achievement.requirement_type
        req_value = achievement.requirement_value
        
        stat_mapping = {
            'sessions_count': getattr(stats, 'total_sessions', 0) or 0,
            'dm_sessions': getattr(stats, 'sessions_as_dm', 0) or 0,
            'character_level': getattr(stats, 'highest_character_level', 1) or 1,
            'total_gold': getattr(stats, 'total_gold_earned', 0) or 0,
            'total_playtime': getattr(stats, 'total_playtime_hours', 0) or 0,
            'players_helped': getattr(stats, 'players_helped', 0) or 0,
            'achievements_count': getattr(stats, 'achievements_unlocked', 0) or 0,
        }
        
        current_value = stat_mapping.get(req_type, 0)
        return current_value >= req_value
    
    async def get_player_achievements(self, user_id: str, guild_id: str) -> Dict:
        """Get all player achievements and stats"""
        db = self.db_manager.get_session()
        try:
            # Get player stats
            stats = db.query(PlayerStats).filter(
                and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
            ).first()
            
            if not stats:
                stats = PlayerStats(user_id=user_id, guild_id=guild_id)
                db.add(stats)
                db.commit()
            
            # Get unlocked achievements
            unlocked = db.query(PlayerAchievement).join(Achievement).filter(
                and_(
                    PlayerAchievement.user_id == user_id,
                    PlayerAchievement.guild_id == guild_id,
                    PlayerAchievement.is_completed == True
                )
            ).all()
            
            # Get available achievements (not unlocked yet)
            unlocked_ids = {pa.achievement_id for pa in unlocked}
            if unlocked_ids:
                available = db.query(Achievement).filter(
                    and_(
                        Achievement.is_active == True,
                        ~Achievement.id.in_(unlocked_ids)
                    )
                ).all()
            else:
                available = db.query(Achievement).filter(Achievement.is_active == True).all()
            
            return {
                'stats': stats,
                'unlocked_achievements': [(pa.achievement, pa.completed_at) for pa in unlocked],
                'available_achievements': available,
                'total_points': getattr(stats, 'total_achievement_points', 0) or 0,
                'total_unlocked': len(unlocked)
            }
            
        except Exception as e:
            logger.error(f"Failed to get player achievements: {e}")
            return {}
        finally:
            db.close()
    
    async def process_session_completion(self, session_data: dict, participants: list):
        """Process achievements when a session completes"""
        try:
            guild_id = str(session_data.get('guild_id', ''))
            session_duration_minutes = session_data.get('duration_minutes', 0)
            dm_id = str(session_data.get('dm_id', ''))
            
            # Update DM stats
            if dm_id:
                dm_updates = {
                    'sessions_as_dm': 1,
                    'longest_session_minutes': session_duration_minutes
                }
                await self.update_player_stats(dm_id, guild_id, dm_updates)
            
            # Update participant stats
            for participant in participants:
                user_id = str(participant.get('user_id', ''))
                character_level = participant.get('character_level', 1)
                participation_minutes = participant.get('participation_time_seconds', 0) // 60
                xp_earned = participant.get('final_xp', 0)
                gold_earned = participant.get('final_gold', 0)
                
                if user_id and participation_minutes >= 30:  # Minimum 30 minutes
                    updates = {
                        'total_sessions': 1,
                        'total_playtime_hours': participation_minutes / 60.0,
                        'highest_character_level': character_level,
                        'total_xp_earned': xp_earned,
                        'total_gold_earned': gold_earned,
                        'longest_session_minutes': participation_minutes
                    }
                    
                    await self.update_player_stats(user_id, guild_id, updates)
            
            logger.info(f"Processed achievements for session completion with {len(participants)} participants")
            
        except Exception as e:
            logger.error(f"Failed to process session completion achievements: {e}")
    
    async def create_achievement_embed(self, player_data: Dict, user: discord.User) -> discord.Embed:
        """Create achievement display embed"""
        stats = player_data['stats']
        unlocked = player_data['unlocked_achievements']
        total_points = player_data['total_points']
        
        embed = discord.Embed(
            title=f"🏆 {user.display_name}'s Achievements",
            description=f"**{len(unlocked)}** achievements unlocked • **{total_points}** points earned",
            color=0xffd700
        )
        
        # Add stats summary
        embed.add_field(
            name="📊 Adventure Stats",
            value=(
                f"Sessions: **{stats.total_sessions or 0}**\n"
                f"Playtime: **{stats.total_playtime_hours or 0:.1f}h**\n"
                f"Highest Level: **{stats.highest_character_level or 1}**\n"
                f"As DM: **{stats.sessions_as_dm or 0}**"
            ),
            inline=True
        )
        
        # Recent achievements (last 5)
        if unlocked:
            recent_achievements = sorted(unlocked, key=lambda x: x[1], reverse=True)[:5]
            recent_text = "\n".join([
                f"{ach.icon} **{ach.name}** ({ach.points} pts)"
                for ach, _ in recent_achievements
            ])
            embed.add_field(
                name="🆕 Recent Achievements",
                value=recent_text,
                inline=True
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Use /achievements progress to see available achievements")
        
        return embed
    
    async def get_leaderboard(self, guild_id: str, category: Optional[str] = None, limit: int = 10) -> List:
        """Get achievement leaderboard for a guild"""
        db = self.db_manager.get_session()
        try:
            # Base query for player stats
            query = db.query(PlayerStats).filter(PlayerStats.guild_id == guild_id)
            
            # Filter by category if specified (could be enhanced to filter achievements by category)
            # For now, just return top players by total achievement points
            
            # Order by total achievement points, then by achievements unlocked
            leaderboard = query.order_by(
                PlayerStats.total_achievement_points.desc(),
                PlayerStats.achievements_unlocked.desc(),
                PlayerStats.total_sessions.desc()
            ).limit(limit).all()
            
            # Format for return
            result = []
            for stats in leaderboard:
                result.append((
                    stats.user_id,
                    stats,
                    getattr(stats, 'total_achievement_points', 0) or 0,
                    getattr(stats, 'achievements_unlocked', 0) or 0
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}")
            return []
        finally:
            db.close()