import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
import discord
import json
import os
import logging
from database import get_db_session
from models import GuildMember

logger = logging.getLogger(__name__)

class RPSession:
    """Represents a roleplay session"""
    
    def __init__(self, session_id: str, dm_id: int, channel_id: int, session_name: Optional[str] = None, session_type: Optional[str] = None, max_players: Optional[int] = None, thread_id: Optional[int] = None, session_description: Optional[str] = None):
        self.session_id = session_id
        self.dm_id = dm_id
        self.channel_id = channel_id
        self.session_name = session_name or session_id
        self.session_type = session_type or "Other"
        self.max_players = max_players or 6  # Default to 6 if not specified
        self.thread_id = thread_id
        self.session_description = session_description
        self.start_time = None  # Will be set when session is manually started
        self.created_time = datetime.now()  # When the session was created
        self.end_time = None
        self.pause_time = None
        self.total_paused_duration = timedelta()
        self.is_active = True
        self.is_paused = False
        self.session_started = False  # New flag to track if session timer has started
        self.participants: Dict[int, datetime] = {}  # user_id -> join_time
        self.participant_times: Dict[int, timedelta] = {}  # user_id -> total_time
        self.participant_characters: Dict[int, Dict[str, Any]] = {}  # user_id -> {'name': str, 'level': int}
        self.participant_display_names: Dict[int, str] = {}  # user_id -> display_name
        self.pause_start = None

    def store_display_name(self, user_id: int, display_name: str):
        """Store a user's display name for later use"""
        self.participant_display_names[user_id] = display_name
    
    def get_display_name(self, user_id: int, guild_id: Optional[str] = None) -> str:
        """Get display name for a user, using database lookup for better performance"""
        # First check if we have it stored in session
        if user_id in self.participant_display_names:
            return self.participant_display_names[user_id]
        
        # Try database lookup if guild_id is available
        if guild_id:
            try:
                with get_db_session() as db_session:
                    member = db_session.query(GuildMember).filter(
                        GuildMember.guild_id == str(guild_id),
                        GuildMember.user_id == str(user_id)
                    ).first()
                    
                    if member:
                        # Use display name with priority: nickname > global_name > username
                        display_name = member.nickname or member.global_name or member.username
                        # Cache it for future use
                        self.participant_display_names[user_id] = display_name
                        return display_name
            except Exception as e:
                logger.error(f"Database lookup failed for user {user_id}: {e}")
        
        # Fallback to user ID
        return f"User{str(user_id)[-4:]}"
        
    def start_session(self) -> bool:
        """Manually start the session timer"""
        if not self.session_started and self.is_active:
            self.start_time = datetime.now()
            self.session_started = True
            # Update join times for existing participants
            current_time = self.start_time
            for user_id in self.participants:
                self.participants[user_id] = current_time
            return True
        return False
        
    def add_participant(self, user_id: int, character_name: Optional[str] = None, character_level: Optional[int] = None) -> bool:
        """Add a participant to the session"""
        if user_id not in self.participants and self.is_active:
            # Check if session is full
            if len(self.participants) >= self.max_players:
                return False
            
            # If session hasn't started yet, use creation time as placeholder
            if not self.session_started:
                join_time = self.created_time
            else:
                join_time = datetime.now() if not self.is_paused else (self.pause_start or datetime.now())
            
            self.participants[user_id] = join_time
            if user_id not in self.participant_times:
                self.participant_times[user_id] = timedelta()
            
            # Store character information
            if character_name and character_level is not None:
                self.participant_characters[user_id] = {
                    'name': character_name,
                    'level': character_level
                }
            return True
        return False

    def remove_participant(self, user_id: int) -> bool:
        """Remove a participant from the session"""
        if user_id in self.participants:
            # Calculate time spent before removal
            if not self.is_paused:
                leave_time = datetime.now()
                time_spent = leave_time - self.participants[user_id]
                self.participant_times[user_id] += time_spent
            else:
                # If paused, calculate time up to pause
                if self.pause_start:
                    time_spent = self.pause_start - self.participants[user_id]
                    self.participant_times[user_id] += time_spent
            
            del self.participants[user_id]
            # Keep character info for reward calculation, don't remove it
            return True
        return False

    def pause_session(self):
        """Pause the session"""
        if self.is_active and not self.is_paused:
            self.is_paused = True
            self.pause_start = datetime.now()
            
            # Update participant times up to pause point
            for user_id, join_time in self.participants.items():
                time_spent = self.pause_start - join_time
                self.participant_times[user_id] += time_spent
                self.participants[user_id] = self.pause_start

    def resume_session(self):
        """Resume the session"""
        if self.is_active and self.is_paused:
            self.is_paused = False
            resume_time = datetime.now()
            
            if self.pause_start:
                self.total_paused_duration += resume_time - self.pause_start
            
            # Update participant join times to resume time
            for user_id in self.participants:
                self.participants[user_id] = resume_time
            
            self.pause_start = None

    def end_session(self):
        """End the session"""
        if self.is_active:
            self.is_active = False
            self.end_time = datetime.now()
            
            # Calculate final times for all participants
            end_time = self.pause_start if self.is_paused else self.end_time
            
            for user_id, join_time in self.participants.items():
                if end_time:
                    time_spent = end_time - join_time
                    self.participant_times[user_id] += time_spent

    def get_session_duration(self) -> timedelta:
        """Get total session duration excluding paused time"""
        # If session hasn't started yet, return zero duration
        if not self.session_started or not self.start_time:
            return timedelta()
            
        if not self.is_active and self.end_time:
            return (self.end_time - self.start_time) - self.total_paused_duration
        elif self.is_paused and self.pause_start:
            return (self.pause_start - self.start_time) - self.total_paused_duration
        else:
            return (datetime.now() - self.start_time) - self.total_paused_duration

    def get_participant_time(self, user_id: int) -> timedelta:
        """Get total time a participant has spent in the session"""
        total_time = self.participant_times.get(user_id, timedelta())
        
        # Add current active time if participant is still in session and session has started
        if user_id in self.participants and self.is_active and self.session_started:
            if not self.is_paused:
                current_time = datetime.now() - self.participants[user_id]
                total_time += current_time
        
        return total_time
    
    def is_full(self) -> bool:
        """Check if the session has reached maximum capacity"""
        return len(self.participants) >= self.max_players
    
    def get_active_player_count(self) -> int:
        """Get the current number of active players"""
        return len(self.participants)

