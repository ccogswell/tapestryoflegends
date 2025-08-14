import discord
from discord import ui
import logging
from typing import Optional, Dict, Any
from bot.alias_manager import AliasManager

logger = logging.getLogger(__name__)

class ContinueToAppearanceView(ui.View):
    """View with button to continue to appearance modal"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.alias_manager = alias_manager
        self.character_data = character_data
    
    @ui.button(label="Continue to Appearance", style=discord.ButtonStyle.primary, emoji="👤")
    async def continue_to_appearance(self, interaction: discord.Interaction, button: ui.Button):
        """Continue to appearance modal"""
        appearance_modal = CharacterAppearanceModal(self.alias_manager, self.character_data)
        await interaction.response.send_modal(appearance_modal)
    
    @ui.button(label="Skip Appearance", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_appearance(self, interaction: discord.Interaction, button: ui.Button):
        """Skip appearance and show next step options"""
        view = ContinueToBackstoryView(self.alias_manager, self.character_data)
        
        embed = discord.Embed(
            title="⏭️ Skipped Appearance Details",
            color=discord.Color.blue(),
            description=f"Character **{self.character_data['name']}** appearance details skipped."
        )
        embed.add_field(name="Next Step", value="Choose whether to add background details or finish creating your character.", inline=False)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ContinueToBackstoryView(ui.View):
    """View with button to continue to backstory modal"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.alias_manager = alias_manager
        self.character_data = character_data
    
    @ui.button(label="Continue to Background", style=discord.ButtonStyle.primary, emoji="📖")
    async def continue_to_backstory(self, interaction: discord.Interaction, button: ui.Button):
        """Continue to backstory modal"""
        backstory_modal = CharacterBackstoryModal(self.alias_manager, self.character_data)
        await interaction.response.send_modal(backstory_modal)
    
    @ui.button(label="Skip Background", style=discord.ButtonStyle.success, emoji="✅")
    async def finish_character(self, interaction: discord.Interaction, button: ui.Button):
        """Skip background and finish character creation"""
        try:
            # Create the alias with current data (skipping background info)
            # Ensure avatar_url is never None
            avatar_url = self.character_data.get('avatar_url') or "https://cdn.discordapp.com/embed/avatars/0.png"
            alias = self.alias_manager.create_alias(
                user_id=self.character_data['user_id'],
                guild_id=self.character_data['guild_id'],
                name=self.character_data['name'],
                trigger=self.character_data['trigger'],
                avatar_url=avatar_url,
                group_name=self.character_data.get('group_name'),
                character_class=self.character_data.get('class_level'),
                race=self.character_data.get('race'),
                pronouns=self.character_data.get('pronouns'),
                age=self.character_data.get('age'),
                alignment=self.character_data.get('alignment'),
                description=self.character_data.get('description'),
                personality=self.character_data.get('personality')
            )
            
            embed = discord.Embed(
                title=f"✅ Character Created: {alias.name}",
                color=discord.Color.green(),
                description="Your character has been created and is ready for roleplay!"
            )
            embed.add_field(name="🎯 Trigger", value=f"`{alias.trigger}`", inline=True)
            embed.set_footer(text="Use '/alias edit' to add more details anytime!")
            
            # If no custom avatar was provided, show upload option
            if not self.character_data.get('avatar_url'):
                from bot.alias_commands import AliasUploadView
                view = AliasUploadView(self.alias_manager, alias.name, interaction.client)
                embed.add_field(name="💡 Add Avatar", value="Upload a custom avatar using the button below!", inline=False)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                embed.set_thumbnail(url=alias.avatar_url)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error finishing character creation: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating your character. Please try again.", 
                ephemeral=True
            )

