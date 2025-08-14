"""
Edit modal classes for comprehensive character editing
"""

import discord
from discord import ui
from typing import Dict, Any
import logging
from bot.alias_manager import AliasManager

logger = logging.getLogger(__name__)

# View classes for edit flow
class ContinueToEditAppearanceView(ui.View):
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.alias_manager = alias_manager
        self.character_data = character_data

    @ui.button(label='Continue to Appearance', style=discord.ButtonStyle.primary, emoji='👤')
    async def continue_to_appearance(self, interaction: discord.Interaction, button: ui.Button):
        appearance_modal = CharacterEditAppearanceModal(self.alias_manager, self.character_data)
        await interaction.response.send_modal(appearance_modal)
    
    @ui.button(label='Skip Appearance', style=discord.ButtonStyle.secondary, emoji='⏭️')
    async def skip_appearance(self, interaction: discord.Interaction, button: ui.Button):
        """Skip appearance and show next step options"""
        view = ContinueToEditBackstoryView(self.alias_manager, self.character_data)
        
        embed = discord.Embed(
            title="⏭️ Skipped Appearance Editing",
            color=discord.Color.blue(),
            description=f"Character **{self.character_data['name']}** appearance editing skipped."
        )
        embed.add_field(name="Next Step", value="Choose whether to edit background details or save your changes.", inline=False)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ContinueToEditBackstoryView(ui.View):
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.alias_manager = alias_manager
        self.character_data = character_data

    @ui.button(label='Continue to Background', style=discord.ButtonStyle.primary, emoji='📖')
    async def continue_to_backstory(self, interaction: discord.Interaction, button: ui.Button):
        backstory_modal = CharacterEditBackstoryModal(self.alias_manager, self.character_data)
        await interaction.response.send_modal(backstory_modal)
    
    @ui.button(label='Skip Background', style=discord.ButtonStyle.success, emoji='✅')
    async def save_changes(self, interaction: discord.Interaction, button: ui.Button):
        """Skip background editing and save current changes"""
        try:
            # Update the existing alias with current data (skipping background info)
            # Ensure avatar_url is never None
            avatar_url = self.character_data.get('avatar_url') or "https://cdn.discordapp.com/embed/avatars/0.png"
            updated_alias = self.alias_manager.update_alias(
                user_id=self.character_data['user_id'],
                guild_id=self.character_data['guild_id'],
                name=self.character_data['original_name'],  # Use original name to find alias
                new_name=self.character_data['name'],
                new_trigger=self.character_data['trigger'],
                new_avatar=avatar_url,
                new_group=self.character_data.get('group_name'),
                character_class=self.character_data.get('class_level'),
                race=self.character_data.get('race'),
                pronouns=self.character_data.get('pronouns'),
                age=self.character_data.get('age'),
                alignment=self.character_data.get('alignment'),
                description=self.character_data.get('description'),
                personality=self.character_data.get('personality')
            )
            
            embed = discord.Embed(
                title=f"✅ Character Updated: {updated_alias.name}",
                color=discord.Color.green(),
                description="Your character has been successfully updated!"
            )
            embed.add_field(name="🎯 Trigger", value=f"`{updated_alias.trigger}`", inline=True)
            embed.set_footer(text="Use '/alias edit' to modify more details anytime!")
            
            # If no custom avatar, show upload option
            if not self.character_data.get('avatar_url'):
                from bot.alias_commands import AliasUploadView
                view = AliasUploadView(self.alias_manager, updated_alias.name, interaction.client)
                embed.add_field(name="💡 Add Avatar", value="Upload a custom avatar using the button below!", inline=False)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                embed.set_thumbnail(url=updated_alias.avatar_url)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error saving character edits: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your character. Please try again.", ephemeral=True
            )

