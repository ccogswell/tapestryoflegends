import discord
from discord.ext import commands, tasks
from typing import Optional
import re
import asyncio
from database import get_db_session
from models import GuildMember
import logging

logger = logging.getLogger(__name__)

def get_display_name_from_db(user_id: int, guild_id: str) -> Optional[str]:
    """Get display name from database for better performance than Discord API calls"""
    try:
        with get_db_session() as db_session:
            member = db_session.query(GuildMember).filter(
                GuildMember.guild_id == str(guild_id),
                GuildMember.user_id == str(user_id)
            ).first()
            
            if member:
                # Use display name with priority: display_name > global_name > username
                return member.display_name or member.global_name or member.username
    except Exception as e:
        logger.error(f"Database lookup failed for user {user_id} in guild {guild_id}: {e}")
    
    return None

async def update_participant_table(guild: discord.Guild, session, reward_calculator):
    """Update the participant table in the session control embed (real-time updates)"""
    if not session.thread_id or not guild:
        return
    
    try:
        # Get the thread
        thread = guild.get_thread(session.thread_id)
        if not isinstance(thread, discord.Thread):
            return
        
        # Find the session control message (first message in thread that has embed with participant table)
        async for message in thread.history(limit=20, oldest_first=True):
            if message.embeds and "👥 Participants" in str(message.embeds[0].fields):
                # Found the control message, update it
                embed = message.embeds[0]
                
                # Generate updated participant table
                participant_table = await _generate_participant_table(session, reward_calculator, guild)
                
                # Update multiple fields: duration, status, and participant table
                session_duration = session.get_session_duration()
                duration_str = reward_calculator.format_time_duration(session_duration)
                
                # Determine status including not started state
                if not session.session_started:
                    status = "⚠️ Not Started"
                elif session.is_paused:
                    status = "⏸️ Paused"
                elif session.is_active:
                    status = "▶️ Active"
                else:
                    status = "🛑 Completed"
                
                # Update embed description status as well
                if embed.description and "**Status:**" in embed.description:
                    # Extract and replace the status in the description
                    description_lines = embed.description.split('\n')
                    for i, line in enumerate(description_lines):
                        if line.startswith("**Status:**"):
                            # Check if session has started for status display
                            if not session.session_started:
                                status = "⚠️ Not Started"
                            description_lines[i] = f"**Status:** {status}"
                            break
                    embed.description = '\n'.join(description_lines)
                
                for i, field in enumerate(embed.fields):
                    if field.name and field.name.startswith("👥 Participants"):
                        embed.set_field_at(i, name=f"👥 Participants ({len(session.participants)})", value=participant_table, inline=False)
                    elif field.name and "Duration" in field.name:
                        embed.set_field_at(i, name="⏱️ Duration", value=duration_str, inline=True)
                    elif field.name and "Status" in field.name:
                        embed.set_field_at(i, name="📊 Status", value=status, inline=True)
                
                # Update the message
                try:
                    await message.edit(embed=embed)
                    print(f"DEBUG: Successfully updated participant table for session {session.session_id}")
                except discord.HTTPException as e:
                    print(f"DEBUG: Failed to edit message: {e}")
                except Exception as e:
                    print(f"DEBUG: Unexpected error editing message: {e}")
                break
    except Exception as e:
        # Debug output for troubleshooting
        print(f"DEBUG: Error in update_participant_table: {e}")
        import traceback
        traceback.print_exc()

async def _generate_rewards_table(session, reward_calculator, guild=None, calculated_rewards=None):
    """Generate a formatted participant table for rewards posting (without status column)"""
    # If no participants, show empty table
    if not session.participants and not session.participant_times:
        return "`Player        Character       Lv   Time   XP     Gold`\n`────────────────────────────────────────────────────────`\n`No participants yet - Use 'Join Session' to participate!`"
    
    # Combine active participants and those with recorded time
    all_participants = set(session.participants.keys()) | set(session.participant_times.keys())
    
    # Use consistent monospace formatting for proper alignment with centered headers
    table_rows = []
    table_rows.append("`Player        Character       Lv   Time   XP     Gold`")
    table_rows.append("`────────────────────────────────────────────────────────`")
    
    for user_id in sorted(all_participants):
        # Get display name from database first, fallback to Discord API
        player_name = "Unknown"
        if guild:
            # Try database lookup first (much faster)
            db_name = get_display_name_from_db(user_id, str(guild.id))
            if db_name:
                player_name = db_name[:14].ljust(14)
            else:
                # Fallback to Discord API calls
                try:
                    member = guild.get_member(user_id)
                    if member:
                        player_name = member.display_name[:14].ljust(14)
                    else:
                        try:
                            member = await guild.fetch_member(user_id)
                            if member:
                                player_name = member.display_name[:14].ljust(14)
                            else:
                                player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
                        except:
                            player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
                except Exception:
                    player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
        else:
            player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
        
        # Get character info
        if user_id in session.participant_characters:
            char_data = session.participant_characters[user_id]
            character_name = str(char_data['name'])[:15].ljust(15)
            character_level = str(char_data['level']).center(4)
        else:
            character_name = "Unknown".ljust(15)
            character_level = "?".center(4)
        
        # Get time spent
        time_spent = session.get_participant_time(user_id)
        total_minutes = int(time_spent.total_seconds() / 60)
        if total_minutes < 60:
            time_str = f"{total_minutes}m".center(6)
        else:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if minutes > 0:
                time_str = f"{hours}h{minutes}m".center(6)
            else:
                time_str = f"{hours}h".center(6)
        
        # Get XP and Gold from calculated rewards or default to 0
        xp, gold = 0, 0
        if calculated_rewards and user_id in calculated_rewards:
            reward_data = calculated_rewards[user_id]
            if isinstance(reward_data, tuple) and len(reward_data) == 2:
                xp, gold = reward_data
            elif isinstance(reward_data, dict):
                xp = reward_data.get('xp', 0)
                gold = reward_data.get('gold', 0)
        
        # Format XP and Gold with centering - match participant table format
        xp_str = str(xp)[:5].center(6)  # Max 5 digits, centered in 6 chars
        gold_str = str(gold)[:5].center(6)  # Max 5 digits, centered in 6 chars
        
        # Format the row to match header exactly (no status column for rewards table)
        # Header analysis: Player(14) Character(16) Lv(5) Time(7) XP(7) Gold(7)
        player_field = player_name[:14].ljust(14)       # Position 0-13 (14 chars)
        character_field = character_name[:9].ljust(16)  # Position 14-29 (16 chars)
        lv_field = str(character_level).center(5)       # Position 30-34 (5 chars) - convert to string first
        time_field = time_str.center(7)                 # Position 35-41 (7 chars)
        xp_field = str(xp).center(7)                    # Position 42-48 (7 chars)
        gold_field = str(gold).center(7)                # Position 49-55 (7 chars)
        
        row = f"`{player_field}{character_field}{lv_field}{time_field}{xp_field}{gold_field}`"
        table_rows.append(row)
    
    return "\n".join(table_rows)