class CharacterBasicModal(ui.Modal, title='Character Creation - Basic Info'):
    """First modal: Basic character information"""
    
    def __init__(self, alias_manager: AliasManager):
        super().__init__()
        self.alias_manager = alias_manager
    
    character_name = ui.TextInput(
        label='Character Name',
        placeholder='Enter your character\'s name (e.g., Kael Brightblade)',
        max_length=80,
        required=True
    )
    
    trigger_pattern = ui.TextInput(
        label='Trigger Pattern',
        placeholder='e.g., k: or [text] or (text) or kael:',
        max_length=100,
        required=True
    )
    
    character_class = ui.TextInput(
        label='Class & Level (Optional)',
        placeholder='e.g., Wizard 5, Fighter 3/Rogue 2, Commoner',
        max_length=50,
        required=False
    )
    
    race = ui.TextInput(
        label='Race/Species (Optional)',
        placeholder='e.g., Human, Elf, Dragonborn, Construct',
        max_length=50,
        required=False
    )
    
    group_name = ui.TextInput(
        label='Group/Campaign (Optional)',
        placeholder='e.g., Curse of Strahd, Main Campaign, NPCs',
        max_length=100,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Store basic info and proceed to appearance modal"""
        try:
            # Store data for next step
            character_data = {
                'name': str(self.character_name.value),
                'trigger': str(self.trigger_pattern.value),
                'class_level': str(self.character_class.value).strip() if self.character_class.value else None,
                'race': str(self.race.value).strip() if self.race.value else None,
                'group_name': str(self.group_name.value).strip() if self.group_name.value else None,
                'user_id': interaction.user.id,
                'guild_id': interaction.guild.id if interaction.guild else 0
            }
            
            # Create a view with a button to continue to the next step
            view = ContinueToAppearanceView(self.alias_manager, character_data)
            
            embed = discord.Embed(
                title="✅ Basic Info Saved",
                color=discord.Color.blue(),
                description=f"Character **{character_data['name']}** basic info recorded!"
            )
            embed.add_field(name="Next Step", value="Click the button below to continue with appearance details.", inline=False)
            embed.add_field(name="Character Name", value=character_data['name'], inline=True)
            embed.add_field(name="Trigger", value=f"`{character_data['trigger']}`", inline=True)
            if character_data.get('class_level'):
                embed.add_field(name="Class", value=character_data['class_level'], inline=True)
            if character_data.get('race'):
                embed.add_field(name="Race", value=character_data['race'], inline=True)
            if character_data.get('group_name'):
                embed.add_field(name="Group", value=character_data['group_name'], inline=True)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in basic character modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.", ephemeral=True
            )

class CharacterAppearanceModal(ui.Modal, title='Character Creation - Appearance'):
    """Second modal: Character appearance and avatar"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__()
        self.alias_manager = alias_manager
        self.character_data = character_data
    
    avatar_url = ui.TextInput(
        label='Avatar Image URL (Optional)',
        placeholder='Paste image URL here, or leave blank to upload later',
        max_length=500,
        required=False
    )
    
    description = ui.TextInput(
        label='Physical Description (Optional)',
        style=discord.TextStyle.paragraph,
        placeholder='Describe your character\'s appearance, height, build, distinguishing features...',
        max_length=1000,
        required=False
    )
    
    pronouns = ui.TextInput(
        label='Pronouns (Optional)',
        placeholder='e.g., she/her, he/him, they/them, any',
        max_length=50,
        required=False
    )
    
    age = ui.TextInput(
        label='Age (Optional, 18+ only)',
        placeholder='Character age (must be 18 or older, leave blank if unknown)',
        max_length=10,
        required=False
    )
    
    alignment = ui.TextInput(
        label='Alignment (Optional)',
        placeholder='e.g., Chaotic Good, Lawful Neutral, True Neutral',
        max_length=50,
        required=False
    )
    

    
    async def on_submit(self, interaction: discord.Interaction):
        """Store appearance info and proceed to backstory modal"""
        try:
            # Validate age if provided
            age_value = str(self.age.value).strip() if self.age.value else None
            if age_value:
                try:
                    age_num = int(age_value)
                    if age_num < 18:
                        await interaction.response.send_message(
                            "❌ Character age must be 18 or older. Please update the age field.", 
                            ephemeral=True
                        )
                        return
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Age must be a valid number. Please enter a numeric age or leave blank.", 
                        ephemeral=True
                    )
                    return
            
            # Add appearance data
            self.character_data.update({
                'avatar_url': str(self.avatar_url.value).strip() if self.avatar_url.value else None,
                'description': str(self.description.value).strip() if self.description.value else None,
                'pronouns': str(self.pronouns.value).strip() if self.pronouns.value else None,
                'age': age_value,
                'alignment': str(self.alignment.value).strip() if self.alignment.value else None
            })
            
            # Create a view with a button to continue to the final step
            view = ContinueToBackstoryView(self.alias_manager, self.character_data)
            
            embed = discord.Embed(
                title="✅ Appearance Details Saved",
                color=discord.Color.blue(),
                description=f"Character **{self.character_data['name']}** appearance recorded!"
            )
            embed.add_field(name="Final Step", value="Click the button below to add backstory and complete creation.", inline=False)
            
            if self.character_data.get('description'):
                embed.add_field(name="Description", value=self.character_data['description'][:100] + "..." if len(self.character_data['description']) > 100 else self.character_data['description'], inline=False)
            
            # Show additional character details
            details = []
            if self.character_data.get('age'):
                details.append(f"Age: {self.character_data['age']}")
            if self.character_data.get('alignment'):
                details.append(f"Alignment: {self.character_data['alignment']}")
            if details:
                embed.add_field(name="Character Details", value=" • ".join(details), inline=False)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in appearance character modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.", ephemeral=True
            )

