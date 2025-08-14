import discord
from discord.ext import commands
from discord import app_commands
from bot.views import SessionControlView, SessionInfoView
from bot.session_setup_view import SessionTypeSelectionView
from typing import Optional
import re
from datetime import datetime

class RPCommands(commands.Cog):
    """Roleplay session management commands"""
    
    def __init__(self, bot, session_manager, reward_calculator, achievement_system=None, stats_system=None):
        self.bot = bot
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator
        self.achievement_system = achievement_system
        self.stats_system = stats_system
    


    def validate_session_id(self, session_id: str) -> bool:
        """Validate session ID format (alphanumeric, hyphens, underscores only)"""
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', session_id)) and 1 <= len(session_id) <= 50
    
    def _get_session_from_thread(self, interaction: discord.Interaction):
        """Helper function to get session from current thread context"""
        # Check if we're in a thread
        if not isinstance(interaction.channel, discord.Thread):
            return None, None, "❌ This command can only be used in session threads."
        
        # Find the session running in this thread
        session = None
        session_id = None
        
        if interaction.guild_id in self.session_manager.sessions:
            for sid, sess in self.session_manager.sessions[interaction.guild_id].items():
                if sess.thread_id == interaction.channel.id:
                    session = sess
                    session_id = sid
                    break
        
        if not session:
            return None, None, "❌ No active session found in this thread."
        
        # Return the session, session_id, and no error
        return session, session_id, None

    @app_commands.command(name="rp_new", description="Start a new roleplay session")
    async def rp_new(self, interaction: discord.Interaction):
        """Start a new roleplay session"""
        try:
            print(f"DEBUG: rp_new called by {interaction.user.display_name}")
            
            # Defer response to prevent timeout (we have 15 minutes after deferring)
            await interaction.response.defer(ephemeral=True)
            
            # Check if user is already DMing a session
            if self.session_manager.is_user_dm_of_active_session(interaction.guild_id, interaction.user.id):
                await interaction.followup.send(
                    "❌ You are already DMing an active session. End it first before starting a new one.",
                    ephemeral=True
                )
                return
        except Exception as e:
            print(f"DEBUG: Error in rp_new: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ An error occurred: {str(e)}",
                    ephemeral=True
                )
            return
        
        try:
            # Generate unique session ID based on user and timestamp
            import time
            timestamp = int(time.time() % 10000)  # Last 4 digits of timestamp
            session_id = f"{interaction.user.display_name.lower().replace(' ', '-')}-{timestamp}"
            
            # Ensure session ID is valid and unique
            session_id = re.sub(r'[^a-zA-Z0-9_-]', '', session_id)[:46]  # Clean and limit length
            counter = 1
            original_id = session_id
            while self.session_manager.get_session(interaction.guild_id, session_id):
                session_id = f"{original_id}-{counter}"
                counter += 1
                if len(session_id) > 50:  # Fallback if name is too long
                    session_id = f"session-{timestamp}-{counter}"
            
            print(f"DEBUG: Generated session ID: {session_id}")
            
            # Show session type selection buttons
            embed = discord.Embed(
                title="🎲 Start New RP Session",
                description="Choose your session type to continue:",
                color=0x00ff00
            )
            embed.add_field(name="⚔️ Combat", value="Battle-focused session", inline=True)
            embed.add_field(name="💬 Social", value="Roleplay & interaction", inline=True)
            embed.add_field(name="🎭 Mixed", value="Combat + social elements", inline=True)
            embed.add_field(name="🎲 Other", value="Custom session type", inline=True)
            embed.set_footer(text=f"Session ID: {session_id}")
            
            print(f"DEBUG: Creating SessionTypeSelectionView...")
            view = SessionTypeSelectionView(self.session_manager, self.reward_calculator, session_id)
            print(f"DEBUG: Sending followup...")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            print(f"DEBUG: Followup sent successfully")
            
        except Exception as e:
            print(f"DEBUG: Error in rp_new main logic: {e}")
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ Error starting session: {str(e)}",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ Error starting session: {str(e)}",
                        ephemeral=True
                    )
            except Exception as followup_error:
                print(f"DEBUG: Failed to send error message: {followup_error}")

    @app_commands.command(name="rp_end", description="End the active roleplay session in this thread")
    async def rp_end(self, interaction: discord.Interaction):
        """End a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # session is guaranteed to exist at this point due to helper function check
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread is already ended.",
                ephemeral=True
            )
            return
        
        # Check permissions (DM or admin) 
        # session is guaranteed to exist at this point due to helper function check
        has_manage_channels = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_channels
        if interaction.user.id != session.dm_id and not has_manage_channels:
            await interaction.response.send_message(
                "❌ Only the DM or server administrators can end this session.",
                ephemeral=True
            )
            return
        
        # End the session
        ended_session = self.session_manager.end_session(interaction.guild_id, session_id)
        
        # Update forum post tags if it's a forum thread
        if ended_session and ended_session.thread_id and interaction.guild:
            await self._update_forum_tags_on_session_end(interaction.guild, ended_session)
        
        if ended_session:
            # Calculate rewards
            rewards = self.reward_calculator.calculate_session_rewards(ended_session)
            
            # Create session summary
            embed = discord.Embed(
                title="🛑 Roleplay Session Ended",
                description=f"Session **{session_id}** has concluded!",
                color=0xff0000
            )
            
            session_duration = ended_session.get_session_duration()
            duration_str = self.reward_calculator.format_time_duration(session_duration)
            
            embed.add_field(name="Duration", value=duration_str, inline=True)
            # Count all participants, not just those with rewards
            all_participants = set(ended_session.participants.keys()) | set(ended_session.participant_times.keys())
            embed.add_field(name="Participants", value=str(len(all_participants)), inline=True)
            embed.add_field(name="DM", value=f"<@{ended_session.dm_id}>", inline=True)
            
            # Post session end message in current channel
            await interaction.response.send_message(embed=embed)
            
            # Always post rewards table (even if empty) in the SESSION THREAD using consistent format
            from bot.views import _generate_rewards_table
            
            reward_embed = discord.Embed(
                title="💰 Session Rewards",
                color=0x00ff00 if rewards else 0x888888
            )
            
            # Use same table format as rp-rewards channel for consistency
            participant_table = await _generate_rewards_table(ended_session, self.reward_calculator, interaction.guild, rewards)
            reward_embed.add_field(name="📊 Session Results", value=participant_table, inline=False)
            
            # Add session info
            session_duration = ended_session.get_session_duration()
            duration_str = self.reward_calculator.format_time_duration(session_duration)
            
            reward_embed.add_field(name="Session", value=session_id, inline=True)
            reward_embed.add_field(name="Duration", value=duration_str, inline=True)
            reward_embed.add_field(name="DM", value=f"<@{ended_session.dm_id}>", inline=True)
            
            # Import here to avoid circular imports
            from bot.views import RewardManagementView
            
            # Create reward management view (always show, even for empty rewards)
            reward_view = RewardManagementView(
                rewards, ended_session, self.reward_calculator, session_id
            )
            
            # Find the session thread and post rewards there
            if ended_session.thread_id and interaction.guild:
                session_thread = interaction.guild.get_thread(ended_session.thread_id)
                if session_thread:
                    try:
                        await session_thread.send(embed=reward_embed, view=reward_view)
                        print(f"DEBUG: Posted rewards to thread {session_thread.name}")
                    except Exception as e:
                        print(f"DEBUG: Failed to post to thread: {e}")
                        # Fallback to current channel if thread post fails
                        await interaction.followup.send(embed=reward_embed, view=reward_view)
                else:
                    print(f"DEBUG: Thread {ended_session.thread_id} not found")
                    # Fallback to current channel if thread not found
                    await interaction.followup.send(embed=reward_embed, view=reward_view)
            else:
                print(f"DEBUG: No thread_id or guild. thread_id={ended_session.thread_id}")
                # Fallback to current channel if no thread
                await interaction.followup.send(embed=reward_embed, view=reward_view)
            
            # Process achievements if achievement system is available
            if self.achievement_system:
                try:
                    # Prepare session data for achievement processing
                    session_data = {
                        'guild_id': interaction.guild_id,
                        'dm_id': ended_session.dm_id,
                        'duration_minutes': int(session_duration.total_seconds() // 60),
                        'session_id': session_id,
                        'session_type': ended_session.session_type
                    }
                    
                    # Prepare participant data
                    participants_data = []
                    for user_id, (xp, gold) in rewards.items():
                        character_info = ended_session.participant_characters.get(user_id, {})
                        participation_time = ended_session.get_participant_time(user_id)
                        
                        participants_data.append({
                            'user_id': user_id,
                            'character_name': character_info.get('name', 'Unknown'),
                            'character_level': character_info.get('level', 1),
                            'participation_time_seconds': int(participation_time.total_seconds()),
                            'final_xp': xp,
                            'final_gold': gold
                        })
                    
                    # Process achievements
                    await self.achievement_system.process_session_completion(session_data, participants_data)
                    
                except Exception as e:
                    # Don't fail session end if achievement processing fails
                    print(f"DEBUG: Achievement processing failed: {e}")
                
                # Update player statistics
                if self.stats_system:
                    try:
                        for user_id, rewards in rewards.items():
                            participation_time = session.get_participant_time(user_id)
                            time_hours = participation_time.total_seconds() / 3600
                            
                            character_info = session.participant_characters.get(user_id, {})
                            character_level = character_info.get('level', 1)
                            
                            # Determine if session was completed (didn't leave early)
                            left_early = user_id not in session.participants
                            
                            stats_data = {
                                'participated': True,
                                'session_type': session.session_type,
                                'time_spent_hours': time_hours,
                                'was_dm': user_id == session.dm_id,
                                'character_level': character_level,
                                'xp_earned': rewards[0],  # rewards is tuple (xp, gold)
                                'gold_earned': rewards[1],
                                'completed_session': not left_early,
                                'left_early': left_early,
                                'session_date': session.end_time or datetime.now(),
                                'new_character': False  # Could enhance this later
                            }
                            
                            await self.stats_system.update_session_stats(
                                str(user_id), 
                                str(interaction.guild_id), 
                                stats_data
                            )
                            
                        print(f"DEBUG: Updated stats for {len(rewards)} participants")
                        
                    except Exception as e:
                        # Don't fail session end if stats processing fails
                        print(f"DEBUG: Stats processing failed: {e}")
                    
        else:
            await interaction.response.send_message("❌ Failed to end the session.", ephemeral=True)

    @app_commands.command(name="rp_join", description="Join the active roleplay session in this thread")
    @app_commands.describe(character_info="Character name and level (e.g., 'Gandalf 15')")
    async def rp_join(self, interaction: discord.Interaction, character_info: str):
        """Join a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # session is guaranteed to exist at this point due to helper function check
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread is not active.",
                ephemeral=True
            )
            return
        
        if interaction.user.id in session.participants:
            await interaction.response.send_message(
                f"❌ You are already in this session.",
                ephemeral=True
            )
            return
        
        # Store user's display name for later use
        display_name = "Unknown"
        if isinstance(interaction.user, discord.Member):
            if interaction.user.nick:
                display_name = interaction.user.nick
            elif hasattr(interaction.user, 'global_name') and interaction.user.global_name:
                display_name = interaction.user.global_name
            else:
                display_name = interaction.user.name
        else:
            display_name = interaction.user.name
        
        session.store_display_name(interaction.user.id, display_name)
        print(f"DEBUG: Stored display name '{display_name}' for user {interaction.user.id} in join command")
        
        # Parse character name and level
        input_text = character_info.strip()
        parts = input_text.rsplit(' ', 1)
        
        if len(parts) == 2:
            character_name, level_str = parts
            try:
                character_level = int(level_str)
                if character_level < 1 or character_level > 20:
                    await interaction.response.send_message(
                        "❌ Character level must be between 1 and 20.", 
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Please enter character info as: 'Character Name Level' (e.g., 'Gandalf 15')", 
                    ephemeral=True
                )
                return
        else:
            await interaction.response.send_message(
                "❌ Please enter character info as: 'Character Name Level' (e.g., 'Gandalf 15')", 
                ephemeral=True
            )
            return
        
        # Check if session is full
        if session.is_full():
            await interaction.response.send_message(
                f"❌ Session is full! ({session.get_active_player_count()}/{session.max_players} players)", 
                ephemeral=True
            )
            return
        
        if session.add_participant(interaction.user.id, character_name, character_level):
            await interaction.response.send_message(
                f"✅ {interaction.user.mention} joined the session as **{character_name}** (Level {character_level})!"
            )
            
            # Update message stats for session participation
            if self.stats_system:
                try:
                    await self.stats_system.update_message_stats(
                        str(interaction.user.id), 
                        str(interaction.guild_id), 
                        1
                    )
                except Exception as e:
                    print(f"DEBUG: Failed to update message stats: {e}")
            # Update participant table and forum tags in real-time
            if interaction.guild:
                from bot.views import update_participant_table, update_session_capacity_tags
                await update_participant_table(interaction.guild, session, self.reward_calculator)
                await update_session_capacity_tags(interaction.guild, session)
        else:
            await interaction.response.send_message("❌ Failed to join the session.", ephemeral=True)

    @app_commands.command(name="rp_leave", description="Leave the active roleplay session in this thread")
    async def rp_leave(self, interaction: discord.Interaction):
        """Leave a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread is not active.",
                ephemeral=True
            )
            return
        
        if interaction.user.id not in session.participants:
            await interaction.response.send_message(
                f"❌ You are not in this session.",
                ephemeral=True
            )
            return
        
        if session.remove_participant(interaction.user.id):
            time_spent = session.get_participant_time(interaction.user.id)
            rounded_time = self.reward_calculator.round_to_nearest_30_minutes(time_spent)
            time_str = self.reward_calculator.format_time_duration(rounded_time)
            await interaction.response.send_message(
                f"👋 {interaction.user.mention} left the session after {time_str}."
            )
            # Update participant table and forum tags in real-time
            if interaction.guild:
                from bot.views import update_participant_table, update_session_capacity_tags
                await update_participant_table(interaction.guild, session, self.reward_calculator)
                await update_session_capacity_tags(interaction.guild, session)
        else:
            await interaction.response.send_message("❌ Failed to leave the session.", ephemeral=True)

    @app_commands.command(name="rp_pause", description="Pause the active roleplay session in this thread (DM only)")
    async def rp_pause(self, interaction: discord.Interaction):
        """Pause a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread is not active.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != session.dm_id:
            await interaction.response.send_message(
                "❌ Only the DM can pause the session.",
                ephemeral=True
            )
            return
        
        if session.is_paused:
            await interaction.response.send_message(
                f"❌ The session is already paused.",
                ephemeral=True
            )
            return
        
        session.pause_session()
        await interaction.response.send_message(f"⏸️ Session paused by the DM.")

    @app_commands.command(name="rp_resume", description="Resume the paused roleplay session in this thread (DM only)")
    async def rp_resume(self, interaction: discord.Interaction):
        """Resume a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread is not active.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != session.dm_id:
            await interaction.response.send_message(
                "❌ Only the DM can resume the session.",
                ephemeral=True
            )
            return
        
        if not session.is_paused:
            await interaction.response.send_message(
                f"❌ The session is not paused.",
                ephemeral=True
            )
            return
        
        session.resume_session()
        await interaction.response.send_message(f"▶️ Session resumed by the DM.")

    @app_commands.command(name="rp_status", description="View information about active roleplay sessions")
    async def rp_status(self, interaction: discord.Interaction):
        """Display status of active roleplay sessions"""
        active_sessions = self.session_manager.get_active_sessions(interaction.guild_id)
        
        if not active_sessions:
            embed = discord.Embed(
                title="📊 Active Sessions",
                description="No active roleplay sessions.",
                color=0x888888
            )
            await interaction.response.send_message(embed=embed)
            return
        
        embed = discord.Embed(
            title="📊 Active Sessions",
            description=f"Found {len(active_sessions)} active session(s):",
            color=0x0099ff
        )
        
        for session in active_sessions:
            duration = session.get_session_duration()
            duration_str = self.reward_calculator.format_time_duration(duration)
            
            status = "⏸️ Paused" if session.is_paused else "▶️ Active"
            participants_count = len(session.participants)
            
            # List participant names with character info using proper display names
            participant_mentions = []
            for user_id in list(session.participants.keys())[:5]:  # Show up to 5 participants
                # Get display name from database first, fallback to Discord API
                display_name = "Unknown"
                if interaction.guild:
                    try:
                        # Try database lookup first
                        from bot.views import get_display_name_from_db
                        db_name = get_display_name_from_db(user_id, str(interaction.guild.id))
                        if db_name:
                            display_name = db_name
                        else:
                            # Fallback to Discord API
                            member = interaction.guild.get_member(user_id)
                            if member:
                                display_name = member.display_name
                    except:
                        pass
                
                if user_id in session.participant_characters:
                    char_data = session.participant_characters[user_id]
                    participant_mentions.append(f"{display_name} ({char_data['name']} Lvl{char_data['level']})")
                else:
                    participant_mentions.append(display_name)
            
            participants_text = ", ".join(participant_mentions)
            if len(session.participants) > 5:
                participants_text += f" and {len(session.participants) - 5} more"
            
            if not participants_text:
                participants_text = "None"
            
            embed.add_field(
                name=f"Session: {session.session_id}",
                value=f"DM: <@{session.dm_id}>\n"
                      f"Status: {status}\n"
                      f"Duration: {duration_str}\n"
                      f"Participants ({participants_count}): {participants_text}",
                inline=False
            )
        
        # Add refresh button
        view = SessionInfoView(self.session_manager, self.reward_calculator)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="rp_kick", description="Remove a player from the roleplay session in this thread (DM only)")
    @app_commands.describe(user="User to remove from the session")
    async def rp_kick(self, interaction: discord.Interaction, user: discord.Member):
        """Remove a player from a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread is not active.",
                ephemeral=True
            )
            return
        
        has_manage_channels = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_channels
        if interaction.user.id != session.dm_id and not has_manage_channels:
            await interaction.response.send_message(
                "❌ Only the DM or server administrators can remove players.",
                ephemeral=True
            )
            return
        
        if user.id not in session.participants:
            await interaction.response.send_message(
                f"❌ {user.mention} is not in this session.",
                ephemeral=True
            )
            return
        
        if session.remove_participant(user.id):
            time_spent = session.get_participant_time(user.id)
            rounded_time = self.reward_calculator.round_to_nearest_30_minutes(time_spent)
            time_str = self.reward_calculator.format_time_duration(rounded_time)
            await interaction.response.send_message(
                f"🚪 {user.mention} was removed from the session after {time_str}."
            )
            # Update participant table and forum tags in real-time
            if interaction.guild:
                from bot.views import update_participant_table, update_session_capacity_tags
                await update_participant_table(interaction.guild, session, self.reward_calculator)
                await update_session_capacity_tags(interaction.guild, session)
        else:
            await interaction.response.send_message("❌ Failed to remove the player.", ephemeral=True)

    @app_commands.command(name="rp_info", description="Get detailed information about the session in this thread")
    async def rp_info(self, interaction: discord.Interaction):
        """Get detailed information about a roleplay session"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # Create detailed embed
        embed = discord.Embed(
            title=f"📋 Session Info: {session_id}",
            color=0x0099ff if session.is_active else 0x888888
        )
        
        # Basic info
        status = "⏸️ Paused" if session.is_paused else ("▶️ Active" if session.is_active else "🛑 Ended")
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="DM", value=f"<@{session.dm_id}>", inline=True)
        
        # Time info
        if session.is_active:
            duration = session.get_session_duration()
        else:
            duration = session.end_time - session.start_time - session.total_paused_duration
        
        duration_str = self.reward_calculator.format_time_duration(duration)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        
        # Participants
        if session.participants or session.participant_times:
            all_participants = set(session.participants.keys()) | set(session.participant_times.keys())
            participant_info = []
            
            for user_id in all_participants:
                time_spent = session.get_participant_time(user_id)
                time_str = self.reward_calculator.format_time_duration(time_spent)
                active_indicator = " (active)" if user_id in session.participants else ""
                
                # Get display name from database first, fallback to Discord API
                display_name = "Unknown"
                if interaction.guild:
                    try:
                        # Try database lookup first
                        from bot.views import get_display_name_from_db
                        db_name = get_display_name_from_db(user_id, str(interaction.guild.id))
                        if db_name:
                            display_name = db_name
                        else:
                            # Fallback to Discord API
                            member = interaction.guild.get_member(user_id)
                            if member:
                                display_name = member.display_name
                    except:
                        pass
                
                participant_info.append(f"{display_name}: {time_str}{active_indicator}")
            
            participants_text = "\n".join(participant_info[:10])  # Show up to 10
            if len(all_participants) > 10:
                participants_text += f"\n... and {len(all_participants) - 10} more"
            
            embed.add_field(name="Participants", value=participants_text, inline=False)
        else:
            embed.add_field(name="Participants", value="None", inline=False)
        
        # If session is ended, show final rewards
        if not session.is_active and session.end_time:
            rewards = self.reward_calculator.calculate_session_rewards(session)
            if rewards:
                total_xp = sum(xp for xp, _ in rewards.values())
                total_gold = sum(gold for _, gold in rewards.values())
                embed.add_field(
                    name="Final Rewards",
                    value=f"Total: {total_xp} XP, {total_gold} gold",
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed)
    
    async def _update_forum_tags_on_session_end(self, guild: discord.Guild, session):
        """Update forum post tags when session ends - remove ALL tags except 'Completed'"""
        try:
            # Find the rp-sessions channel
            rp_sessions_channel = discord.utils.get(guild.channels, name="rp-sessions")
            if not isinstance(rp_sessions_channel, discord.ForumChannel):
                return
            
            # Get the thread
            thread = guild.get_thread(session.thread_id)
            if not isinstance(thread, discord.Thread) or thread.parent != rp_sessions_channel:
                return
            
            # Find or create the "Completed" tag
            completed_tag = None
            for tag in rp_sessions_channel.available_tags:
                if tag.name.lower() == "completed":
                    completed_tag = tag
                    break
            
            # Create completed tag if it doesn't exist
            if not completed_tag and len(rp_sessions_channel.available_tags) < 20:
                try:
                    completed_tag = await rp_sessions_channel.create_tag(name="Completed")
                except discord.HTTPException:
                    pass
            
            # Replace ALL tags with just the "Completed" tag
            new_tags = [completed_tag] if completed_tag else []
            
            # Update thread tags (removes all other tags, keeps only Completed)
            await thread.edit(applied_tags=new_tags)
            
            # Schedule the thread to be locked in 4 hours
            import asyncio
            from bot.views import schedule_forum_lock
            asyncio.create_task(schedule_forum_lock(thread))
            
        except Exception as e:
            # Silent fail - tag updates are nice-to-have, not critical
            pass
    
    @app_commands.command(name="rp_repost", description="Repost the session control panel in this thread")
    async def rp_repost(self, interaction: discord.Interaction):
        """Repost the session control panel for the session running in this thread"""
        session, session_id, error_msg = self._get_session_from_thread(interaction)
        
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # session is guaranteed to exist at this point due to helper function check
        if not session.is_active:
            await interaction.response.send_message(
                f"❌ The session in this thread has already ended.",
                ephemeral=True
            )
            return
        
        # Check if user is DM or has admin permissions
        has_manage_channels = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_channels
        if interaction.user.id != session.dm_id and not has_manage_channels:
            await interaction.response.send_message(
                "❌ Only the DM or server administrators can repost the session control panel.",
                ephemeral=True
            )
            return
        
        try:
            # We're already in the correct thread
            thread = interaction.channel
            
            # Import the session setup view to create a new control panel
            from bot.session_setup_view import SessionSetupView
            from bot.views import _generate_participant_table
            
            # Generate the control panel embed
            embed = discord.Embed(
                title=f"🎲 D&D Session: {session_id}",
                description=f"**DM:** <@{session.dm_id}>\n**Type:** {getattr(session, 'session_type', 'Unknown')}\n**Status:** {'⏸️ Paused' if session.is_paused else '▶️ Active'}",
                color=0x00ff00 if session.is_active else 0x888888
            )
            
            # Add session info
            duration = session.get_session_duration()
            duration_str = self.reward_calculator.format_time_duration(duration)
            status = "⏸️ Paused" if session.is_paused else ("▶️ Active" if session.is_active else "🛑 Completed")
            embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)
            embed.add_field(name="👥 Active Players", value=f"{len(session.participants)}/{getattr(session, 'max_players', 20)}", inline=True)
            embed.add_field(name="📊 Status", value=status, inline=True)
            embed.add_field(name="🎯 Session ID", value=f"`{session_id}`", inline=True)
            
            # Add participant table
            participant_table = await _generate_participant_table(session, self.reward_calculator, interaction.guild)
            embed.add_field(name=f"👥 Participants ({len(session.participants)})", value=participant_table, inline=False)
            
            # Create the control view
            view = SessionSetupView.create_session_control_view(session_id, session.dm_id)
            
            # Post the new control panel in the thread
            await thread.send(embed=embed, view=view)
            
            await interaction.response.send_message(
                f"✅ Reposted session control panel for **{session_id}** in the session thread.",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to repost session control panel: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="rp_debug_update", description="Force update participant tables (debug)")
    async def rp_debug_update(self, interaction: discord.Interaction):
        """Debug command to force update all participant tables"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin only command.", ephemeral=True)
            return
        
        await interaction.response.send_message("🔄 Forcing participant table updates...", ephemeral=True)
        
        try:
            from bot.views import update_all_participant_tables
            await update_all_participant_tables()
            await interaction.followup.send("✅ Update completed. Check console for debug output.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Update failed: {e}", ephemeral=True)

    @app_commands.command(name="bot_docs", description="Post/update bot command documentation (Moderator only)")
    @app_commands.describe(
        action="Choose to post new documentation or update existing",
        channel="Channel to post documentation (defaults to bot-information)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Post New Documentation", value="post"),
        app_commands.Choice(name="Update Existing Documentation", value="update")
    ])
    async def post_bot_documentation(self, interaction: discord.Interaction, action: str, channel: Optional[discord.TextChannel] = None):
        """Post or update bot command documentation in a thread"""
        try:
            # Check if user has moderator permissions
            if not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                return
            
            # Check for moderator role or manage channels permission
            has_mod_role = any(role.name.lower() in ['moderator', 'mod', 'admin', 'administrator'] for role in interaction.user.roles)
            has_manage_permission = interaction.user.guild_permissions.manage_channels
            
            if not (has_mod_role or has_manage_permission):
                await interaction.response.send_message(
                    "❌ You need moderator role or manage channels permission to use this command.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # Default to bot-information channel if none specified
            target_channel = channel
            if not target_channel:
                bot_info_channel = discord.utils.get(interaction.guild.channels, name="bot-information")
                if not bot_info_channel:
                    await interaction.followup.send(
                        "❌ No #bot-information channel found. Please specify a channel or create #bot-information.",
                        ephemeral=True
                    )
                    return
                
                # Handle forum channels differently
                if isinstance(bot_info_channel, discord.ForumChannel):
                    # For forum channels, we need to create a post directly
                    target_channel = bot_info_channel
                else:
                    # Regular text channel
                    target_channel = bot_info_channel
            
            # Load documentation content
            try:
                with open('DISCORD_BOT_COMMANDS.md', 'r', encoding='utf-8') as f:
                    doc_content = f.read()
            except FileNotFoundError:
                await interaction.followup.send(
                    "❌ Documentation file not found. Please contact the bot developer.",
                    ephemeral=True
                )
                return
            
            if action == "post":
                # Create new thread with documentation
                thread_name = f"🤖 Bot Commands Reference - {discord.utils.utcnow().strftime('%Y-%m-%d')}"
                
                # Create initial embed
                embed = discord.Embed(
                    title="🤖 Discord D&D Bot - Command Reference",
                    description="Complete documentation for all bot commands and features.",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(
                    name="📋 What's Included",
                    value="• Session Management Commands\n• Character Alias System\n• Sharing & Collaboration\n• Achievement System\n• Tips & Best Practices",
                    inline=False
                )
                embed.add_field(
                    name="🔄 Updates",
                    value="This documentation is updated automatically when new features are added.",
                    inline=False
                )
                embed.set_footer(text="Use /bot_docs action:Update to refresh this documentation")
                
                # Handle forum channels vs regular text channels
                if isinstance(target_channel, discord.ForumChannel):
                    # Create a forum post directly
                    thread, message = await target_channel.create_thread(
                        name=thread_name,
                        content="📚 **Bot Command Documentation**",
                        embed=embed,
                        auto_archive_duration=10080  # 7 days
                    )
                else:
                    # Regular text channel - post message and create thread
                    message = await target_channel.send(embed=embed)
                    thread = await message.create_thread(name=thread_name, auto_archive_duration=10080)  # 7 days
                
                # Split documentation into chunks (Discord's 2000 char limit)
                await self._post_documentation_chunks(thread, doc_content)
                
                await interaction.followup.send(
                    f"✅ Bot documentation posted in {target_channel.mention} with thread: {thread.mention}",
                    ephemeral=True
                )
                
            elif action == "update":
                # Find existing documentation thread
                threads = []
                
                # Handle forum channels vs regular text channels
                if isinstance(target_channel, discord.ForumChannel):
                    # For forum channels, check archived threads
                    async for thread in target_channel.archived_threads(limit=50):
                        if thread.name.startswith("🤖 Bot Commands Reference"):
                            threads.append(thread)
                    
                    # Also check active threads in forum
                    for thread in target_channel.threads:
                        if thread.name.startswith("🤖 Bot Commands Reference"):
                            threads.append(thread)
                else:
                    # For regular text channels
                    async for thread in target_channel.archived_threads(limit=50):
                        if thread.name.startswith("🤖 Bot Commands Reference"):
                            threads.append(thread)
                    
                    # Also check active threads
                    for thread in target_channel.threads:
                        if thread.name.startswith("🤖 Bot Commands Reference"):
                            threads.append(thread)
                
                if not threads:
                    await interaction.followup.send(
                        "❌ No existing documentation thread found. Use 'Post New Documentation' instead.",
                        ephemeral=True
                    )
                    return
                
                # Use the most recent thread
                latest_thread = max(threads, key=lambda t: t.created_at)
                
                # Clear old messages (keep the first embed message)
                messages_to_delete = []
                async for message in latest_thread.history(limit=100):
                    if message.author == self.bot.user and len(message.embeds) == 0:
                        messages_to_delete.append(message)
                
                # Delete in batches to avoid rate limits
                for message in messages_to_delete:
                    try:
                        await message.delete()
                    except discord.NotFound:
                        pass
                
                # Post updated documentation
                await self._post_documentation_chunks(latest_thread, doc_content)
                
                # Update the main embed with timestamp
                async for message in latest_thread.history(limit=1, oldest_first=True):
                    if message.author == self.bot.user and message.embeds:
                        embed = message.embeds[0]
                        embed.timestamp = discord.utils.utcnow()
                        embed.set_field_at(1, name="🔄 Last Updated", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>", inline=False)
                        await message.edit(embed=embed)
                        break
                
                await interaction.followup.send(
                    f"✅ Documentation updated in thread: {latest_thread.mention}",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in bot_docs command: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    async def _post_documentation_chunks(self, thread: discord.Thread, content: str):
        """Split and post documentation content in chunks with proper Discord formatting"""
        lines = content.split('\n')
        current_chunk = ""
        
        for line in lines:
            # Process line for better Discord formatting
            processed_line = self._format_line_for_discord(line)
            
            # Check if adding this line would exceed Discord's limit
            if len(current_chunk) + len(processed_line) + 1 > 1900:  # Leave some buffer
                if current_chunk.strip():
                    await thread.send(current_chunk.strip())
                current_chunk = processed_line + "\n"
            else:
                current_chunk += processed_line + "\n"
        
        # Send the last chunk
        if current_chunk.strip():
            await thread.send(current_chunk.strip())
    
    def _format_line_for_discord(self, line: str) -> str:
        """Format a line for proper Discord display"""
        # Handle headers with command names
        if line.startswith("### `/") and "` - " in line:
            # Split at the dash to avoid markdown formatting issues
            parts = line.split("` - ", 1)
            if len(parts) == 2:
                command_part = parts[0] + "`"
                description_part = parts[1]
                return f"**{command_part}** - {description_part}"
        
        # Handle section headers
        elif line.startswith("## "):
            return f"**{line[3:]}**\n" + "─" * min(len(line[3:]), 40)
        
        # Handle main headers  
        elif line.startswith("# "):
            return f"**🎯 {line[2:]}**\n" + "═" * min(len(line[2:]) + 4, 40)
        
        # Handle subsection headers
        elif line.startswith("#### "):
            return f"**{line[5:]}**"
        
        # Handle bullet points
        elif line.strip().startswith("- "):
            return f"• {line.strip()[2:]}"
        
        # Handle code blocks - keep as is but ensure proper formatting
        elif line.strip().startswith("```"):
            return line
        
        # Handle inline code
        elif "`" in line and not line.strip().startswith("```"):
            # Replace backticks with Discord's inline code formatting
            return line
        
        # Regular lines
        else:
            return line