async def _generate_participant_table(session, reward_calculator, guild=None):
    """Generate a formatted participant table for display using wider format"""
    if not session.participants and not session.participant_times:
        # Use same format as populated table for consistency
        return "`Player        Character       Lv   Time   XP     Gold   Status`\n`──────────────────────────────────────────────────────────────`\n`No participants yet - Use 'Join Session' to participate!      `"
    
    # Combine active participants and those with recorded time
    all_participants = set(session.participants.keys()) | set(session.participant_times.keys())
    
    # Use consistent monospace formatting for proper alignment
    table_rows = []
    # Header: Player(14) Character(15) Lv(4) Time(6) XP(6) Gold(6) Status(6)
    table_rows.append("`Player        Character       Lv   Time   XP     Gold   Status`")
    table_rows.append("`──────────────────────────────────────────────────────────────`")
    
    for user_id in sorted(all_participants):
        # Get display name from guild member if available
        player_name = "Unknown"
        if guild:
            # Try database lookup first (much faster)
            db_name = get_display_name_from_db(user_id, str(guild.id))
            if db_name:
                player_name = db_name[:14].ljust(14)
            else:
                # Fallback to Discord API calls
                try:
                    # Try to get member from guild
                    member = guild.get_member(user_id)
                    if member:
                        # Use display name (server nickname if set, otherwise username)  
                        player_name = member.display_name[:14].ljust(14)
                    else:
                        # If member not found, try to fetch from Discord API
                        try:
                            member = await guild.fetch_member(user_id)
                            if member:
                                player_name = member.display_name[:14].ljust(14)
                            else:
                                player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
                        except:
                            player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
                except Exception as e:
                    # Fallback to last 4 digits of user ID
                    player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
        else:
            player_name = f"User{str(user_id)[-4:]}"[:14].ljust(14)
        
        # Get character info - separate name and level
        if user_id in session.participant_characters:
            char_data = session.participant_characters[user_id]
            character_name = str(char_data['name'])[:15].ljust(15)
            character_level = str(char_data['level']).center(4)
        else:
            character_name = "Unknown".ljust(15)
            character_level = "?".center(4)
        
        # Get time spent - display only minutes (rounded down)
        time_spent = session.get_participant_time(user_id)
        total_minutes = int(time_spent.total_seconds() / 60)  # Round down to minutes
        if total_minutes < 60:
            time_str = f"{total_minutes}m".center(6)
        else:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if minutes > 0:
                time_str = f"{hours}h{minutes}m".center(6)
            else:
                time_str = f"{hours}h".center(6)
        
        # Calculate potential rewards based on current time
        xp_reward = 0
        gold_reward = 0
        
        if user_id in session.participant_characters:
            char_data = session.participant_characters[user_id]
            character_level = char_data['level']
            
            # Use the reward calculator to get current potential rewards
            rounded_time = reward_calculator.round_to_nearest_30_minutes(time_spent)
            
            if rounded_time.total_seconds() >= (reward_calculator.min_participation_minutes * 60):
                # Calculate XP based on character level
                xp_per_hour = reward_calculator.get_xp_rate_for_level(character_level)
                hours = rounded_time.total_seconds() / 3600
                xp_reward = int(xp_per_hour * hours)
                
                # Calculate Gold based on character level  
                gold_per_hour = character_level * 10
                gold_reward = int(gold_per_hour * hours)
                
                # Apply DM bonus if this user is the DM
                if user_id == session.dm_id:
                    xp_reward = int(xp_reward * 1.5)
                    gold_reward = int(gold_reward * 1.5)
                
                # Apply session length bonus if session is long (2+ hours)
                session_duration = session.get_session_duration()
                if session_duration.total_seconds() >= (reward_calculator.long_session_bonus_threshold * 60):
                    xp_reward = int(xp_reward * 1.2)
                    gold_reward = int(gold_reward * 1.2)
        
        # Format reward columns - compact centered fields  
        xp_str = str(xp_reward)[:5].center(6)  # Max 5 digits, centered in 6 chars
        gold_str = str(gold_reward)[:5].center(6)  # Max 5 digits, centered in 6 chars
        
        # Get status
        status = "Active" if user_id in session.participants else "Left"
        if session.is_paused and user_id in session.participants:
            status = "Paused"
        status_str = status[:6].center(6)  # Status in 6 chars, centered
        
        # Use consistent monospace format with proper alignment to match header exactly
        # Header analysis: Player(14) Character(16) Lv(5) Time(7) XP(7) Gold(7) Status(6)
        # Format each field to match header positions precisely
        player_field = player_name[:14].ljust(14)       # Position 0-13 (14 chars)
        character_field = character_name[:9].ljust(16)  # Position 14-29 (16 chars) 
        lv_field = str(character_level).center(5)       # Position 30-34 (5 chars) - convert to string first
        time_field = time_str.center(7)                 # Position 35-41 (7 chars)
        xp_field = str(xp_reward).center(7)             # Position 42-48 (7 chars) - use actual values
        gold_field = str(gold_reward).center(7)         # Position 49-55 (7 chars) - use actual values
        status_field = status_str.center(6)             # Position 56-61 (6 chars)
        
        table_rows.append(f"`{player_field}{character_field}{lv_field}{time_field}{xp_field}{gold_field}{status_field}`")
    
    # Limit to 12 rows to prevent message being too long
    if len(table_rows) > 14:  # 2 header rows + 12 data rows
        table_rows = table_rows[:14]
        table_rows.append("*... and more (truncated for Discord limits)*")
    
    # Return as plain text with inline code blocks for each row - this gives more width
    return "\n".join(table_rows)