class CharacterBackstoryModal(ui.Modal, title='Character Creation - Background'):
    """Third modal: Character backstory and final creation"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__()
        self.alias_manager = alias_manager
        self.character_data = character_data
    
    backstory = ui.TextInput(
        label='Backstory (Optional)',
        style=discord.TextStyle.paragraph,
        placeholder='Character\'s history, background, important events...',
        max_length=1500,
        required=False
    )
    
    goals = ui.TextInput(
        label='Goals & Motivations (Optional)',
        style=discord.TextStyle.paragraph,
        placeholder='What drives your character? Current goals, fears, desires...',
        max_length=800,
        required=False
    )
    
    notes = ui.TextInput(
        label='Additional Notes (Optional)',
        style=discord.TextStyle.paragraph,
        placeholder='Any other important details, quirks, or reminders...',
        max_length=800,
        required=False
    )
    
    dndbeyond_url = ui.TextInput(
        label='D&D Beyond Profile URL (Optional)',
        placeholder='Link to your D&D Beyond character sheet',
        max_length=500,
        required=False
    )
    
    personality = ui.TextInput(
        label='Personality Traits (Optional)',
        style=discord.TextStyle.paragraph,
        placeholder='Key personality traits, mannerisms, speech patterns...',
        max_length=1000,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Complete character creation with all collected data"""
        try:
            # Add final data
            self.character_data.update({
                'backstory': str(self.backstory.value).strip() if self.backstory.value else None,
                'goals': str(self.goals.value).strip() if self.goals.value else None,
                'notes': str(self.notes.value).strip() if self.notes.value else None,
                'dndbeyond_url': str(self.dndbeyond_url.value).strip() if self.dndbeyond_url.value else None,
                'personality': str(self.personality.value).strip() if self.personality.value else None
            })
            
            # Create the character alias with all collected data
            avatar_url = self.character_data.get('avatar_url') or "https://cdn.discordapp.com/embed/avatars/0.png"
            
            alias = self.alias_manager.create_alias(
                user_id=self.character_data['user_id'],
                guild_id=self.character_data['guild_id'],
                name=self.character_data['name'],
                trigger=self.character_data['trigger'],
                avatar_url=avatar_url,
                group_name=self.character_data.get('group_name'),
                character_class=self.character_data.get('class_level'),
                race=self.character_data.get('race'),
                pronouns=self.character_data.get('pronouns'),
                age=self.character_data.get('age'),
                alignment=self.character_data.get('alignment'),
                description=self.character_data.get('description'),
                personality=self.character_data.get('personality'),
                backstory=self.character_data.get('backstory'),
                goals=self.character_data.get('goals'),
                notes=self.character_data.get('notes'),
                dndbeyond_url=self.character_data.get('dndbeyond_url')
            )
            
            # Store additional character data (would need database schema extension)
            # For now, we'll create a detailed embed showing all the info
            
            embed = discord.Embed(
                title=f"✅ Character Created: {alias.name}",
                color=discord.Color.green(),
                description="Your character has been successfully registered!"
            )
            
            # Basic info
            embed.add_field(name="🎯 Trigger", value=f"`{alias.trigger}`", inline=True)
            if self.character_data.get('class_level'):
                embed.add_field(name="⚔️ Class", value=self.character_data['class_level'], inline=True)
            if self.character_data.get('race'):
                embed.add_field(name="🧬 Race", value=self.character_data['race'], inline=True)
            if self.character_data.get('pronouns'):
                embed.add_field(name="🗣️ Pronouns", value=self.character_data['pronouns'], inline=True)
            if self.character_data.get('group_name'):
                embed.add_field(name="📁 Group", value=self.character_data['group_name'], inline=True)
            
            # Additional character info section
            details = []
            if self.character_data.get('age'):
                details.append(f"Age: {self.character_data['age']}")
            if self.character_data.get('alignment'):
                details.append(f"Alignment: {self.character_data['alignment']}")
            if details:
                embed.add_field(name="📊 Details", value=" • ".join(details), inline=False)
            
            # Detailed info
            if self.character_data.get('description'):
                embed.add_field(
                    name="👤 Appearance", 
                    value=self.character_data['description'][:1000], 
                    inline=False
                )
            
            if self.character_data.get('personality'):
                embed.add_field(
                    name="🎭 Personality", 
                    value=self.character_data['personality'][:1000], 
                    inline=False
                )
            
            if self.character_data.get('backstory'):
                embed.add_field(
                    name="📖 Backstory", 
                    value=self.character_data['backstory'][:1000], 
                    inline=False
                )
            
            if self.character_data.get('goals'):
                embed.add_field(
                    name="🎯 Goals", 
                    value=self.character_data['goals'][:1000], 
                    inline=False
                )
            
            if self.character_data.get('notes'):
                embed.add_field(
                    name="📝 Notes", 
                    value=self.character_data['notes'][:1000], 
                    inline=False
                )
            
            # D&D Beyond link
            if self.character_data.get('dndbeyond_url'):
                embed.add_field(
                    name="🌐 D&D Beyond", 
                    value=f"[View Character Sheet]({self.character_data['dndbeyond_url']})", 
                    inline=False
                )
            
            # Usage example
            def get_usage_example(trigger: str) -> str:
                if trigger.startswith('[') and trigger.endswith(']'):
                    return f"Type `[Hello everyone!]` to post as {alias.name}"
                elif trigger.startswith('(') and trigger.endswith(')'):
                    return f"Type `(Hello everyone!)` to post as {alias.name}"
                elif trigger.endswith(':'):
                    return f"Type `{trigger}Hello everyone!` to post as {alias.name}"
                else:
                    return f"Type `{trigger} Hello everyone!` to post as {alias.name}"
            
            embed.add_field(
                name="💡 How to Use", 
                value=get_usage_example(alias.trigger), 
                inline=False
            )
            
            if avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png":
                embed.set_thumbnail(url=avatar_url)
            
            embed.set_footer(text="Use '/alias edit' to modify your character anytime!")
            
            # If no avatar was provided, offer upload option
            if not self.character_data.get('avatar_url'):
                from bot.alias_commands import AliasUploadView
                view = AliasUploadView(self.alias_manager, alias.name, interaction.client)
                embed.add_field(name="💡 Add Avatar", value="Upload a custom avatar using the button below!", inline=False)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error completing character creation: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating your character. Please try again.", 
                ephemeral=True
            )