class SessionManager:
    """Manages all roleplay sessions across guilds"""
    
    def __init__(self):
        self.sessions: Dict[int, Dict[str, RPSession]] = {}  # guild_id -> {session_id -> session}
        self.active_sessions: Dict[int, Set[str]] = {}  # guild_id -> {active_session_ids}
        self.use_persistence = os.getenv('REPLIT_DEPLOYMENT') == '1'  # Only use persistence in deployment
        self.use_database = os.getenv('DATABASE_URL') is not None  # Use PostgreSQL if available
        
        # Initialize database if available
        self.db_manager = None
        if self.use_database:
            try:
                from database import DatabaseManager
                self.db_manager = DatabaseManager()
                logger.info("PostgreSQL database initialized successfully")
                self._load_sessions_from_database()
            except Exception as e:
                logger.warning(f"Failed to initialize database, falling back to file storage: {e}")
                self.use_database = False
                
        if not self.use_database:
            self._load_sessions_from_storage()

    def initialize_guild(self, guild_id: int):
        """Initialize session storage for a guild"""
        if guild_id not in self.sessions:
            self.sessions[guild_id] = {}
            self.active_sessions[guild_id] = set()

    def create_session(self, guild_id: int, session_id: str, dm_id: int, channel_id: int, session_name: Optional[str] = None, session_type: Optional[str] = None, max_players: Optional[int] = None, thread_id: Optional[int] = None, session_description: Optional[str] = None) -> Optional[RPSession]:
        """Create a new roleplay session"""
        self.initialize_guild(guild_id)
        
        if session_id in self.sessions[guild_id]:
            return None  # Session already exists
        
        session = RPSession(session_id, dm_id, channel_id, session_name, session_type, max_players, thread_id, session_description)
        self.sessions[guild_id][session_id] = session
        self.active_sessions[guild_id].add(session_id)
        
        # Save state after creating session
        if self.use_database:
            self._save_session_to_database(session, guild_id)
        else:
            self._save_sessions_to_storage()
        
        return session

    def get_session(self, guild_id: int, session_id: str) -> Optional[RPSession]:
        """Get a session by ID"""
        if guild_id in self.sessions:
            return self.sessions[guild_id].get(session_id)
        return None

    def get_active_sessions(self, guild_id: int) -> List[RPSession]:
        """Get all active sessions for a guild"""
        if guild_id not in self.active_sessions:
            return []
        
        active_sessions = []
        for session_id in self.active_sessions[guild_id]:
            session = self.sessions[guild_id].get(session_id)
            if session and session.is_active:
                active_sessions.append(session)
        
        return active_sessions

    def end_session(self, guild_id: int, session_id: str) -> Optional[RPSession]:
        """End a session"""
        session = self.get_session(guild_id, session_id)
        if session and session.is_active:
            session.end_session()
            if guild_id in self.active_sessions:
                self.active_sessions[guild_id].discard(session_id)
            
            # Save state after ending session
            if self.use_database:
                self._save_session_to_database(session, guild_id)
            else:
                self._save_sessions_to_storage()
            return session
        return None

    def get_user_active_sessions(self, guild_id: int, user_id: int) -> List[RPSession]:
        """Get all active sessions a user is participating in"""
        user_sessions = []
        for session in self.get_active_sessions(guild_id):
            if user_id in session.participants:
                user_sessions.append(session)
        return user_sessions

    def is_user_dm_of_active_session(self, guild_id: int, user_id: int) -> bool:
        """Check if user is DM of any active session"""
        for session in self.get_active_sessions(guild_id):
            if session.dm_id == user_id:
                return True
        return False
    
    def _session_to_dict(self, session: RPSession) -> dict:
        """Convert a session to a dictionary for storage"""
        return {
            'session_id': session.session_id,
            'dm_id': session.dm_id,
            'channel_id': session.channel_id,
            'session_name': session.session_name,
            'session_type': session.session_type,
            'max_players': session.max_players,
            'thread_id': session.thread_id,
            'start_time': session.start_time.isoformat() if session.start_time else None,
            'end_time': session.end_time.isoformat() if session.end_time else None,
            # pause_time is transient state, not persisted
            'total_paused_duration': session.total_paused_duration.total_seconds(),
            'is_active': session.is_active,
            'is_paused': session.is_paused,
            'participants': {str(uid): dt.isoformat() for uid, dt in session.participants.items()},
            'participant_times': {str(uid): td.total_seconds() for uid, td in session.participant_times.items()},
            'participant_characters': {str(uid): chars for uid, chars in session.participant_characters.items()},
            'pause_start': session.pause_start.isoformat() if session.pause_start else None
        }
    
    def _dict_to_session(self, data: dict) -> RPSession:
        """Convert a dictionary to a session object"""
        session = RPSession(
            data['session_id'],
            data['dm_id'],
            data['channel_id'],
            data.get('session_name'),
            data.get('session_type'),
            data.get('max_players'),
            data.get('thread_id')
        )
        
        session.start_time = datetime.fromisoformat(data['start_time'])
        session.end_time = datetime.fromisoformat(data['end_time']) if data.get('end_time') else None
        # Note: pause_time is not settable directly, handled via pause/resume methods
        session.total_paused_duration = timedelta(seconds=data.get('total_paused_duration', 0))
        session.is_active = data.get('is_active', True)
        session.is_paused = data.get('is_paused', False)
        session.participants = {int(uid): datetime.fromisoformat(dt) for uid, dt in data.get('participants', {}).items()}
        session.participant_times = {int(uid): timedelta(seconds=seconds) for uid, seconds in data.get('participant_times', {}).items()}
        session.participant_characters = {int(uid): chars for uid, chars in data.get('participant_characters', {}).items()}
        session.pause_start = datetime.fromisoformat(data['pause_start']) if data.get('pause_start') else None
        
        return session
    
    def _save_sessions_to_storage(self):
        """Save all sessions to persistent storage"""
        if not self.use_persistence:
            return
            
        try:
            # Use a simple file-based storage since ReplDB might not be available
            storage_data = {}
            for guild_id, guild_sessions in self.sessions.items():
                storage_data[str(guild_id)] = {
                    'sessions': {sid: self._session_to_dict(session) for sid, session in guild_sessions.items()},
                    'active_sessions': list(self.active_sessions.get(guild_id, set()))
                }
            
            with open('/tmp/sessions_backup.json', 'w') as f:
                json.dump(storage_data, f, indent=2)
                
        except Exception as e:
            print(f"Warning: Failed to save sessions to storage: {e}")
    
    def _load_sessions_from_storage(self):
        """Load sessions from persistent storage"""
        if not self.use_persistence:
            return
            
        try:
            if os.path.exists('/tmp/sessions_backup.json'):
                with open('/tmp/sessions_backup.json', 'r') as f:
                    storage_data = json.load(f)
                
                for guild_id_str, guild_data in storage_data.items():
                    guild_id = int(guild_id_str)
                    self.sessions[guild_id] = {}
                    self.active_sessions[guild_id] = set(guild_data.get('active_sessions', []))
                    
                    for session_id, session_data in guild_data.get('sessions', {}).items():
                        session = self._dict_to_session(session_data)
                        self.sessions[guild_id][session_id] = session
                        
                print(f"Loaded {sum(len(guild_sessions) for guild_sessions in self.sessions.values())} sessions from storage")
                        
        except Exception as e:
            print(f"Warning: Failed to load sessions from storage: {e}")
            
    def save_session_state(self):
        """Public method to save current session state"""
        if self.use_database:
            self._save_all_sessions_to_database()
        else:
            self._save_sessions_to_storage()
    
    def _load_sessions_from_database(self):
        """Load sessions from PostgreSQL database"""
        if not self.db_manager:
            return
            
        try:
            # Query database for all active sessions across all guilds
            db = self.db_manager.get_session()
            try:
                from models import RPSession as DBRPSession
                active_db_sessions = db.query(DBRPSession).filter(DBRPSession.is_active == True).all()
                
                for db_session in active_db_sessions:
                    guild_id = db_session.guild_id
                    
                    # Convert database session to memory session
                    session_data = {
                        'session_id': db_session.session_id,
                        'dm_id': db_session.dm_id,
                        'channel_id': db_session.channel_id,
                        'thread_id': db_session.thread_id,
                        'session_name': db_session.session_name,
                        'session_type': db_session.session_type,
                        'max_players': db_session.max_players,
                        'start_time': db_session.start_time,
                        'end_time': db_session.end_time,
                        'total_paused_duration': db_session.total_paused_duration_seconds or 0,
                        'is_active': db_session.is_active,
                        'is_paused': db_session.is_paused,
                        'pause_start': db_session.pause_start,
                        'participants': {},
                        'participant_times': {},
                        'participant_characters': {}
                    }
                    
                    # Load participants for this session
                    for participant in db_session.participants:
                        if participant.is_active:
                            session_data['participants'][participant.user_id] = participant.join_time
                        
                        session_data['participant_times'][participant.user_id] = timedelta(seconds=participant.total_time_seconds)
                        
                        if participant.character_name and participant.character_level:
                            session_data['participant_characters'][participant.user_id] = {
                                'name': participant.character_name,
                                'level': participant.character_level
                            }
                    
                    # Convert to session object and store
                    session = self._dict_to_session(session_data)
                    if guild_id not in self.sessions:
                        self.sessions[guild_id] = {}
                        self.active_sessions[guild_id] = set()
                    
                    self.sessions[guild_id][session.session_id] = session
                    if session.is_active:
                        self.active_sessions[guild_id].add(session.session_id)
                
                total_loaded = sum(len(guild_sessions) for guild_sessions in self.sessions.values())
                if total_loaded > 0:
                    logger.info(f"Loaded {total_loaded} active sessions from PostgreSQL database")
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to load sessions from database: {e}")
    
    def _save_session_to_database(self, session: RPSession, guild_id: int):
        """Save a single session to PostgreSQL database"""
        if not self.db_manager:
            return
            
        try:
            session_data = self._session_to_dict(session)
            session_db_id = self.db_manager.save_session_to_db(session_data, guild_id)
            
            # Save participants
            for user_id, char_data in session.participant_characters.items():
                participant_data = {
                    'user_id': user_id,
                    'character_name': char_data.get('name'),
                    'character_level': char_data.get('level'),
                    'join_time': session.participants.get(user_id),
                    'total_time_seconds': int(session.participant_times.get(user_id, timedelta()).total_seconds()),
                    'is_active': user_id in session.participants
                }
                self.db_manager.save_participant_to_db(session_db_id, participant_data)
                
        except Exception as e:
            logger.error(f"Failed to save session to database: {e}")
    
    def _save_all_sessions_to_database(self):
        """Save all sessions to PostgreSQL database"""
        if not self.db_manager:
            return
            
        try:
            for guild_id, guild_sessions in self.sessions.items():
                for session in guild_sessions.values():
                    self._save_session_to_database(session, guild_id)
                    
        except Exception as e:
            logger.error(f"Failed to save all sessions to database: {e}")
    
    def save_rewards_to_database(self, guild_id: int, session_id: str, rewards_data: list):
        """Save session rewards to database"""
        if not self.db_manager:
            return
            
        try:
            # Find the database session ID
            from models import RPSession as DBRPSession
            db = self.db_manager.get_session()
            try:
                db_session = db.query(DBRPSession).filter(
                    DBRPSession.guild_id == guild_id,
                    DBRPSession.session_id == session_id
                ).first()
                
                if db_session:
                    self.db_manager.save_rewards_to_db(db_session.id, rewards_data)
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to save rewards to database: {e}")