async def update_session_capacity_tags(guild: discord.Guild, session):
    """Update forum tags based on current player capacity"""
    if not session.thread_id or not guild:
        return
    
    try:
        # Find the rp-sessions channel
        rp_sessions_channel = discord.utils.get(guild.channels, name="rp-sessions")
        if not isinstance(rp_sessions_channel, discord.ForumChannel):
            return
        
        # Get the thread
        thread = guild.get_thread(session.thread_id)
        if not isinstance(thread, discord.Thread) or thread.parent != rp_sessions_channel:
            return
        
        # Get current tags
        current_tags = list(thread.applied_tags)
        
        # Find or create capacity tags
        accepting_tag = None
        full_tag = None
        
        for tag in rp_sessions_channel.available_tags:
            if tag.name.lower() == "accepting players":
                accepting_tag = tag
            elif tag.name.lower() == "full":
                full_tag = tag
        
        # Create tags if they don't exist
        if not accepting_tag and len(rp_sessions_channel.available_tags) < 20:
            try:
                accepting_tag = await rp_sessions_channel.create_tag(name="Accepting Players")
            except discord.HTTPException:
                pass
        
        if not full_tag and len(rp_sessions_channel.available_tags) < 20:
            try:
                full_tag = await rp_sessions_channel.create_tag(name="Full")
            except discord.HTTPException:
                pass
        
        # Update tags based on current capacity
        if session.is_full():
            # Session is full - remove accepting, add full
            if accepting_tag and accepting_tag in current_tags:
                current_tags.remove(accepting_tag)
            if full_tag and full_tag not in current_tags:
                current_tags.append(full_tag)
        else:
            # Session has space - remove full, add accepting
            if full_tag and full_tag in current_tags:
                current_tags.remove(full_tag)
            if accepting_tag and accepting_tag not in current_tags:
                current_tags.append(accepting_tag)
        
        # Update thread tags
        await thread.edit(applied_tags=current_tags)
        
    except Exception as e:
        # Silent fail - tag updates are nice-to-have, not critical
        pass

async def schedule_forum_lock(thread: discord.Thread):
    """Schedule forum post to be locked in 4 hours"""
    if not isinstance(thread, discord.Thread):
        return
    
    try:
        # Wait for 4 hours (14400 seconds)
        await asyncio.sleep(14400)
        
        # Lock the thread
        await thread.edit(locked=True, reason="Session completed - auto-locked after 4 hours")
        
    except Exception as e:
        # Silent fail - locking is nice-to-have, not critical
        pass

# Global task for updating participant tables
participant_update_task = None

@tasks.loop(minutes=1)
async def update_all_participant_tables():
    """Update participant tables every minute for all active sessions"""
    try:
        print("DEBUG: Running participant table update task...")
        # Import here to avoid circular imports
        from main import bot
        
        if not bot or not hasattr(bot, 'get_cog'):
            print("DEBUG: Bot not available or no get_cog method")
            return
            
        commands_cog = bot.get_cog('RPCommands')
        if not commands_cog:
            print("DEBUG: RPCommands cog not found")
            return
            
        # Access the attributes directly from the cog
        session_manager = getattr(commands_cog, 'session_manager', None)
        reward_calculator = getattr(commands_cog, 'reward_calculator', None)
        
        if not session_manager or not reward_calculator:
            print("DEBUG: Session manager or reward calculator not available")
            return
        
        active_session_count = 0
        # Update tables for all active sessions across all guilds
        for guild_id, sessions in session_manager.sessions.items():
            guild = bot.get_guild(guild_id)
            if not guild:
                continue
                
            for session in sessions.values():
                if session.is_active:
                    # Only update if session has participants (include paused sessions)
                    if session.participants or session.participant_times:
                        active_session_count += 1
                        print(f"DEBUG: Updating table for session {session.session_id}")
                        try:
                            await update_participant_table(guild, session, reward_calculator)
                        except Exception as e:
                            print(f"DEBUG: Failed to update session {session.session_id}: {e}")
        
        print(f"DEBUG: Updated {active_session_count} active sessions")
                        
    except Exception as e:
        print(f"DEBUG: Error in update_all_participant_tables: {e}")
        import traceback
        traceback.print_exc()

def start_participant_update_task():
    """Start the participant table update task"""
    global participant_update_task
    if participant_update_task is None or participant_update_task.is_being_cancelled():
        participant_update_task = update_all_participant_tables
        participant_update_task.start()

def stop_participant_update_task():
    """Stop the participant table update task"""
    global participant_update_task
    if participant_update_task and not participant_update_task.is_being_cancelled():
        participant_update_task.cancel()

