import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import logging
from bot.stats_system import StatsSystem
from bot.views import get_display_name_from_db

logger = logging.getLogger(__name__)

class StatsCommands(commands.Cog):
    """Commands for viewing session and player statistics"""
    
    def __init__(self, bot, stats_system: StatsSystem):
        self.bot = bot
        self.stats_system = stats_system
    
    @app_commands.command(name="stats", description="View session statistics and leaderboards")
    @app_commands.describe(
        scope="What type of statistics to view",
        user="View stats for a specific user (for personal stats only)",
        category="Category to display (personal stats) or leaderboard type",
    )
    async def stats(
        self, 
        interaction: discord.Interaction,
        scope: Optional[Literal["personal", "server", "leaderboard"]] = "personal",
        user: Optional[discord.Member] = None,
        category: Optional[Literal["overview", "sessions", "hosting", "characters", "rewards", "engagement"]] = "overview"
    ):
        """Display statistics based on scope (personal, server, or leaderboard)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        # Defer after initial checks
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        
        try:
            if scope == "server":
                # Show server-wide statistics
                guild_stats = await self.stats_system.get_guild_stats_summary(guild_id)
                if not guild_stats:
                    await interaction.followup.send("❌ No server statistics available yet.")
                    return
                embed = await self._create_guild_stats_embed(guild_stats, interaction.guild)
                
            elif scope == "leaderboard":
                # Show leaderboard (use category as leaderboard type)
                leaderboard_type = category  # Reuse category parameter for leaderboard type
                leaderboard_data = await self.stats_system.get_leaderboard(guild_id, leaderboard_type, limit=10)
                if not leaderboard_data:
                    await interaction.followup.send(f"❌ No data available for {leaderboard_type} leaderboard.")
                    return
                embed = await self._create_leaderboard_embed(leaderboard_data, leaderboard_type, interaction.guild)
                
            else:  # scope == "personal" (default)
                # Show personal statistics
                target_user = user or interaction.user
                user_id = str(target_user.id)
                
                try:
                    stats = await self.stats_system.get_player_stats(user_id, guild_id)
                    if not stats:
                        await interaction.followup.send("📊 No statistics available yet. Participate in some sessions to start tracking your progress!", ephemeral=True)
                        return
                except Exception as e:
                    logger.error(f"Error getting player stats: {e}")
                    await interaction.followup.send("❌ The statistics system is currently being set up. Please try again later!", ephemeral=True)
                    return
                
                # Get display name
                display_name = get_display_name_from_db(target_user.id, guild_id)
                if not display_name:
                    display_name = target_user.display_name
                
                embed = await self._create_stats_embed(stats, display_name, category, target_user)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving statistics.")
    

    async def _create_stats_embed(self, stats, display_name: str, category: str, user: discord.Member) -> discord.Embed:
        """Create a detailed statistics embed"""
        if category == "overview":
            embed = discord.Embed(
                title=f"📊 {display_name}'s D&D Statistics",
                color=0x0099ff
            )
            
            # Overview stats
            embed.add_field(
                name="🎲 Session Summary",
                value=f"**Total Sessions:** {stats.total_sessions}\n"
                      f"**Total Playtime:** {stats.total_session_time_hours:.1f} hours\n"
                      f"**Sessions as DM:** {stats.sessions_as_dm}\n"
                      f"**DM Time:** {stats.dm_time_hours:.1f} hours",
                inline=True
            )
            
            embed.add_field(
                name="🏆 Achievements",
                value=f"**XP Earned:** {stats.total_xp_earned:,}\n"
                      f"**Gold Earned:** {stats.total_gold_earned:,}\n"
                      f"**Highest Level:** {stats.highest_character_level}\n"
                      f"**Characters Played:** {stats.total_characters_played}",
                inline=True
            )
            
            # Session type breakdown
            session_types = []
            if stats.combat_sessions > 0:
                session_types.append(f"Combat: {stats.combat_sessions}")
            if stats.social_sessions > 0:
                session_types.append(f"Social: {stats.social_sessions}")
            if stats.mixed_sessions > 0:
                session_types.append(f"Mixed: {stats.mixed_sessions}")
            if stats.other_sessions > 0:
                session_types.append(f"Other: {stats.other_sessions}")
            
            embed.add_field(
                name="📋 Session Types",
                value="\n".join(session_types) if session_types else "No sessions yet",
                inline=True
            )
            
            # Favorite type and streaks
            if stats.favorite_session_type:
                embed.add_field(
                    name="⭐ Preferences",
                    value=f"**Favorite Type:** {stats.favorite_session_type}\n"
                          f"**Current Streak:** {stats.consecutive_sessions}\n"
                          f"**Best Streak:** {stats.max_consecutive_sessions}",
                    inline=True
                )
            
            # Recent activity
            if stats.last_session_date:
                embed.add_field(
                    name="📅 Recent Activity",
                    value=f"**Last Session:** {stats.last_session_date.strftime('%Y-%m-%d')}\n"
                          f"**This Week:** {stats.sessions_this_week}\n"
                          f"**This Month:** {stats.sessions_this_month}",
                    inline=True
                )
            
            # Engagement stats
            embed.add_field(
                name="💬 Engagement",
                value=f"**Messages in Sessions:** {stats.messages_sent_in_sessions}\n"
                      f"**Alias Messages:** {stats.alias_messages_sent}\n"
                      f"**Active Aliases:** {stats.active_aliases}",
                inline=True
            )
            
        elif category == "sessions":
            embed = discord.Embed(
                title=f"🎲 {display_name}'s Session Statistics",
                color=0x0099ff
            )
            
            embed.add_field(
                name="📊 Session Participation",
                value=f"**Total Sessions:** {stats.total_sessions}\n"
                      f"**Combat Sessions:** {stats.combat_sessions}\n"
                      f"**Social Sessions:** {stats.social_sessions}\n"
                      f"**Mixed Sessions:** {stats.mixed_sessions}\n"
                      f"**Other Sessions:** {stats.other_sessions}",
                inline=True
            )
            
            embed.add_field(
                name="⏱️ Time Breakdown",
                value=f"**Total Time:** {stats.total_session_time_hours:.1f}h\n"
                      f"**Combat Time:** {stats.combat_time_hours:.1f}h\n"
                      f"**Social Time:** {stats.social_time_hours:.1f}h\n"
                      f"**Mixed Time:** {stats.mixed_time_hours:.1f}h\n"
                      f"**Other Time:** {stats.other_time_hours:.1f}h",
                inline=True
            )
            
            embed.add_field(
                name="📈 Session Quality",
                value=f"**Average Length:** {stats.average_session_length_hours:.1f}h\n"
                      f"**Longest Session:** {stats.longest_session_hours:.1f}h\n"
                      f"**Shortest Session:** {stats.shortest_session_hours:.1f}h\n"
                      f"**Completed:** {stats.sessions_completed}\n"
                      f"**Early Leaves:** {stats.sessions_early_leave}",
                inline=True
            )
            
        elif category == "hosting":
            embed = discord.Embed(
                title=f"🎭 {display_name}'s DM Statistics",
                color=0xff9900
            )
            
            embed.add_field(
                name="🎲 Sessions Hosted",
                value=f"**Total as DM:** {stats.sessions_as_dm}\n"
                      f"**Combat Sessions:** {stats.sessions_hosted_combat}\n"
                      f"**Social Sessions:** {stats.sessions_hosted_social}\n"
                      f"**Mixed Sessions:** {stats.sessions_hosted_mixed}\n"
                      f"**Other Sessions:** {stats.sessions_hosted_other}",
                inline=True
            )
            
            embed.add_field(
                name="⏱️ DM Time",
                value=f"**Total DM Time:** {stats.dm_time_hours:.1f} hours\n"
                      f"**Players Helped:** {stats.players_helped_as_dm}\n"
                      f"**Avg Session Length:** {(stats.dm_time_hours / stats.sessions_as_dm if stats.sessions_as_dm > 0 else 0):.1f}h",
                inline=True
            )
            
        elif category == "characters":
            embed = discord.Embed(
                title=f"🧙‍♀️ {display_name}'s Character Statistics",
                color=0x9932cc
            )
            
            embed.add_field(
                name="🎭 Character Info",
                value=f"**Total Characters:** {stats.total_characters_played}\n"
                      f"**Unique Names:** {stats.unique_character_names}\n"
                      f"**Highest Level:** {stats.highest_character_level}\n"
                      f"**Active Aliases:** {stats.active_aliases}",
                inline=True
            )
            
            embed.add_field(
                name="💬 Roleplay Engagement",
                value=f"**Total Aliases Created:** {stats.total_aliases_created}\n"
                      f"**Alias Messages:** {stats.alias_messages_sent}\n"
                      f"**Regular Messages:** {stats.messages_sent_in_sessions}\n"
                      f"**RP Message Ratio:** {(stats.alias_messages_sent / max(stats.messages_sent_in_sessions, 1) * 100):.1f}%",
                inline=True
            )
            
        elif category == "rewards":
            embed = discord.Embed(
                title=f"💰 {display_name}'s Reward Statistics",
                color=0xffd700
            )
            
            embed.add_field(
                name="🏆 Total Rewards",
                value=f"**Total XP:** {stats.total_xp_earned:,}\n"
                      f"**Total Gold:** {stats.total_gold_earned:,}\n"
                      f"**Achievement Points:** {stats.total_achievement_points}",
                inline=True
            )
            
            embed.add_field(
                name="📊 Averages",
                value=f"**Avg XP/Session:** {stats.average_xp_per_session:.0f}\n"
                      f"**Avg Gold/Session:** {stats.average_gold_per_session:.0f}\n"
                      f"**XP per Hour:** {(stats.total_xp_earned / max(stats.total_session_time_hours, 1)):.0f}",
                inline=True
            )
            
        elif category == "engagement":
            embed = discord.Embed(
                title=f"💬 {display_name}'s Engagement Statistics",
                color=0x00ff7f
            )
            
            embed.add_field(
                name="📱 Communication",
                value=f"**Session Messages:** {stats.messages_sent_in_sessions}\n"
                      f"**Alias Messages:** {stats.alias_messages_sent}\n"
                      f"**Messages/Session:** {(stats.messages_sent_in_sessions / max(stats.total_sessions, 1)):.1f}",
                inline=True
            )
            
            embed.add_field(
                name="🎯 Consistency",
                value=f"**Current Streak:** {stats.consecutive_sessions}\n"
                      f"**Best Streak:** {stats.max_consecutive_sessions}\n"
                      f"**This Week:** {stats.sessions_this_week}\n"
                      f"**This Month:** {stats.sessions_this_month}",
                inline=True
            )
        
        # Add user avatar
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Add footer with last update
        if stats.updated_at:
            embed.set_footer(text=f"Last updated: {stats.updated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        
        return embed
    
    async def _create_guild_stats_embed(self, guild_stats: dict, guild: discord.Guild) -> discord.Embed:
        """Create guild statistics embed"""
        embed = discord.Embed(
            title=f"📊 {guild.name} Server Statistics",
            color=0x0099ff
        )
        
        # Session overview
        embed.add_field(
            name="🎲 Session Overview",
            value=f"**Total Sessions:** {guild_stats.get('total_sessions', 0)}\n"
                  f"**Active Sessions:** {guild_stats.get('active_sessions', 0)}\n"
                  f"**Total Playtime:** {guild_stats.get('total_playtime_hours', 0):.1f} hours",
            inline=True
        )
        
        # Session types
        session_types = guild_stats.get('sessions_by_type', {})
        if session_types:
            type_text = []
            for session_type, count in session_types.items():
                type_text.append(f"**{session_type}:** {count}")
            
            embed.add_field(
                name="📋 Session Types",
                value="\n".join(type_text),
                inline=True
            )
        
        # Top players
        top_players = guild_stats.get('top_players', [])
        if top_players:
            player_text = []
            for i, (user_id, sessions, hours) in enumerate(top_players[:5], 1):
                display_name = get_display_name_from_db(int(user_id), str(guild.id))
                if not display_name:
                    display_name = f"User{user_id}"
                player_text.append(f"{i}. {display_name}: {sessions} sessions ({hours:.1f}h)")
            
            embed.add_field(
                name="🏆 Most Active Players",
                value="\n".join(player_text),
                inline=False
            )
        
        # Top DMs
        top_dms = guild_stats.get('top_dms', [])
        if top_dms:
            dm_text = []
            for i, (user_id, sessions, hours) in enumerate(top_dms[:5], 1):
                display_name = get_display_name_from_db(int(user_id), str(guild.id))
                if not display_name:
                    display_name = f"User{user_id}"
                dm_text.append(f"{i}. {display_name}: {sessions} sessions ({hours:.1f}h)")
            
            embed.add_field(
                name="🎭 Most Active DMs",
                value="\n".join(dm_text),
                inline=False
            )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        return embed
    
    async def _create_leaderboard_embed(self, leaderboard: list, category: str, guild: discord.Guild) -> discord.Embed:
        """Create leaderboard embed"""
        category_names = {
            'total_sessions': 'Total Sessions',
            'total_time': 'Total Playtime (hours)',
            'sessions_as_dm': 'Sessions as DM',
            'xp_earned': 'XP Earned',
            'gold_earned': 'Gold Earned',
            'aliases_created': 'Aliases Created',
            'messages_sent': 'Messages in Sessions',
            'consecutive_sessions': 'Current Session Streak'
        }
        
        category_display = category_names.get(category, category.replace('_', ' ').title())
        
        embed = discord.Embed(
            title=f"🏆 {category_display} Leaderboard",
            description=f"Top players in {guild.name}",
            color=0xffd700
        )
        
        leaderboard_text = []
        for i, (user_id, value) in enumerate(leaderboard, 1):
            display_name = get_display_name_from_db(int(user_id), str(guild.id))
            if not display_name:
                display_name = f"User{user_id}"
            
            # Format value based on category
            if category == 'total_time':
                value_str = f"{value:.1f}h"
            elif category in ['xp_earned', 'gold_earned']:
                value_str = f"{int(value):,}"
            else:
                value_str = str(int(value))
            
            # Add medal emojis for top 3
            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            
            leaderboard_text.append(f"{medal}{i}. **{display_name}** - {value_str}")
        
        embed.description = "\n".join(leaderboard_text)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        return embed

async def setup(bot):
    """Setup function for the cog"""
    pass