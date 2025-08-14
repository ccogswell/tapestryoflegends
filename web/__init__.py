"""
Web interface package for Discord D&D Bot
Provides OAuth authentication and alias management
"""

from .routes import web_bp
from .auth import DiscordAuth

__all__ = ['web_bp', 'DiscordAuth']