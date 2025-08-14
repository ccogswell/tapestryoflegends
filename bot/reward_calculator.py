from datetime import timedelta
from typing import Dict, Tuple, Optional
import math

class RewardCalculator:
    """Calculates rewards based on session participation"""
    
    def __init__(self):
        # Minimum participation time
        self.min_participation_minutes = 1  # Minimum 1 minute to earn rewards (testing)
        
        # Level-based XP rates per hour (XP/hr by level range)
        self.xp_rates_by_level = {
            (2, 4): 300,    # Levels 2-4: 300 XP/hr
            (5, 8): 600,    # Levels 5-8: 600 XP/hr
            (9, 12): 800,   # Levels 9-12: 800 XP/hr
            (13, 16): 1000, # Levels 13-16: 1000 XP/hr
            (17, 20): 1100  # Levels 17-20: 1100 XP/hr
        }
        
        # Gold rate: character level * 10 per hour
        self.gold_per_level_per_hour = 10
        
        # Bonus multipliers
        self.dm_bonus_multiplier = 1.5  # DM gets 50% bonus
        self.long_session_bonus_threshold = 120  # Minutes (2 hours)
        self.long_session_bonus_multiplier = 1.2  # 20% bonus for long sessions

    def get_xp_rate_for_level(self, character_level: int) -> int:
        """Get XP per hour rate based on character level"""
        for (min_level, max_level), xp_rate in self.xp_rates_by_level.items():
            if min_level <= character_level <= max_level:
                return xp_rate
        # Default rate for level 1 or out of range
        return 200  # Base rate for level 1

    def round_to_nearest_30_minutes(self, participation_time: timedelta) -> timedelta:
        """
        Round participation time to the nearest 30-minute interval.
        Only applies rounding after the first 30 minutes.
        """
        total_minutes = participation_time.total_seconds() / 60
        
        # If less than 30 minutes, no rounding - return as is
        if total_minutes < 30:
            return participation_time
        
        # After 30 minutes, round to nearest 30-minute interval
        rounded_minutes = round(total_minutes / 30) * 30
        
        # Convert back to timedelta
        return timedelta(minutes=rounded_minutes)

    def calculate_rewards(self, participation_time: timedelta, is_dm: bool = False, 
                         session_duration: Optional[timedelta] = None, 
                         character_level: int = 1) -> Tuple[int, int]:
        """
        Calculate XP and gold rewards based on participation time and character level
        
        Args:
            participation_time: Time the player participated
            is_dm: Whether the player was the DM
            session_duration: Total session duration for bonus calculations
            character_level: Character level for scaling rewards
            
        Returns:
            Tuple of (xp, gold)
        """
        # Check minimum participation before rounding
        if (participation_time.total_seconds() / 60) < self.min_participation_minutes:
            return (0, 0)
        
        # Round participation time to nearest 30 minutes
        rounded_participation = self.round_to_nearest_30_minutes(participation_time)
        
        # Convert to hours for calculation
        hours_participated = max(0, rounded_participation.total_seconds() / 3600)
        
        # Calculate level-based rewards
        xp_per_hour = self.get_xp_rate_for_level(character_level)
        gold_per_hour = character_level * self.gold_per_level_per_hour
        
        # Base rewards
        base_xp = int(hours_participated * xp_per_hour)
        base_gold = int(hours_participated * gold_per_hour)
        
        # Apply DM bonus
        if is_dm:
            base_xp = int(base_xp * self.dm_bonus_multiplier)
            base_gold = int(base_gold * self.dm_bonus_multiplier)
        
        # Apply long session bonus
        if session_duration and session_duration.total_seconds() / 60 >= self.long_session_bonus_threshold:
            base_xp = int(base_xp * self.long_session_bonus_multiplier)
            base_gold = int(base_gold * self.long_session_bonus_multiplier)
        
        return (base_xp, base_gold)

    def calculate_session_rewards(self, session) -> Dict[int, Tuple[int, int]]:
        """
        Calculate rewards for all participants in a session
        
        Args:
            session: RPSession object
            
        Returns:
            Dict mapping user_id to (xp, gold) tuple
        """
        rewards = {}
        session_duration = session.get_session_duration()
        
        # Calculate rewards for all participants (including those who left)
        all_participants = set(session.participants.keys()) | set(session.participant_times.keys())
        
        for user_id in all_participants:
            participation_time = session.get_participant_time(user_id)
            is_dm = (user_id == session.dm_id)
            
            # Get character level, default to 1 if not found
            character_level = 1
            if user_id in session.participant_characters:
                character_level = session.participant_characters[user_id]['level']
            
            xp, gold = self.calculate_rewards(
                participation_time=participation_time,
                is_dm=is_dm,
                session_duration=session_duration,
                character_level=character_level
            )
            
            if xp > 0 or gold > 0:  # Only include users who earned rewards
                rewards[user_id] = (xp, gold)
        
        return rewards

    def format_time_duration(self, duration: timedelta) -> str:
        """Format a timedelta into a human-readable string (11h55m format)"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h{minutes}m"
        elif minutes > 0:
            return f"{minutes}m"
        else:
            return "0m"

    def get_reward_summary_text(self, rewards: Dict[int, Tuple[int, int]], 
                               bot, session) -> str:
        """
        Generate a formatted summary of session rewards
        
        Args:
            rewards: Dict mapping user_id to (xp, gold)
            bot: Discord bot instance for user lookup
            session: RPSession object
            
        Returns:
            Formatted reward summary string
        """
        if not rewards:
            # Show all participants even if they didn't get rewards
            all_participants = set(session.participants.keys()) | set(session.participant_times.keys())
            if all_participants:
                summary_lines = []
                for user_id in all_participants:
                    participation_time = session.get_participant_time(user_id)
                    time_str = self.format_time_duration(participation_time)
                    
                    # Get character information
                    character_info = ""
                    if user_id in session.participant_characters:
                        char_data = session.participant_characters[user_id]
                        character_info = f" as **{char_data['name']}** (Lvl {char_data['level']})"
                    
                    dm_indicator = " (DM)" if user_id == session.dm_id else ""
                    summary_lines.append(f"<@{user_id}>{dm_indicator}{character_info}: **0 XP**, **0 gold** ({time_str}) - *Below minimum time*")
                
                summary = "\n".join(summary_lines)
                summary += f"\n\n**Total Distributed:** 0 XP, 0 gold\n*No participants met the minimum 30-minute requirement.*"
                return summary
            else:
                return "No participants joined this session."
        
        summary_lines = []
        total_xp = 0
        total_gold = 0
        
        # Sort by XP (highest first)
        sorted_rewards = sorted(rewards.items(), key=lambda x: x[1][0], reverse=True)
        
        for user_id, (xp, gold) in sorted_rewards:
            # Get participation time
            participation_time = session.get_participant_time(user_id)
            rounded_participation = self.round_to_nearest_30_minutes(participation_time)
            time_str = self.format_time_duration(rounded_participation)
            
            # Check if user was DM
            dm_indicator = " (DM)" if user_id == session.dm_id else ""
            
            # Get character information
            character_info = ""
            if user_id in session.participant_characters:
                char_data = session.participant_characters[user_id]
                character_info = f" as **{char_data['name']}** (Lvl {char_data['level']})"
            
            summary_lines.append(f"<@{user_id}>{dm_indicator}{character_info}: **{xp} XP**, **{gold} gold** ({time_str})")
            total_xp += xp
            total_gold += gold
        
        summary = "\n".join(summary_lines)
        summary += f"\n\n**Total Distributed:** {total_xp} XP, {total_gold} gold"
        
        return summary