class CharacterEditAppearanceModal(ui.Modal, title='Edit Character - Appearance'):
    """Second edit modal: Character appearance"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__()
        self.alias_manager = alias_manager
        self.character_data = character_data
        
        # Pre-fill fields with existing data
        self.avatar_url.default = character_data.get('avatar_url', '') or ''
        self.description.default = character_data.get('description', '') or ''
        self.pronouns.default = character_data.get('pronouns', '') or ''
        self.age.default = character_data.get('age', '') or ''
        self.alignment.default = character_data.get('alignment', '') or ''
    
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
        """Store appearance info and proceed to backstory editing"""
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
            view = ContinueToEditBackstoryView(self.alias_manager, self.character_data)
            
            embed = discord.Embed(
                title="✅ Appearance Details Updated",
                color=discord.Color.blue(),
                description=f"Character **{self.character_data['name']}** appearance updated!"
            )
            embed.add_field(name="Final Step", value="Click the button below to edit backstory and save changes.", inline=False)
            
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
            logger.error(f"Error in edit appearance character modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.", ephemeral=True
            )

class CharacterEditBackstoryModal(ui.Modal, title='Edit Character - Background'):
    """Third edit modal: Character backstory and final save"""
    
    def __init__(self, alias_manager: AliasManager, character_data: Dict[str, Any]):
        super().__init__()
        self.alias_manager = alias_manager
        self.character_data = character_data
        
        # Pre-fill fields with existing data
        self.backstory.default = character_data.get('backstory', '') or ''
        self.goals.default = character_data.get('goals', '') or ''
        self.notes.default = character_data.get('notes', '') or ''
        self.dndbeyond_url.default = character_data.get('dndbeyond_url', '') or ''
        self.personality.default = character_data.get('personality', '') or ''
    
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
        """Complete character editing with all collected data"""
        try:
            # Add final data
            self.character_data.update({
                'backstory': str(self.backstory.value).strip() if self.backstory.value else None,
                'goals': str(self.goals.value).strip() if self.goals.value else None,
                'notes': str(self.notes.value).strip() if self.notes.value else None,
                'dndbeyond_url': str(self.dndbeyond_url.value).strip() if self.dndbeyond_url.value else None,
                'personality': str(self.personality.value).strip() if self.personality.value else None
            })
            
            # Update the existing alias
            updated_alias = self.alias_manager.update_alias(
                user_id=self.character_data['user_id'],
                guild_id=self.character_data['guild_id'],
                name=self.character_data['original_name'],  # Use original name to find alias
                new_name=self.character_data['name'],
                new_trigger=self.character_data['trigger'],
                new_avatar=self.character_data.get('avatar_url'),
                new_group=self.character_data.get('group_name'),
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
            
            # Create comprehensive preview embed
            embed = discord.Embed(
                title=f"✅ Character Updated: {updated_alias.name}",
                color=discord.Color.green(),
                description="Your character has been successfully updated with all details!"
            )
            
            # Basic info
            embed.add_field(name="🎯 Trigger", value=f"`{updated_alias.trigger}`", inline=True)
            if self.character_data.get('class_level'):
                embed.add_field(name="⚔️ Class", value=self.character_data['class_level'], inline=True)
            if self.character_data.get('race'):
                embed.add_field(name="🧬 Race", value=self.character_data['race'], inline=True)
            
            # Additional details
            if self.character_data.get('pronouns'):
                embed.add_field(name="🗣️ Pronouns", value=self.character_data['pronouns'], inline=True)
            if self.character_data.get('age'):
                embed.add_field(name="📅 Age", value=self.character_data['age'], inline=True)
            if self.character_data.get('alignment'):
                embed.add_field(name="⚖️ Alignment", value=self.character_data['alignment'], inline=True)
            
            # D&D Beyond link
            if self.character_data.get('dndbeyond_url'):
                embed.add_field(
                    name="🌐 D&D Beyond", 
                    value=f"[View Character Sheet]({self.character_data['dndbeyond_url']})", 
                    inline=False
                )
            
            embed.set_footer(text="Your character is ready for roleplay! Right-click character messages to view the full profile.")
            
            # Check if we already have a custom avatar or just default
            has_custom_avatar = (self.character_data.get('avatar_url') and 
                               self.character_data.get('avatar_url') != "https://cdn.discordapp.com/embed/avatars/0.png")
            
            # If no custom avatar was provided, show upload option  
            if not has_custom_avatar:
                from bot.alias_commands import AliasUploadView
                view = AliasUploadView(self.alias_manager, updated_alias.name, interaction.client)
                embed.add_field(name="💡 Add Avatar", value="Upload a custom avatar using the button below!", inline=False)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
            
            # Set avatar if available
            if updated_alias.avatar_url and updated_alias.avatar_url != "https://cdn.discordapp.com/embed/avatars/0.png":
                embed.set_thumbnail(url=updated_alias.avatar_url)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in edit backstory character modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your character. Please try again.", ephemeral=True
            )