class CharacterInfoModal(discord.ui.Modal, title='Character Information'):
    """Modal for collecting character name and level"""
    
    def __init__(self, session_manager, reward_calculator, session_id: str):
        super().__init__()
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator
        self.session_id = session_id

    character_info = discord.ui.TextInput(
        label='Character Name and Level',
        placeholder='Enter: Character Name Level (e.g., "Gandalf 15")',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Process character information and join session"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        if interaction.user.id in session.participants:
            await interaction.response.send_message("❌ You are already in this session.", ephemeral=True)
            return
        
        # Parse character name and level
        input_text = self.character_info.value.strip()
        
        # Try to extract level from the end of the input
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
        print(f"DEBUG: Stored display name '{display_name}' for user {interaction.user.id}")
        
        # Add participant with character info
        if session.add_participant(interaction.user.id, character_name, character_level):
            await interaction.response.send_message(
                f"✅ {interaction.user.mention} joined as **{character_name}** (Level {character_level})!", 
                ephemeral=False
            )
            # Update participant table and forum tags
            if interaction.guild:
                await update_participant_table(interaction.guild, session, self.reward_calculator)
                await update_session_capacity_tags(interaction.guild, session)
        else:
            await interaction.response.send_message("❌ Failed to join the session.", ephemeral=True)

async def get_or_create_rp_host_role(guild: discord.Guild) -> discord.Role:
    """Get or create the RP Session Host role"""
    role_name = "RP Session Host"
    
    # Check if role already exists
    existing_role = discord.utils.get(guild.roles, name=role_name)
    if existing_role:
        return existing_role
    
    # Create the role with appropriate permissions
    try:
        role = await guild.create_role(
            name=role_name,
            reason="Auto-created for RP session management",
            mentionable=False,
            hoist=False
        )
        return role
    except discord.Forbidden:
        raise Exception(f"Bot lacks permission to create '{role_name}' role")
    except discord.HTTPException as e:
        raise Exception(f"Failed to create '{role_name}' role: {e}")

async def assign_rp_host_role(member: discord.Member, channel: discord.abc.GuildChannel) -> bool:
    """Assign RP Session Host role if in rp-sessions channel"""
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return False
    
    # Check if we're in rp-sessions channel or its threads
    target_channel = channel
    if isinstance(channel, discord.Thread):
        target_channel = channel.parent
    
    if not target_channel or target_channel.name != "rp-sessions":
        return False
    
    try:
        role = await get_or_create_rp_host_role(member.guild)
        await member.add_roles(role, reason="Started RP session")
        return True
    except Exception as e:
        print(f"DEBUG: Failed to assign RP host role: {e}")
        return False

async def remove_rp_host_role(member: discord.Member) -> bool:
    """Remove RP Session Host role"""
    try:
        role = discord.utils.get(member.guild.roles, name="RP Session Host")
        if role and role in member.roles:
            await member.remove_roles(role, reason="RP session completed")
            return True
        return False
    except Exception as e:
        print(f"DEBUG: Failed to remove RP host role: {e}")
        return False

def has_rp_host_role(member: discord.Member, channel: discord.abc.GuildChannel) -> bool:
    """Check if member has RP Session Host role and is in rp-sessions channel"""
    # Check if we're in rp-sessions channel or its threads
    target_channel = channel
    if isinstance(channel, discord.Thread):
        target_channel = channel.parent
    
    if not target_channel or target_channel.name != "rp-sessions":
        return False
    
    role = discord.utils.get(member.guild.roles, name="RP Session Host")
    return role is not None and role in member.roles

class SessionControlView(discord.ui.View):
    """Interactive view with buttons for session control"""
    
    def __init__(self, session_manager, reward_calculator, session_id: str):
        super().__init__(timeout=None)  # No timeout for persistent view
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator
        self.session_id = session_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can interact with control buttons"""
        # Get the custom_id to identify which button was pressed
        custom_id = interaction.data.get('custom_id', '') if hasattr(interaction, 'data') and interaction.data else ''
        
        print(f"DEBUG: Button pressed: {custom_id} by {interaction.user.display_name}")
        
        # These buttons are available to everyone - no role check needed
        public_buttons = ['join_session', 'leave_session']
        
        if custom_id in public_buttons:
            print(f"DEBUG: Allowing public button: {custom_id}")
            return True
        
        # For DM control buttons, check if user is DM or has RP Host role
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        if not session:
            return True  # Let the button handle the error
            
        # Check if user has RP Host role or is the original DM
        has_permission = (interaction.user.id == session.dm_id or 
                         (isinstance(interaction.user, discord.Member) and interaction.guild and interaction.channel and 
                          isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and
                          has_rp_host_role(interaction.user, interaction.channel)))
        
        if not has_permission:
            print(f"DEBUG: Permission denied for {interaction.user.display_name} on button {custom_id}")
            await interaction.response.send_message("❌ Only users with RP Session Host role can use session controls.", ephemeral=True)
            return False
            
        return True

    @discord.ui.button(label='Start Session', style=discord.ButtonStyle.primary, emoji='🚀')
    async def start_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to manually start the session timer (RP Host only)"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        # Check if user has RP Host role or is the original DM (for backwards compatibility)
        if not (interaction.user.id == session.dm_id or 
               (isinstance(interaction.user, discord.Member) and interaction.guild and interaction.channel and 
                isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and
                has_rp_host_role(interaction.user, interaction.channel))):
            await interaction.response.send_message("❌ Only users with RP Session Host role can start the session timer.", ephemeral=True)
            return
        
        if session.session_started:
            await interaction.response.send_message("❌ Session timer has already been started.", ephemeral=True)
            return
        
        if session.start_session():
            await interaction.response.send_message("🚀 Session timer started! Tracking begins now.", ephemeral=False)
            # Update participant table to reflect started status
            if interaction.guild:
                await update_participant_table(interaction.guild, session, self.reward_calculator)
        else:
            await interaction.response.send_message("❌ Failed to start session timer.", ephemeral=True)

    @discord.ui.button(label='Join Session', style=discord.ButtonStyle.green, emoji='➕', custom_id='join_session')
    async def join_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to join the roleplay session"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        if interaction.user.id in session.participants:
            await interaction.response.send_message("❌ You are already in this session.", ephemeral=True)
            return
        
        # Show character info modal
        modal = CharacterInfoModal(self.session_manager, self.reward_calculator, self.session_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='Leave Session', style=discord.ButtonStyle.red, emoji='➖', custom_id='leave_session')
    async def leave_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to leave the roleplay session"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        if interaction.user.id not in session.participants:
            await interaction.response.send_message("❌ You are not in this session.", ephemeral=True)
            return
        
        if session.remove_participant(interaction.user.id):
            time_spent = session.get_participant_time(interaction.user.id)
            rounded_time = self.reward_calculator.round_to_nearest_30_minutes(time_spent)
            time_str = self.reward_calculator.format_time_duration(rounded_time)
            await interaction.response.send_message(
                f"👋 {interaction.user.mention} left the roleplay session after {time_str}.", 
                ephemeral=False
            )
            # Update participant table and forum tags
            if interaction.guild:
                await update_participant_table(interaction.guild, session, self.reward_calculator)
                await update_session_capacity_tags(interaction.guild, session)
        else:
            await interaction.response.send_message("❌ Failed to leave the session.", ephemeral=True)

    @discord.ui.button(label='Pause', style=discord.ButtonStyle.secondary, emoji='⏸️')
    async def pause_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to pause the roleplay session (DM only)"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        # Check if user has RP Host role or is the original DM
        if not (interaction.user.id == session.dm_id or 
               (isinstance(interaction.user, discord.Member) and interaction.guild and interaction.channel and 
                isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and
                has_rp_host_role(interaction.user, interaction.channel))):
            await interaction.response.send_message("❌ Only users with RP Session Host role can pause the session.", ephemeral=True)
            return
        
        if session.is_paused:
            await interaction.response.send_message("❌ Session is already paused.", ephemeral=True)
            return
        
        session.pause_session()
        await interaction.response.send_message("⏸️ Session paused by the DM.", ephemeral=False)
        # Update participant table to reflect paused status
        if interaction.guild:
            await update_participant_table(interaction.guild, session, self.reward_calculator)

    @discord.ui.button(label='Resume', style=discord.ButtonStyle.secondary, emoji='▶️')
    async def resume_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to resume the roleplay session (DM only)"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        # Check if user has RP Host role or is the original DM
        if not (interaction.user.id == session.dm_id or 
               (isinstance(interaction.user, discord.Member) and interaction.guild and interaction.channel and 
                isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and
                has_rp_host_role(interaction.user, interaction.channel))):
            await interaction.response.send_message("❌ Only users with RP Session Host role can resume the session.", ephemeral=True)
            return
        
        if not session.is_paused:
            await interaction.response.send_message("❌ Session is not paused.", ephemeral=True)
            return
        
        session.resume_session()
        await interaction.response.send_message("▶️ Session resumed by the DM.", ephemeral=False)
        # Update participant table to reflect resumed status
        if interaction.guild:
            await update_participant_table(interaction.guild, session, self.reward_calculator)

    @discord.ui.button(label='Kick Player', style=discord.ButtonStyle.secondary, emoji='🦶')
    async def kick_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to kick a player from the session (DM only)"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        # Check if user has RP Host role or is the original DM
        if not (interaction.user.id == session.dm_id or 
               (isinstance(interaction.user, discord.Member) and interaction.guild and interaction.channel and 
                isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and
                has_rp_host_role(interaction.user, interaction.channel))):
            await interaction.response.send_message("❌ Only users with RP Session Host role can kick players.", ephemeral=True)
            return
        
        if not session.participants:
            await interaction.response.send_message("❌ No players are currently in the session.", ephemeral=True)
            return
        
        # Show kick player modal
        from bot.modals import KickPlayerModal
        modal = KickPlayerModal(self.session_manager, self.reward_calculator, self.session_id, session)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='End Session', style=discord.ButtonStyle.danger, emoji='🛑')
    async def end_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to end the roleplay session (DM only)"""
        session = self.session_manager.get_session(interaction.guild_id, self.session_id)
        
        if not session or not session.is_active:
            await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
            return
        
        # Check if user has RP Host role or is the original DM
        if not (interaction.user.id == session.dm_id or 
               (isinstance(interaction.user, discord.Member) and interaction.guild and interaction.channel and 
                isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and
                has_rp_host_role(interaction.user, interaction.channel))):
            await interaction.response.send_message("❌ Only users with RP Session Host role can end the session.", ephemeral=True)
            return
        
        # End the session
        ended_session = self.session_manager.end_session(interaction.guild_id, self.session_id)
        
        # Update forum post tags if it's a forum thread
        if ended_session and ended_session.thread_id and interaction.guild:
            await self._update_forum_tags(interaction.guild, ended_session)
        
        if ended_session:
            # Disable all buttons
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            
            # Session ended message 
            embed = discord.Embed(
                title="🛑 Roleplay Session Ended",
                description=f"Session **{self.session_id}** has concluded!",
                color=0xff0000
            )
            
            session_duration = ended_session.get_session_duration()
            duration_str = self.reward_calculator.format_time_duration(session_duration)
            
            embed.add_field(name="Duration", value=duration_str, inline=True)
            # Count all participants, not just those with rewards
            all_participants = set(ended_session.participants.keys()) | set(ended_session.participant_times.keys())
            embed.add_field(name="Participants", value=str(len(all_participants)), inline=True)
            embed.add_field(name="DM", value=f"<@{ended_session.dm_id}>", inline=True)
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            # Calculate and post rewards using the same logic as the command handler
            rewards = self.reward_calculator.calculate_session_rewards(ended_session)
            
            reward_embed = discord.Embed(
                title="💰 Session Rewards",
                color=0x00ff00 if rewards else 0x888888
            )
            
            # Use same table format as rp-rewards channel for consistency
            participant_table = await _generate_rewards_table(ended_session, self.reward_calculator, interaction.guild, rewards)
            reward_embed.add_field(name="📊 Session Results", value=participant_table, inline=False)
            
            # Add session info
            reward_embed.add_field(name="Session", value=self.session_id, inline=True)
            reward_embed.add_field(name="Duration", value=duration_str, inline=True)
            reward_embed.add_field(name="DM", value=f"<@{ended_session.dm_id}>", inline=True)
            
            # Create reward management view
            reward_view = RewardManagementView(
                rewards, ended_session, self.reward_calculator, self.session_id
            )
            
            await interaction.followup.send(embed=reward_embed, view=reward_view)
        else:
            await interaction.response.send_message("❌ Failed to end the session.", ephemeral=True)
    
    async def _update_forum_tags(self, guild: discord.Guild, session):
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
            asyncio.create_task(schedule_forum_lock(thread))
            
        except Exception as e:
            # Silent fail - tag updates are nice-to-have, not critical
            pass
    


class SessionInfoView(discord.ui.View):
    """View for displaying session information"""
    
    def __init__(self, session_manager, reward_calculator):
        super().__init__(timeout=60)
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator

    @discord.ui.button(label='Refresh', style=discord.ButtonStyle.secondary, emoji='🔄')
    async def refresh_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to refresh session information"""
        active_sessions = self.session_manager.get_active_sessions(interaction.guild_id)
        
        if not active_sessions:
            embed = discord.Embed(
                title="📊 Active Sessions",
                description="No active roleplay sessions.",
                color=0x888888
            )
        else:
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
                
                embed.add_field(
                    name=f"Session: {session.session_id}",
                    value=f"DM: <@{session.dm_id}>\n"
                          f"Status: {status}\n"
                          f"Duration: {duration_str}\n"
                          f"Participants: {participants_count}",
                    inline=True
                )
        
        await interaction.response.edit_message(embed=embed, view=self)


class RewardManagementView(discord.ui.View):
    """View for managing session rewards with edit and post options"""
    
    def __init__(self, rewards, session, reward_calculator, session_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.rewards = rewards
        self.session = session
        self.reward_calculator = reward_calculator
        self.session_id = session_id
        self.posted_to_rewards_channel = False  # Track if rewards have been posted
    

    
    @discord.ui.button(label='Edit Rewards', style=discord.ButtonStyle.secondary, emoji='✏️')
    async def edit_rewards(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to edit rewards via modal"""
        if self.posted_to_rewards_channel:
            await interaction.response.send_message(
                "❌ Rewards have already been posted to #rp-rewards and cannot be edited.", 
                ephemeral=True
            )
            return
        
        modal = RewardEditModal(self.rewards, self.session, self.reward_calculator, self.session_id, self, interaction.guild)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label='Post to rp-rewards', style=discord.ButtonStyle.primary, emoji='📤')
    async def post_to_rewards_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to post rewards to rp-rewards channel"""
        if self.posted_to_rewards_channel:
            await interaction.response.send_message(
                "❌ Rewards have already been posted to #rp-rewards.", 
                ephemeral=True
            )
            return
        
        # Find rp-rewards channel
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild not found.", ephemeral=True)
            return
            
        rewards_channel = discord.utils.get(interaction.guild.channels, name="rp-rewards")
        
        if not rewards_channel:
            await interaction.response.send_message(
                "❌ Could not find #rp-rewards channel. Please create it first.", 
                ephemeral=True
            )
            return
        
        # Create embed for rp-rewards channel with current (possibly edited) rewards
        embed = discord.Embed(
            title="💰 RP Session Rewards",
            color=0x00ff00
        )
        
        # Add session title and description in the requested format
        session_info = []
        if hasattr(self.session, 'session_name') and self.session.session_name:
            session_info.append(f"**Title:** {self.session.session_name}")
        
        if hasattr(self.session, 'session_description') and self.session.session_description:
            session_info.append(f"**Description:** {self.session.session_description}")
        
        if session_info:
            embed.add_field(name="Session Details", value="\n".join(session_info), inline=False)
        
        # Use current rewards data (which may be edited) to generate the table
        # Update session reward data with current rewards before generating table
        updated_session = self.session
        if hasattr(updated_session, 'final_rewards'):
            # If rewards were edited, use the edited rewards
            updated_session.final_rewards = self.rewards
        
        # Generate participant table with current rewards
        participant_table = await _generate_rewards_table(updated_session, self.reward_calculator, interaction.guild, self.rewards)
        embed.add_field(name="📊 Session Results", value=participant_table, inline=False)
        
        # Add participant notifications field to ping all players
        if self.rewards:
            participant_pings = []
            for user_id in self.rewards.keys():
                participant_pings.append(f"<@{user_id}>")
            if participant_pings:
                embed.add_field(name="🔔 Participants", value=" ".join(participant_pings), inline=False)
        
        # Add session info
        session_duration = self.session.get_session_duration()
        duration_str = self.reward_calculator.format_time_duration(session_duration)
        
        # Add session type if available
        session_type = getattr(self.session, 'session_type', 'Unknown')
        embed.add_field(name="Session Type", value=session_type, inline=True)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(name="DM", value=f"<@{self.session.dm_id}>", inline=True)
        
        # Add thread link if available
        if hasattr(self.session, 'thread_id') and self.session.thread_id and interaction.guild:
            thread = interaction.guild.get_thread(self.session.thread_id)
            if thread:
                embed.add_field(name="Session Thread", value=f"[View Session Thread]({thread.jump_url})", inline=False)
        
        try:
            if isinstance(rewards_channel, discord.TextChannel):
                # Create mod-only view for editing rewards in the channel
                mod_view = RpRewardsModView(self.session, self.reward_calculator, self.session_id, self.rewards)
                await rewards_channel.send(embed=embed, view=mod_view)
                # Mark as posted and disable buttons
                self.posted_to_rewards_channel = True
                self.update_buttons()
                
                # Remove RP Session Host role from the DM
                if isinstance(interaction.user, discord.Member):
                    await remove_rp_host_role(interaction.user)
            else:
                await interaction.response.send_message(
                    "❌ rp-rewards channel found but is not a text channel.", 
                    ephemeral=True
                )
                return
            await interaction.response.send_message(
                f"✅ Rewards posted to {rewards_channel.mention}! RP Session Host role removed.", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to post to {rewards_channel.mention}: {str(e)}", 
                ephemeral=True
            )
    
    def update_buttons(self):
        """Update button states based on posting status"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if self.posted_to_rewards_channel:
                    item.disabled = True
                    if item.label == 'Post to rp-rewards':
                        item.style = discord.ButtonStyle.success
                        item.label = 'Posted to rp-rewards'


