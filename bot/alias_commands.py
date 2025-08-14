import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import re
import logging
from bot.alias_manager import AliasManager

logger = logging.getLogger(__name__)

class FolderViewModal(discord.ui.Modal, title='📁 Your Character Folders'):
    def __init__(self, tree_content: str, total_count: int):
        super().__init__()
        self.tree_display = discord.ui.TextInput(
            label=f'Character Tree Structure ({total_count} total aliases)',
            style=discord.TextStyle.long,
            placeholder='Your aliases organized by groups and subgroups...',
            default=tree_content,
            max_length=4000,
            required=False
        )
        self.add_item(self.tree_display)
    
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📁 Folder Management Tips",
            color=discord.Color.blue(),
            description="Here are some ways to organize your aliases better:"
        )
        embed.add_field(
            name="🏷️ Using Groups", 
            value="Set a group name when creating aliases to organize by campaign/story",
            inline=False
        )
        embed.add_field(
            name="📂 Using Subgroups",
            value="Use subgroups to create nested folders within your main groups",
            inline=False
        )
        embed.add_field(
            name="🌐 Web Interface",
            value="Visit the web interface for drag-and-drop organization and bulk management",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Global context menu for character profile cards (must be defined outside of a class)
@app_commands.context_menu(name="View Character Profile")
async def view_character_profile(interaction: discord.Interaction, message: discord.Message):
    """Context menu to view character profile from webhook message"""
    try:
        # Check if this is a webhook message (character alias)
        if not message.webhook_id:
            await interaction.response.send_message(
                "❌ This message is not from a character alias.", ephemeral=True
            )
            return
        
        # Extract character name from webhook username
        character_name = message.author.display_name
        
        # Get the alias manager from the bot
        cog = interaction.client.get_cog("AliasCommands")
        if not cog:
            await interaction.response.send_message(
                "❌ Alias system not available.", ephemeral=True
            )
            return
        
        alias_manager = cog.alias_manager
        
        # Try to find the character alias in the database
        found_alias = None
        found_user_id = None
        
        # Get all aliases in this guild and find matching character name
        db = alias_manager.db_manager.get_session()
        try:
            from models import CharacterAlias
            aliases = db.query(CharacterAlias).filter(
                CharacterAlias.guild_id == str(interaction.guild.id if interaction.guild else 0),
                CharacterAlias.name == character_name
            ).all()
            
            if aliases:
                # If multiple users have the same character name, prefer the most recently used
                found_alias = max(aliases, key=lambda a: a.last_used or a.created_at)
                found_user_id = found_alias.user_id
                
        finally:
            db.close()
        
        if not found_alias:
            await interaction.response.send_message(
                f"❌ Character '{character_name}' not found in the alias database.", ephemeral=True
            )
            return
        
        # Create character profile embed
        embed = discord.Embed(
            title=f"🎭 Character Profile: {found_alias.name}",
            color=discord.Color.blue()
        )
        
        # Add character avatar
        if found_alias.avatar_url and found_alias.avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png":
            embed.set_thumbnail(url=found_alias.avatar_url)
        
        # Basic character info
        embed.add_field(name="👤 Owner", value=f"<@{found_user_id}>", inline=True)
        embed.add_field(name="🎯 Trigger", value=f"`{found_alias.trigger}`", inline=True)
        
        if found_alias.group_name:
            embed.add_field(name="📁 Group", value=str(found_alias.group_name), inline=True)
        
        # Extended character information section
        character_details = []
        if hasattr(found_alias, 'character_class') and found_alias.character_class:
            character_details.append(f"⚔️ **Class:** {found_alias.character_class}")
        if hasattr(found_alias, 'race') and found_alias.race:
            character_details.append(f"🧬 **Race:** {found_alias.race}")
        if hasattr(found_alias, 'pronouns') and found_alias.pronouns:
            character_details.append(f"🗣️ **Pronouns:** {found_alias.pronouns}")
        if hasattr(found_alias, 'age') and found_alias.age:
            character_details.append(f"📅 **Age:** {found_alias.age}")
        if hasattr(found_alias, 'alignment') and found_alias.alignment:
            character_details.append(f"⚖️ **Alignment:** {found_alias.alignment}")
        
        if character_details:
            embed.add_field(
                name="📊 Character Details", 
                value="\n".join(character_details), 
                inline=False
            )
        else:
            # Check if this is an older character without detailed info
            has_detailed_info = any([
                hasattr(found_alias, 'description') and found_alias.description,
                hasattr(found_alias, 'personality') and found_alias.personality,
                hasattr(found_alias, 'backstory') and found_alias.backstory,
                hasattr(found_alias, 'goals') and found_alias.goals,
                hasattr(found_alias, 'notes') and found_alias.notes
            ])
            
            if not has_detailed_info:
                embed.add_field(
                    name="💡 Enhance Your Character", 
                    value="This character was created with basic info. Use `/alias edit` to add detailed character information like class, race, description, and backstory!", 
                    inline=False
                )
        
        # Physical description
        if hasattr(found_alias, 'description') and found_alias.description:
            description = found_alias.description
            if len(description) > 500:
                description = description[:500] + "..."
            embed.add_field(name="👤 Description", value=description, inline=False)
        
        # Personality traits
        if hasattr(found_alias, 'personality') and found_alias.personality:
            personality = found_alias.personality
            if len(personality) > 500:
                personality = personality[:500] + "..."
            embed.add_field(name="🎭 Personality", value=personality, inline=False)
        
        # Backstory
        if hasattr(found_alias, 'backstory') and found_alias.backstory:
            backstory = found_alias.backstory
            if len(backstory) > 800:
                backstory = backstory[:800] + "..."
            embed.add_field(name="📖 Backstory", value=backstory, inline=False)
        
        # Goals and motivations
        if hasattr(found_alias, 'goals') and found_alias.goals:
            goals = found_alias.goals
            if len(goals) > 500:
                goals = goals[:500] + "..."
            embed.add_field(name="🎯 Goals & Motivations", value=goals, inline=False)
        
        # Additional notes
        if hasattr(found_alias, 'notes') and found_alias.notes:
            notes = found_alias.notes
            if len(notes) > 400:
                notes = notes[:400] + "..."
            embed.add_field(name="📝 Notes", value=notes, inline=False)
        
        # D&D Beyond profile link
        if hasattr(found_alias, 'dndbeyond_url') and found_alias.dndbeyond_url:
            embed.add_field(
                name="🌐 D&D Beyond Profile", 
                value=f"[View Character Sheet]({found_alias.dndbeyond_url})", 
                inline=False
            )
        
        # Usage statistics
        msg_count = found_alias.message_count or 0
        embed.add_field(
            name="💬 Messages Sent", 
            value=f"{msg_count} message{'s' if msg_count != 1 else ''}", 
            inline=True
        )
        
        # Creation and last used
        embed.add_field(
            name="📅 Created", 
            value=f"<t:{int(found_alias.created_at.timestamp())}:R>", 
            inline=True
        )
        
        if found_alias.last_used:
            embed.add_field(
                name="🕐 Last Used", 
                value=f"<t:{int(found_alias.last_used.timestamp())}:R>", 
                inline=True
            )
        else:
            embed.add_field(name="🕐 Last Used", value="Never", inline=True)
        
        # How to use this character
        def get_usage_example(trigger: str) -> str:
            """Generate a usage example for a trigger"""
            if trigger.startswith('[') and trigger.endswith(']'):
                return f"Type `[Hello everyone!]` to post as this character"
            elif trigger.startswith('(') and trigger.endswith(')'):
                return f"Type `(Hello everyone!)` to post as this character"
            elif trigger.endswith(':'):
                return f"Type `{trigger}Hello everyone!` to post as this character"
            else:
                return f"Type `{trigger} Hello everyone!` to post as this character"
        
        usage_example = get_usage_example(found_alias.trigger)
        embed.add_field(name="💡 How to Use", value=usage_example, inline=False)
        
        # Add original message link
        if message.jump_url:
            embed.add_field(
                name="🔗 Original Message", 
                value=f"[Jump to Message]({message.jump_url})", 
                inline=False
            )
        
        embed.set_footer(text="Right-click any character message to view their profile!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in view character profile context menu: {e}")
        await interaction.response.send_message(
            "❌ An error occurred while retrieving the character profile.", ephemeral=True
        )

class AliasRegistrationModal(discord.ui.Modal, title='Register New Character'):
    """Modal for character alias registration"""
    
    def __init__(self, alias_manager: AliasManager):
        super().__init__()
        self.alias_manager = alias_manager
    
    character_name = discord.ui.TextInput(
        label='Character Name',
        placeholder='Enter your character\'s name (e.g., Kael Brightblade)',
        max_length=80,
        required=True
    )
    
    trigger_pattern = discord.ui.TextInput(
        label='Trigger Pattern', 
        placeholder='e.g., k: or [text] or (text) or kael:',
        max_length=100,
        required=True
    )
    
    avatar_url = discord.ui.TextInput(
        label='Avatar Image URL (Optional)',
        placeholder='Paste image URL here, or leave blank to upload a file',
        max_length=500,
        required=False
    )
    
    group_name = discord.ui.TextInput(
        label='Group/Campaign (Optional)',
        placeholder='e.g., Curse of Strahd, Main Campaign, NPCs',
        max_length=100,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        try:
            # Check if user left avatar field blank - trigger upload interface
            if not str(self.avatar_url.value).strip():
                # Create the alias first with default avatar
                alias = self.alias_manager.create_alias(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild.id if interaction.guild else 0,
                    name=str(self.character_name.value),
                    trigger=str(self.trigger_pattern.value),
                    avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
                    group_name=str(self.group_name.value).strip() if self.group_name.value else None
                )
                
                # Create a view with upload button
                view = AliasUploadView(self.alias_manager, alias.name, interaction.client)
                
                embed = discord.Embed(
                    title="✅ Character Alias Registered",
                    color=discord.Color.green(),
                    description=f"Successfully created alias for **{alias.name}**\n\nChoose how to add an avatar image:"
                )
                embed.add_field(name="Character Name", value=str(alias.name), inline=True)
                embed.add_field(name="Trigger", value=f"`{str(alias.trigger)}`", inline=True)
                if alias.group_name:
                    embed.add_field(name="Group", value=str(alias.group_name), inline=True)
                embed.add_field(name="How to Use", value=self._get_usage_example(str(alias.trigger)), inline=False)
                embed.set_thumbnail(url=alias.avatar_url)
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
            
            # User provided a URL - use it directly
            avatar = str(self.avatar_url.value).strip()
            
            # Create the alias
            alias = self.alias_manager.create_alias(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id if interaction.guild else 0,
                name=str(self.character_name.value),
                trigger=str(self.trigger_pattern.value),
                avatar_url=avatar,
                group_name=str(self.group_name.value).strip() if self.group_name.value else None
            )
            
            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Character Alias Registered",
                color=discord.Color.green(),
                description=f"Successfully created alias for **{alias.name}**"
            )
            embed.add_field(name="Character Name", value=str(alias.name), inline=True)
            embed.add_field(name="Trigger", value=f"`{str(alias.trigger)}`", inline=True)
            if alias.group_name:
                embed.add_field(name="Group", value=str(alias.group_name), inline=True)
            embed.add_field(name="How to Use", value=self._get_usage_example(str(alias.trigger)), inline=False)
            embed.set_thumbnail(url=alias.avatar_url)
            embed.set_footer(text="Use /alias help for more information")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error registering alias via modal: {e}")
            await interaction.response.send_message(
                "❌ Database connection error. Please try again in a moment.", ephemeral=True
            )
    
    def _get_usage_example(self, trigger: str) -> str:
        """Generate usage example for a trigger pattern"""
        trigger = trigger.strip()
        
        if trigger.endswith(':'):
            return f"Type `{trigger} Hello there!` to send a message"
        elif trigger.startswith('[') and trigger.endswith(']'):
            return f"Type `{trigger}` around your message like `[Hello there!]`"
        elif trigger.startswith('(') and trigger.endswith(')'):
            return f"Type `{trigger}` around your message like `(Hello there!)`"
        elif '{}' in trigger or '{text}' in trigger:
            return f"Replace `{{text}}` with your message: `{trigger.replace('{text}', 'Hello there!').replace('{}', 'Hello there!')}`"
        else:
            return f"Type `{trigger} Hello there!` to send a message"


class AliasEditModal(discord.ui.Modal, title='Edit Character Alias'):
    """Modal for editing character alias"""
    
    def __init__(self, alias_manager: AliasManager, existing_alias):
        super().__init__()
        self.alias_manager = alias_manager
        self.existing_alias = existing_alias
        
        # Pre-fill fields with existing values
        self.character_name.default = existing_alias.name
        self.trigger_pattern.default = existing_alias.trigger
        self.avatar_url.default = existing_alias.avatar_url if existing_alias.avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png" else ""
        self.group_name.default = existing_alias.group_name or ""
    
    character_name = discord.ui.TextInput(
        label='Character Name',
        placeholder='Enter your character\'s name (e.g., Kael Brightblade)',
        max_length=80,
        required=True
    )
    
    trigger_pattern = discord.ui.TextInput(
        label='Trigger Pattern', 
        placeholder='e.g., k: or [text] or (text) or kael:',
        max_length=100,
        required=True
    )
    
    avatar_url = discord.ui.TextInput(
        label='Avatar Image URL (Optional)',
        placeholder='Paste image URL here, or leave blank for default',
        max_length=500,
        required=False
    )
    
    group_name = discord.ui.TextInput(
        label='Group/Campaign (Optional)',
        placeholder='e.g., Curse of Strahd, Main Campaign, NPCs',
        max_length=100,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        try:
            # Get new values
            new_name = str(self.character_name.value).strip()
            new_trigger = str(self.trigger_pattern.value).strip()
            new_avatar = str(self.avatar_url.value).strip() or "https://cdn.discordapp.com/embed/avatars/0.png"
            new_group = str(self.group_name.value).strip() if self.group_name.value else None
            
            # Update the alias
            updated_alias = self.alias_manager.update_alias(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id if interaction.guild else 0,
                name=self.existing_alias.name,  # Use original name to find the alias
                new_name=new_name,
                new_trigger=new_trigger,
                new_avatar=new_avatar,
                new_group=new_group
            )
            
            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Character Alias Updated",
                color=discord.Color.green(),
                description=f"Successfully updated alias for **{updated_alias.name}**"
            )
            embed.add_field(name="Character Name", value=str(updated_alias.name), inline=True)
            embed.add_field(name="Trigger", value=f"`{str(updated_alias.trigger)}`", inline=True)
            if updated_alias.group_name:
                embed.add_field(name="Group", value=str(updated_alias.group_name), inline=True)
            embed.add_field(name="How to Use", value=self._get_usage_example(str(updated_alias.trigger)), inline=False)
            embed.set_thumbnail(url=updated_alias.avatar_url)
            embed.set_footer(text="Use /alias help for more information")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error updating alias via modal: {e}")
            await interaction.response.send_message(
                "❌ Database connection error. Please try again in a moment.", ephemeral=True
            )
    
    def _get_usage_example(self, trigger: str) -> str:
        """Generate usage example for a trigger pattern"""
        trigger = trigger.strip()
        
        if trigger.endswith(':'):
            return f"Type `{trigger} Hello there!` to send a message"
        elif trigger.startswith('[') and trigger.endswith(']'):
            return f"Type `{trigger}` around your message like `[Hello there!]`"
        elif trigger.startswith('(') and trigger.endswith(')'):
            return f"Type `{trigger}` around your message like `(Hello there!)`"
        elif '{}' in trigger or '{text}' in trigger:
            return f"Replace `{{text}}` with your message: `{trigger.replace('{text}', 'Hello there!').replace('{}', 'Hello there!')}`"
        else:
            return f"Type `{trigger} Hello there!` to send a message"


class AliasUploadView(discord.ui.View):
    """View for uploading character avatar after registration"""
    
    def __init__(self, alias_manager: AliasManager, character_name: str, bot):
        super().__init__(timeout=300)  # 5 minute timeout
        self.alias_manager = alias_manager
        self.character_name = character_name
        self.bot = bot
    
    @discord.ui.button(label='Upload Avatar Image', style=discord.ButtonStyle.primary, emoji='📷')
    async def upload_avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle avatar upload button click - redirect to proper avatar command"""
        embed = discord.Embed(
            title="Upload Character Avatar",
            color=discord.Color.blue(),
            description=f"To upload an avatar for **{self.character_name}**, please use the `/alias avatar` command.\n\n"
                       f"**Steps:**\n"
                       f"1. Type `/alias avatar`\n"
                       f"2. Enter character name: `{self.character_name}`\n"
                       f"3. Upload your image file directly"
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='Skip for Now', style=discord.ButtonStyle.secondary)
    async def skip_avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip avatar upload"""
        embed = discord.Embed(
            title="Character Ready!",
            color=discord.Color.green(),
            description=f"**{self.character_name}** is ready to use!\n\n"
                       "You can upload an avatar later using `/alias avatar`"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class AliasCommands(commands.Cog):
    """Character alias system commands"""
    
    def __init__(self, bot, alias_manager: AliasManager):
        self.bot = bot
        self.alias_manager = alias_manager
    
    # Main alias command group
    alias_group = app_commands.Group(name="alias", description="Character alias system for roleplay")
    

    
    @alias_group.command(name="register", description="Register a new character alias with popup form")
    async def register_alias(self, interaction: discord.Interaction):
        """Register a new character alias using a popup form"""
        # For simple registration, use the original modal
        modal = AliasRegistrationModal(self.alias_manager)
        await interaction.response.send_modal(modal)
    
    @alias_group.command(name="create", description="Create a detailed character with multi-step form")
    async def create_detailed_alias(self, interaction: discord.Interaction):
        """Create a detailed character using multi-step modal process"""
        from bot.character_creation_modals import CharacterBasicModal
        modal = CharacterBasicModal(self.alias_manager)
        await interaction.response.send_modal(modal)
    
    @alias_group.command(name="list", description="List your character aliases in tree view")
    @app_commands.describe(
        user="View aliases for another user (optional)",
        group="Filter by group/campaign name (optional)",
        view_type="Choose how to display aliases"
    )
    @app_commands.choices(view_type=[
        app_commands.Choice(name="Tree view (with shared aliases)", value="tree"),
        app_commands.Choice(name="Simple list (personal only)", value="simple")
    ])
    async def list_aliases(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, group: str = "", view_type: str = "tree"):
        """List character aliases with different view options"""
        target_user = user or interaction.user
        
        if view_type == "simple":
            # Original simple list view (personal aliases only)
            aliases = self.alias_manager.get_user_aliases(target_user.id, interaction.guild.id if interaction.guild else 0)
            
            # Filter by group if specified
            if group.strip():
                aliases = [alias for alias in aliases if alias.group_name and alias.group_name.lower() == group.strip().lower()]
                embed_title = f"Character Aliases for {target_user.display_name} - Group: {group.strip()}"
            else:
                embed_title = f"Character Aliases for {target_user.display_name}"
            
            embed = discord.Embed(
                title=embed_title,
                color=discord.Color.blue()
            )
            
            if not aliases:
                embed.description = "No character aliases registered."
                embed.add_field(
                    name="Get Started",
                    value="Use `/alias register` to create your first character!",
                    inline=False
                )
            else:
                # Get usage statistics
                alias_stats = self.alias_manager.get_alias_stats(target_user.id, interaction.guild.id if interaction.guild else 0)
                
                # Group aliases by group_name for better organization
                grouped_aliases = {}
                ungrouped_aliases = []
                
                # First, find matching aliases in our filtered set
                matching_aliases = [alias for alias in aliases]
                
                for alias in matching_aliases:
                    if alias.group_name:
                        if alias.group_name not in grouped_aliases:
                            grouped_aliases[alias.group_name] = []
                        grouped_aliases[alias.group_name].append(alias)
                    else:
                        ungrouped_aliases.append(alias)
                
                alias_list = []
                
                # Add grouped aliases
                for group_name in sorted(grouped_aliases.keys()):
                    alias_list.append(f"**📁 {group_name}**")
                    for alias in grouped_aliases[group_name]:
                        usage = self._get_usage_example(alias.trigger)
                        msg_count = alias.message_count or 0
                        usage_text = f"({msg_count} message{'s' if msg_count != 1 else ''})" if msg_count > 0 else "(unused)"
                        alias_list.append(f"  ├ **{alias.name}** - `{alias.trigger}` {usage_text}")
                
                # Add ungrouped aliases
                if ungrouped_aliases:
                    if grouped_aliases:  # Only add separator if there are grouped aliases
                        alias_list.append("**📄 No Group**")
                    for alias in ungrouped_aliases:
                        usage = self._get_usage_example(alias.trigger)
                        msg_count = alias.message_count or 0
                        usage_text = f"({msg_count} message{'s' if msg_count != 1 else ''})" if msg_count > 0 else "(unused)"
                        prefix = "  ├ " if grouped_aliases else ""
                        alias_list.append(f"{prefix}**{alias.name}** - `{alias.trigger}` {usage_text}")
                
                embed.description = "\n\n".join(alias_list)
                
                total_messages = sum(stat['message_count'] for stat in alias_stats)
                embed.set_footer(text=f"Total: {len(aliases)} aliases • {total_messages} messages sent")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        else:
            # Tree view (enhanced view with shared aliases) - use the folders logic
            await self._show_tree_view(interaction, target_user, group)
    
    @alias_group.command(name="show", description="Show detailed information about an alias")
    @app_commands.describe(name="The name of the alias to view")
    async def show_alias(self, interaction: discord.Interaction, name: str):
        """Show detailed alias information"""
        try:
            alias = self.alias_manager.get_alias_by_name(
                interaction.user.id, interaction.guild.id if interaction.guild else 0, name
            )
            
            if not alias:
                await interaction.response.send_message(
                    f"❌ No character named '{name}' found.", ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title=f"Character: {str(alias.name)}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Trigger", value=f"`{str(alias.trigger)}`", inline=True)
            embed.add_field(name="Owner", value=f"<@{str(alias.user_id)}>", inline=True)
            if alias.group_name:
                embed.add_field(name="Group", value=str(alias.group_name), inline=True)
            
            # Add usage statistics
            msg_count = alias.message_count or 0
            embed.add_field(
                name="Usage", 
                value=f"{msg_count} message{'s' if msg_count != 1 else ''} sent", 
                inline=True
            )
            
            embed.add_field(name="How to Use", value=self._get_usage_example(str(alias.trigger)), inline=False)
            embed.add_field(name="Created", value=f"<t:{int(alias.created_at.timestamp())}:R>", inline=True)
            
            if alias.last_used:
                embed.add_field(
                    name="Last Used", 
                    value=f"<t:{int(alias.last_used.timestamp())}:R>", 
                    inline=True
                )
            else:
                embed.add_field(name="Last Used", value="Never", inline=True)
            
            # Display avatar as large image at bottom
            if alias.avatar_url and alias.avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png":
                embed.set_image(url=alias.avatar_url)
                logger.info(f"Displaying avatar for {alias.name}: {alias.avatar_url}")
            else:
                # Use default avatar image
                embed.set_image(url="https://cdn.discordapp.com/embed/avatars/0.png")
                logger.info(f"Using default avatar for {alias.name}: no custom avatar set")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing alias: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while retrieving the alias.", ephemeral=True
            )
    
    @alias_group.command(name="edit", description="Edit an existing character alias with popup form")
    @app_commands.describe(name="The name of the alias to edit")
    async def edit_alias(self, interaction: discord.Interaction, name: str):
        """Edit an existing alias using a popup form"""
        try:
            # Find the existing alias
            alias = self.alias_manager.get_alias_by_name(
                interaction.user.id, interaction.guild.id if interaction.guild else 0, name
            )
            
            if not alias:
                await interaction.response.send_message(
                    f"❌ No character named '{name}' found.", ephemeral=True
                )
                return
            
            # Convert existing alias data to character_data format for editing
            character_data = {
                'name': alias.name,
                'trigger': alias.trigger,
                'class_level': getattr(alias, 'character_class', None),
                'race': getattr(alias, 'race', None),
                'group_name': alias.group_name,
                'avatar_url': alias.avatar_url,
                'description': getattr(alias, 'description', None),
                'pronouns': getattr(alias, 'pronouns', None),
                'age': getattr(alias, 'age', None),
                'alignment': getattr(alias, 'alignment', None),
                'personality': getattr(alias, 'personality', None),
                'backstory': getattr(alias, 'backstory', None),
                'goals': getattr(alias, 'goals', None),
                'notes': getattr(alias, 'notes', None),
                'dndbeyond_url': getattr(alias, 'dndbeyond_url', None),
                'user_id': interaction.user.id,
                'guild_id': interaction.guild.id if interaction.guild else 0,
                'editing_existing': True,
                'original_name': alias.name
            }
            
            # Import and open the edit modal with pre-filled data
            from bot.character_creation_modals import CharacterEditBasicModal
            modal = CharacterEditBasicModal(self.alias_manager, character_data)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error opening edit modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while opening the edit form.", ephemeral=True
            )
    
    @alias_group.command(name="conflicts", description="Check for trigger conflicts between your aliases")
    async def check_conflicts(self, interaction: discord.Interaction):
        """Check for trigger conflicts in user's aliases"""
        try:
            user_aliases = self.alias_manager.get_user_aliases(
                interaction.user.id, interaction.guild.id if interaction.guild else 0
            )
            
            if not user_aliases:
                await interaction.response.send_message(
                    "❌ You don't have any aliases yet. Use `/alias create` to get started!", 
                    ephemeral=True
                )
                return
            
            # Get shared aliases too
            shared_aliases = self._get_shared_aliases_for_user(
                interaction.user.id, interaction.guild.id if interaction.guild else 0
            )
            
            # Get user's personal overrides
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import AliasOverride
                
                user_id_str = str(interaction.user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                user_overrides = db.query(AliasOverride).filter(
                    AliasOverride.user_id == user_id_str,
                    AliasOverride.guild_id == guild_id_str,
                    AliasOverride.is_active == True
                ).all()
                
                # Create a mapping of original alias ID to override trigger
                override_map = {override.original_alias_id: override.personal_trigger for override in user_overrides}
                
            finally:
                db.close()
            
            # Group aliases by EFFECTIVE trigger to find conflicts
            trigger_groups = {}
            
            # Add user's own aliases
            for alias in user_aliases:
                trigger = str(alias.trigger).lower()
                if trigger not in trigger_groups:
                    trigger_groups[trigger] = []
                trigger_groups[trigger].append({
                    'alias': alias,
                    'type': 'owned',
                    'owner': 'You'
                })
            
            # Add shared aliases with their effective triggers (considering overrides)
            for shared_data in shared_aliases:
                alias = shared_data['alias']
                
                # Check if user has an override for this shared alias
                if alias.id in override_map:
                    # Use the override trigger instead of the original
                    effective_trigger = override_map[alias.id].lower()
                else:
                    # Use the original trigger
                    effective_trigger = str(alias.trigger).lower()
                
                if effective_trigger not in trigger_groups:
                    trigger_groups[effective_trigger] = []
                
                owner_name = shared_data.get('owner_name', f"User {alias.user_id}")
                trigger_groups[effective_trigger].append({
                    'alias': alias,
                    'type': 'shared',
                    'owner': owner_name,
                    'permission': shared_data['permission'],
                    'effective_trigger': effective_trigger,
                    'has_override': alias.id in override_map
                })
            
            # Find conflicts (triggers with multiple aliases)
            conflicts = {trigger: aliases for trigger, aliases in trigger_groups.items() if len(aliases) > 1}
            
            embed = discord.Embed(
                title="🔍 Alias Trigger Analysis",
                color=discord.Color.orange() if conflicts else discord.Color.green()
            )
            
            if not conflicts:
                embed.description = "✅ **No conflicts found!** All your triggers are unique."
                embed.add_field(
                    name="💡 This means:",
                    value="Each trigger points to exactly one character, so messages will always go to the intended alias.",
                    inline=False
                )
            else:
                embed.description = f"⚠️ **Found {len(conflicts)} trigger conflict{'s' if len(conflicts) != 1 else ''}**"
                
                conflict_list = []
                for trigger, aliases in conflicts.items():
                    conflict_entry = [f"**Trigger: `{trigger}`**"]
                    for alias_data in aliases:
                        alias = alias_data['alias']
                        type_icon = "👤" if alias_data['type'] == 'owned' else "🤝"
                        owner_text = f"({alias_data['owner']})" if alias_data['type'] == 'shared' else ""
                        
                        # Show if this is using an override
                        override_note = ""
                        if alias_data.get('has_override'):
                            original_trigger = alias.trigger
                            override_note = f" [Override: {original_trigger} → {trigger}]"
                        
                        conflict_entry.append(f"  {type_icon} {alias.name} {owner_text}{override_note}")
                    
                    conflict_entry.append(f"  ➤ **Current priority:** {aliases[0]['alias'].name}")
                    conflict_list.append("\n".join(conflict_entry))
                
                embed.add_field(
                    name="🚨 Conflicts Found:",
                    value="\n\n".join(conflict_list[:3]),  # Show first 3 conflicts
                    inline=False
                )
                
                if len(conflicts) > 3:
                    embed.add_field(
                        name="",
                        value=f"... and {len(conflicts) - 3} more conflict{'s' if len(conflicts) - 3 != 1 else ''}",
                        inline=False
                    )
                
                embed.add_field(
                    name="🛠️ How to Fix:",
                    value=(
                        "**Option 1:** Change triggers using `/alias edit [character]` (for your own aliases)\n"
                        "**Option 2:** Create personal triggers using `/alias override [character] [new_trigger]` (for shared aliases)\n"
                        "**Option 3:** The first matching alias will be used (shown above)\n"
                        "**Priority:** Personal overrides > Your aliases > Shared aliases"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="💡 Suggested Solutions:",
                    value=(
                        f"• **For your own aliases:** Use unique prefixes like `mal.`, `mage.`, `monk.` instead of `m.`\n"
                        f"• **For shared aliases:** Use `/alias override [character] [new_trigger]` to create personal triggers\n"
                        f"• Try character initials: `mb.` for 'Malachi Brightblade'\n"  
                        f"• Use brackets: `[mal]`, `[mage]` for different feel\n"
                        f"• Consider short names: `mal`, `mage` (no punctuation)"
                    ),
                    inline=False
                )
                
                # Add override-specific instructions if there are shared alias conflicts
                shared_conflicts = []
                for trigger, aliases in trigger_groups.items():
                    if len(aliases) > 1:
                        has_shared = any(alias_data['type'] == 'shared' for alias_data in aliases)
                        if has_shared:
                            shared_conflicts.append((trigger, aliases))
                
                if shared_conflicts:
                    override_examples = []
                    for trigger, aliases in shared_conflicts[:2]:  # Show first 2 examples
                        shared_alias = next(alias_data for alias_data in aliases if alias_data['type'] == 'shared')
                        char_name = shared_alias['alias'].name
                        example_trigger = f"{char_name.lower()[:3]}."
                        override_examples.append(f"`/alias override {char_name} {example_trigger}`")
                    
                    embed.add_field(
                        name="🔧 Personal Override Examples:",
                        value=(
                            "Create personal triggers for shared aliases without affecting others:\n" +
                            "\n".join(override_examples) +
                            "\n\n💡 Use `/alias overrides` to see your current overrides"
                        ),
                        inline=False
                    )
            
            # Add summary statistics
            total_triggers = len(trigger_groups)
            total_accessible_aliases = sum(len(aliases) for aliases in trigger_groups.values())
            shared_count = sum(1 for shared_data in shared_aliases)
            owned_count = len(user_aliases)
            
            # Count overrides
            override_count = len([alias_data for trigger_aliases in trigger_groups.values() 
                                for alias_data in trigger_aliases if alias_data.get('has_override')])
            
            footer_text = f"Accessible: {total_accessible_aliases} aliases • {owned_count} owned, {shared_count} shared • {total_triggers} triggers"
            if override_count > 0:
                footer_text += f" • {override_count} personal overrides"
            
            embed.set_footer(text=footer_text)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error checking conflicts: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while checking for conflicts.", ephemeral=True
            )

    @alias_group.command(name="override", description="Create personal trigger for a shared alias")
    @app_commands.describe(
        alias_name="Name of the shared alias to override",
        new_trigger="Your personal trigger for this alias"
    )
    async def override_alias(self, interaction: discord.Interaction, alias_name: str, new_trigger: str):
        """Create a personal trigger override for a shared alias"""
        try:
            # Check if the alias exists among shared aliases
            shared_aliases = self._get_shared_aliases_for_user(
                interaction.user.id, interaction.guild.id if interaction.guild else 0
            )
            
            target_alias = None
            for shared_data in shared_aliases:
                if shared_data['alias'].name.lower() == alias_name.lower():
                    target_alias = shared_data
                    break
            
            if not target_alias:
                await interaction.response.send_message(
                    f"❌ No shared alias named '{alias_name}' found. Use `/alias shared` to see available shared aliases.",
                    ephemeral=True
                )
                return
            
            # Validate new trigger
            if not new_trigger or len(new_trigger) > 200:
                await interaction.response.send_message(
                    "❌ Trigger must be between 1-200 characters.", ephemeral=True
                )
                return
            
            # Check if trigger conflicts with user's own aliases
            user_aliases = self.alias_manager.get_user_aliases(
                interaction.user.id, interaction.guild.id if interaction.guild else 0
            )
            
            conflicts_with_own = any(alias.trigger.lower() == new_trigger.lower() for alias in user_aliases)
            if conflicts_with_own:
                await interaction.response.send_message(
                    f"❌ Trigger `{new_trigger}` conflicts with one of your own aliases. Choose a different trigger.",
                    ephemeral=True
                )
                return
            
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import AliasOverride
                
                user_id_str = str(interaction.user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                original_alias = target_alias['alias']
                
                # Check if override already exists
                existing_override = db.query(AliasOverride).filter(
                    AliasOverride.user_id == user_id_str,
                    AliasOverride.guild_id == guild_id_str,
                    AliasOverride.original_alias_id == original_alias.id
                ).first()
                
                if existing_override:
                    # Update existing override
                    old_trigger = existing_override.personal_trigger
                    existing_override.personal_trigger = new_trigger
                    existing_override.updated_at = datetime.utcnow()
                    action = "updated"
                else:
                    # Create new override
                    new_override = AliasOverride(
                        user_id=user_id_str,
                        guild_id=guild_id_str,
                        original_alias_id=original_alias.id,
                        personal_trigger=new_trigger
                    )
                    db.add(new_override)
                    action = "created"
                    old_trigger = original_alias.trigger
                
                db.commit()
                
                # Create success embed
                embed = discord.Embed(
                    title="✅ Personal Trigger Override " + action.title(),
                    color=discord.Color.green()
                )
                embed.add_field(name="Character", value=original_alias.name, inline=True)
                embed.add_field(name="Original Trigger", value=f"`{original_alias.trigger}`", inline=True)
                embed.add_field(name="Your Personal Trigger", value=f"`{new_trigger}`", inline=True)
                
                if action == "updated":
                    embed.add_field(name="Previous Override", value=f"`{old_trigger}`", inline=True)
                
                embed.add_field(
                    name="💡 What this means:",
                    value=(
                        f"• You can now use `{new_trigger}` to post as {original_alias.name}\n"
                        f"• The original trigger `{original_alias.trigger}` still works for the owner\n"
                        f"• This only affects you - other users see the original trigger\n"
                        f"• This resolves conflicts without changing the shared alias"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Usage Example:",
                    value=f"`{new_trigger} Hello everyone!` → Posts as {original_alias.name}",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error creating alias override: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the trigger override.", ephemeral=True
            )

    @alias_group.command(name="overrides", description="List your personal trigger overrides")
    async def list_overrides(self, interaction: discord.Interaction):
        """List all personal trigger overrides for the user"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import AliasOverride, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                overrides = db.query(AliasOverride, CharacterAlias).join(
                    CharacterAlias, AliasOverride.original_alias_id == CharacterAlias.id
                ).filter(
                    AliasOverride.user_id == user_id_str,
                    AliasOverride.guild_id == guild_id_str,
                    AliasOverride.is_active == True
                ).all()
                
                embed = discord.Embed(
                    title="🔧 Your Personal Trigger Overrides",
                    color=discord.Color.blue()
                )
                
                if not overrides:
                    embed.description = "You don't have any personal trigger overrides yet."
                    embed.add_field(
                        name="💡 What are overrides?",
                        value=(
                            "Overrides let you create personal triggers for shared aliases without affecting "
                            "the original. Use `/alias override [character] [new_trigger]` to create one."
                        ),
                        inline=False
                    )
                else:
                    override_list = []
                    for override, alias in overrides:
                        owner_name = self._get_user_display_name(int(alias.user_id), interaction.guild.id)
                        override_list.append(
                            f"**{alias.name}** from {owner_name}\n"
                            f"  Original: `{alias.trigger}` → Your trigger: `{override.personal_trigger}`"
                        )
                    
                    embed.description = "\n\n".join(override_list)
                    embed.add_field(
                        name="🛠️ Managing Overrides:",
                        value=(
                            "• Use `/alias override [character] [new_trigger]` to update\n"
                            "• Use `/alias remove_override [character]` to delete\n"
                            "• Your overrides don't affect other users"
                        ),
                        inline=False
                    )
                
                embed.set_footer(text=f"Total: {len(overrides)} override{'s' if len(overrides) != 1 else ''}")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error listing overrides: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing overrides.", ephemeral=True
            )

    @alias_group.command(name="remove_override", description="Remove a personal trigger override")
    @app_commands.describe(alias_name="Name of the alias to remove override for")
    async def remove_override(self, interaction: discord.Interaction, alias_name: str):
        """Remove a personal trigger override"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import AliasOverride, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Find the override
                override_query = db.query(AliasOverride, CharacterAlias).join(
                    CharacterAlias, AliasOverride.original_alias_id == CharacterAlias.id
                ).filter(
                    AliasOverride.user_id == user_id_str,
                    AliasOverride.guild_id == guild_id_str,
                    CharacterAlias.name.ilike(alias_name),
                    AliasOverride.is_active == True
                ).first()
                
                if not override_query:
                    await interaction.response.send_message(
                        f"❌ No personal trigger override found for '{alias_name}'. Use `/alias overrides` to see your overrides.",
                        ephemeral=True
                    )
                    return
                
                override, alias = override_query
                
                # Remove the override
                db.delete(override)
                db.commit()
                
                embed = discord.Embed(
                    title="✅ Personal Trigger Override Removed",
                    color=discord.Color.green()
                )
                embed.add_field(name="Character", value=alias.name, inline=True)
                embed.add_field(name="Removed Trigger", value=f"`{override.personal_trigger}`", inline=True)
                embed.add_field(name="Original Trigger", value=f"`{alias.trigger}`", inline=True)
                embed.add_field(
                    name="💡 What happened:",
                    value=f"Your personal trigger `{override.personal_trigger}` has been removed. "
                          f"You can still use the original trigger `{alias.trigger}` if the alias is still shared with you.",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error removing override: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while removing the override.", ephemeral=True
            )

    @alias_group.command(name="remove", description="Remove a character alias")
    @app_commands.describe(name="The name of the alias to remove")
    async def remove_alias(self, interaction: discord.Interaction, name: str):
        """Remove a character alias"""
        try:
            success = self.alias_manager.delete_alias(
                interaction.user.id, interaction.guild.id if interaction.guild else 0, name
            )
            
            if success:
                await interaction.response.send_message(
                    f"✅ Successfully removed the alias '{name}'.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ No character named '{name}' found.", ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error removing alias: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while removing the alias.", ephemeral=True
            )
    
    @alias_group.command(name="avatar", description="Upload an avatar image for your character")
    @app_commands.describe(
        name="The name of the character to set avatar for",
        image="Upload an image file for the character's avatar"
    )
    async def set_avatar(self, interaction: discord.Interaction, name: str, image: discord.Attachment):
        """Set character avatar by uploading an image"""
        try:
            # Validate image attachment
            if not image.content_type or not image.content_type.startswith('image/'):
                await interaction.response.send_message(
                    "❌ Please upload a valid image file (PNG, JPG, GIF).", ephemeral=True
                )
                return
            
            # Check file size (8MB Discord limit, but we'll use 2MB for safety)
            if image.size > 2 * 1024 * 1024:  # 2MB
                await interaction.response.send_message(
                    "❌ Image file too large. Please use an image smaller than 2MB.", ephemeral=True
                )
                return
            
            # Find the character
            alias = self.alias_manager.get_alias_by_name(
                interaction.user.id, interaction.guild.id if interaction.guild else 0, name
            )
            
            if not alias:
                await interaction.response.send_message(
                    f"❌ No character named '{name}' found.", ephemeral=True
                )
                return
            
            # Update the alias with the image URL
            updated_alias = self.alias_manager.update_alias(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id if interaction.guild else 0,
                name=name,
                new_name="",
                new_trigger="",
                new_avatar=image.url
            )
            
            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Character Avatar Updated",
                color=discord.Color.green(),
                description=f"Successfully updated avatar for **{updated_alias.name}**"
            )
            embed.add_field(name="Character", value=str(updated_alias.name), inline=True)
            embed.add_field(name="Trigger", value=f"`{str(updated_alias.trigger)}`", inline=True)
            embed.set_image(url=image.url)
            embed.set_footer(text="Your character is now ready for roleplay!")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting avatar: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while setting the avatar. Please try again.", ephemeral=True
            )

    @alias_group.command(name="export", description="Export your character aliases to a CSV file")
    async def export_aliases(self, interaction: discord.Interaction):
        """Export user's aliases to CSV format"""
        try:
            aliases = self.alias_manager.get_user_aliases(
                interaction.user.id, 
                interaction.guild.id if interaction.guild else 0
            )
            
            if not aliases:
                await interaction.response.send_message(
                    "❌ You don't have any character aliases to export.", ephemeral=True
                )
                return
            
            # Generate CSV content
            import io
            csv_content = io.StringIO()
            csv_content.write("name,trigger,avatar_url,group_name\n")
            
            for alias in aliases:
                # Escape quotes in CSV fields
                name = str(alias.name).replace('"', '""')
                trigger = str(alias.trigger).replace('"', '""')
                avatar_url = str(alias.avatar_url or "").replace('"', '""')
                group_name = str(alias.group_name or "").replace('"', '""')
                
                csv_content.write(f'"{name}","{trigger}","{avatar_url}","{group_name}"\n')
            
            # Create file
            csv_data = csv_content.getvalue().encode('utf-8')
            csv_file = discord.File(
                io.BytesIO(csv_data), 
                filename=f"character_aliases_{interaction.user.display_name}.csv"
            )
            
            embed = discord.Embed(
                title="📥 Character Aliases Exported",
                color=discord.Color.blue(),
                description=f"Exported {len(aliases)} character aliases to CSV file."
            )
            embed.add_field(
                name="File Format", 
                value="CSV with columns: name, trigger, avatar_url, group_name (avatar_url and group_name are optional)", 
                inline=False
            )
            embed.set_footer(text="Use /alias import to import aliases from a CSV file")
            
            await interaction.response.send_message(
                embed=embed, 
                file=csv_file, 
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error exporting aliases: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while exporting aliases. Please try again.", ephemeral=True
            )

    @alias_group.command(name="import", description="Import character aliases from a CSV file")
    @app_commands.describe(
        csv_file="CSV file with columns: name, trigger, avatar_url, group_name (avatar_url and group_name optional)",
        overwrite="Whether to overwrite existing aliases with same names"
    )
    async def import_aliases(self, interaction: discord.Interaction, csv_file: discord.Attachment, overwrite: bool = False):
        """Import aliases from CSV format"""
        try:
            # Validate file type
            if not csv_file.filename.lower().endswith('.csv'):
                await interaction.response.send_message(
                    "❌ Please upload a CSV file (.csv extension).", ephemeral=True
                )
                return
            
            # Check file size (1MB limit)
            if csv_file.size > 1024 * 1024:
                await interaction.response.send_message(
                    "❌ CSV file too large. Please use a file smaller than 1MB.", ephemeral=True
                )
                return
            
            # Download and parse CSV
            csv_data = await csv_file.read()
            csv_content = csv_data.decode('utf-8')
            
            import csv
            import io
            reader = csv.DictReader(io.StringIO(csv_content))
            
            # Validate headers - only name and trigger are required
            required_headers = {'name', 'trigger'}
            if not required_headers.issubset(set(reader.fieldnames or [])):
                await interaction.response.send_message(
                    "❌ Invalid CSV format. Required columns: name, trigger (avatar_url and group_name are optional)", ephemeral=True
                )
                return
            
            imported_count = 0
            skipped_count = 0
            error_count = 0
            
            await interaction.response.defer(ephemeral=True)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 to account for header
                try:
                    name = row['name'].strip()
                    trigger = row['trigger'].strip()
                    # Avatar URL is optional - use default if not provided or empty
                    avatar_url = row.get('avatar_url', '').strip() or "https://cdn.discordapp.com/embed/avatars/0.png"
                    # Group name is optional
                    group_name = row.get('group_name', '').strip() or None
                    
                    if not name or not trigger:
                        error_count += 1
                        continue
                    
                    # Check if alias already exists
                    existing = self.alias_manager.get_alias_by_name(
                        interaction.user.id, 
                        interaction.guild.id if interaction.guild else 0, 
                        name
                    )
                    
                    if existing and not overwrite:
                        skipped_count += 1
                        continue
                    
                    if existing and overwrite:
                        # Update existing alias
                        self.alias_manager.update_alias(
                            user_id=interaction.user.id,
                            guild_id=interaction.guild.id if interaction.guild else 0,
                            name=name,
                            new_name="",
                            new_trigger=trigger,
                            new_avatar=avatar_url,
                            new_group=group_name
                        )
                    else:
                        # Create new alias
                        self.alias_manager.create_alias(
                            user_id=interaction.user.id,
                            guild_id=interaction.guild.id if interaction.guild else 0,
                            name=name,
                            trigger=trigger,
                            avatar_url=avatar_url,
                            group_name=group_name
                        )
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error importing row {row_num}: {e}")
                    error_count += 1
            
            # Create result embed
            embed = discord.Embed(
                title="📤 Character Aliases Import Complete",
                color=discord.Color.green() if imported_count > 0 else discord.Color.orange()
            )
            embed.add_field(name="✅ Imported", value=str(imported_count), inline=True)
            embed.add_field(name="⏭️ Skipped", value=str(skipped_count), inline=True)
            embed.add_field(name="❌ Errors", value=str(error_count), inline=True)
            
            if skipped_count > 0:
                embed.add_field(
                    name="Note", 
                    value="Skipped aliases already exist. Use `overwrite: True` to replace them.", 
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error importing aliases: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ An error occurred while importing aliases. Please check your CSV format.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ An error occurred while importing aliases. Please check your CSV format.", ephemeral=True
                )

    @alias_group.command(name="auto", description="Enable/disable sticky auto-proxy")
    @app_commands.describe(
        character="Character to start with (optional - will switch when you use triggers)",
        action="Action: enable, disable, or status"
    )
    async def auto_proxy(self, interaction: discord.Interaction, character: str = "", action: str = "status"):
        """Enable or disable auto-proxy for a character"""
        try:
            action = action.lower()
            
            if action == "status":
                # Check current auto-proxy status
                current_alias = self.alias_manager.get_auto_proxy_status(
                    interaction.user.id, 
                    interaction.guild.id if interaction.guild else 0
                )
                
                if current_alias:
                    embed = discord.Embed(
                        title="🔄 Auto-Proxy Status",
                        color=discord.Color.green(),
                        description=f"Auto-proxy is **enabled** for **{current_alias.name}**"
                    )
                    embed.add_field(
                        name="Sticky Mode", 
                        value="Character switches automatically when you use different triggers (m., s., etc.)", 
                        inline=False
                    )
                    embed.set_footer(text="Use '/alias auto action:disable' to turn off auto-proxy")
                elif interaction.user.id in self.alias_manager.auto_proxy:
                    # Auto-proxy enabled but no character set yet
                    embed = discord.Embed(
                        title="🔄 Auto-Proxy Status",
                        color=discord.Color.orange(),
                        description="**Auto-proxy** is enabled, waiting for first trigger"
                    )
                    embed.add_field(
                        name="How It Works", 
                        value="Use any trigger (m., s., etc.) to start posting as that character. Character will stick until you use a different trigger.", 
                        inline=False
                    )
                else:
                    embed = discord.Embed(
                        title="🔄 Auto-Proxy Status",
                        color=discord.Color.blue(),
                        description="Auto-proxy is **disabled**"
                    )
                    embed.add_field(
                        name="How to Enable", 
                        value="Use `/alias auto action:enable` to start sticky auto-proxy mode.", 
                        inline=False
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            elif action == "disable":
                # Disable auto-proxy
                success = self.alias_manager.disable_auto_proxy(interaction.user.id)
                
                if success:
                    embed = discord.Embed(
                        title="🔄 Auto-Proxy Disabled",
                        color=discord.Color.orange(),
                        description="Auto-proxy has been turned off. Your messages will no longer be automatically posted as a character."
                    )
                else:
                    embed = discord.Embed(
                        title="ℹ️ Auto-Proxy Status",
                        color=discord.Color.blue(),
                        description="Auto-proxy was already disabled."
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            elif action == "enable":
                # Enable auto-proxy mode
                success = self.alias_manager.enable_auto_proxy(
                    interaction.user.id, 
                    interaction.guild.id if interaction.guild else 0, 
                    character.strip() if character.strip() else ""
                )
                
                if success:
                    if character.strip():
                        embed = discord.Embed(
                            title="🔄 Auto-Proxy Enabled",
                            color=discord.Color.green(),
                            description=f"Auto-proxy enabled starting with **{character.strip()}**"
                        )
                    else:
                        embed = discord.Embed(
                            title="🔄 Auto-Proxy Enabled",
                            color=discord.Color.green(),
                            description="Auto-proxy is now active!"
                        )
                    
                    embed.add_field(
                        name="How It Works", 
                        value="• Use any trigger (`m.`, `s.`, etc.) to switch to that character\n• Character sticks until you use a different trigger\n• No need to keep typing triggers once set", 
                        inline=False
                    )
                    embed.add_field(
                        name="Example", 
                        value="`m. hello` → switches to Malachi, then `world` → still Malachi\n`s. hi there` → switches to Sam, then `how are you?` → still Sam", 
                        inline=False
                    )
                    embed.set_footer(text="Use '/alias auto action:disable' to turn off auto-proxy")
                elif character.strip():
                    embed = discord.Embed(
                        title="❌ Character Not Found",
                        color=discord.Color.red(),
                        description=f"Could not find a character named '{character.strip()}'."
                    )
                    embed.add_field(
                        name="Tip", 
                        value="Use '/alias list' to see your registered characters, or enable without a starting character.", 
                        inline=False
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Error",
                        color=discord.Color.red(),
                        description="Failed to enable auto-proxy."
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            else:
                await interaction.response.send_message(
                    "❌ Invalid action. Use 'enable', 'disable', or 'status'.", ephemeral=True
                )
        
        except Exception as e:
            logger.error(f"Error in auto proxy command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing auto-proxy. Please try again.", ephemeral=True
            )

    @alias_group.command(name="share", description="Share your alias group with another user")
    @app_commands.describe(
        group="The group name to share",
        user="The user to share with (mention them)",
        permission="Permission level: speaker, manager, or owner"
    )
    @app_commands.choices(permission=[
        app_commands.Choice(name="Speaker (can use aliases)", value="speaker"),
        app_commands.Choice(name="Manager (can use and edit aliases)", value="manager"),
        app_commands.Choice(name="Owner (full control)", value="owner")
    ])
    async def share_group(self, interaction: discord.Interaction, group: str, user: discord.Member, permission: str):
        """Share an alias group with another user"""
        try:
            if user.bot:
                await interaction.response.send_message("❌ Cannot share groups with bots.", ephemeral=True)
                return
                
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ Cannot share groups with yourself.", ephemeral=True)
                return
            
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                target_user_id_str = str(user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Check if user has aliases in this group
                group_aliases = db.query(CharacterAlias).filter(
                    CharacterAlias.user_id == user_id_str,
                    CharacterAlias.guild_id == guild_id_str,
                    CharacterAlias.group_name == group
                ).first()
                
                if not group_aliases:
                    await interaction.response.send_message(
                        f"❌ No aliases found in group '{group}'. Use `/alias list` to see your groups.", 
                        ephemeral=True
                    )
                    return
                
                # Check if shared group already exists
                existing_group = db.query(SharedGroup).filter(
                    SharedGroup.owner_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.group_name == group
                ).first()
                
                if not existing_group:
                    # Create new shared group
                    shared_group = SharedGroup(
                        owner_id=user_id_str,
                        guild_id=guild_id_str,
                        group_name=group,
                        subgroup_name="",
                        description=f"Shared group: {group}"
                    )
                    db.add(shared_group)
                    db.flush()  # Get the ID
                    group_id = shared_group.id
                else:
                    group_id = existing_group.id
                
                # Check if permission already exists
                existing_permission = db.query(SharedGroupPermission).filter(
                    SharedGroupPermission.shared_group_id == group_id,
                    SharedGroupPermission.user_id == target_user_id_str
                ).first()
                
                if existing_permission:
                    # Update existing permission
                    existing_permission.permission_level = permission
                    action = "updated"
                else:
                    # Create new permission
                    new_permission = SharedGroupPermission(
                        shared_group_id=group_id,
                        user_id=target_user_id_str,
                        permission_level=permission,
                        granted_by=user_id_str
                    )
                    db.add(new_permission)
                    action = "granted"
                
                db.commit()
                
                # Create success embed
                embed = discord.Embed(
                    title="✅ Group Shared Successfully",
                    color=discord.Color.green()
                )
                embed.add_field(name="Group", value=group, inline=True)
                embed.add_field(name="Shared With", value=user.mention, inline=True)
                embed.add_field(name="Permission", value=permission.title(), inline=True)
                embed.add_field(
                    name="What this means:",
                    value=(
                        f"• **Speaker**: Can use all aliases in '{group}'\n"
                        f"• **Manager**: Can use and edit aliases in '{group}'\n"
                        f"• **Owner**: Full control over '{group}'"
                    )[:permission == 'speaker' and 1 or 2 or 3],
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Try to DM the user about the share
                try:
                    dm_embed = discord.Embed(
                        title="🎭 New Alias Group Shared!",
                        color=discord.Color.blue()
                    )
                    dm_embed.add_field(name="From", value=interaction.user.mention, inline=True)
                    dm_embed.add_field(name="Group", value=group, inline=True)
                    dm_embed.add_field(name="Permission", value=permission.title(), inline=True)
                    dm_embed.add_field(
                        name="Access your shared groups:",
                        value="Visit the web interface to view and use shared aliases!",
                        inline=False
                    )
                    
                    await user.send(embed=dm_embed)
                    
                except discord.Forbidden:
                    # User has DMs disabled, that's fine
                    pass
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error sharing group: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while sharing the group.", ephemeral=True
            )
    
    @alias_group.command(name="unshare", description="Remove sharing permissions for a group")
    @app_commands.describe(
        group="The group name to unshare",
        user="The user to remove permissions from"
    )
    async def unshare_group(self, interaction: discord.Interaction, group: str, user: discord.Member):
        """Remove sharing permissions for a group"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission
                
                user_id_str = str(interaction.user.id)
                target_user_id_str = str(user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Find the shared group
                shared_group = db.query(SharedGroup).filter(
                    SharedGroup.owner_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.group_name == group
                ).first()
                
                if not shared_group:
                    await interaction.response.send_message(
                        f"❌ No shared group '{group}' found.", ephemeral=True
                    )
                    return
                
                # Remove permission
                removed = db.query(SharedGroupPermission).filter(
                    SharedGroupPermission.shared_group_id == shared_group.id,
                    SharedGroupPermission.user_id == target_user_id_str
                ).delete()
                
                db.commit()
                
                if removed > 0:
                    await interaction.response.send_message(
                        f"✅ Removed {user.mention}'s access to group '{group}'.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ {user.mention} didn't have access to group '{group}'.", ephemeral=True
                    )
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error unsharing group: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while removing group access.", ephemeral=True
            )
    
    @alias_group.command(name="share_alias", description="Share a single character alias with another user")
    @app_commands.describe(
        alias_name="The character name to share",
        user="The user to share with (mention them)",
        permission="Permission level: speaker, manager, or owner"
    )
    @app_commands.choices(permission=[
        app_commands.Choice(name="Speaker (can use alias)", value="speaker"),
        app_commands.Choice(name="Manager (can use and edit alias)", value="manager"),
        app_commands.Choice(name="Owner (full control)", value="owner")
    ])
    async def share_single_alias(self, interaction: discord.Interaction, alias_name: str, user: discord.Member, permission: str):
        """Share a single character alias with another user"""
        try:
            if user.bot:
                await interaction.response.send_message("❌ Cannot share aliases with bots.", ephemeral=True)
                return
                
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ Cannot share aliases with yourself.", ephemeral=True)
                return
            
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                target_user_id_str = str(user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Find the specific alias
                alias = db.query(CharacterAlias).filter(
                    CharacterAlias.user_id == user_id_str,
                    CharacterAlias.guild_id == guild_id_str,
                    CharacterAlias.name == alias_name
                ).first()
                
                if not alias:
                    await interaction.response.send_message(
                        f"❌ No character named '{alias_name}' found. Use `/alias list` to see your characters.", 
                        ephemeral=True
                    )
                    return
                
                # Create a unique shared group name for this single alias
                shared_group_name = f"_SINGLE_ALIAS_{alias.id}"
                
                # Check if shared group already exists for this alias
                existing_group = db.query(SharedGroup).filter(
                    SharedGroup.owner_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.group_name == shared_group_name
                ).first()
                
                if not existing_group:
                    # Create new shared group for single alias
                    shared_group = SharedGroup(
                        owner_id=user_id_str,
                        guild_id=guild_id_str,
                        group_name=shared_group_name,
                        subgroup_name="",
                        description=f"Shared character: {alias.name}",
                        is_single_alias=True,
                        single_alias_id=alias.id
                    )
                    db.add(shared_group)
                    db.flush()  # Get the ID
                    group_id = shared_group.id
                else:
                    group_id = existing_group.id
                
                # Check if permission already exists
                existing_permission = db.query(SharedGroupPermission).filter(
                    SharedGroupPermission.shared_group_id == group_id,
                    SharedGroupPermission.user_id == target_user_id_str
                ).first()
                
                if existing_permission:
                    # Update existing permission
                    existing_permission.permission_level = permission
                    action = "updated"
                else:
                    # Create new permission
                    new_permission = SharedGroupPermission(
                        shared_group_id=group_id,
                        user_id=target_user_id_str,
                        permission_level=permission,
                        granted_by=user_id_str
                    )
                    db.add(new_permission)
                    action = "granted"
                
                db.commit()
                
                # Create success embed
                embed = discord.Embed(
                    title="✅ Character Shared Successfully",
                    color=discord.Color.green()
                )
                embed.add_field(name="Character", value=alias.name, inline=True)
                embed.add_field(name="Shared With", value=user.mention, inline=True)
                embed.add_field(name="Permission", value=permission.title(), inline=True)
                embed.add_field(
                    name="What this means:",
                    value=(
                        f"• **Speaker**: Can use '{alias.name}' alias\n"
                        f"• **Manager**: Can use and edit '{alias.name}'\n"
                        f"• **Owner**: Full control over '{alias.name}'"
                    ),
                    inline=False
                )
                
                if alias.avatar_url and alias.avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png":
                    embed.set_thumbnail(url=alias.avatar_url)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Try to DM the user about the share
                try:
                    dm_embed = discord.Embed(
                        title="🎭 Character Shared With You!",
                        color=discord.Color.blue()
                    )
                    dm_embed.add_field(name="From", value=interaction.user.mention, inline=True)
                    dm_embed.add_field(name="Character", value=alias.name, inline=True)
                    dm_embed.add_field(name="Permission", value=permission.title(), inline=True)
                    dm_embed.add_field(
                        name="Access your shared characters:",
                        value="Visit the web interface to view and use shared aliases!",
                        inline=False
                    )
                    
                    if alias.avatar_url and alias.avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png":
                        dm_embed.set_thumbnail(url=alias.avatar_url)
                    
                    await user.send(embed=dm_embed)
                    
                except discord.Forbidden:
                    # User has DMs disabled, that's fine
                    pass
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error sharing single alias: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while sharing the character.", ephemeral=True
            )

    def _get_shared_aliases_for_user(self, user_id: int, guild_id: int):
        """Get all aliases shared with a specific user"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission, CharacterAlias
                
                user_id_str = str(user_id)
                guild_id_str = str(guild_id)
                
                # Query for shared groups that this user has access to
                shared_groups = db.query(SharedGroup, SharedGroupPermission).join(
                    SharedGroupPermission, SharedGroup.id == SharedGroupPermission.shared_group_id
                ).filter(
                    SharedGroupPermission.user_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.is_active == True
                ).all()
                
                shared_aliases = []
                
                for shared_group, permission in shared_groups:
                    if shared_group.is_single_alias and shared_group.single_alias_id:
                        # Handle single alias shares
                        alias = db.query(CharacterAlias).filter(
                            CharacterAlias.id == shared_group.single_alias_id
                        ).first()
                        
                        if alias:
                            # Get owner name from cache or user ID
                            owner_name = self._get_user_display_name(int(shared_group.owner_id), guild_id)
                            shared_aliases.append({
                                "alias": alias,
                                "owner_name": owner_name,
                                "permission": permission.permission_level,
                                "shared_group": shared_group
                            })
                    else:
                        # Handle group/subgroup shares
                        query = db.query(CharacterAlias).filter(
                            CharacterAlias.user_id == shared_group.owner_id,
                            CharacterAlias.guild_id == guild_id_str,
                            CharacterAlias.group_name == shared_group.group_name
                        )
                        
                        if shared_group.subgroup_name:
                            query = query.filter(CharacterAlias.subgroup == shared_group.subgroup_name)
                        
                        aliases = query.all()
                        owner_name = self._get_user_display_name(int(shared_group.owner_id), guild_id)
                        
                        for alias in aliases:
                            shared_aliases.append({
                                "alias": alias,
                                "owner_name": owner_name,
                                "permission": permission.permission_level,
                                "shared_group": shared_group
                            })
                
                return shared_aliases
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting shared aliases for user: {e}")
            return []
    
    def _get_user_display_name(self, user_id: int, guild_id: int):
        """Get display name for a user from database, fallback to user ID"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import GuildMember
                
                # Query for the guild member record
                member = db.query(GuildMember).filter(
                    GuildMember.guild_id == str(guild_id),
                    GuildMember.user_id == str(user_id),
                    GuildMember.is_active == True
                ).first()
                
                if member:
                    # Use display_name (server nickname) if available, otherwise username
                    return member.display_name or member.username
                
                return f"User {user_id}"
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting user display name: {e}")
            return f"User {user_id}"

    @alias_group.command(name="unshare_alias", description="Remove sharing permissions for a single character")
    @app_commands.describe(
        alias_name="The character name to unshare",
        user="The user to remove permissions from"
    )
    async def unshare_single_alias(self, interaction: discord.Interaction, alias_name: str, user: discord.Member):
        """Remove sharing permissions for a single character alias"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                target_user_id_str = str(user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Find the specific alias
                alias = db.query(CharacterAlias).filter(
                    CharacterAlias.user_id == user_id_str,
                    CharacterAlias.guild_id == guild_id_str,
                    CharacterAlias.name == alias_name
                ).first()
                
                if not alias:
                    await interaction.response.send_message(
                        f"❌ No character named '{alias_name}' found.", ephemeral=True
                    )
                    return
                
                # Find the shared group for this single alias
                shared_group_name = f"_SINGLE_ALIAS_{alias.id}"
                shared_group = db.query(SharedGroup).filter(
                    SharedGroup.owner_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.group_name == shared_group_name
                ).first()
                
                if not shared_group:
                    await interaction.response.send_message(
                        f"❌ Character '{alias_name}' is not shared.", ephemeral=True
                    )
                    return
                
                # Remove permission
                removed = db.query(SharedGroupPermission).filter(
                    SharedGroupPermission.shared_group_id == shared_group.id,
                    SharedGroupPermission.user_id == target_user_id_str
                ).delete()
                
                db.commit()
                
                if removed > 0:
                    await interaction.response.send_message(
                        f"✅ Removed {user.mention}'s access to character '{alias_name}'.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ {user.mention} didn't have access to character '{alias_name}'.", ephemeral=True
                    )
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error unsharing single alias: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while removing character access.", ephemeral=True
            )

    @alias_group.command(name="shared", description="List groups that have been shared with you")
    async def list_shared_groups(self, interaction: discord.Interaction):
        """List groups that have been shared with you"""
        try:
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission
                from sqlalchemy.orm import joinedload
                
                user_id_str = str(interaction.user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Get groups shared with this user
                permissions = db.query(SharedGroupPermission).options(
                    joinedload(SharedGroupPermission.shared_group)
                ).filter(
                    SharedGroupPermission.user_id == user_id_str,
                    SharedGroupPermission.shared_group.has(SharedGroup.guild_id == guild_id_str)
                ).all()
                
                embed = discord.Embed(
                    title="🤝 Groups Shared With You",
                    color=discord.Color.blue()
                )
                
                if not permissions:
                    embed.description = "No groups have been shared with you yet."
                    embed.add_field(
                        name="How to get shared groups:",
                        value="Ask other users to share their alias groups with you using `/alias share`!",
                        inline=False
                    )
                else:
                    for perm in permissions:
                        group = perm.shared_group
                        embed.add_field(
                            name=f"📁 {group.group_name}",
                            value=(
                                f"**Owner**: <@{group.owner_id}>\n"
                                f"**Your Role**: {perm.permission_level.title()}\n"
                                f"**Shared**: <t:{int(perm.granted_at.timestamp())}:R>"
                            ),
                            inline=True
                        )
                
                embed.add_field(
                    name="💡 Pro Tip",
                    value="Use the web interface to view and use shared aliases more easily!",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error listing shared groups: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing shared groups.", ephemeral=True
            )

    @alias_group.command(name="share_subgroup", description="Share a specific subgroup with another user")
    @app_commands.describe(
        group="The main group name",
        subgroup="The subgroup name to share",
        user="The user to share with (mention them)",
        permission="Permission level: speaker, manager, or owner"
    )
    @app_commands.choices(permission=[
        app_commands.Choice(name="Speaker (can use aliases)", value="speaker"),
        app_commands.Choice(name="Manager (can use and edit aliases)", value="manager"),
        app_commands.Choice(name="Owner (full control)", value="owner")
    ])
    async def share_subgroup(self, interaction: discord.Interaction, group: str, subgroup: str, user: discord.Member, permission: str):
        """Share a specific subgroup with another user"""
        try:
            if user.bot:
                await interaction.response.send_message("❌ Cannot share subgroups with bots.", ephemeral=True)
                return
                
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ Cannot share subgroups with yourself.", ephemeral=True)
                return
            
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import SharedGroup, SharedGroupPermission, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                target_user_id_str = str(user.id)
                guild_id_str = str(interaction.guild.id if interaction.guild else 0)
                
                # Check if user has aliases in this group/subgroup
                subgroup_aliases = db.query(CharacterAlias).filter(
                    CharacterAlias.user_id == user_id_str,
                    CharacterAlias.guild_id == guild_id_str,
                    CharacterAlias.group_name == group,
                    CharacterAlias.subgroup == subgroup
                ).first()
                
                if not subgroup_aliases:
                    await interaction.response.send_message(
                        f"❌ No aliases found in subgroup '{group}/{subgroup}'. Use `/alias list` to see your groups.", 
                        ephemeral=True
                    )
                    return
                
                # Check if shared group already exists for this subgroup
                existing_group = db.query(SharedGroup).filter(
                    SharedGroup.owner_id == user_id_str,
                    SharedGroup.guild_id == guild_id_str,
                    SharedGroup.group_name == group,
                    SharedGroup.subgroup_name == subgroup
                ).first()
                
                if not existing_group:
                    # Create new shared group for subgroup
                    shared_group = SharedGroup(
                        owner_id=user_id_str,
                        guild_id=guild_id_str,
                        group_name=group,
                        subgroup_name=subgroup,
                        description=f"Shared subgroup: {group}/{subgroup}"
                    )
                    db.add(shared_group)
                    db.flush()  # Get the ID
                    group_id = shared_group.id
                else:
                    group_id = existing_group.id
                
                # Check if permission already exists
                existing_permission = db.query(SharedGroupPermission).filter(
                    SharedGroupPermission.shared_group_id == group_id,
                    SharedGroupPermission.user_id == target_user_id_str
                ).first()
                
                if existing_permission:
                    # Update existing permission
                    existing_permission.permission_level = permission
                    action = "updated"
                else:
                    # Create new permission
                    new_permission = SharedGroupPermission(
                        shared_group_id=group_id,
                        user_id=target_user_id_str,
                        permission_level=permission,
                        granted_by=user_id_str
                    )
                    db.add(new_permission)
                    action = "granted"
                
                db.commit()
                
                # Create success embed
                embed = discord.Embed(
                    title="✅ Subgroup Shared Successfully",
                    color=discord.Color.green()
                )
                embed.add_field(name="Group", value=group, inline=True)
                embed.add_field(name="Subgroup", value=subgroup, inline=True)
                embed.add_field(name="Shared With", value=user.mention, inline=True)
                embed.add_field(name="Permission", value=permission.title(), inline=True)
                embed.add_field(
                    name="What this means:",
                    value=(
                        f"• **Speaker**: Can use all aliases in '{group}/{subgroup}'\n"
                        f"• **Manager**: Can use and edit aliases in '{group}/{subgroup}'\n"
                        f"• **Owner**: Full control over '{group}/{subgroup}'"
                    ),
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Try to DM the user about the share
                try:
                    dm_embed = discord.Embed(
                        title="🎭 Subgroup Shared With You!",
                        color=discord.Color.blue()
                    )
                    dm_embed.add_field(name="From", value=interaction.user.mention, inline=True)
                    dm_embed.add_field(name="Subgroup", value=f"{group}/{subgroup}", inline=True)
                    dm_embed.add_field(name="Permission", value=permission.title(), inline=True)
                    dm_embed.add_field(
                        name="Access your shared subgroups:",
                        value="Visit the web interface to view and use shared aliases!",
                        inline=False
                    )
                    
                    await user.send(embed=dm_embed)
                    
                except discord.Forbidden:
                    # User has DMs disabled, that's fine
                    pass
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error sharing subgroup: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while sharing the subgroup.", ephemeral=True
            )

    @alias_group.command(name="subgroups", description="List your subgroups within a group")
    @app_commands.describe(group="The group name to view subgroups for")
    async def list_subgroups(self, interaction: discord.Interaction, group: str):
        """List subgroups within a specific group"""
        try:
            aliases = self.alias_manager.get_user_aliases(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            # Filter aliases by group and collect subgroups
            group_aliases = [alias for alias in aliases if alias.group_name == group]
            
            if not group_aliases:
                await interaction.response.send_message(
                    f"❌ No group named '{group}' found. Use `/alias list` to see your groups.", 
                    ephemeral=True
                )
                return
            
            # Collect subgroups
            subgroups = {}
            for alias in group_aliases:
                subgroup_name = alias.subgroup or "Main"
                if subgroup_name not in subgroups:
                    subgroups[subgroup_name] = []
                subgroups[subgroup_name].append(alias)
            
            embed = discord.Embed(
                title=f"📁 Subgroups in '{group}'",
                color=discord.Color.blue()
            )
            
            for subgroup_name, aliases_in_subgroup in subgroups.items():
                alias_list = []
                for alias in aliases_in_subgroup[:5]:  # Limit to first 5 to avoid embed limits
                    msg_count = alias.message_count or 0
                    usage_text = f"({msg_count} msg{'s' if msg_count != 1 else ''})" if msg_count > 0 else "(unused)"
                    alias_list.append(f"• **{alias.name}** - `{alias.trigger}` {usage_text}")
                
                if len(aliases_in_subgroup) > 5:
                    alias_list.append(f"... and {len(aliases_in_subgroup) - 5} more")
                
                embed.add_field(
                    name=f"🏷️ {subgroup_name} ({len(aliases_in_subgroup)} aliases)",
                    value="\n".join(alias_list) if alias_list else "No aliases",
                    inline=False
                )
            
            embed.add_field(
                name="💡 Sharing Subgroups",
                value="Use `/alias share_subgroup` to share specific subgroups with other users!",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error listing subgroups: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing subgroups.", ephemeral=True
            )

    async def _show_tree_view(self, interaction: discord.Interaction, target_user: discord.Member, group: str = ""):
        """Display aliases in a modal with folder-style tree structure including shared aliases"""
        try:
            # Get target user's aliases
            aliases = self.alias_manager.get_user_aliases(target_user.id, interaction.guild.id if interaction.guild else 0)
            
            # Get shared aliases accessible to this user
            shared_aliases = self._get_shared_aliases_for_user(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            if not aliases and not shared_aliases:
                await interaction.response.send_message("❌ You don't have any aliases yet. Use `/alias create` to get started!", ephemeral=True)
                return
            
            # Organize user's own aliases into groups and subgroups
            tree_structure = {}
            ungrouped = []
            
            for alias in aliases:
                if alias.group_name:
                    group = alias.group_name.strip()
                    if group not in tree_structure:
                        tree_structure[group] = {"Main": [], "subgroups": {}, "is_shared": False}
                    
                    if alias.subgroup:
                        subgroup = alias.subgroup.strip()
                        if subgroup not in tree_structure[group]["subgroups"]:
                            tree_structure[group]["subgroups"][subgroup] = []
                        tree_structure[group]["subgroups"][subgroup].append(alias)
                    else:
                        tree_structure[group]["Main"].append(alias)
                else:
                    ungrouped.append(alias)
            
            # Organize shared aliases
            shared_structure = {}
            shared_ungrouped = []
            
            for shared_data in shared_aliases:
                alias = shared_data["alias"]
                owner_name = shared_data["owner_name"]
                permission = shared_data["permission"]
                
                if alias.group_name:
                    # Group shared aliases by owner and group
                    owner_group_key = f"{owner_name}'s {alias.group_name}"
                    if owner_group_key not in shared_structure:
                        shared_structure[owner_group_key] = {"Main": [], "subgroups": {}, "is_shared": True, "owner": owner_name, "permission": permission}
                    
                    if alias.subgroup:
                        subgroup = alias.subgroup.strip()
                        if subgroup not in shared_structure[owner_group_key]["subgroups"]:
                            shared_structure[owner_group_key]["subgroups"][subgroup] = []
                        shared_structure[owner_group_key]["subgroups"][subgroup].append({"alias": alias, "permission": permission})
                    else:
                        shared_structure[owner_group_key]["Main"].append({"alias": alias, "permission": permission})
                else:
                    shared_ungrouped.append({"alias": alias, "owner_name": owner_name, "permission": permission})
            
            # Build the tree display
            tree_lines = []
            tree_lines.append("📁 YOUR CHARACTER ALIASES")
            tree_lines.append("═" * 33)
            tree_lines.append("")
            
            # Show user's own grouped aliases
            if tree_structure:
                for group_name, group_data in sorted(tree_structure.items()):
                    tree_lines.append(f"📂 {group_name}")
                    
                    # Main group aliases (no subgroup)
                    if group_data["Main"]:
                        for i, alias in enumerate(group_data["Main"]):
                            is_last = i == len(group_data["Main"]) - 1 and not group_data["subgroups"]
                            prefix = "└─" if is_last else "├─"
                            msg_count = alias.message_count or 0
                            usage = f"({msg_count})" if msg_count > 0 else ""
                            tree_lines.append(f"  {prefix} 🎭 {alias.name} `{alias.trigger}` {usage}")
                    
                    # Subgroup aliases
                    subgroup_items = list(group_data["subgroups"].items())
                    for sg_idx, (subgroup_name, subgroup_aliases) in enumerate(subgroup_items):
                        is_last_subgroup = sg_idx == len(subgroup_items) - 1
                        sg_prefix = "└─" if is_last_subgroup else "├─"
                        tree_lines.append(f"  {sg_prefix} 📁 {subgroup_name}")
                        
                        for alias_idx, alias in enumerate(subgroup_aliases):
                            is_last_alias = alias_idx == len(subgroup_aliases) - 1
                            alias_prefix = "    └─" if (is_last_subgroup and is_last_alias) else "    ├─"
                            if not is_last_subgroup:
                                alias_prefix = "  │ └─" if is_last_alias else "  │ ├─"
                            
                            msg_count = alias.message_count or 0
                            usage = f"({msg_count})" if msg_count > 0 else ""
                            tree_lines.append(f"{alias_prefix} 🎭 {alias.name} `{alias.trigger}` {usage}")
                    
                    tree_lines.append("")  # Blank line between groups
            
            # Show user's ungrouped aliases
            if ungrouped:
                tree_lines.append("📄 Ungrouped")
                for i, alias in enumerate(ungrouped):
                    is_last = i == len(ungrouped) - 1
                    prefix = "└─" if is_last else "├─"
                    msg_count = alias.message_count or 0
                    usage = f"({msg_count})" if msg_count > 0 else ""
                    tree_lines.append(f"  {prefix} 🎭 {alias.name} `{alias.trigger}` {usage}")
                tree_lines.append("")
            
            # Show shared aliases section
            if shared_structure or shared_ungrouped:
                tree_lines.append("🤝 SHARED WITH YOU")
                tree_lines.append("═" * 33)
                tree_lines.append("")
                
                # Show shared groups
                for group_name, group_data in sorted(shared_structure.items()):
                    permission_icon = "👑" if group_data["permission"] == "owner" else ("🛠️" if group_data["permission"] == "manager" else "💬")
                    tree_lines.append(f"📂 {group_name} {permission_icon}")
                    
                    # Main group shared aliases
                    if group_data["Main"]:
                        for i, alias_data in enumerate(group_data["Main"]):
                            alias = alias_data["alias"]
                            is_last = i == len(group_data["Main"]) - 1 and not group_data["subgroups"]
                            prefix = "└─" if is_last else "├─"
                            msg_count = alias.message_count or 0
                            usage = f"({msg_count})" if msg_count > 0 else ""
                            tree_lines.append(f"  {prefix} 🎭 {alias.name} `{alias.trigger}` {usage}")
                    
                    # Shared subgroup aliases
                    subgroup_items = list(group_data["subgroups"].items())
                    for sg_idx, (subgroup_name, subgroup_aliases) in enumerate(subgroup_items):
                        is_last_subgroup = sg_idx == len(subgroup_items) - 1
                        sg_prefix = "└─" if is_last_subgroup else "├─"
                        tree_lines.append(f"  {sg_prefix} 📁 {subgroup_name}")
                        
                        for alias_idx, alias_data in enumerate(subgroup_aliases):
                            alias = alias_data["alias"]
                            is_last_alias = alias_idx == len(subgroup_aliases) - 1
                            alias_prefix = "    └─" if (is_last_subgroup and is_last_alias) else "    ├─"
                            if not is_last_subgroup:
                                alias_prefix = "  │ └─" if is_last_alias else "  │ ├─"
                            
                            msg_count = alias.message_count or 0
                            usage = f"({msg_count})" if msg_count > 0 else ""
                            tree_lines.append(f"{alias_prefix} 🎭 {alias.name} `{alias.trigger}` {usage}")
                    
                    tree_lines.append("")
                
                # Show shared ungrouped aliases
                if shared_ungrouped:
                    tree_lines.append("📄 Shared Individual Characters")
                    for i, shared_data in enumerate(shared_ungrouped):
                        alias = shared_data["alias"]
                        owner_name = shared_data["owner_name"]
                        permission = shared_data["permission"]
                        is_last = i == len(shared_ungrouped) - 1
                        prefix = "└─" if is_last else "├─"
                        permission_icon = "👑" if permission == "owner" else ("🛠️" if permission == "manager" else "💬")
                        msg_count = alias.message_count or 0
                        usage = f"({msg_count})" if msg_count > 0 else ""
                        tree_lines.append(f"  {prefix} 🎭 {alias.name} `{alias.trigger}` from {owner_name} {permission_icon} {usage}")
                
            # Add legend if there are shared aliases
            if shared_structure or shared_ungrouped:
                tree_lines.append("")
                tree_lines.append("Legend: 💬 Speaker | 🛠️ Manager | 👑 Owner")
            
            content = "\n".join(tree_lines)
            
            # Handle modal length limits with pagination
            if len(content) > 3900:
                # Split into pages that fit in modal
                lines = tree_lines
                pages = []
                current_page = []
                current_length = 0
                
                for line in lines:
                    line_length = len(line) + 1  # +1 for newline
                    if current_length + line_length > 3800:  # Leave room for page info
                        # Finish current page
                        if current_page:
                            pages.append("\n".join(current_page))
                        current_page = [line]
                        current_length = line_length
                    else:
                        current_page.append(line)
                        current_length += line_length
                
                # Add last page
                if current_page:
                    pages.append("\n".join(current_page))
                
                # Show first page with pagination info
                if pages:
                    content = pages[0]
                    if len(pages) > 1:
                        total_aliases = len(aliases) + len(shared_aliases)
                        content += f"\n\n📄 Page 1 of {len(pages)}"
                        content += f"\nUse the web interface to view all {total_aliases} aliases"
                        content += f"\nor use `/alias list` for a different view"
            
            # Create and show modal
            modal = FolderViewModal(content, len(aliases))
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error showing folder view: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while displaying the folder view.", ephemeral=True
            )

    @alias_group.command(name="help", description="Get help with the alias system")
    async def alias_help(self, interaction: discord.Interaction):
        """Show help information for the alias system"""
        embed = discord.Embed(
            title="📚 Character Alias System Help",
            color=discord.Color.blue(),
            description="The alias system lets you post messages as your D&D characters using webhooks!"
        )
        
        embed.add_field(
            name="🎭 How It Works",
            value=(
                "1. Register a character with `/alias register`\n"
                "2. Use the trigger pattern to post as that character\n"
                "3. Your original message gets deleted and replaced with the character's message"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Trigger Examples",
            value=(
                "• `k:` - Type `k:Hello everyone!` to post as your character\n"
                "• `[text]` - Type `[Hello everyone!]` to post as your character\n"
                "• `(text)` - Type `(Hello everyone!)` to post as your character\n"
                "• `Kaelen:` - Type `Kaelen:Hello everyone!` to post as Kaelen"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💬 Multi-Line Conversations",
            value=(
                "Send multiple characters in one message using line breaks (Shift+Enter):\n"
                "```\n"
                "m. Hey how are you?\n"
                "s. I am great, you?\n"
                "m. Not too bad!\n"
                "```\n"
                "Each line will be sent as a separate message from the respective character."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎭 Character Profiles",
            value=(
                "Right-click any character message → Apps → **View Character Profile**\n"
                "This shows character details, usage stats, and owner information."
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 Available Commands",
            value=(
                "`/alias register` - Quick character creation\n"
                "`/alias create` - Detailed character with backstory\n"
                "`/alias avatar` - Upload character image\n"
                "`/alias list` - View your characters\n"
                "`/alias share` - Share group with another user\n"
                "`/alias share_alias` - Share single character\n"
                "`/alias share_subgroup` - Share specific subgroup\n"
                "`/alias subgroups` - List subgroups in a group\n"
                "`/alias list` - View your characters (tree or simple view)\n"
                "`/alias shared` - View groups shared with you\n"
                "`/alias show` - View character details\n"
                "`/alias edit` - Modify a character\n"
                "`/alias remove` - Delete a character\n"
                "`/alias auto` - Enable/disable auto-proxy\n"
                "`/alias export` - Export characters to CSV\n"
                "`/alias import` - Import characters from CSV"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Choose unique triggers to avoid conflicts\n"
                "• Upload images under 2MB for avatars\n"
                "• Keep character names under 80 characters\n"
                "• Use export/import for bulk character management\n"
                "• Test your trigger pattern after creating"
            ),
            inline=False
        )
        
        embed.set_footer(text="Need more help? Ask a moderator!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    def _get_usage_example(self, trigger: str) -> str:
        """Generate a usage example for a trigger"""
        if trigger.startswith('[') and trigger.endswith(']'):
            return "Type `[Hello everyone!]` to post as this character"
        elif trigger.startswith('(') and trigger.endswith(')'):
            return "Type `(Hello everyone!)` to post as this character"
        elif trigger.endswith(':'):
            return f"Type `{trigger}Hello everyone!` to post as this character"
        else:
            return f"Type `{trigger}` to post as this character"
    
    # Autocomplete for individual alias names (for sharing single aliases)
    @share_single_alias.autocomplete('alias_name')
    @unshare_single_alias.autocomplete('alias_name')
    async def single_alias_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for single alias names"""
        try:
            aliases = self.alias_manager.get_user_aliases(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            # Filter aliases based on current input
            filtered_aliases = [
                alias for alias in aliases 
                if current.lower() in str(alias.name).lower()
            ][:25]  # Discord limit
            
            return [
                app_commands.Choice(name=str(alias.name), value=str(alias.name))
                for alias in filtered_aliases
            ]
        except:
            return []

    # Autocomplete for subgroup names 
    @share_subgroup.autocomplete('subgroup')
    async def subgroup_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for subgroup names"""
        try:
            aliases = self.alias_manager.get_user_aliases(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            # Get group parameter value from the current interaction
            group_name = None
            if hasattr(interaction, 'namespace') and hasattr(interaction.namespace, 'group'):
                group_name = interaction.namespace.group
            
            # Get unique subgroup names for the specified group
            subgroup_names = set()
            for alias in aliases:
                if group_name and alias.group_name == group_name and alias.subgroup:
                    subgroup_names.add(alias.subgroup.strip())
                elif not group_name and alias.subgroup:  # If no group specified, show all subgroups
                    subgroup_names.add(alias.subgroup.strip())
            
            # Filter based on current input
            filtered_subgroups = [
                subgroup for subgroup in subgroup_names 
                if current.lower() in subgroup.lower()
            ][:25]  # Discord limit
            
            return [
                app_commands.Choice(name=subgroup, value=subgroup)
                for subgroup in sorted(filtered_subgroups)
            ]
        except:
            return []

    # Autocomplete for group names in subgroup and list commands
    @share_subgroup.autocomplete('group')
    @list_subgroups.autocomplete('group')
    async def subgroup_group_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for group names that have subgroups"""
        try:
            aliases = self.alias_manager.get_user_aliases(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            # Get unique group names that have subgroups
            group_names = set()
            for alias in aliases:
                if alias.group_name and alias.group_name.strip() and alias.subgroup:
                    group_names.add(alias.group_name.strip())
            
            # Filter based on current input
            filtered_groups = [
                group for group in group_names 
                if current.lower() in group.lower()
            ][:25]  # Discord limit
            
            return [
                app_commands.Choice(name=group, value=group)
                for group in sorted(filtered_groups)
            ]
        except:
            return []

    # Autocomplete for group names
    @share_group.autocomplete('group')
    @unshare_group.autocomplete('group')
    async def group_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for group names"""
        try:
            aliases = self.alias_manager.get_user_aliases(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            # Get unique group names
            group_names = set()
            for alias in aliases:
                if alias.group_name and alias.group_name.strip():
                    group_names.add(alias.group_name.strip())
            
            # Filter based on current input
            filtered_groups = [
                group for group in group_names 
                if current.lower() in group.lower()
            ][:25]  # Discord limit
            
            return [
                app_commands.Choice(name=group, value=group)
                for group in sorted(filtered_groups)
            ]
        except:
            return []

    # Autocomplete for alias names
    @edit_alias.autocomplete('name')
    @show_alias.autocomplete('name')
    @remove_alias.autocomplete('name')
    @set_avatar.autocomplete('name')
    @auto_proxy.autocomplete('character')
    async def alias_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for alias names"""
        try:
            aliases = self.alias_manager.get_user_aliases(interaction.user.id, interaction.guild.id if interaction.guild else 0)
            
            # Filter aliases based on current input
            filtered_aliases = [
                alias for alias in aliases 
                if current.lower() in str(alias.name).lower()
            ][:25]  # Discord limit
            
            return [
                app_commands.Choice(name=str(alias.name), value=str(alias.name))
                for alias in filtered_aliases
            ]
        except:
            return []
    
    # Autocomplete for shared alias names  
    @override_alias.autocomplete('alias_name')
    async def shared_alias_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for shared alias names"""
        try:
            if not interaction.guild:
                return []
            
            # Get shared aliases accessible to this user
            shared_aliases = self._get_shared_aliases_for_user(
                interaction.user.id, interaction.guild.id
            )
            
            # Filter based on current input and limit to 25 (Discord limit)
            filtered_aliases = [
                shared_data['alias'] for shared_data in shared_aliases
                if current.lower() in shared_data['alias'].name.lower()
            ][:25]
            
            return [
                app_commands.Choice(name=alias.name, value=alias.name)
                for alias in filtered_aliases
            ]
            
        except Exception as e:
            logger.error(f"Error in shared alias autocomplete: {e}")
            return []

    # Autocomplete for override alias names
    @remove_override.autocomplete('alias_name')
    async def override_alias_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for aliases that have personal overrides"""
        try:
            if not interaction.guild:
                return []
            
            # Get user's overrides
            db = self.alias_manager.db_manager.get_session()
            try:
                from models import AliasOverride, CharacterAlias
                
                user_id_str = str(interaction.user.id)
                guild_id_str = str(interaction.guild.id)
                
                overrides = db.query(AliasOverride, CharacterAlias).join(
                    CharacterAlias, AliasOverride.original_alias_id == CharacterAlias.id
                ).filter(
                    AliasOverride.user_id == user_id_str,
                    AliasOverride.guild_id == guild_id_str,
                    AliasOverride.is_active == True
                ).all()
                
                # Filter based on current input and limit to 25 (Discord limit)
                filtered_aliases = [
                    alias for override, alias in overrides
                    if current.lower() in alias.name.lower()
                ][:25]
                
                return [
                    app_commands.Choice(name=alias.name, value=alias.name)
                    for alias in filtered_aliases
                ]
                
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"Error in override alias autocomplete: {e}")
            return []