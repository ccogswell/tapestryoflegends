from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Guild(Base):
    """Discord Guild/Server model"""
    __tablename__ = 'guilds'
    
    id = Column(String(20), primary_key=True)  # Discord guild ID (BigInt as string)
    name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_member_sync = Column(DateTime, nullable=True)  # When members were last cached
    
    # Relationships
    sessions = relationship("RPSession", back_populates="guild")
    members = relationship("GuildMember", back_populates="guild")

class GuildMember(Base):
    """Cached Discord Guild Member model"""
    __tablename__ = 'guild_members'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    user_id = Column(String(20), nullable=False)  # Discord user ID
    
    # User information
    username = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=True)  # Nickname in this guild
    discriminator = Column(String(10), nullable=True)  # May be None for new usernames
    avatar_url = Column(String(500), nullable=True)
    
    # Guild-specific info
    joined_at = Column(DateTime, nullable=True)
    roles = Column(Text, nullable=True)  # JSON string of role IDs
    
    # Cache metadata
    cached_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)  # False if user left the guild
    
    # Relationships
    guild = relationship("Guild", back_populates="members")
    
    # Unique constraint: one record per user per guild
    __table_args__ = (
        UniqueConstraint('guild_id', 'user_id', name='unique_guild_member'),
    )

class RPSession(Base):
    """Roleplay Session model"""
    __tablename__ = 'rp_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), nullable=False)  # User-friendly session ID
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    dm_id = Column(String(20), nullable=False)  # Discord user ID of DM
    channel_id = Column(String(20), nullable=False)  # Discord channel ID
    thread_id = Column(String(20), nullable=True)  # Discord thread ID
    
    # Session details
    session_name = Column(String(100))
    session_type = Column(String(20), default='Mixed')  # Combat, Social, Mixed, Other
    max_players = Column(Integer, default=6)
    
    # Time tracking
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    total_paused_duration_seconds = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    pause_start = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild", back_populates="sessions")
    participants = relationship("SessionParticipant", back_populates="session")
    
    # Unique constraint on session_id per guild
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

class SessionParticipant(Base):
    """Session Participant model"""
    __tablename__ = 'session_participants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_db_id = Column(Integer, ForeignKey('rp_sessions.id'), nullable=False)
    user_id = Column(String(20), nullable=False)  # Discord user ID
    
    # Character information
    character_name = Column(String(100))
    character_level = Column(Integer)
    
    # Time tracking
    join_time = Column(DateTime, default=datetime.utcnow)
    leave_time = Column(DateTime, nullable=True)
    total_time_seconds = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)  # Currently in session
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    session = relationship("RPSession", back_populates="participants")

class SessionReward(Base):
    """Session Rewards model"""
    __tablename__ = 'session_rewards'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_db_id = Column(Integer, ForeignKey('rp_sessions.id'), nullable=False)
    user_id = Column(String(20), nullable=False)  # Discord user ID
    
    # Character info at time of reward
    character_name = Column(String(100))
    character_level = Column(Integer)
    
    # Time and rewards
    participation_time_seconds = Column(Integer, default=0)
    base_xp = Column(Integer, default=0)
    base_gold = Column(Integer, default=0)
    bonus_multiplier = Column(Float, default=1.0)
    final_xp = Column(Integer, default=0)
    final_gold = Column(Integer, default=0)
    
    # Metadata
    calculated_at = Column(DateTime, default=datetime.utcnow)

# Achievement System Models

class Achievement(Base):
    """Achievement definitions"""
    __tablename__ = 'achievements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)  # Unique identifier
    name = Column(String(100), nullable=False)  # Display name
    description = Column(Text, nullable=False)  # Description
    category = Column(String(30), nullable=False)  # Category (session, character, community, milestone)
    icon = Column(String(10), default='🏆')  # Discord emoji
    points = Column(Integer, default=10)  # Achievement points
    is_hidden = Column(Boolean, default=False)  # Hidden until unlocked
    is_active = Column(Boolean, default=True)  # Can be earned
    
    # Requirements (JSON-like fields stored as strings)
    requirement_type = Column(String(30), nullable=False)  # sessions_count, level_reached, etc.
    requirement_value = Column(Integer, default=1)  # Threshold value
    requirement_data = Column(Text)  # Additional requirements as JSON string

class SharedGroup(Base):
    """Shared alias group with permission system"""
    __tablename__ = 'shared_groups'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    owner_id = Column(String(20), nullable=False)  # Discord user ID of group owner
    
    # Group details
    group_name = Column(String(100), nullable=False)
    subgroup_name = Column(String(100))  # Optional subgroup
    description = Column(Text)
    
    # Settings
    is_active = Column(Boolean, default=True)
    allow_member_invites = Column(Boolean, default=False)  # Can managers invite others
    is_single_alias = Column(Boolean, default=False)  # True if this is for a single alias
    single_alias_id = Column(Integer, nullable=True)  # ID of the single alias if applicable
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild")
    permissions = relationship("SharedGroupPermission", back_populates="shared_group", cascade="all, delete-orphan")
    aliases = relationship("CharacterAlias", back_populates="shared_group")