class RpRewardsModView(discord.ui.View):
    """View for role-based editing of rewards in rp-rewards channel"""
    
    def __init__(self, session, reward_calculator, session_id, rewards):
        super().__init__(timeout=None)  # Persistent view
        self.session = session
        self.reward_calculator = reward_calculator
        self.session_id = session_id
        self.rewards = rewards

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can interact with reward editing buttons"""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Only server members can edit rewards.", ephemeral=True)
            return False
        
        # Check if user has RP Session Host role or traditional mod/admin roles
        has_rp_host = interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) and has_rp_host_role(interaction.user, interaction.channel)
        has_mod_role = any(role.name.lower() in ['mod', 'admin', 'owner', 'bot'] for role in interaction.user.roles)
        
        if not (has_rp_host or has_mod_role):
            await interaction.response.send_message("❌ Only users with RP Session Host role or mod permissions can edit rewards.", ephemeral=True)
            return False
            
        return True
    
    def _has_mod_permissions(self, member: discord.Member) -> bool:
        """Check if user has mod, admin, owner, or bot role"""
        if not member or not member.guild:
            return False
            
        # Check if user is guild owner
        if member.guild.owner_id == member.id:
            return True
            
        # Check for specific role names (case insensitive)
        mod_role_names = {'mod', 'admin', 'owner', 'bot', 'moderator', 'administrator'}
        
        for role in member.roles:
            if role.name.lower() in mod_role_names:
                return True
                
        # Check for administrator permission
        if member.guild_permissions.administrator:
            return True
            
        return False
    
    @discord.ui.button(label='Edit Rewards', style=discord.ButtonStyle.secondary, emoji='✏️')
    async def edit_rewards(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mod-only button to edit rewards posted in rp-rewards channel"""
        # Check permissions
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This feature is only available in servers.", ephemeral=True)
            return
            
        # Permissions are checked by interaction_check method
        
        # Create edit modal
        modal = RpRewardsEditModal(self.rewards, self.session, self.reward_calculator, self.session_id, interaction.guild)
        await interaction.response.send_modal(modal)

