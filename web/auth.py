"""
Discord OAuth authentication for web interface
"""
import os
import requests
from functools import wraps
from flask import session, request, redirect, url_for, jsonify
from authlib.integrations.flask_client import OAuth


class DiscordAuth:
    def __init__(self, app):
        self.app = app
        self.oauth = OAuth(app)
        
        # Discord OAuth configuration
        self.discord = self.oauth.register(
            name='discord',
            client_id=os.getenv('DISCORD_CLIENT_ID'),
            client_secret=os.getenv('DISCORD_CLIENT_SECRET'),
            access_token_url='https://discord.com/api/oauth2/token',
            authorize_url='https://discord.com/api/oauth2/authorize',
            api_base_url='https://discord.com/api/',
            client_kwargs={
                'scope': 'identify guilds'
            }
        )
    
    def login_required(self, f):
        """Decorator to require login for routes"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'discord_user' not in session:
                return redirect(url_for('web.login'))
            return f(*args, **kwargs)
        return decorated_function
    
    def admin_required(self, f):
        """Decorator to require admin permissions"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'discord_user' not in session:
                return redirect(url_for('web.login'))
            
            user_data = session['discord_user']
            if not self.is_admin(user_data['id']):
                return jsonify({'error': 'Admin access required'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    
    def mod_required(self, f):
        """Decorator to require moderator permissions"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'discord_user' not in session:
                return redirect(url_for('web.login'))
            
            user_data = session['discord_user']
            if not self.is_moderator(user_data['id']):
                return jsonify({'error': 'Moderator access required'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user has admin permissions"""
        # TODO: Implement proper admin check against Discord server roles
        # For now, check against environment variable list of admin IDs
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        return str(user_id) in admin_ids
    
    def is_moderator(self, user_id: int) -> bool:
        """Check if user has moderator permissions"""
        # Admin users are also moderators
        if self.is_admin(user_id):
            return True
        
        # TODO: Implement proper mod check against Discord server roles
        mod_ids = os.getenv('MOD_USER_IDS', '').split(',')
        return str(user_id) in mod_ids
    
    def get_user_permissions(self, user_id: int) -> dict:
        """Get user permission levels"""
        return {
            'admin': self.is_admin(user_id),
            'moderator': self.is_moderator(user_id),
            'user': True
        }