class SharedGroupPermission(Base):
    """User permissions for shared alias groups"""
    __tablename__ = 'shared_group_permissions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    shared_group_id = Column(Integer, ForeignKey('shared_groups.id'), nullable=False)
    user_id = Column(String(20), nullable=False)  # Discord user ID
    
    # Permission level: 'owner', 'manager', 'speaker'
    permission_level = Column(String(20), nullable=False)
    
    # Metadata
    granted_by = Column(String(20), nullable=False)  # Who granted this permission
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    shared_group = relationship("SharedGroup", back_populates="permissions")

class GroupPermission(Base):
    """Simple permissions for existing alias groups - no separate shared_groups table needed"""
    __tablename__ = 'group_permissions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    group_name = Column(String(100), nullable=False)
    subgroup_name = Column(String(100), nullable=True)
    owner_id = Column(String(20), nullable=False)  # Discord user ID who owns/created the group
    user_id = Column(String(20), nullable=False)  # Discord user ID who has permission
    permission_level = Column(String(20), nullable=False)  # 'owner', 'manager', 'speaker'
    granted_by = Column(String(20), nullable=False)  # Discord user ID who granted permission
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild")
    
    # Ensure unique permission per user per group
    __table_args__ = (
        UniqueConstraint('guild_id', 'group_name', 'subgroup_name', 'user_id', name='_group_user_permission_uc'),
    )

class CharacterAlias(Base):
    """Character alias model for roleplay posting"""
    __tablename__ = 'character_aliases'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), nullable=False)  # Discord user ID (creator)
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    
    # Shared group association
    shared_group_id = Column(Integer, ForeignKey('shared_groups.id'), nullable=True)
    
    # Character details
    name = Column(String(100), nullable=False)  # Character name
    trigger = Column(String(200), nullable=False)  # Trigger pattern (e.g., "k:", "[text]")
    avatar_url = Column(Text, nullable=False)  # Character avatar URL
    group_name = Column(String(100), nullable=True)  # Optional group/campaign name
    
    # Extended character information
    character_class = Column(String(100), nullable=True)  # Class and level (e.g., "Wizard 5")
    race = Column(String(100), nullable=True)  # Character race/species
    pronouns = Column(String(50), nullable=True)  # Character pronouns
    age = Column(String(10), nullable=True)  # Character age (stored as string for flexibility)
    alignment = Column(String(50), nullable=True)  # Character alignment
    description = Column(Text, nullable=True)  # Physical description
    personality = Column(Text, nullable=True)  # Personality traits
    backstory = Column(Text, nullable=True)  # Character backstory
    goals = Column(Text, nullable=True)  # Goals and motivations
    notes = Column(Text, nullable=True)  # Additional notes
    dndbeyond_url = Column(Text, nullable=True)  # D&D Beyond character sheet URL
    
    # Usage statistics
    message_count = Column(Integer, default=0)  # Track how many messages sent as this character
    last_used = Column(DateTime, nullable=True)  # When character was last used
    is_favorite = Column(Boolean, default=False)  # Whether this alias is favorited
    subgroup = Column(String, nullable=True)  # For nested folder structure within groups
    tags = Column(Text, nullable=True)  # Comma-separated tags for categorization
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild")
    shared_group = relationship("SharedGroup", back_populates="aliases")
    
    # Unique constraint: user can't have duplicate names within a guild
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

