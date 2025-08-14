import discord
from bot.modals import SessionSetupModal

class SessionTypeSelectionView(discord.ui.View):
    """View for selecting session type before showing the setup modal"""
    
    def __init__(self, session_manager, reward_calculator, session_id: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.session_manager = session_manager
        self.reward_calculator = reward_calculator
        self.session_id = session_id
    
    @discord.ui.button(label='Combat', style=discord.ButtonStyle.danger, emoji='⚔️')
    async def combat_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start a combat-focused session"""
        modal = SessionSetupModal(self.session_manager, self.reward_calculator, self.session_id, "Combat")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label='Social', style=discord.ButtonStyle.success, emoji='💬')
    async def social_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start a social/roleplay session"""
        modal = SessionSetupModal(self.session_manager, self.reward_calculator, self.session_id, "Social")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label='Mixed', style=discord.ButtonStyle.primary, emoji='🎭')
    async def mixed_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start a mixed session"""
        modal = SessionSetupModal(self.session_manager, self.reward_calculator, self.session_id, "Mixed")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label='Other', style=discord.ButtonStyle.secondary, emoji='🎲')
    async def other_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start a custom session type"""
        modal = SessionSetupModal(self.session_manager, self.reward_calculator, self.session_id, "Other")
        await interaction.response.send_modal(modal)


class SessionSetupView(discord.ui.View):
    """Session setup and control view for managing sessions"""
    
    def __init__(self, session_id: str, dm_id: int):
        super().__init__(timeout=None)
        self.session_id = session_id
        self.dm_id = dm_id
    
    @classmethod
    def create_session_control_view(cls, session_id: str, dm_id: int):
        """Create a session control view"""
        return cls(session_id, dm_id)
    
    async def on_timeout(self):
        """Called when the view times out"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True