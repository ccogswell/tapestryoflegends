import discord
from typing import Optional, cast

class SessionSetupModal(discord.ui.Modal):
    """Modal for collecting session setup information"""
    
    def __init__(self, session_manager, reward_calculator, session_id: str, session_type: str = "Mixed"):
        super().__init__(title=f"Setup {session_type} RP Session")
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator
        self.session_id = session_id
        self.preset_session_type = session_type
        
        # Session Name input
        self.session_name = discord.ui.TextInput(
            label="Session Name",
            placeholder="Enter a descriptive name for your session",
            required=True,
            max_length=100
        )
        self.add_item(self.session_name)
        
        # Session Description
        self.session_description = discord.ui.TextInput(
            label="Session Description",
            placeholder="Describe what this RP session is about...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.session_description)
        
        # Map Link
        self.map_link = discord.ui.TextInput(
            label="Map Link (Optional)",
            placeholder="Owlbear Rodeo, Roll20, or other map link",
            required=False,
            max_length=500
        )
        self.add_item(self.map_link)
        
        # Maximum Players
        self.max_players = discord.ui.TextInput(
            label="Maximum Players",
            placeholder="Enter maximum number of active players (e.g., 6)",
            required=True,
            max_length=2
        )
        self.add_item(self.max_players)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        try:
            # Use preset session type
            session_type = self.preset_session_type
            
            # Parse max players
            max_players_value = None
            try:
                max_players_value = int(self.max_players.value.strip())
                if max_players_value < 1 or max_players_value > 20:
                    await interaction.response.send_message(
                        "❌ Maximum players must be between 1 and 20.", 
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Please enter a valid number for maximum players.", 
                    ephemeral=True
                )
                return
            
            # Get or create rp-sessions channel
            if not interaction.guild:
                await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                return
                
            rp_sessions_channel = discord.utils.get(interaction.guild.channels, name="rp-sessions")
            if not rp_sessions_channel:
                # Create a forum channel if it doesn't exist (preferred for RP sessions)
                rp_sessions_channel = await interaction.guild.create_forum(
                    "rp-sessions",
                    reason="Created for RP session management"
                )
            
            # Handle forum channels (create forum post) or text channels (create thread)
            if isinstance(rp_sessions_channel, discord.ForumChannel):
                # Create forum post for session
                thread_name = f"{self.session_name.value} ({session_type})"
                
                # Get or create tags for the forum
                session_type_tag = await self._get_or_create_forum_tag(rp_sessions_channel, session_type, self._get_session_type_emoji(session_type))
                active_tag = await self._get_or_create_forum_tag(rp_sessions_channel, "Active", "🟢")
                accepting_tag = await self._get_or_create_forum_tag(rp_sessions_channel, "Accepting Players", "🟢")
                
                # Prepare tags for forum post (starts accepting players)
                applied_tags = [session_type_tag, active_tag, accepting_tag]
                
                # Create the forum post with tags and welcome message
                thread, message = await rp_sessions_channel.create_thread(
                    name=thread_name[:100],  # Discord thread name limit
                    content=f"Welcome to **{self.session_name.value}**!\n\n{self.session_description.value}\n\nUse the controls below to join the session.",
                    applied_tags=applied_tags,
                    reason=f"RP Session: {self.session_id}"
                )
                
            elif isinstance(rp_sessions_channel, discord.TextChannel):
                # Create thread in text channel with a starter message
                thread_name = f"{self.session_name.value} ({session_type})"
                # For text channels, we need to create a thread from a message
                starter_message = await rp_sessions_channel.send(
                    f"Welcome to **{self.session_name.value}**!\n\n{self.session_description.value}\n\nUse the controls below to join the session."
                )
                thread = await starter_message.create_thread(
                    name=thread_name[:100],  # Discord thread name limit
                    reason=f"RP Session: {self.session_id}"
                )
            else:
                await interaction.response.send_message("❌ rp-sessions must be either a text channel or forum channel.", ephemeral=True)
                return
            
            # Create the session with all the information
            session = self.session_manager.create_session(
                guild_id=interaction.guild_id,
                session_id=self.session_id,
                dm_id=interaction.user.id,
                channel_id=interaction.channel_id,
                session_name=self.session_name.value,
                session_type=session_type,
                max_players=max_players_value,
                thread_id=thread.id,
                session_description=self.session_description.value
            )
            
            if not session:
                await interaction.response.send_message(
                    f"❌ A session with ID '{self.session_id}' already exists.",
                    ephemeral=True
                )
                return
            
            # Import here to avoid circular imports
            from bot.views import SessionControlView
            
            # Assign RP Session Host role to the DM when session is created
            if isinstance(interaction.user, discord.Member) and interaction.guild:
                from bot.views import assign_rp_host_role
                await assign_rp_host_role(interaction.user, thread)
            
            # Create interactive view
            view = SessionControlView(self.session_manager, self.reward_calculator, self.session_id)
            
            # Post unified control panel for both forum and text channel threads
            control_embed = discord.Embed(
                title=f"🎲 {self.session_name.value}",
                description=f"**Description:** {self.session_description.value}\n\n**DM:** {interaction.user.mention}\n**Type:** {session_type}\n**Status:** ⚠️ Not Started",
                color=0x0099ff
            )
            
            # Session info
            control_embed.add_field(name="🎯 Session ID", value=f"`{self.session_id}`", inline=True)
            control_embed.add_field(name="👥 Max Players", value=f"{max_players_value}", inline=True)
            control_embed.add_field(name="⏱️ Duration", value="Not started", inline=True)
            
            if self.map_link.value.strip():
                control_embed.add_field(name="🗺️ Map", value=f"[View Map]({self.map_link.value.strip()})", inline=False)
            
            # Add standardized empty participant table
            control_embed.add_field(
                name="👥 Participants (0)",
                value="`Player           Character        Lv Time  XP   Gold  Status`\n`──────────────────────────────────────────────────────────────`\n`No participants yet - Use 'Join Session' to participate!      `",
                inline=False
            )
            
            await thread.send(embed=control_embed, view=view)
            
            # Post announcement in call-to-rp channel
            call_to_rp_channel = discord.utils.get(interaction.guild.channels, name="call-to-rp")
            if call_to_rp_channel and isinstance(call_to_rp_channel, discord.TextChannel):
                # Add role tags based on session type
                role_mentions = []
                
                # Debug: Show all available roles
                role_names = [role.name for role in interaction.guild.roles]
                print(f"DEBUG: Available roles: {role_names}")
                
                # Find roles and create proper mentions (case-insensitive search)
                if session_type == "Combat":
                    combat_role = discord.utils.find(lambda r: r.name.lower() == "combat", interaction.guild.roles)
                    print(f"DEBUG: Combat role found: {combat_role}")
                    if combat_role:
                        role_mentions.append(f"<@&{combat_role.id}>")
                elif session_type == "Social":
                    social_role = discord.utils.find(lambda r: r.name.lower() == "social", interaction.guild.roles)
                    print(f"DEBUG: Social role found: {social_role}")
                    if social_role:
                        role_mentions.append(f"<@&{social_role.id}>")
                elif session_type == "Mixed":
                    combat_role = discord.utils.find(lambda r: r.name.lower() == "combat", interaction.guild.roles)
                    social_role = discord.utils.find(lambda r: r.name.lower() == "social", interaction.guild.roles)
                    print(f"DEBUG: Combat role found: {combat_role}, Social role found: {social_role}")
                    if combat_role:
                        role_mentions.append(f"<@&{combat_role.id}>")
                    if social_role:
                        role_mentions.append(f"<@&{social_role.id}>")
                
                print(f"DEBUG: Final role mentions: {role_mentions}")
                # Other type gets no role mentions
                
                # Build clean session description 
                description = f"**{self.session_name.value}**\n{self.session_description.value}"
                
                link_embed = discord.Embed(
                    title="🔔 New RP Session Started!",
                    description=description,
                    color=0x00ff00
                )
                link_embed.add_field(name="Type", value=session_type, inline=True)
                link_embed.add_field(name="DM", value=interaction.user.mention, inline=True)
                link_embed.add_field(name="Join Session", value=f"[Click Here]({thread.jump_url})", inline=False)
                
                if self.map_link.value.strip():
                    link_embed.add_field(name="Map", value=f"[View Map]({self.map_link.value.strip()})", inline=True)
                
                # Send role mentions as separate content above the embed (this will ping users)
                if role_mentions:
                    mention_text = ' '.join(role_mentions)
                    await call_to_rp_channel.send(content=mention_text, embed=link_embed)
                else:
                    await call_to_rp_channel.send(embed=link_embed)
            
            # Respond to the user
            success_message = (
                f"✅ Session **{self.session_name.value}** created successfully!\n"
                f"Thread: {thread.mention}\n"
                f"Session ID: `{self.session_id}`\n"
                f"🎭 RP Session Host role assigned!"
            )
            
            if not interaction.response.is_done():
                await interaction.response.send_message(success_message, ephemeral=True)
            else:
                await interaction.followup.send(success_message, ephemeral=True)
            
        except Exception as e:
            error_message = f"❌ Error creating session: {str(e)}"
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_message, ephemeral=True)
                else:
                    await interaction.followup.send(error_message, ephemeral=True)
            except Exception:
                pass  # Ignore response errors
    
    async def _get_or_create_forum_tag(self, forum_channel: discord.ForumChannel, tag_name: str, emoji: str) -> discord.ForumTag:
        """Get existing forum tag or create a new one"""
        # Check if tag already exists
        for tag in forum_channel.available_tags:
            if tag.name.lower() == tag_name.lower():
                return tag
        
        # Create new tag if it doesn't exist and there's space (max 20 tags per forum)
        if len(forum_channel.available_tags) < 20:
            try:
                # Create new tag without emoji for now (Discord API limitation)
                new_tag = await forum_channel.create_tag(name=tag_name)
                return new_tag
            except discord.HTTPException:
                # If creation fails, try to find a similar existing tag
                for tag in forum_channel.available_tags:
                    if tag_name.lower() in tag.name.lower():
                        return tag
        
        # Fallback to first available tag if we can't create new ones
        if forum_channel.available_tags:
            return forum_channel.available_tags[0]
        
        # If no tags exist, we can't apply any
        raise ValueError("No forum tags available and cannot create new ones")
    
    def _get_session_type_emoji(self, session_type: str) -> str:
        """Get emoji for session type"""
        emoji_map = {
            "Combat": "⚔️",
            "Social": "💬", 
            "Mixed": "🎭",
            "Other": "🎲"
        }
        return emoji_map.get(session_type, "🎲")