class RpRewardsEditModal(discord.ui.Modal):
    """Modal for editing rewards posted in rp-rewards channel"""
    
    def __init__(self, rewards, session, reward_calculator, session_id, guild=None):
        super().__init__(title="Edit Posted Rewards")
        self.rewards = rewards
        self.session = session
        self.reward_calculator = reward_calculator
        self.session_id = session_id
        self.guild = guild
        
        # Create text input with current reward data
        current_text = self._format_rewards_for_editing()
        
        self.reward_text = discord.ui.TextInput(
            label="Edit Rewards (DisplayName Character XP Gold)",
            placeholder="Edit XP and Gold values below.\nFormat: DisplayName CharacterName XP Gold",
            default=current_text,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.reward_text)
    
    def _format_rewards_for_editing(self):
        """Format current rewards data for editing in text form"""
        if not self.rewards:
            return ""
        
        lines = []
        for user_id, reward_data in self.rewards.items():
            if isinstance(reward_data, tuple):
                xp, gold = reward_data
            else:
                xp = reward_data.get('xp', 0)
                gold = reward_data.get('gold', 0)
            
            # Get readable player and character names
            player_display = self._get_player_display_name(user_id)
            lines.append(f"{player_display} {xp} {gold}")
        
        return "\n".join(lines)
    
    def _get_player_display_name(self, user_id):
        """Get a readable display name for a player"""
        # Get character name from session if available
        character_name = "Unknown"
        if hasattr(self.session, 'participant_characters') and user_id in self.session.participant_characters:
            character_name = self.session.participant_characters[user_id].get('name', 'Unknown')
        
        # Try to get display name from session storage or Discord
        display_name = f"User{user_id}"
        
        # First check if we have stored display name in session
        if hasattr(self.session, 'participant_display_names') and user_id in self.session.participant_display_names:
            display_name = self.session.participant_display_names[user_id]
            print(f"DEBUG RpRewards: Using stored display name for {user_id}: {display_name}")
        else:
            # Try database lookup first
            try:
                user_id_int = int(user_id)
                
                if self.guild:
                    db_name = get_display_name_from_db(user_id_int, str(self.guild.id))
                    if db_name:
                        display_name = db_name
                        print(f"DEBUG RpRewards: Found display name from database for {user_id}: {display_name}")
                    else:
                        # Fallback to Discord API
                        member = self.guild.get_member(user_id_int)
                        
                        if member:
                            # Priority order: nickname > global_name > username
                            if member.nick:  # Server nickname has highest priority
                                display_name = member.nick
                            elif hasattr(member, 'global_name') and member.global_name:
                                display_name = member.global_name
                            else:
                                display_name = member.name  # Fall back to username
                            
                            print(f"DEBUG RpRewards: Found member {user_id}: nick={getattr(member, 'nick', None)}, global_name={getattr(member, 'global_name', None)}, name={member.name}")
                        else:
                            # If member not found, keep fallback name
                            print(f"DEBUG RpRewards: Member not found, using fallback name User{user_id}")
                    
            except Exception as e:
                print(f"DEBUG RpRewards: Exception in name lookup for {user_id}: {e}")
                pass
        
        # For editing purposes, show readable format (what user wanted)
        # Format: DisplayName CharacterName
        return f"{display_name} {character_name}"
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process edited rewards and update the rp-rewards message"""
        lines = self.reward_text.value.strip().split('\n')
        new_rewards = {}
        
        if lines == ['']:
            # Empty input - set all rewards to 0
            for user_id in self.session.participants.keys() | self.session.participant_times.keys():
                new_rewards[user_id] = {'xp': 0, 'gold': 0}
        else:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Parse line: DisplayName CharacterName XP Gold
                parts = line.split()
                if len(parts) < 3:
                    await interaction.response.send_message(
                        f"❌ Invalid format in line: {line}\nUse: DisplayName CharacterName XP Gold", 
                        ephemeral=True
                    )
                    return
                
                # Take last two parts as XP and Gold
                xp_str, gold_str = parts[-2], parts[-1]
                # Everything before the last two parts is display name + character name
                display_and_char = " ".join(parts[:-2])
                
                # Find the user ID by matching display name to session participants
                user_id = None
                if self.guild:
                    for participant_id in self.session.participants.keys() | self.session.participant_times.keys():
                        try:
                            member = self.guild.get_member(int(participant_id))
                            if member:
                                # Try different name combinations
                                possible_names = [member.display_name, member.name]
                                if hasattr(member, 'global_name') and member.global_name:
                                    possible_names.append(member.global_name)
                                
                                # Check if this line starts with any of the member's possible names
                                for name in possible_names:
                                    if display_and_char.startswith(name):
                                        user_id = participant_id
                                        break
                                if user_id:
                                    break
                        except:
                            continue
                
                if not user_id:
                    # If we can't match by display name, try to find by character name
                    for participant_id in self.session.participants.keys() | self.session.participant_times.keys():
                        if hasattr(self.session, 'participant_characters') and participant_id in self.session.participant_characters:
                            char_name = self.session.participant_characters[participant_id].get('name', '')
                            if char_name and char_name in display_and_char:
                                user_id = participant_id
                                break
                
                if not user_id:
                    await interaction.response.send_message(
                        f"❌ Could not find participant matching: {display_and_char}", 
                        ephemeral=True
                    )
                    return
                
                # Parse XP and Gold
                try:
                    xp = int(xp_str)
                    gold = int(gold_str)
                    if xp < 0 or gold < 0:
                        raise ValueError("Negative values")
                except ValueError:
                    await interaction.response.send_message(
                        f"❌ Invalid XP or Gold values in line: {line}", 
                        ephemeral=True
                    )
                    return
                
                new_rewards[user_id] = {'xp': xp, 'gold': gold}
        
        # Update rewards
        self.rewards.clear()
        self.rewards.update(new_rewards)
        
        # Create updated embed with enhanced rp-rewards format
        embed = discord.Embed(
            title="💰 RP Session Rewards",
            color=0x00ff00
        )
        
        # Add session title and description in the requested format
        session_info = []
        if hasattr(self.session, 'session_name') and self.session.session_name:
            session_info.append(f"**Title:** {self.session.session_name}")
        
        if hasattr(self.session, 'session_description') and self.session.session_description:
            session_info.append(f"**Description:** {self.session.session_description}")
        
        if session_info:
            embed.add_field(name="Session Details", value="\n".join(session_info), inline=False)
        
        # Generate participant table with updated rewards
        participant_table = await _generate_rewards_table(self.session, self.reward_calculator, interaction.guild, self.rewards)
        embed.add_field(name="📊 Session Results", value=participant_table, inline=False)
        
        # Add participant notifications field to ping all players
        if self.rewards:
            participant_pings = []
            for user_id in self.rewards.keys():
                participant_pings.append(f"<@{user_id}>")
            if participant_pings:
                embed.add_field(name="🔔 Participants", value=" ".join(participant_pings), inline=False)
        
        # Add session info
        session_duration = self.session.get_session_duration()
        duration_str = self.reward_calculator.format_time_duration(session_duration)
        
        # Add session type if available
        session_type = getattr(self.session, 'session_type', 'Unknown')
        embed.add_field(name="Session Type", value=session_type, inline=True)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(name="DM", value=f"<@{self.session.dm_id}>", inline=True)
        
        # Add thread link if available
        if hasattr(self.session, 'thread_id') and self.session.thread_id and interaction.guild:
            thread = interaction.guild.get_thread(self.session.thread_id)
            if thread:
                embed.add_field(name="Session Thread", value=f"[View Session Thread]({thread.jump_url})", inline=False)
        
        embed.set_footer(text="✅ Rewards edited by moderator")
        
        # Update the message with the new embed and keep the view
        mod_view = RpRewardsModView(self.session, self.reward_calculator, self.session_id, self.rewards)
        await interaction.response.edit_message(embed=embed, view=mod_view)

class RewardEditModal(discord.ui.Modal):
    """Modal for editing session rewards"""
    
    def __init__(self, rewards, session, reward_calculator, session_id, parent_view, guild=None):
        super().__init__(title="Edit Session Rewards")
        self.rewards = rewards
        self.session = session
        self.reward_calculator = reward_calculator
        self.session_id = session_id
        self.parent_view = parent_view
        self.guild = guild
        
        # Create text input with current reward data
        current_text = self._format_rewards_for_editing()
        
        self.reward_text = discord.ui.TextInput(
            label="Edit Rewards (DisplayName Character XP Gold)",
            placeholder="Edit XP and Gold values below.\nFormat: DisplayName CharacterName XP Gold",
            default=current_text,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.reward_text)
    
    def _format_rewards_for_editing(self):
        """Format current rewards for the text input"""
        if not self.rewards:
            return ""  # Return empty string if no rewards
        
        lines = []
        for user_id, reward_data in self.rewards.items():
            # Handle both tuple (xp, gold) and dict {'xp': xp, 'gold': gold} formats
            if isinstance(reward_data, tuple):
                xp, gold = reward_data
            else:
                xp = reward_data['xp']
                gold = reward_data['gold']
            
            # Get readable player and character names
            player_display = self._get_player_display_name(user_id)
            lines.append(f"{player_display} {xp} {gold}")
        return "\n".join(lines)
    
    def _get_player_display_name(self, user_id):
        """Get a readable display name for a player"""
        # Get character name from session if available
        character_name = "Unknown"
        if hasattr(self.session, 'participant_characters') and user_id in self.session.participant_characters:
            character_name = self.session.participant_characters[user_id].get('name', 'Unknown')
        
        # Try to get display name from session storage or Discord
        display_name = f"User{user_id}"
        
        # First check if we have stored display name in session
        if hasattr(self.session, 'participant_display_names') and user_id in self.session.participant_display_names:
            display_name = self.session.participant_display_names[user_id]
            print(f"DEBUG RewardEdit: Using stored display name for {user_id}: {display_name}")
        else:
            # Try to get from Discord member cache
            try:
                user_id_int = int(user_id)
                
                # Try to get member from guild if available
                member = None
                if self.guild:
                    # Try database lookup first
                    db_name = get_display_name_from_db(user_id_int, str(self.guild.id))
                    if db_name:
                        display_name = db_name
                        print(f"DEBUG RewardEdit: Found display name from database for {user_id}: {display_name}")
                    else:
                        # Fallback to Discord API
                        member = self.guild.get_member(user_id_int)
                        
                        if member:
                            # Priority order: nickname > global_name > username
                            if member.nick:  # Server nickname has highest priority
                                display_name = member.nick
                            elif hasattr(member, 'global_name') and member.global_name:
                                display_name = member.global_name
                            else:
                                display_name = member.name  # Fall back to username
                            
                            print(f"DEBUG RewardEdit: Found member {user_id}: nick={getattr(member, 'nick', None)}, global_name={getattr(member, 'global_name', None)}, name={member.name}")
                        else:
                            # If member not found, keep fallback name
                            print(f"DEBUG RewardEdit: Member not found, using fallback name User{user_id}")
                    
            except Exception as e:
                print(f"DEBUG RewardEdit: Exception in name lookup for {user_id}: {e}")
                pass
        
        # For editing purposes, show readable format (what user wanted)
        # Format: DisplayName CharacterName
        return f"{display_name} {character_name}"
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle reward edits submission"""
        try:
            # Parse the edited rewards
            new_rewards = {}
            lines = self.reward_text.value.strip().split('\n')
            
            for line in lines:
                if not line.strip():
                    continue
                
                # Parse line: DisplayName CharacterName XP Gold
                parts = line.split()
                if len(parts) < 3:
                    await interaction.response.send_message(
                        f"❌ Invalid format in line: {line}\nUse: DisplayName CharacterName XP Gold", 
                        ephemeral=True
                    )
                    return
                
                # Take last two parts as XP and Gold
                xp_str, gold_str = parts[-2], parts[-1]
                # Everything before the last two parts is display name + character name
                display_and_char = " ".join(parts[:-2])
                
                # Find the user ID by matching display name to session participants
                user_id = None
                if self.guild:
                    for participant_id in self.session.participants.keys() | self.session.participant_times.keys():
                        try:
                            member = self.guild.get_member(int(participant_id))
                            if member:
                                # Try different name combinations
                                possible_names = [member.display_name, member.name]
                                if hasattr(member, 'global_name') and member.global_name:
                                    possible_names.append(member.global_name)
                                
                                # Check if this line starts with any of the member's possible names
                                for name in possible_names:
                                    if display_and_char.startswith(name):
                                        user_id = participant_id
                                        break
                                if user_id:
                                    break
                        except:
                            continue
                
                if not user_id:
                    # If we can't match by display name, try to find by character name
                    for participant_id in self.session.participants.keys() | self.session.participant_times.keys():
                        if hasattr(self.session, 'participant_characters') and participant_id in self.session.participant_characters:
                            char_name = self.session.participant_characters[participant_id].get('name', '')
                            if char_name and char_name in display_and_char:
                                user_id = participant_id
                                break
                
                if not user_id:
                    await interaction.response.send_message(
                        f"❌ Could not find participant matching: {display_and_char}", 
                        ephemeral=True
                    )
                    return
                
                # Parse XP and Gold
                try:
                    xp = int(xp_str)
                    gold = int(gold_str)
                    if xp < 0 or gold < 0:
                        raise ValueError("Negative values")
                except ValueError:
                    await interaction.response.send_message(
                        f"❌ Invalid XP or Gold values in line: {line}", 
                        ephemeral=True
                    )
                    return
                
                new_rewards[user_id] = {'xp': xp, 'gold': gold}
            
            # Update rewards
            self.rewards.clear()
            self.rewards.update(new_rewards)
            
            # Update parent view rewards
            self.parent_view.rewards = self.rewards
            
            # Create updated embed using the new consistent format
            reward_embed = discord.Embed(
                title="💰 Session Rewards",
                color=0x00ff00 if self.rewards else 0x888888
            )
            
            # Use same table format as rp-rewards channel for consistency
            participant_table = await _generate_rewards_table(self.session, self.reward_calculator, interaction.guild, self.rewards)
            reward_embed.add_field(name="📊 Session Results", value=participant_table, inline=False)
            
            # Add session info
            session_duration = self.session.get_session_duration()
            duration_str = self.reward_calculator.format_time_duration(session_duration)
            
            reward_embed.add_field(name="Session", value=self.session_id, inline=True)
            reward_embed.add_field(name="Duration", value=duration_str, inline=True)
            reward_embed.add_field(name="DM", value=f"<@{self.session.dm_id}>", inline=True)
            
            reward_embed.set_footer(text="✅ Rewards updated successfully!")
            
            await interaction.response.edit_message(embed=reward_embed, view=self.parent_view)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating rewards: {str(e)}", 
                ephemeral=True
            )
