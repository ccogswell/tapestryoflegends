import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from sqlalchemy import and_, func, desc
from sqlalchemy.orm import Session
from database import get_db_session, DatabaseManager
from models import PlayerStats, RPSession, SessionParticipant, CharacterAlias, GuildMember

logger = logging.getLogger(__name__)

class StatsSystem:
    """Comprehensive statistics tracking system for D&D sessions"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    async def update_session_stats(self, user_id: str, guild_id: str, session_data: Dict):
        """Update player statistics when a session ends or participant changes"""
        try:
            with get_db_session() as db_session:
                # Get or create player stats
                stats = db_session.query(PlayerStats).filter(
                    and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
                ).first()
                
                if not stats:
                    stats = PlayerStats(user_id=user_id, guild_id=guild_id)
                    db_session.add(stats)
                
                # Update session participation stats
                if session_data.get('participated'):
                    stats.total_sessions += 1
                    
                    # Update session type counts
                    session_type = session_data.get('session_type', 'Other').lower()
                    if session_type == 'combat':
                        stats.combat_sessions += 1
                    elif session_type == 'social':
                        stats.social_sessions += 1
                    elif session_type == 'mixed':
                        stats.mixed_sessions += 1
                    else:
                        stats.other_sessions += 1
                
                # Update time stats
                if session_data.get('time_spent_hours'):
                    time_spent = session_data['time_spent_hours']
                    stats.total_session_time_hours += time_spent
                    
                    # Update session type time breakdown
                    session_type = session_data.get('session_type', 'Other').lower()
                    if session_type == 'combat':
                        stats.combat_time_hours += time_spent
                    elif session_type == 'social':
                        stats.social_time_hours += time_spent
                    elif session_type == 'mixed':
                        stats.mixed_time_hours += time_spent
                    else:
                        stats.other_time_hours += time_spent
                    
                    # Update session length metrics
                    if time_spent > stats.longest_session_hours:
                        stats.longest_session_hours = time_spent
                    if time_spent < stats.shortest_session_hours:
                        stats.shortest_session_hours = time_spent
                
                # Update DM stats
                if session_data.get('was_dm'):
                    stats.sessions_as_dm += 1
                    if session_data.get('time_spent_hours'):
                        stats.dm_time_hours += session_data['time_spent_hours']
                    
                    # Update hosted session type counts
                    session_type = session_data.get('session_type', 'Other').lower()
                    if session_type == 'combat':
                        stats.sessions_hosted_combat += 1
                    elif session_type == 'social':
                        stats.sessions_hosted_social += 1
                    elif session_type == 'mixed':
                        stats.sessions_hosted_mixed += 1
                    else:
                        stats.sessions_hosted_other += 1
                
                # Update character stats
                if session_data.get('character_level'):
                    if session_data['character_level'] > stats.highest_character_level:
                        stats.highest_character_level = session_data['character_level']
                
                if session_data.get('new_character'):
                    stats.total_characters_played += 1
                
                # Update reward stats
                if session_data.get('xp_earned'):
                    stats.total_xp_earned += session_data['xp_earned']
                if session_data.get('gold_earned'):
                    stats.total_gold_earned += session_data['gold_earned']
                
                # Update completion stats
                if session_data.get('completed_session'):
                    stats.sessions_completed += 1
                elif session_data.get('left_early'):
                    stats.sessions_early_leave += 1
                
                # Update dates and streaks
                session_date = session_data.get('session_date', datetime.utcnow())
                if not stats.first_session_date:
                    stats.first_session_date = session_date
                stats.last_session_date = session_date
                
                # Update consecutive sessions
                if stats.last_session_date:
                    days_since_last = (session_date - stats.last_session_date).days
                    if days_since_last <= 7:  # Within a week
                        stats.consecutive_sessions += 1
                        if stats.consecutive_sessions > stats.max_consecutive_sessions:
                            stats.max_consecutive_sessions = stats.consecutive_sessions
                    else:
                        stats.consecutive_sessions = 1
                
                # Calculate averages
                if stats.total_sessions > 0:
                    stats.average_session_length_hours = stats.total_session_time_hours / stats.total_sessions
                    stats.average_xp_per_session = stats.total_xp_earned / stats.total_sessions
                    stats.average_gold_per_session = stats.total_gold_earned / stats.total_sessions
                
                # Update weekly/monthly counters
                await self._update_time_period_stats(stats, session_date)
                
                # Calculate favorite session type
                stats.favorite_session_type = self._calculate_favorite_session_type(stats)
                
                db_session.commit()
                logger.info(f"Updated stats for user {user_id} in guild {guild_id}")
                
        except Exception as e:
            logger.error(f"Failed to update session stats: {e}")
    
    async def update_alias_stats(self, user_id: str, guild_id: str, alias_data: Dict):
        """Update player statistics related to alias usage"""
        try:
            with get_db_session() as db_session:
                stats = db_session.query(PlayerStats).filter(
                    and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
                ).first()
                
                if not stats:
                    stats = PlayerStats(user_id=user_id, guild_id=guild_id)
                    db_session.add(stats)
                
                # Update alias stats
                if alias_data.get('message_sent'):
                    stats.alias_messages_sent += 1
                
                if alias_data.get('new_alias'):
                    stats.total_aliases_created += 1
                
                # Get current active alias count
                active_count = db_session.query(CharacterAlias).filter(
                    and_(
                        CharacterAlias.user_id == user_id,
                        CharacterAlias.guild_id == guild_id,
                        CharacterAlias.is_active == True
                    )
                ).count()
                stats.active_aliases = active_count
                
                # Get unique character names count
                unique_names = db_session.query(CharacterAlias.name).filter(
                    and_(
                        CharacterAlias.user_id == user_id,
                        CharacterAlias.guild_id == guild_id
                    )
                ).distinct().count()
                stats.unique_character_names = unique_names
                
                db_session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update alias stats: {e}")
    
    async def update_message_stats(self, user_id: str, guild_id: str, message_count: int = 1):
        """Update message statistics for a user during sessions"""
        try:
            with get_db_session() as db_session:
                stats = db_session.query(PlayerStats).filter(
                    and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
                ).first()
                
                if not stats:
                    stats = PlayerStats(user_id=user_id, guild_id=guild_id)
                    db_session.add(stats)
                
                stats.messages_sent_in_sessions += message_count
                db_session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update message stats: {e}")
    
    async def ensure_player_stats_exist(self, user_id: str, guild_id: str) -> PlayerStats:
        """Ensure a PlayerStats record exists for the user, create if needed"""
        try:
            with get_db_session() as db_session:
                stats = db_session.query(PlayerStats).filter(
                    and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
                ).first()
                
                if not stats:
                    stats = PlayerStats(
                        user_id=user_id, 
                        guild_id=guild_id,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db_session.add(stats)
                    db_session.commit()
                    logger.info(f"Created new PlayerStats for user {user_id} in guild {guild_id}")
                
                return stats
        except Exception as e:
            logger.error(f"Error ensuring player stats exist: {e}")
            raise
    
    async def get_player_stats(self, user_id: str, guild_id: str) -> Optional[PlayerStats]:
        """Get comprehensive player statistics"""
        try:
            with get_db_session() as db_session:
                stats = db_session.query(PlayerStats).filter(
                    and_(PlayerStats.user_id == user_id, PlayerStats.guild_id == guild_id)
                ).first()
                
                if not stats:
                    # Create default stats if none exist
                    stats = PlayerStats(user_id=user_id, guild_id=guild_id)
                    db_session.add(stats)
                    db_session.commit()
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get player stats: {e}")
            return None
    
    async def get_guild_stats_summary(self, guild_id: str) -> Dict:
        """Get overall guild statistics summary"""
        try:
            with get_db_session() as db_session:
                # Total sessions
                total_sessions = db_session.query(RPSession).filter(
                    RPSession.guild_id == guild_id
                ).count()
                
                # Active sessions
                active_sessions = db_session.query(RPSession).filter(
                    and_(RPSession.guild_id == guild_id, RPSession.is_active == True)
                ).count()
                
                # Sessions by type
                session_types = db_session.query(
                    RPSession.session_type,
                    func.count(RPSession.id)
                ).filter(RPSession.guild_id == guild_id).group_by(RPSession.session_type).all()
                
                # Total playtime
                total_playtime = db_session.query(
                    func.sum(PlayerStats.total_session_time_hours)
                ).filter(PlayerStats.guild_id == guild_id).scalar() or 0
                
                # Most active players
                top_players = db_session.query(
                    PlayerStats.user_id,
                    PlayerStats.total_sessions,
                    PlayerStats.total_session_time_hours
                ).filter(PlayerStats.guild_id == guild_id).order_by(
                    desc(PlayerStats.total_sessions)
                ).limit(5).all()
                
                # Most active DMs
                top_dms = db_session.query(
                    PlayerStats.user_id,
                    PlayerStats.sessions_as_dm,
                    PlayerStats.dm_time_hours
                ).filter(
                    and_(PlayerStats.guild_id == guild_id, PlayerStats.sessions_as_dm > 0)
                ).order_by(desc(PlayerStats.sessions_as_dm)).limit(5).all()
                
                return {
                    'total_sessions': total_sessions,
                    'active_sessions': active_sessions,
                    'sessions_by_type': dict(session_types),
                    'total_playtime_hours': total_playtime,
                    'top_players': top_players,
                    'top_dms': top_dms
                }
                
        except Exception as e:
            logger.error(f"Failed to get guild stats: {e}")
            return {}
    
    async def get_leaderboard(self, guild_id: str, category: str = 'total_sessions', limit: int = 10) -> List[Tuple]:
        """Get leaderboard for specified category"""
        try:
            with get_db_session() as db_session:
                valid_categories = {
                    'total_sessions': PlayerStats.total_sessions,
                    'total_time': PlayerStats.total_session_time_hours,
                    'sessions_as_dm': PlayerStats.sessions_as_dm,
                    'dm_time': PlayerStats.dm_time_hours,
                    'xp_earned': PlayerStats.total_xp_earned,
                    'gold_earned': PlayerStats.total_gold_earned,
                    'aliases_created': PlayerStats.total_aliases_created,
                    'active_aliases': PlayerStats.active_aliases,
                    'messages_sent': PlayerStats.messages_sent_in_sessions,
                    'alias_messages': PlayerStats.alias_messages_sent,
                    'characters_played': PlayerStats.total_characters_played,
                    'consecutive_sessions': PlayerStats.consecutive_sessions,
                    'max_streak': PlayerStats.max_consecutive_sessions,
                    'combat_sessions': PlayerStats.combat_sessions,
                    'social_sessions': PlayerStats.social_sessions,
                    'longest_session': PlayerStats.longest_session_hours,
                    'achievement_points': PlayerStats.total_achievement_points
                }
                
                if category not in valid_categories:
                    category = 'total_sessions'
                
                order_column = valid_categories[category]
                
                leaderboard = db_session.query(
                    PlayerStats.user_id,
                    order_column
                ).filter(
                    and_(PlayerStats.guild_id == guild_id, order_column > 0)
                ).order_by(desc(order_column)).limit(limit).all()
                
                return leaderboard
                
        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}")
            return []
    
    def _calculate_favorite_session_type(self, stats: PlayerStats) -> str:
        """Calculate the player's favorite session type based on participation"""
        types = {
            'Combat': stats.combat_sessions,
            'Social': stats.social_sessions,
            'Mixed': stats.mixed_sessions,
            'Other': stats.other_sessions
        }
        
        if not any(types.values()):
            return None
        
        return max(types, key=types.get)
    
    async def _update_time_period_stats(self, stats: PlayerStats, session_date: datetime):
        """Update weekly and monthly session counters"""
        now = datetime.utcnow()
        
        # Weekly stats
        if not stats.week_start_date or (now - stats.week_start_date).days >= 7:
            stats.week_start_date = now
            stats.sessions_this_week = 1
        else:
            stats.sessions_this_week += 1
        
        # Monthly stats
        if not stats.month_start_date or stats.month_start_date.month != now.month:
            stats.month_start_date = now
            stats.sessions_this_month = 1
        else:
            stats.sessions_this_month += 1
    
    async def reset_weekly_stats(self, guild_id: str):
        """Reset weekly statistics for all players (call this weekly)"""
        try:
            with get_db_session() as db_session:
                db_session.query(PlayerStats).filter(
                    PlayerStats.guild_id == guild_id
                ).update({
                    'sessions_this_week': 0,
                    'week_start_date': datetime.utcnow()
                })
                db_session.commit()
                logger.info(f"Reset weekly stats for guild {guild_id}")
                
        except Exception as e:
            logger.error(f"Failed to reset weekly stats: {e}")
    
    async def reset_monthly_stats(self, guild_id: str):
        """Reset monthly statistics for all players (call this monthly)"""
        try:
            with get_db_session() as db_session:
                db_session.query(PlayerStats).filter(
                    PlayerStats.guild_id == guild_id
                ).update({
                    'sessions_this_month': 0,
                    'month_start_date': datetime.utcnow()
                })
                db_session.commit()
                logger.info(f"Reset monthly stats for guild {guild_id}")
                
        except Exception as e:
            logger.error(f"Failed to reset monthly stats: {e}")