class KickPlayerModal(discord.ui.Modal):
    """Modal for selecting a player to kick from the session"""
    
    def __init__(self, session_manager, reward_calculator, session_id: str, session):
        super().__init__(title="Kick Player from Session")
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator
        self.session_id = session_id
        self.session = session
        
        # Create dropdown options from current participants
        player_options = []
        for user_id in session.participants:
            # Get display name if available
            display_name = session.participant_display_names.get(user_id, f"User{str(user_id)[-4:]}")
            
            # Get character info
            char_info = session.participant_characters.get(user_id, {})
            char_name = char_info.get('name', 'Unknown')
            char_level = char_info.get('level', '?')
            
            option_text = f"{display_name} - {char_name} (Lv {char_level})"
            player_options.append(f"{user_id}|{option_text}")
        
        # Player selection dropdown (as text input since we can't use Select in Modal)
        options_text = "\n".join([f"{i+1}. {opt.split('|')[1]}" for i, opt in enumerate(player_options)])
        
        self.player_selection = discord.ui.TextInput(
            label="Select Player to Kick (Enter Number)",
            placeholder=f"Choose 1-{len(player_options)}:\n{options_text}"[:100] + "...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=10
        )
        self.add_item(self.player_selection)
        
        # Store options for validation
        self._player_options = player_options
        
        self.kick_reason = discord.ui.TextInput(
            label="Reason (Optional)",
            placeholder="Reason for kicking player...",
            required=False,
            max_length=200
        )
        self.add_item(self.kick_reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle kick player modal submission"""
        try:
            # Parse selection
            try:
                selection = int(self.player_selection.value.strip()) - 1
                if selection < 0 or selection >= len(self._player_options):
                    await interaction.response.send_message(
                        f"❌ Invalid selection. Please choose 1-{len(self._player_options)}.", 
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Please enter a valid number.", 
                    ephemeral=True
                )
                return
            
            # Get selected player
            selected_option = self._player_options[selection]
            user_id = int(selected_option.split('|')[0])
            player_description = selected_option.split('|')[1]
            
            # Verify session and permissions
            session = self.session_manager.get_session(interaction.guild_id, self.session_id)
            if not session or not session.is_active:
                await interaction.response.send_message("❌ This session is no longer active.", ephemeral=True)
                return
            
            if interaction.user.id != session.dm_id:
                await interaction.response.send_message("❌ Only the DM can kick players.", ephemeral=True)
                return
            
            if user_id not in session.participants:
                await interaction.response.send_message("❌ That player is not in the session.", ephemeral=True)
                return
            
            # Kick the player
            if session.remove_participant(user_id):
                time_spent = session.get_participant_time(user_id)
                rounded_time = self.reward_calculator.round_to_nearest_30_minutes(time_spent)
                time_str = self.reward_calculator.format_time_duration(rounded_time)
                
                reason_text = f" (Reason: {self.kick_reason.value})" if self.kick_reason.value.strip() else ""
                
                await interaction.response.send_message(
                    f"🦶 **{player_description}** was removed from the session by the DM after {time_str}{reason_text}.", 
                    ephemeral=False
                )
                
                # Update participant table and forum tags
                if interaction.guild:
                    from bot.views import update_participant_table, update_session_capacity_tags
                    await update_participant_table(interaction.guild, session, self.reward_calculator)
                    await update_session_capacity_tags(interaction.guild, session)
            else:
                await interaction.response.send_message("❌ Failed to remove player from session.", ephemeral=True)
                
        except Exception as e:
            print(f"DEBUG: Error in kick player modal: {e}")
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)