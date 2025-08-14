import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from models import Base, Guild, RPSession, SessionParticipant, SessionReward, CharacterAlias, SharedGroup, SharedGroupPermission, GroupPermission
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Database manager for PostgreSQL operations"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        # Create engine with improved connection handling
        self.engine = create_engine(
            self.database_url, 
            echo=False,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                "sslmode": "prefer",
                "connect_timeout": 10,
                "application_name": "discord_bot"
            }
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Create tables
        self.create_tables()
    
    def create_tables(self):
        """Create all tables if they don't exist"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created/verified successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def get_session(self):
        """Get a new database session with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = self.SessionLocal()
                # Test the connection
                session.execute(text("SELECT 1")).fetchone()
                return session
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"All database connection attempts failed: {e}")
                    raise
    
    def ensure_guild_exists(self, guild_id: int, guild_name: str = None) -> Guild:
        """Ensure guild exists in database"""
        db = self.get_session()
        try:
            guild_id_str = str(guild_id)
            guild = db.query(Guild).filter(Guild.id == guild_id_str).first()
            if not guild:
                guild = Guild(id=guild_id_str, name=guild_name or f"Guild {guild_id}")
                db.add(guild)
                db.commit()
                logger.info(f"Created guild record for {guild_name or 'Unknown Guild'} ({guild_id})")
            return guild
        finally:
            db.close()
    
    def save_session_to_db(self, session_data: dict, guild_id: int):
        """Save session data to database"""
        db = self.get_session()
        try:
            # Ensure guild exists
            self.ensure_guild_exists(guild_id)
            
            # Check if session already exists
            guild_id_str = str(guild_id)
            existing = db.query(RPSession).filter(
                RPSession.guild_id == guild_id_str,
                RPSession.session_id == session_data['session_id']
            ).first()
            
            if existing:
                # Update existing session
                for key, value in session_data.items():
                    if key == 'total_paused_duration':
                        setattr(existing, 'total_paused_duration_seconds', int(value))
                    elif hasattr(existing, key):
                        setattr(existing, key, value)
                db_session = existing
            else:
                # Create new session
                session_data_copy = session_data.copy()
                if 'total_paused_duration' in session_data_copy:
                    session_data_copy['total_paused_duration_seconds'] = int(session_data_copy.pop('total_paused_duration'))
                
                # Convert IDs to strings
                session_data_copy['guild_id'] = str(guild_id)
                session_data_copy['dm_id'] = str(session_data_copy['dm_id'])
                session_data_copy['channel_id'] = str(session_data_copy['channel_id'])
                if session_data_copy.get('thread_id'):
                    session_data_copy['thread_id'] = str(session_data_copy['thread_id'])
                
                db_session = RPSession(**session_data_copy)
                db.add(db_session)
            
            db.commit()
            return db_session.id
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save session to database: {e}")
            raise
        finally:
            db.close()
    
    def save_participant_to_db(self, session_db_id: int, participant_data: dict):
        """Save participant data to database"""
        db = self.get_session()
        try:
            # Check if participant already exists for this session
            existing = db.query(SessionParticipant).filter(
                SessionParticipant.session_db_id == session_db_id,
                SessionParticipant.user_id == participant_data['user_id']
            ).first()
            
            if existing:
                # Update existing participant
                for key, value in participant_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                participant = existing
            else:
                # Create new participant
                participant = SessionParticipant(session_db_id=session_db_id, **participant_data)
                db.add(participant)
            
            db.commit()
            return participant.id
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save participant to database: {e}")
            raise
        finally:
            db.close()
    
    def load_active_sessions_from_db(self, guild_id: int):
        """Load all active sessions for a guild from database"""
        db = self.get_session()
        try:
            guild_id_str = str(guild_id)
            sessions = db.query(RPSession).filter(
                RPSession.guild_id == guild_id_str,
                RPSession.is_active.is_(True)
            ).all()
            
            session_data = []
            for session in sessions:
                session_dict = {
                    'session_id': session.session_id,
                    'dm_id': session.dm_id,
                    'channel_id': session.channel_id,
                    'thread_id': session.thread_id,
                    'session_name': session.session_name,
                    'session_type': session.session_type,
                    'max_players': session.max_players,
                    'start_time': session.start_time,
                    'end_time': session.end_time,
                    'total_paused_duration': session.total_paused_duration_seconds or 0,
                    'is_active': session.is_active,
                    'is_paused': session.is_paused,
                    'pause_start': session.pause_start,
                    'participants': {},
                    'participant_times': {},
                    'participant_characters': {}
                }
                
                # Load participants
                for participant in session.participants:
                    if participant.is_active:
                        session_dict['participants'][participant.user_id] = participant.join_time
                    
                    session_dict['participant_times'][participant.user_id] = participant.total_time_seconds
                    
                    if participant.character_name and participant.character_level:
                        session_dict['participant_characters'][participant.user_id] = {
                            'name': participant.character_name,
                            'level': participant.character_level
                        }
                
                session_data.append(session_dict)
            
            return session_data
            
        except Exception as e:
            logger.error(f"Failed to load sessions from database: {e}")
            return []
        finally:
            db.close()
    
    def save_rewards_to_db(self, session_db_id: int, rewards_data: list):
        """Save session rewards to database"""
        db = self.get_session()
        try:
            for reward in rewards_data:
                db_reward = SessionReward(session_db_id=session_db_id, **reward)
                db.add(db_reward)
            
            db.commit()
            logger.info(f"Saved {len(rewards_data)} rewards to database")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save rewards to database: {e}")
            raise
        finally:
            db.close()
    
    def get_session_statistics(self, guild_id: int):
        """Get session statistics for a guild"""
        db = self.get_session()
        try:
            total_sessions = db.query(RPSession).filter(RPSession.guild_id == guild_id).count()
            active_sessions = db.query(RPSession).filter(
                RPSession.guild_id == guild_id,
                RPSession.is_active == True
            ).count()
            
            return {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions
            }
        finally:
            db.close()

# Initialize database instance
db_manager = DatabaseManager()

def get_db_session():
    """Get a database session for web interface"""
    return db_manager.get_session()