# Edit Modal Classes for /alias edit command

class CharacterEditBasicModal(ui.Modal, title='Edit Character - Basic Info'):
    """First edit modal: Basic character information"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__()
        self.alias_manager = alias_manager
        self.character_data = character_data
        
        # Pre-fill fields with existing data
        self.character_name.default = character_data.get('name', '')
        self.trigger_pattern.default = character_data.get('trigger', '')
        self.character_class.default = character_data.get('class_level', '') or ''
        self.race.default = character_data.get('race', '') or ''
        self.group_name.default = character_data.get('group_name', '') or ''
    
    character_name = ui.TextInput(
        label='Character Name',
        placeholder='Enter your character\'s name (e.g., Kael Brightblade)',
        max_length=80,
        required=True
    )
    
    trigger_pattern = ui.TextInput(
        label='Trigger Pattern', 
        placeholder='e.g., k: or [text] or (text) or kael:',
        max_length=100,
        required=True
    )
    
    character_class = ui.TextInput(
        label='Class & Level (Optional)',
        placeholder='e.g., Fighter 5, Wizard 3/Cleric 2, Rogue',
        max_length=50,
        required=False
    )
    
    race = ui.TextInput(
        label='Race (Optional)',
        placeholder='e.g., Human, Elf, Dwarf, Half-Orc',
        max_length=50,
        required=False
    )
    
    group_name = ui.TextInput(
        label='Group/Campaign (Optional)',
        placeholder='e.g., Curse of Strahd, Main Campaign, NPCs',
        max_length=100,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Store basic info and continue to appearance editing"""
        try:
            # Update character data
            self.character_data.update({
                'name': str(self.character_name.value),
                'trigger': str(self.trigger_pattern.value),
                'class_level': str(self.character_class.value).strip() if self.character_class.value else None,
                'race': str(self.race.value).strip() if self.race.value else None,
                'group_name': str(self.group_name.value).strip() if self.group_name.value else None
            })
            
            # Import view classes
            from bot.edit_modals import ContinueToEditAppearanceView
            view = ContinueToEditAppearanceView(self.alias_manager, self.character_data)
            
            embed = discord.Embed(
                title="✅ Basic Info Updated",
                color=discord.Color.blue(),
                description=f"Character **{self.character_data['name']}** basic info updated!"
            )
            embed.add_field(name="Next Step", value="Click the button below to continue editing appearance details.", inline=False)
            embed.add_field(name="Character Name", value=self.character_data['name'], inline=True)
            embed.add_field(name="Trigger", value=f"`{self.character_data['trigger']}`", inline=True)
            if self.character_data.get('class_level'):
                embed.add_field(name="Class", value=self.character_data['class_level'], inline=True)
            if self.character_data.get('race'):
                embed.add_field(name="Race", value=self.character_data['race'], inline=True)
            if self.character_data.get('group_name'):
                embed.add_field(name="Group", value=self.character_data['group_name'], inline=True)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in edit basic character modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.", ephemeral=True
            )