class AliasOverride(Base):
    """Personal trigger overrides for shared aliases"""
    __tablename__ = 'alias_overrides'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), nullable=False)  # Discord user ID (the person creating the override)
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    
    # Reference to the original shared alias
    original_alias_id = Column(Integer, ForeignKey('character_aliases.id'), nullable=False)
    
    # The personal trigger override
    personal_trigger = Column(String(200), nullable=False)  # New trigger pattern for this user only
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    guild = relationship("Guild")
    original_alias = relationship("CharacterAlias")
    
    # Unique constraint: user can only have one override per alias per guild
    __table_args__ = (
        UniqueConstraint('user_id', 'guild_id', 'original_alias_id', name='_user_alias_override_uc'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

class PlayerAchievement(Base):
    """Player's unlocked achievements"""
    __tablename__ = 'player_achievements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), nullable=False)  # Discord user ID
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    achievement_id = Column(Integer, ForeignKey('achievements.id'), nullable=False)
    
    # Progress tracking
    current_progress = Column(Integer, default=0)
    is_unlocked = Column(Boolean, default=False)
    unlocked_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild")
    achievement = relationship("Achievement")

class PlayerStats(Base):
    """Comprehensive player statistics for session planning and achievements"""
    __tablename__ = 'player_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), nullable=False)  # Discord user ID
    guild_id = Column(String(20), ForeignKey('guilds.id'), nullable=False)
    
    # Session Participation Stats
    total_sessions = Column(Integer, default=0)
    total_session_time_hours = Column(Float, default=0.0)
    sessions_as_dm = Column(Integer, default=0)
    dm_time_hours = Column(Float, default=0.0)
    
    # Session Type Breakdown (Participation)
    combat_sessions = Column(Integer, default=0)
    social_sessions = Column(Integer, default=0)
    mixed_sessions = Column(Integer, default=0)
    other_sessions = Column(Integer, default=0)
    
    # Session Type Time Breakdown
    combat_time_hours = Column(Float, default=0.0)
    social_time_hours = Column(Float, default=0.0)
    mixed_time_hours = Column(Float, default=0.0)
    other_time_hours = Column(Float, default=0.0)
    
    # Hosting Stats (as DM)
    sessions_hosted_combat = Column(Integer, default=0)
    sessions_hosted_social = Column(Integer, default=0)
    sessions_hosted_mixed = Column(Integer, default=0)
    sessions_hosted_other = Column(Integer, default=0)
    
    # Communication & Engagement Stats
    messages_sent_in_sessions = Column(Integer, default=0)
    alias_messages_sent = Column(Integer, default=0)  # Messages using character aliases
    total_aliases_created = Column(Integer, default=0)
    active_aliases = Column(Integer, default=0)
    
    # Character & Roleplay Stats
    highest_character_level = Column(Integer, default=1)
    total_characters_played = Column(Integer, default=0)
    unique_character_names = Column(Integer, default=0)
    
    # Reward & Progression Stats
    total_xp_earned = Column(Integer, default=0)
    total_gold_earned = Column(Integer, default=0)
    average_xp_per_session = Column(Float, default=0.0)
    average_gold_per_session = Column(Float, default=0.0)
    
    # Session Quality & Engagement Metrics
    average_session_length_hours = Column(Float, default=0.0)
    longest_session_hours = Column(Float, default=0.0)
    shortest_session_hours = Column(Float, default=24.0)  # Start high, update with actual minimums
    sessions_completed = Column(Integer, default=0)  # Sessions that ran to completion (not abandoned)
    sessions_early_leave = Column(Integer, default=0)  # Times left session early
    
    # Consistency & Reliability Stats
    consecutive_sessions = Column(Integer, default=0)  # Current streak
    max_consecutive_sessions = Column(Integer, default=0)  # Best streak
    sessions_this_week = Column(Integer, default=0)
    sessions_this_month = Column(Integer, default=0)
    last_session_date = Column(DateTime, nullable=True)
    
    # Community & Social Stats
    total_achievement_points = Column(Integer, default=0)
    players_helped_as_dm = Column(Integer, default=0)  # Unique players DM'd for
    favorite_session_type = Column(String(20), nullable=True)  # Auto-calculated
    
    # Special Milestones
    first_session_date = Column(DateTime, nullable=True)
    first_dm_session_date = Column(DateTime, nullable=True)
    most_active_day = Column(String(10), nullable=True)  # Day of week
    most_active_hour = Column(Integer, nullable=True)  # Hour of day (0-23)
    
    # Legacy columns (keeping for compatibility)
    longest_session_minutes = Column(Integer, default=0)  # Will be calculated from longest_session_hours
    active_characters = Column(Integer, default=0)  # Same as active_aliases
    players_helped = Column(Integer, default=0)  # Same as players_helped_as_dm
    sessions_joined_late = Column(Integer, default=0)
    perfect_attendance_streaks = Column(Integer, default=0)  # Same as max_consecutive_sessions
    achievements_unlocked = Column(Integer, default=0)
    
    # Weekly Reset Fields (for weekly statistics)
    week_start_date = Column(DateTime, nullable=True)
    month_start_date = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild")
    
    # Unique constraint: one record per user per guild
    __table_args__ = (
        UniqueConstraint('guild_id', 'user_id', name='unique_player_stats'),
    )

class Milestone(Base):
    """Special milestone achievements"""
    __tablename__ = 'milestones'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    icon = Column(String(10), default='🌟')
    points = Column(Integer, default=50)  # Higher points for milestones
    
    # Milestone requirements (more complex than achievements)
    requirement_conditions = Column(Text, nullable=False)  # JSON string of multiple conditions
    reward_description = Column(Text)  # Special rewards description
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player_milestones = relationship("PlayerMilestone", back_populates="milestone")

class PlayerMilestone(Base):
    """Player milestone unlocks"""
    __tablename__ = 'player_milestones'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), nullable=False)
    guild_id = Column(String(20), nullable=False)
    milestone_id = Column(Integer, ForeignKey('milestones.id'), nullable=False)
    
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    character_name = Column(String(100))
    character_level = Column(Integer)
    session_context = Column(Text)  # JSON string of session details when earned
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    milestone = relationship("Milestone", back_populates="player_milestones")