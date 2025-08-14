import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import logging
from bot.achievement_system import AchievementSystem

logger = logging.getLogger(__name__)

class AchievementCommands(commands.Cog):
    """Achievement system commands"""
    
    def __init__(self, bot, achievement_system: AchievementSystem):
        self.bot = bot
        self.achievement_system = achievement_system
    
    @app_commands.command(name="achievements", description="View your achievements and progress")
    @app_commands.describe(
        user="View achievements for another player (optional)"
    )
    async def achievements(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Display player achievements"""
        await interaction.response.defer(ephemeral=True)
        
        target_user = user or interaction.user
        guild_id = str(interaction.guild.id) if interaction.guild else ""
        user_id = str(target_user.id)
        
        try:
            # Get player achievement data
            player_data = await self.achievement_system.get_player_achievements(user_id, guild_id)
            
            if not player_data:
                await interaction.followup.send("❌ Failed to load achievement data.", ephemeral=True)
                return
            
            # Create achievement embed
            embed = await self.achievement_system.create_achievement_embed(player_data, target_user)
            
            # Create view with buttons for more details  
            view = AchievementView(self.achievement_system, user_id, guild_id, target_user)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in achievements command: {e}")
            await interaction.followup.send("❌ An error occurred while loading achievements.", ephemeral=True)
    
    @app_commands.command(name="leaderboard", description="View the achievement leaderboard")
    @app_commands.describe(
        category="Filter by achievement category (optional)",
        top="Number of players to show (default 10)"
    )
    async def leaderboard(
        self, 
        interaction: discord.Interaction, 
        category: Optional[str] = None,
        top: Optional[int] = 10
    ):
        """Display achievement leaderboard"""
        await interaction.response.defer()
        
        if top and top > 25:
            top = 25  # Limit to prevent embed overflow
        elif not top:
            top = 10
            
        try:
            # Get leaderboard data
            guild_id = str(interaction.guild.id) if interaction.guild else ""
            leaderboard_data = await self.achievement_system.get_leaderboard(
                guild_id, 
                category, 
                top
            )
            
            if not leaderboard_data:
                await interaction.followup.send("📊 No leaderboard data available yet!")
                return
            
            # Create leaderboard embed
            if interaction.guild:
                embed = await self._create_leaderboard_embed(leaderboard_data, interaction.guild, category, top)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ This command can only be used in a server.")
            
        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            await interaction.followup.send("❌ An error occurred while loading the leaderboard.")
    
    async def _create_leaderboard_embed(self, data: list, guild: discord.Guild, category: Optional[str], top: int) -> discord.Embed:
        """Create leaderboard embed"""
        title = f"🏆 Achievement Leaderboard"
        if category:
            title += f" - {category.title()}"
        
        embed = discord.Embed(
            title=title,
            description=f"Top {len(data)} players in **{guild.name}**",
            color=0xffd700
        )
        
        if not data:
            embed.add_field(name="No Data", value="No players have earned achievements yet!", inline=False)
            return embed
        
        leaderboard_text = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id, stats, points, achievement_count) in enumerate(data):
            try:
                user = await self.bot.fetch_user(int(user_id))
                display_name = user.display_name
            except:
                display_name = f"User {user_id}"
            
            medal = medals[i] if i < 3 else f"#{i+1}"
            
            leaderboard_text += (
                f"{medal} **{display_name}**\n"
                f"    {points} points • {achievement_count} achievements\n\n"
            )
        
        embed.add_field(name="Rankings", value=leaderboard_text, inline=False)
        embed.set_footer(text="Earn achievements by participating in RP sessions!")
        
        return embed

class AchievementView(discord.ui.View):
    """Interactive view for achievement display"""
    
    def __init__(self, achievement_system: AchievementSystem, user_id: str, guild_id: str, target_user: discord.User):
        super().__init__(timeout=300)
        self.achievement_system = achievement_system
        self.user_id = user_id
        self.guild_id = guild_id
        self.target_user = target_user
    
    @discord.ui.button(label="View Progress", style=discord.ButtonStyle.primary, emoji="📈")
    async def view_progress(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show achievement progress"""
        await interaction.response.defer()
        
        try:
            player_data = await self.achievement_system.get_player_achievements(self.user_id, self.guild_id)
            available_achievements = player_data.get('available_achievements', [])
            
            if not available_achievements:
                embed = discord.Embed(
                    title="🎉 All Caught Up!",
                    description=f"{self.target_user.display_name} has unlocked all available achievements!",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title=f"📈 {self.target_user.display_name}'s Achievement Progress",
                    description="Here are the achievements you can work towards:",
                    color=0x3498db
                )
                
                # Group by category
                categories = {}
                for ach in available_achievements[:15]:  # Limit to prevent overflow
                    if not ach.is_hidden or (ach.is_hidden and self._should_show_hidden(ach)):
                        category = ach.category.title()
                        if category not in categories:
                            categories[category] = []
                        categories[category].append(ach)
                
                for category, achievements in categories.items():
                    ach_text = "\n".join([
                        f"{ach.icon} **{ach.name}** ({ach.points} pts)\n    {ach.description}"
                        for ach in achievements[:5]  # Limit per category
                    ])
                    embed.add_field(name=f"{category} Achievements", value=ach_text, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing progress: {e}")
            await interaction.followup.send("❌ Failed to load achievement progress.", ephemeral=True)
    
    @discord.ui.button(label="Statistics", style=discord.ButtonStyle.secondary, emoji="📊")
    async def view_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show detailed statistics"""
        await interaction.response.defer()
        
        try:
            player_data = await self.achievement_system.get_player_achievements(self.user_id, self.guild_id)
            stats = player_data['stats']
            
            embed = discord.Embed(
                title=f"📊 {self.target_user.display_name}'s Adventure Statistics",
                color=0x9b59b6
            )
            
            # Session stats
            embed.add_field(
                name="🎲 Session Statistics", 
                value=(
                    f"Total Sessions: **{stats.total_sessions or 0}**\n"
                    f"Total Playtime: **{stats.total_playtime_hours or 0:.1f}** hours\n"
                    f"Sessions as DM: **{stats.sessions_as_dm or 0}**\n"
                    f"Longest Session: **{(stats.longest_session_minutes or 0) // 60}h {(stats.longest_session_minutes or 0) % 60}m**"
                ),
                inline=True
            )
            
            # Character stats  
            embed.add_field(
                name="⚔️ Character Statistics",
                value=(
                    f"Highest Level: **{stats.highest_character_level or 1}**\n"
                    f"Total XP Earned: **{stats.total_xp_earned or 0:,}**\n"
                    f"Total Gold Earned: **{stats.total_gold_earned or 0:,}**\n"
                    f"Characters Played: **{stats.active_characters or 0}**"
                ),
                inline=True
            )
            
            # Achievement stats
            embed.add_field(
                name="🏆 Achievement Statistics",
                value=(
                    f"Achievements Unlocked: **{stats.achievements_unlocked or 0}**\n"
                    f"Achievement Points: **{stats.total_achievement_points or 0}**\n"
                    f"Players Helped: **{stats.players_helped or 0}**"
                ),
                inline=False
            )
            
            embed.set_thumbnail(url=self.target_user.display_avatar.url)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing statistics: {e}")
            await interaction.followup.send("❌ Failed to load statistics.", ephemeral=True)
    
    def _should_show_hidden(self, achievement) -> bool:
        """Determine if a hidden achievement should be shown (based on progress)"""
        # For now, don't show hidden achievements until partially unlocked
        return False
    
    async def on_timeout(self):
        """Disable buttons when view times out"""
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True

async def setup(bot):
    """Setup function for the cog"""
    from database import DatabaseManager
    
    # Initialize achievement system if not already done
    if not hasattr(bot, 'achievement_system'):
        db_manager = DatabaseManager()
        bot.achievement_system = AchievementSystem(db_manager)
        await bot.achievement_system.initialize()
    
    await bot.add_cog(AchievementCommands(bot, bot.achievement_system))