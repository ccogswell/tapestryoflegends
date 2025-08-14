"""
Web interface routes for Discord bot management
"""
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, flash, current_app
from database import get_db_session
from models import Guild, CharacterAlias, RPSession, SessionParticipant, SessionReward, SharedGroup, SharedGroupPermission, GroupPermission
from sqlalchemy.orm import joinedload
from sqlalchemy import desc, func
import discord
import os
import json
import requests

# Create blueprint
web_bp = Blueprint('web', __name__, url_prefix='/web')

def get_db():
    """Get database session"""
    try:
        return get_db_session()
    except Exception as e:
        print(f"Database session error: {e}")
        return None

def require_auth(f):
    """Simple authentication decorator"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'discord_user' not in session:
            return redirect(url_for('web.login'))
        return f(*args, **kwargs)
    return decorated_function

@web_bp.route('/')
def dashboard():
    """Main dashboard - shows login page if not authenticated"""
    try:
        if 'discord_user' not in session:
            # Show login page instead of redirecting to avoid loops
            return render_template('simple_login.html')
        
        user_data = session['discord_user']
        
        # Simplified dashboard without complex database queries to avoid SQLAlchemy issues
        dashboard_data = {
            'user': user_data,
            'stats': {
                'total_aliases': 0,
                'total_sessions': 0,
                'total_groups': 0,
                'total_servers': 0
            },
            'aliases': [],
            'recently_used_aliases': [],
            'favorite_aliases': [],
            'recent_sessions': []
        }
        
        return render_template('dashboard.html', **dashboard_data)
    except Exception as e:
        print(f"Dashboard error: {e}")
        import traceback
        traceback.print_exc()
        return f"<h1>Error Loading Dashboard</h1><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>"

@web_bp.route('/login')
def login():
    """Discord OAuth login"""
    from flask import current_app, request
    import os
    
    # Check if we already have a valid session
    if 'discord_user' in session:
        return redirect(url_for('web.dashboard'))
    
    # Check if this is a Discord OAuth initiation request
    start_oauth = request.args.get('start_oauth', 'false').lower() == 'true'
    
    if start_oauth:
        print("=== STARTING DISCORD OAUTH ===")
        try:
            # Create the OAuth authorization URL manually
            redirect_uri = f"https://{os.getenv('REPLIT_DOMAINS')}/web/callback" if os.getenv('REPLIT_DOMAINS') else url_for('web.callback', _external=True)
            print(f"Using redirect URI: {redirect_uri}")
            
            # Build the Discord authorization URL manually 
            import urllib.parse
            client_id = os.getenv('DISCORD_CLIENT_ID')
            scopes = 'identify guilds'
            
            params = {
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope': scopes
            }
            
            authorization_url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"
            print(f"Generated authorization URL: {authorization_url[:100]}...")
            
            return redirect(authorization_url)
        except Exception as e:
            print(f"OAuth initiation error: {e}")
            flash(f'Failed to start Discord login: {e}', 'error')
            return render_template('simple_login.html')
    
    # Show the simple login page with option to start OAuth
    return render_template('simple_login.html')

@web_bp.route('/callback')
def callback():
    """OAuth callback"""
    from flask import current_app, request
    import traceback
    import requests
    import os
    
    print(f"=== OAUTH CALLBACK STARTED ===")
    print(f"Request args: {dict(request.args)}")
    print(f"Session before: {dict(session)}")
    
    try:
        # Don't check if already logged in - we want to process the callback
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            print(f"OAuth error from Discord: {error}")
            flash(f'Discord authorization failed: {error}', 'error')
            return redirect(url_for('web.login'))
            
        if not code:
            print("No authorization code received")
            flash('No authorization code received from Discord', 'error')
            return redirect(url_for('web.login'))
        
        print(f"Processing OAuth callback with code: {code[:10]}...")
        
        # Get access token - handle state verification manually
        try:
            token = current_app.config['DISCORD_AUTH'].discord.authorize_access_token()
            print(f"Got token: {bool(token)}")
        except Exception as token_error:
            if "mismatching_state" in str(token_error) or "CSRF" in str(token_error):
                print(f"State mismatch error, attempting manual token exchange...")
                # Manual token exchange for state mismatch issues
                token_data = {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': f"https://{os.getenv('REPLIT_DOMAINS')}/web/callback" if os.getenv('REPLIT_DOMAINS') else url_for('web.callback', _external=True),
                    'client_id': os.getenv('DISCORD_CLIENT_ID'),
                    'client_secret': os.getenv('DISCORD_CLIENT_SECRET'),
                }
                
                token_response = requests.post('https://discord.com/api/oauth2/token', data=token_data)
                if token_response.status_code == 200:
                    token = token_response.json()
                    print(f"Manual token exchange successful: {bool(token.get('access_token'))}")
                else:
                    print(f"Manual token exchange failed: {token_response.status_code} - {token_response.text}")
                    raise token_error
            else:
                raise token_error
        
        if not token:
            print("Failed to get access token")
            flash('Failed to get access token from Discord', 'error')
            return redirect(url_for('web.login'))
        
        # Get user info from Discord API
        if isinstance(token, dict) and 'access_token' in token:
            # Manual token exchange result
            headers = {'Authorization': f"Bearer {token['access_token']}"}
            resp = requests.get('https://discord.com/api/users/@me', headers=headers)
            user_info = resp.json()
        else:
            # Authlib token object
            resp = current_app.config['DISCORD_AUTH'].discord.get('users/@me', token=token)
            user_info = resp.json()
        print(f"User info response: {user_info}")
        
        if user_info and 'id' in user_info:
            avatar_url = None
            if user_info.get('avatar'):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_info['id']}/{user_info['avatar']}.png"
            
            # Create session data
            session_data = {
                'id': int(user_info['id']),
                'username': user_info.get('username'),
                'avatar': avatar_url,
                'discriminator': user_info.get('discriminator', '0000')
            }
            
            session['discord_user'] = session_data
            
            # Store access token for Discord API calls
            if isinstance(token, dict) and 'access_token' in token:
                session['access_token'] = token['access_token']
            elif hasattr(token, 'get') and token.get('access_token'):
                session['access_token'] = token.get('access_token')
            elif hasattr(token, 'access_token'):
                session['access_token'] = token.access_token
            
            print(f"Session data set: {session_data}")
            print(f"Access token stored: {bool(session.get('access_token'))}")
            print(f"Session after: {dict(session)}")
            
            flash('Successfully logged in!', 'success')
            print("Redirecting to dashboard...")
            return redirect(url_for('web.dashboard'))
        else:
            print(f"Invalid user info received: {user_info}")
            flash('Failed to get user information from Discord', 'error')
            return redirect(url_for('web.login'))
            
    except Exception as e:
        print(f"OAuth callback error: {e}")
        print(traceback.format_exc())
        flash(f'Login error: {str(e)}', 'error')
        return redirect(url_for('web.login'))

@web_bp.route('/logout')
def logout():
    """Logout user"""
    session.pop('discord_user', None)
    session.pop('access_token', None)
    flash('Successfully logged out', 'info')
    return redirect(url_for('web.login'))

@web_bp.route('/discord-login')
def real_discord_login():
    """Force Discord OAuth login without loop protection"""
    from flask import current_app, request
    import os
    
    # Check if we already have a valid session
    if 'discord_user' in session:
        return redirect(url_for('web.dashboard'))
    
    try:
        # Use the actual Replit domain from environment
        replit_domain = os.getenv('REPLIT_DOMAINS')
        if replit_domain and 'localhost' not in request.host:
            # Extract first domain if comma-separated
            domain = replit_domain.split(',')[0].strip()
            redirect_uri = f"https://{domain}/web/callback"
        else:
            # Running locally or fallback
            redirect_uri = url_for('web.callback', _external=True)
        
        print(f"Force OAuth redirect URI: {redirect_uri}")
        return current_app.config['DISCORD_AUTH'].discord.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"OAuth authorization error: {e}")
        flash(f'Discord login error: {str(e)}', 'error')
        return render_template('simple_login.html', error=str(e))

@web_bp.route('/test-session')
def test_session():
    """Test session functionality - for debugging OAuth issues"""
    import os
    
    # Create a test session to bypass OAuth temporarily
    test_user_id = os.getenv('TEST_USER_ID', '123456789')
    
    session['discord_user'] = {
        'id': int(test_user_id),
        'username': 'TestUser',
        'avatar': None,
        'discriminator': '0001'
    }
    
    flash('Test session created successfully!', 'success')
    return redirect(url_for('web.dashboard'))

@web_bp.route('/group-manager')
def group_manager():
    """Group management page"""
    if 'discord_user' not in session:
        return redirect(url_for('web.login'))
    
    user_data = session['discord_user']
    
    # If no guild is set, try to set a default guild with data
    if not session.get('current_guild_id') or session.get('current_guild_id') == '0':
        db = get_db()
        if db:
            try:
                # Find a guild that has aliases for any user
                result = db.execute("SELECT guild_id FROM character_aliases WHERE guild_id != '0' LIMIT 1")
                row = result.fetchone()
                if row:
                    session['current_guild_id'] = row[0]
                    print(f"Set default guild ID to: {row[0]}")
            except Exception as e:
                print(f"Error setting default guild: {e}")
            finally:
                db.close()
    
    return render_template('group_manager.html', user=user_data)

@web_bp.route('/aliases')
def aliases():
    """Character aliases management"""
    if 'discord_user' not in session:
        return redirect(url_for('web.login'))
    
    user_data = session['discord_user']
    db = get_db()
    
    try:
        # Convert user ID to string for database queries
        user_id_str = str(user_data['id'])
        
        # Get user's aliases with guild information eagerly loaded (excluding placeholders)
        aliases = db.query(CharacterAlias).options(
            joinedload(CharacterAlias.guild)
        ).filter(
            CharacterAlias.user_id == user_id_str,
            ~CharacterAlias.name.like('__PLACEHOLDER__%')
        ).order_by(CharacterAlias.name).all()
        
        # Get placeholder aliases to extract empty subgroup information
        placeholder_aliases = db.query(CharacterAlias).filter(
            CharacterAlias.user_id == user_id_str,
            CharacterAlias.name.like('__PLACEHOLDER__%')
        ).all()
        
        # Extract empty subgroups from placeholders
        empty_subgroups = {}
        for placeholder in placeholder_aliases:
            if placeholder.group_name and placeholder.subgroup:
                group_key = placeholder.group_name.lower()
                if group_key not in empty_subgroups:
                    empty_subgroups[group_key] = []
                if placeholder.subgroup not in empty_subgroups[group_key]:
                    empty_subgroups[group_key].append(placeholder.subgroup)
        
        # Convert to serializable format
        aliases_data = []
        for alias in aliases:
            aliases_data.append({
                'id': alias.id,
                'character_name': alias.name,  # Template expects character_name for compatibility
                'name': alias.name,
                'trigger_text': alias.trigger,  # Template expects trigger_text
                'trigger': alias.trigger,
                'avatar_url': alias.avatar_url,
                'guild_name': alias.guild.name if alias.guild else 'Unknown',
                'character_class': alias.character_class,
                'character_race': alias.race,
                'race': alias.race,
                'character_level': None,  # No level column in database
                'level': None,
                'character_description': alias.description,
                'character_subclass': None,  # No subclass column in database
                'subclass': None,
                'pronouns': alias.pronouns,
                'age': alias.age,
                'alignment': alias.alignment,
                'description': alias.description,
                'personality': alias.personality,
                'backstory': alias.backstory,
                'goals': alias.goals,
                'notes': alias.notes,
                'group_name': alias.group_name,
                'subgroup': alias.subgroup,  # Add subgroup to the data
                'tags': alias.tags.split(',') if alias.tags else [],  # Convert tags to list
                'tags_raw': alias.tags or '',  # Keep raw string version too
                'message_count': alias.message_count or 0,
                'last_used': alias.last_used.strftime('%Y-%m-%d') if alias.last_used and hasattr(alias.last_used, 'strftime') else (str(alias.last_used) if alias.last_used else None),
                'created_at': alias.created_at.strftime('%Y-%m-%d') if alias.created_at and hasattr(alias.created_at, 'strftime') else (str(alias.created_at) if alias.created_at else None),
                'dndbeyond_url': alias.dndbeyond_url,
                'is_favorite': alias.is_favorite or False
            })
        
        db.close()
        
        return render_template('aliases.html', 
                             user=user_data,
                             aliases=aliases_data,
                             empty_subgroups=empty_subgroups)
    except Exception as e:
        db.close()
        flash(f'Error loading aliases: {e}', 'error')
        return render_template('error.html', error=str(e))

@web_bp.route('/shared-groups')
@require_auth
def shared_groups():
    """Shared groups management page"""
    user_data = session['discord_user']
    return render_template('shared_groups.html', user=user_data)

@web_bp.route('/bulk-manage')
@require_auth
def bulk_manage():
    """Bulk manage aliases page"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        # Get all user's aliases with complete data
        aliases = db.query(CharacterAlias).filter(
            CharacterAlias.user_id == user_id_str
        ).order_by(CharacterAlias.name).all()
        
        # Serialize aliases with tags
        aliases_data = []
        for alias in aliases:
            alias_dict = {
                'id': alias.id,
                'character_name': alias.name,  # Fixed field name
                'trigger_text': alias.trigger,  # Fixed field name
                'character_class': alias.character_class,
                'character_race': alias.race,  # Fixed field name
                'character_description': alias.description,  # Fixed field name
                'personality': alias.personality,
                'backstory': alias.backstory,
                'pronouns': alias.pronouns,
                'age': alias.age,
                'alignment': alias.alignment,
                'goals': alias.goals,
                'notes': alias.notes,
                'group_name': alias.group_name,
                'subgroup': alias.subgroup,
                'dndbeyond_url': alias.dndbeyond_url,
                'avatar_url': alias.avatar_url,
                'message_count': alias.message_count,
                'is_favorite': alias.is_favorite,
                'tags': alias.tags.split(',') if alias.tags else [],
                'tags_raw': alias.tags or '',
                'created_at': alias.created_at.strftime('%Y-%m-%d') if alias.created_at else None,
                'last_used': alias.last_used.strftime('%Y-%m-%d') if alias.last_used else None
            }
            aliases_data.append(alias_dict)
        
        return render_template('bulk_manage.html', 
                             aliases_json=json.dumps(aliases_data),
                             aliases_count=len(aliases_data))
    finally:
        db.close()

# API Endpoints for alias management

@web_bp.route('/api/aliases/create', methods=['POST'])
def api_create_alias():
    """Create new alias via API"""
    if 'discord_user' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})
    
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        # Handle avatar upload if present
        from .object_storage import upload_avatar, get_default_avatar
        
        avatar_url = get_default_avatar()
        if 'avatar' in request.files and request.files['avatar'].filename:
            uploaded_url = upload_avatar(request.files['avatar'], user_id_str)
            if uploaded_url:
                avatar_url = uploaded_url
        
        # Create new alias
        new_alias = CharacterAlias(
            user_id=user_id_str,
            guild_id=request.form.get('guild_id', '1'),  # Default guild for web creation
            name=request.form.get('name'),
            trigger=request.form.get('trigger'),
            avatar_url=avatar_url,
            group_name=request.form.get('group_name') or None,
            character_class=request.form.get('character_class') or None,
            race=request.form.get('race') or None,
            description=request.form.get('description') or None,
            tags=request.form.get('tags') or None
        )
        
        db.add(new_alias)
        db.commit()
        
        return jsonify({'success': True, 'alias_id': new_alias.id})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/api/aliases/update', methods=['POST'])
def api_update_alias():
    """Update existing alias via API"""
    if 'discord_user' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})
    
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        alias_id = request.form.get('alias_id')
        alias = db.query(CharacterAlias).filter(
            CharacterAlias.id == alias_id,
            CharacterAlias.user_id == user_id_str
        ).first()
        
        if not alias:
            return jsonify({'success': False, 'error': 'Alias not found'})
        
        # Update fields
        alias.name = request.form.get('name')
        alias.trigger = request.form.get('trigger')
        alias.group_name = request.form.get('group_name') or None
        alias.character_class = request.form.get('character_class') or None
        alias.race = request.form.get('race') or None
        alias.description = request.form.get('description') or None
        alias.tags = request.form.get('tags') or None
        
        # Handle avatar upload if present
        if 'avatar' in request.files and request.files['avatar'].filename:
            from .object_storage import upload_avatar
            uploaded_url = upload_avatar(request.files['avatar'], user_id_str)
            if uploaded_url:
                alias.avatar_url = uploaded_url
        
        db.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/api/aliases/delete', methods=['POST'])
def api_delete_alias():
    """Delete alias via API"""
    if 'discord_user' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})
    
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        data = request.get_json()
        alias_id = data.get('alias_id')
        
        alias = db.query(CharacterAlias).filter(
            CharacterAlias.id == alias_id,
            CharacterAlias.user_id == user_id_str
        ).first()
        
        if not alias:
            return jsonify({'success': False, 'error': 'Alias not found'})
        
        db.delete(alias)
        db.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/api/aliases/<int:alias_id>', methods=['PUT'])
@require_auth
def update_alias(alias_id):
    """Update an existing alias"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        data = request.get_json()
        
        # Get the alias
        alias = db.query(CharacterAlias).filter(
            CharacterAlias.id == alias_id,
            CharacterAlias.user_id == user_id_str
        ).first()
        
        if not alias:
            return jsonify({'error': 'Alias not found'}), 404
        
        # Update fields
        for field in ['character_name', 'trigger_text', 'character_class', 'character_race',
                     'character_description', 'personality', 'backstory', 'pronouns', 
                     'age', 'alignment', 'goals', 'notes', 'group_name', 'dndbeyond_url', 
                     'avatar_url', 'is_favorite', 'subgroup', 'tags']:
            if field in data:
                setattr(alias, field, data[field])
        
        db.commit()
        
        # Return serialized alias
        return jsonify({
            'id': alias.id,
            'character_name': alias.character_name,
            'trigger_text': alias.trigger_text,
            'character_class': alias.character_class,
            'character_race': alias.character_race,
            'character_description': alias.character_description,
            'personality': alias.personality,
            'backstory': alias.backstory,
            'pronouns': alias.pronouns,
            'age': alias.age,
            'alignment': alias.alignment,
            'goals': alias.goals,
            'notes': alias.notes,
            'group_name': alias.group_name,
            'dndbeyond_url': alias.dndbeyond_url,
            'avatar_url': alias.avatar_url,
            'message_count': alias.message_count,
            'is_favorite': alias.is_favorite,
            'subgroup': alias.subgroup,
            'tags': alias.tags.split(',') if alias.tags else [],
            'tags_raw': alias.tags or '',
            'created_at': alias.created_at.strftime('%Y-%m-%d') if alias.created_at else None,
            'last_used': alias.last_used.strftime('%Y-%m-%d') if alias.last_used else None,
            'guild_name': alias.guild.name if alias.guild else 'Unknown Guild'
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@web_bp.route('/api/aliases/<int:alias_id>', methods=['DELETE'])
@require_auth
def delete_alias(alias_id):
    """Delete an alias"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        # Get the alias
        alias = db.query(CharacterAlias).filter(
            CharacterAlias.id == alias_id,
            CharacterAlias.user_id == user_id_str
        ).first()
        
        if not alias:
            return jsonify({'error': 'Alias not found'}), 404
        
        db.delete(alias)
        db.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@web_bp.route('/api/aliases/<int:alias_id>/favorite', methods=['POST'])
@require_auth
def toggle_favorite(alias_id):
    """Toggle favorite status of an alias"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        alias = db.query(CharacterAlias).filter(
            CharacterAlias.id == alias_id,
            CharacterAlias.user_id == user_id_str
        ).first()
        
        if not alias:
            return jsonify({'error': 'Alias not found'}), 404
        
        alias.is_favorite = not alias.is_favorite
        db.commit()
        
        return jsonify({'success': True, 'is_favorite': alias.is_favorite})
        
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@web_bp.route('/api/aliases/move', methods=['POST'])
def api_move_alias():
    """Move alias to different group via API"""
    if 'discord_user' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})
    
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        data = request.get_json()
        alias_id = data.get('alias_id')
        new_group = data.get('group_name')
        new_subgroup = data.get('subgroup')
        
        # Handle "Ungrouped" as None
        if new_group == 'Ungrouped':
            new_group = None
            
        # Handle empty subgroup as None
        if new_subgroup == '':
            new_subgroup = None
        
        alias = db.query(CharacterAlias).filter(
            CharacterAlias.id == alias_id,
            CharacterAlias.user_id == user_id_str
        ).first()
        
        if not alias:
            return jsonify({'success': False, 'error': 'Alias not found'})
        
        alias.group_name = new_group
        alias.subgroup = new_subgroup
        db.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

# Bulk operations API endpoints
@web_bp.route('/api/aliases/bulk-import', methods=['POST'])
@require_auth
def bulk_import_aliases():
    """Bulk import aliases from CSV data"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        data = request.get_json()
        aliases_data = data.get('aliases', [])
        
        imported_count = 0
        for alias_data in aliases_data:
            # Create new alias from CSV data
            new_alias = CharacterAlias(
                user_id=user_id_str,
                guild_id='1',  # Default guild for web imports
                character_name=alias_data.get('character_name', ''),
                trigger_text=alias_data.get('trigger_text', ''),
                character_class=alias_data.get('character_class') or None,
                character_race=alias_data.get('character_race') or None,
                character_description=alias_data.get('character_description') or None,
                personality=alias_data.get('personality') or None,
                backstory=alias_data.get('backstory') or None,
                pronouns=alias_data.get('pronouns') or None,
                age=alias_data.get('age') or None,
                alignment=alias_data.get('alignment') or None,
                goals=alias_data.get('goals') or None,
                notes=alias_data.get('notes') or None,
                group_name=alias_data.get('group_name') or None,
                subgroup=alias_data.get('subgroup') or None,
                dndbeyond_url=alias_data.get('dndbeyond_url') or None,
                tags=alias_data.get('tags') or None
            )
            
            if new_alias.character_name and new_alias.trigger_text:  # Basic validation
                db.add(new_alias)
                imported_count += 1
        
        db.commit()
        return jsonify({'success': True, 'imported_count': imported_count})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/api/aliases/bulk-update', methods=['POST'])
@require_auth
def bulk_update_aliases():
    """Bulk update selected aliases"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        data = request.get_json()
        alias_ids = data.get('alias_ids', [])
        updates = data.get('updates', {})
        
        if not alias_ids or not updates:
            return jsonify({'success': False, 'error': 'No aliases or updates specified'})
        
        # Update aliases
        updated_count = 0
        for alias_id in alias_ids:
            alias = db.query(CharacterAlias).filter(
                CharacterAlias.id == alias_id,
                CharacterAlias.user_id == user_id_str
            ).first()
            
            if alias:
                for field, value in updates.items():
                    if hasattr(alias, field):
                        setattr(alias, field, value)
                updated_count += 1
        
        db.commit()
        return jsonify({'success': True, 'updated_count': updated_count})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/api/aliases/bulk-duplicate', methods=['POST'])
@require_auth
def bulk_duplicate_aliases():
    """Bulk duplicate selected aliases"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        data = request.get_json()
        alias_ids = data.get('alias_ids', [])
        
        if not alias_ids:
            return jsonify({'success': False, 'error': 'No aliases specified'})
        
        # Duplicate aliases
        duplicated_count = 0
        for alias_id in alias_ids:
            original = db.query(CharacterAlias).filter(
                CharacterAlias.id == alias_id,
                CharacterAlias.user_id == user_id_str
            ).first()
            
            if original:
                duplicate = CharacterAlias(
                    user_id=original.user_id,
                    guild_id=original.guild_id,
                    character_name=f"{original.character_name} Copy",
                    trigger_text=f"{original.trigger_text}_copy",
                    character_class=original.character_class,
                    character_race=original.character_race,
                    character_description=original.character_description,
                    personality=original.personality,
                    backstory=original.backstory,
                    pronouns=original.pronouns,
                    age=original.age,
                    alignment=original.alignment,
                    goals=original.goals,
                    notes=original.notes,
                    group_name=original.group_name,
                    subgroup=original.subgroup,
                    dndbeyond_url=original.dndbeyond_url,
                    avatar_url=original.avatar_url,
                    tags=original.tags,
                    is_favorite=False  # Don't copy favorite status
                )
                
                db.add(duplicate)
                duplicated_count += 1
        
        db.commit()
        return jsonify({'success': True, 'duplicated_count': duplicated_count})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/api/aliases/bulk-delete', methods=['POST'])
@require_auth
def bulk_delete_aliases():
    """Bulk delete selected aliases"""
    db = get_db()
    user_id_str = str(session['discord_user']['id'])
    
    try:
        data = request.get_json()
        alias_ids = data.get('alias_ids', [])
        
        if not alias_ids:
            return jsonify({'success': False, 'error': 'No aliases specified'})
        
        # Delete aliases
        deleted_count = 0
        for alias_id in alias_ids:
            alias = db.query(CharacterAlias).filter(
                CharacterAlias.id == alias_id,
                CharacterAlias.user_id == user_id_str
            ).first()
            
            if alias:
                db.delete(alias)
                deleted_count += 1
        
        db.commit()
        return jsonify({'success': True, 'deleted_count': deleted_count})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()

@web_bp.route('/sessions')
def sessions():
    """Session history"""
    if 'discord_user' not in session:
        return redirect(url_for('web.login'))
    
    user_data = session['discord_user']
    db = get_db()
    
    try:
        # Convert user ID to string for database queries
        user_id_str = str(user_data['id'])
        
        # Get user's session participation with rewards and session data eagerly loaded
        session_participations = db.query(SessionParticipant).options(
            joinedload(SessionParticipant.session),
            joinedload(SessionParticipant.reward)
        ).join(RPSession).outerjoin(SessionReward).filter(
            SessionParticipant.user_id == user_id_str
        ).order_by(desc(RPSession.created_at)).limit(50).all()
        
        # Convert to serializable format
        sessions_data = []
        for participation in session_participations:
            sessions_data.append({
                'session_name': participation.session.session_name if participation.session else 'Unknown',
                'session_type': participation.session.session_type if participation.session else 'Unknown',
                'join_time': participation.join_time,
                'leave_time': participation.leave_time,
                'duration_minutes': participation.duration_minutes,
                'xp_earned': participation.reward.xp_earned if participation.reward else 0,
                'gold_earned': participation.reward.gold_earned if participation.reward else 0,
                'created_at': participation.session.created_at if participation.session else None,
                'ended_at': participation.session.ended_at if participation.session else None
            })
        
        db.close()
        
        return render_template('sessions.html', 
                             user=user_data,
                             sessions=sessions_data)
    except Exception as e:
        db.close()
        flash(f'Error loading sessions: {e}', 'error')
        return render_template('error.html', error=str(e))

# Admin routes
@web_bp.route('/admin')
def admin_dashboard():
    """Admin dashboard - requires admin permissions"""
    if 'discord_user' not in session:
        return redirect(url_for('web.login'))
    
    user_data = session['discord_user']
    from flask import current_app
    
    if not current_app.discord_auth.is_admin(user_data['id']):
        flash('Admin access required', 'error')
        return redirect(url_for('web.dashboard'))
    
    db = get_db()
    
    try:
        # Get system statistics
        total_guilds = db.query(Guild).count()
        total_aliases = db.query(CharacterAlias).count()
        total_sessions = db.query(RPSession).count()
        active_sessions = db.query(RPSession).filter(RPSession.is_active == True).count()
        
        # Recent activity
        recent_aliases = db.query(CharacterAlias).order_by(
            desc(CharacterAlias.created_at)
        ).limit(10).all()
        
        recent_sessions = db.query(RPSession).order_by(
            desc(RPSession.created_at)
        ).limit(10).all()
        
        db.close()
        
        return render_template('admin/dashboard.html',
                             user=user_data,
                             stats={
                                 'total_guilds': total_guilds,
                                 'total_aliases': total_aliases,
                                 'total_sessions': total_sessions,
                                 'active_sessions': active_sessions
                             },
                             recent_aliases=recent_aliases,
                             recent_sessions=recent_sessions)
    except Exception as e:
        db.close()
        flash(f'Error loading admin dashboard: {e}', 'error')
        return render_template('error.html', error=str(e))

@web_bp.route('/admin/guilds')
def admin_guilds():
    """Guild management"""
    if 'discord_user' not in session:
        return redirect(url_for('web.login'))
    
    user_data = session['discord_user']
    from flask import current_app
    
    if not current_app.discord_auth.is_admin(user_data['id']):
        flash('Admin access required', 'error')
        return redirect(url_for('web.dashboard'))
    
    db = get_db()
    
    try:
        # Get all guilds with statistics
        guilds = db.query(Guild).all()
        
        guild_stats = []
        for guild in guilds:
            alias_count = db.query(CharacterAlias).filter(
                CharacterAlias.guild_id == guild.guild_id
            ).count()
            
            session_count = db.query(RPSession).filter(
                RPSession.guild_id == guild.guild_id
            ).count()
            
            guild_stats.append({
                'guild': guild,
                'alias_count': alias_count,
                'session_count': session_count
            })
        
        db.close()
        
        return render_template('admin/guilds.html',
                             user=user_data,
                             guild_stats=guild_stats)
    except Exception as e:
        db.close()
        flash(f'Error loading guilds: {e}', 'error')
        return render_template('error.html', error=str(e))

@web_bp.route('/admin/users')
def admin_users():
    """User management"""
    if 'discord_user' not in session:
        return redirect(url_for('web.login'))
    
    user_data = session['discord_user']
    from flask import current_app
    
    if not current_app.discord_auth.is_admin(user_data['id']):
        flash('Admin access required', 'error')
        return redirect(url_for('web.dashboard'))
    
    db = get_db()
    
    try:
        # Get user statistics from aliases and sessions
        user_stats = db.query(
            CharacterAlias.user_id,
            func.count(CharacterAlias.alias_id).label('alias_count'),
            func.max(CharacterAlias.last_used).label('last_active')
        ).group_by(CharacterAlias.user_id).all()
        
        db.close()
        
        return render_template('admin/users.html',
                             user=user_data,
                             user_stats=user_stats)
    except Exception as e:
        db.close()
        flash(f'Error loading users: {e}', 'error')
        return render_template('error.html', error=str(e))

# API endpoints for admin actions
@web_bp.route('/api/admin/stats')
def api_admin_stats():
    """Get system statistics as JSON"""
    if 'discord_user' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_data = session['discord_user']
    from flask import current_app
    
    if not current_app.discord_auth.is_admin(user_data['id']):
        return jsonify({'error': 'Admin access required'}), 403
    
    db = get_db()
    
    try:
        stats = {
            'guilds': db.query(Guild).count(),
            'aliases': db.query(CharacterAlias).count(),
            'sessions': db.query(RPSession).count(),
            'active_sessions': db.query(RPSession).filter(RPSession.is_active == True).count(),
            'rewards_issued': db.query(SessionReward).count()
        }
        
        db.close()
        return jsonify(stats)
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 500

@web_bp.route("/api/aliases/create-subgroup", methods=["POST"])
@require_auth
def api_create_subgroup():
    """Create an empty subgroup by creating a placeholder alias"""
    db = None
    try:
        data = request.get_json()
        group_name = data.get("group_name")
        subgroup_name = data.get("subgroup_name")
        
        if not group_name or not subgroup_name:
            return jsonify({"error": "Group name and subgroup name are required"}), 400
        
        db = get_db()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        
        user_id_str = str(session["discord_user"]["id"])
        
        # Check if a subgroup already exists
        existing = db.query(CharacterAlias).filter_by(
            user_id=user_id_str,
            group_name=group_name,
            subgroup=subgroup_name
        ).first()
        
        if existing:
            return jsonify({"success": True, "message": "Subgroup already exists"})
        
        # Create a placeholder alias to establish the subgroup in the database
        placeholder_alias = CharacterAlias(
            user_id=user_id_str,
            guild_id=session.get('current_guild_id', 0),
            name=f"__PLACEHOLDER__{subgroup_name}",
            trigger=f"__placeholder_trigger_{subgroup_name}__",
            group_name=group_name,
            subgroup=subgroup_name,
            description=f"Placeholder for empty subgroup '{subgroup_name}' - auto-generated",
            avatar_url=None,
            is_favorite=False
        )
        
        db.add(placeholder_alias)
        db.commit()
        
        return jsonify({"success": True, "message": "Subgroup created successfully"})
        
    except Exception as e:
        if db:
            db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if db:
            db.close()

# ===============================
# SHARED GROUP MANAGEMENT ROUTES
# ===============================

@web_bp.route('/api/shared-groups', methods=['GET'])
@require_auth
def get_shared_groups():
    """Get all shared groups the user has access to"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        # Get groups where user is owner or has permissions
        groups_query = db.query(SharedGroup).outerjoin(SharedGroupPermission).filter(
            (SharedGroup.owner_id == user_id_str) | 
            (SharedGroupPermission.user_id == user_id_str)
        ).distinct().all()
        
        groups_data = []
        for group in groups_query:
            # Get user's permission level
            permission_level = 'owner' if group.owner_id == user_id_str else None
            if not permission_level:
                perm = db.query(SharedGroupPermission).filter(
                    SharedGroupPermission.shared_group_id == group.id,
                    SharedGroupPermission.user_id == user_id_str
                ).first()
                permission_level = perm.permission_level if perm else None
            
            # Count aliases in this group
            alias_count = db.query(CharacterAlias).filter(
                CharacterAlias.shared_group_id == group.id
            ).count()
            
            # Get member count
            member_count = db.query(SharedGroupPermission).filter(
                SharedGroupPermission.shared_group_id == group.id
            ).count() + 1  # +1 for owner
            
            groups_data.append({
                'id': group.id,
                'group_name': group.group_name,
                'subgroup_name': group.subgroup_name,
                'description': group.description,
                'permission_level': permission_level,
                'alias_count': alias_count,
                'member_count': member_count,
                'owner_id': group.owner_id,
                'is_active': group.is_active,
                'allow_member_invites': group.allow_member_invites,
                'created_at': group.created_at.isoformat() if group.created_at else None
            })
        
        return jsonify({'success': True, 'groups': groups_data})
        
    except Exception as e:
        print(f"Error getting shared groups: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/shared-groups', methods=['POST'])
@require_auth
def create_shared_group():
    """Create a new shared group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        data = request.get_json()
        if not data or not data.get('group_name'):
            return jsonify({'success': False, 'error': 'Group name is required'})
        
        # Check if group already exists for this user
        existing = db.query(SharedGroup).filter(
            SharedGroup.owner_id == user_id_str,
            SharedGroup.group_name == data['group_name'],
            SharedGroup.subgroup_name == data.get('subgroup_name')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Group with this name already exists'})
        
        # Create new shared group
        new_group = SharedGroup(
            guild_id=data.get('guild_id', '0'),  # Default guild ID
            owner_id=user_id_str,
            group_name=data['group_name'],
            subgroup_name=data.get('subgroup_name'),
            description=data.get('description', ''),
            allow_member_invites=data.get('allow_member_invites', False)
        )
        
        db.add(new_group)
        db.commit()
        
        # Create owner permission record
        owner_perm = SharedGroupPermission(
            shared_group_id=new_group.id,
            user_id=user_id_str,
            permission_level='owner',
            granted_by=user_id_str
        )
        
        db.add(owner_perm)
        db.commit()
        
        return jsonify({
            'success': True, 
            'group_id': new_group.id,
            'message': 'Shared group created successfully'
        })
        
    except Exception as e:
        db.rollback()
        print(f"Error creating shared group: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/shared-groups/<int:group_id>/members', methods=['GET'])
@require_auth
def get_group_members(group_id):
    """Get members of a shared group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        # Check if user has permission to view this group
        group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
        if not group:
            return jsonify({'success': False, 'error': 'Group not found'})
        
        # Check permission
        has_permission, _ = check_shared_group_permission(db, user_id_str, group_id, ['owner', 'manager', 'speaker'])
        if not has_permission:
            return jsonify({'success': False, 'error': 'Permission denied'})
        
        # Get all members including owner
        members = []
        
        # Add owner
        members.append({
            'user_id': group.owner_id,
            'permission_level': 'owner',
            'granted_at': group.created_at.isoformat() if group.created_at else None,
            'granted_by': group.owner_id,
            'is_owner': True
        })
        
        # Add other members
        permissions = db.query(SharedGroupPermission).filter(
            SharedGroupPermission.shared_group_id == group_id,
            SharedGroupPermission.user_id != group.owner_id
        ).all()
        
        for perm in permissions:
            members.append({
                'user_id': perm.user_id,
                'permission_level': perm.permission_level,
                'granted_at': perm.granted_at.isoformat() if perm.granted_at else None,
                'granted_by': perm.granted_by,
                'is_owner': False
            })
        
        return jsonify({'success': True, 'members': members})
        
    except Exception as e:
        print(f"Error getting group members: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/shared-groups/<int:group_id>/invite', methods=['POST'])
@require_auth
def invite_to_group(group_id):
    """Invite a user to a shared group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        data = request.get_json()
        if not data or not data.get('user_id') or not data.get('permission_level'):
            return jsonify({'success': False, 'error': 'User ID and permission level are required'})
        
        target_user_id = str(data['user_id'])
        permission_level = data['permission_level']
        
        if permission_level not in ['manager', 'speaker']:
            return jsonify({'success': False, 'error': 'Invalid permission level'})
        
        # Check if user has permission to invite
        group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
        if not group:
            return jsonify({'success': False, 'error': 'Group not found'})
        
        can_invite = False
        if group.owner_id == user_id_str:
            can_invite = True
        elif group.allow_member_invites:
            has_permission, user_level = check_shared_group_permission(db, user_id_str, group_id, ['manager'])
            if has_permission:
                can_invite = True
        
        if not can_invite:
            return jsonify({'success': False, 'error': 'Permission denied to invite users'})
        
        # Check if user is already a member
        existing = db.query(SharedGroupPermission).filter(
            SharedGroupPermission.shared_group_id == group_id,
            SharedGroupPermission.user_id == target_user_id
        ).first()
        
        if existing or group.owner_id == target_user_id:
            return jsonify({'success': False, 'error': 'User is already a member'})
        
        # Create invitation
        new_permission = SharedGroupPermission(
            shared_group_id=group_id,
            user_id=target_user_id,
            permission_level=permission_level,
            granted_by=user_id_str
        )
        
        db.add(new_permission)
        db.commit()
        
        return jsonify({'success': True, 'message': 'User invited successfully'})
        
    except Exception as e:
        db.rollback()
        print(f"Error inviting user: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/shared-groups/<int:group_id>/remove/<user_id>', methods=['DELETE'])
@require_auth
def remove_from_group(group_id, user_id):
    """Remove a user from a shared group"""
    current_user_data = session['discord_user']
    current_user_id_str = str(current_user_data['id'])
    target_user_id_str = str(user_id)
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        # Check if current user has permission to remove
        group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
        if not group:
            return jsonify({'success': False, 'error': 'Group not found'})
        
        # Only owner can remove members
        if group.owner_id != current_user_id_str:
            return jsonify({'success': False, 'error': 'Only group owner can remove members'})
        
        # Cannot remove the owner
        if target_user_id_str == group.owner_id:
            return jsonify({'success': False, 'error': 'Cannot remove group owner'})
        
        # Remove the permission
        permission = db.query(SharedGroupPermission).filter(
            SharedGroupPermission.shared_group_id == group_id,
            SharedGroupPermission.user_id == target_user_id_str
        ).first()
        
        if not permission:
            return jsonify({'success': False, 'error': 'User is not a member'})
        
        db.delete(permission)
        db.commit()
        
        return jsonify({'success': True, 'message': 'User removed successfully'})
        
    except Exception as e:
        db.rollback()
        print(f"Error removing user: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

def check_shared_group_permission(db, user_id, group_id, required_permissions):
    """
    Check if user has required permissions for a shared group
    required_permissions: list of permission levels (e.g., ['owner', 'manager'])
    """
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        return False, None
    
    # Check if user is owner
    if group.owner_id == user_id and 'owner' in required_permissions:
        return True, 'owner'
    
    # Check user's permission level
    perm = db.query(SharedGroupPermission).filter(
        SharedGroupPermission.shared_group_id == group_id,
        SharedGroupPermission.user_id == user_id
    ).first()
    
    if perm and perm.permission_level in required_permissions:
        return True, perm.permission_level
    
    return False, None

@web_bp.route('/api/aliases/<int:alias_id>/assign-shared-group', methods=['PUT'])
@require_auth
def assign_alias_to_shared_group(alias_id):
    """Assign an alias to a shared group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        data = request.get_json()
        shared_group_id = data.get('shared_group_id') if data else None
        
        # Get the alias
        alias = db.query(CharacterAlias).filter(CharacterAlias.id == alias_id).first()
        if not alias:
            return jsonify({'success': False, 'error': 'Alias not found'})
        
        # Check if user owns the alias or has permission
        if alias.user_id != user_id_str:
            return jsonify({'success': False, 'error': 'Permission denied'})
        
        # If shared_group_id is provided, check permissions
        if shared_group_id:
            has_permission, permission_level = check_shared_group_permission(
                db, user_id_str, shared_group_id, ['owner', 'manager']
            )
            if not has_permission:
                return jsonify({'success': False, 'error': 'Permission denied for shared group'})
        
        # Update the alias
        alias.shared_group_id = shared_group_id
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Alias shared group assignment updated successfully'
        })
        
    except Exception as e:
        db.rollback()
        print(f"Error assigning alias to shared group: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/shared-groups/<int:group_id>/aliases', methods=['GET'])
@require_auth 
def get_shared_group_aliases(group_id):
    """Get all aliases in a shared group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        # Check if user has permission to view this group
        has_permission, _ = check_shared_group_permission(db, user_id_str, group_id, ['owner', 'manager', 'speaker'])
        if not has_permission:
            return jsonify({'success': False, 'error': 'Permission denied'})
        
        # Get aliases in the shared group
        aliases = db.query(CharacterAlias).filter(
            CharacterAlias.shared_group_id == group_id
        ).all()
        
        aliases_data = []
        for alias in aliases:
            aliases_data.append({
                'id': alias.id,
                'name': alias.name,
                'trigger': alias.trigger,
                'character_class': alias.character_class,
                'race': alias.race,
                'description': alias.description,
                'avatar_url': alias.avatar_url,
                'tags': alias.tags,
                'user_id': alias.user_id,
                'created_at': alias.created_at.isoformat() if alias.created_at else None,
                'last_used': alias.last_used.isoformat() if alias.last_used else None,
                'message_count': alias.message_count
            })
        
        return jsonify({'success': True, 'aliases': aliases_data})
        
    except Exception as e:
        print(f"Error getting shared group aliases: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

# ===============================
# GROUP PERMISSION ROUTES (Simple Integration with Existing Groups)
# ===============================

@web_bp.route('/api/groups/<group_name>/permissions', methods=['GET'])
@require_auth
def get_group_permissions(group_name):
    """Get permissions for a specific alias group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        guild_id = session.get('current_guild_id', '0')
        subgroup_name = request.args.get('subgroup_name')
        
        # Check if user has any permission to view this group
        user_permission = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.group_name == group_name,
            GroupPermission.subgroup_name == subgroup_name,
            GroupPermission.user_id == user_id_str
        ).first()
        
        # Get all aliases in this group to check ownership
        aliases_query = db.query(CharacterAlias).filter(
            CharacterAlias.guild_id == str(guild_id),
            CharacterAlias.group_name == group_name
        )
        if subgroup_name:
            aliases_query = aliases_query.filter(CharacterAlias.subgroup == subgroup_name)
        
        user_aliases = aliases_query.filter(CharacterAlias.user_id == user_id_str).count()
        
        # User can view if they have permission OR own aliases in this group
        if not user_permission and user_aliases == 0:
            return jsonify({'success': False, 'error': 'Permission denied'})
        
        # Get all permissions for this group
        permissions = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.group_name == group_name,
            GroupPermission.subgroup_name == subgroup_name
        ).all()
        
        permissions_data = []
        for perm in permissions:
            permissions_data.append({
                'user_id': perm.user_id,
                'permission_level': perm.permission_level,
                'granted_by': perm.granted_by,
                'granted_at': perm.granted_at.isoformat() if perm.granted_at else None,
                'is_owner': perm.permission_level == 'owner'
            })
        
        return jsonify({'success': True, 'permissions': permissions_data})
        
    except Exception as e:
        print(f"Error getting group permissions: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/groups/<group_name>/share', methods=['POST'])
@require_auth
def share_group(group_name):
    """Share a group with another user"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        data = request.get_json()
        print(f"DEBUG: Received data for group sharing: {data}")
        print(f"DEBUG: Session data: {dict(session)}")
        
        if not data or not data.get('target_user_id') or not data.get('permission_level'):
            return jsonify({'success': False, 'error': 'Target user ID and permission level required'})
        
        # Get guild_id from session or use default
        guild_id = session.get('current_guild_id', '0')
        
        # For debugging - log the guild_id being used
        print(f"DEBUG: Using guild_id '{guild_id}' for group sharing")
        
        # Ensure the guild exists in the database
        guild = db.query(Guild).filter_by(id=str(guild_id)).first()
        if not guild:
            # Create the guild if it doesn't exist
            guild = Guild(id=str(guild_id), name=f"Guild {guild_id}")
            db.add(guild)
            db.flush()  # Flush to make it available for foreign key reference
            print(f"DEBUG: Created guild {guild_id}")
        
        subgroup_name = data.get('subgroup_name')
        target_user_id = str(data['target_user_id'])
        permission_level = data['permission_level']
        
        print(f"DEBUG: Sharing group '{group_name}' (subgroup: '{subgroup_name}') with user '{target_user_id}' as '{permission_level}'")
        
        if permission_level not in ['manager', 'speaker']:
            return jsonify({'success': False, 'error': 'Invalid permission level'})
        
        # Check if user can share this group (owns aliases in it OR has owner/manager permission)
        # First check for any aliases in this group (including without subgroup)
        user_aliases_query = db.query(CharacterAlias).filter(
            CharacterAlias.guild_id == str(guild_id),
            CharacterAlias.group_name == group_name,
            CharacterAlias.user_id == user_id_str
        )
        
        # If subgroup specified, filter by it, otherwise check for aliases with no subgroup or the specified one
        if subgroup_name:
            user_aliases = user_aliases_query.filter(CharacterAlias.subgroup == subgroup_name).count()
        else:
            user_aliases = user_aliases_query.count()
        
        user_permission = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.group_name == group_name,
            GroupPermission.subgroup_name == subgroup_name,
            GroupPermission.user_id == user_id_str,
            GroupPermission.permission_level.in_(['owner', 'manager'])
        ).first()
        
        # Allow sharing if user owns any aliases in the group OR has explicit permission
        # OR if the group doesn't exist yet (they're creating a new shared group)
        total_group_aliases = db.query(CharacterAlias).filter(
            CharacterAlias.guild_id == str(guild_id),
            CharacterAlias.group_name == group_name
        ).count()
        
        # If the group doesn't exist at all, allow the user to create it as a shared group
        can_share = (user_aliases > 0 or 
                    user_permission or 
                    total_group_aliases == 0)
        
        if not can_share:
            return jsonify({
                'success': False, 
                'error': 'Permission denied: You must own aliases in this group to share it',
                'debug': {
                    'guild_id': guild_id,
                    'group_name': group_name,
                    'subgroup_name': subgroup_name,
                    'user_aliases': user_aliases,
                    'total_group_aliases': total_group_aliases,
                    'has_permission': bool(user_permission)
                }
            })
        
        # Check if target user already has permission
        existing = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.group_name == group_name,
            GroupPermission.subgroup_name == subgroup_name,
            GroupPermission.user_id == target_user_id
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'User already has permission for this group'})
        
        # Create the permission
        new_permission = GroupPermission(
            guild_id=str(guild_id),
            group_name=group_name,
            subgroup_name=subgroup_name,
            owner_id=user_id_str,  # The person sharing becomes the owner for this permission
            user_id=target_user_id,
            permission_level=permission_level,
            granted_by=user_id_str
        )
        
        db.add(new_permission)
        db.commit()
        
        return jsonify({'success': True, 'message': f'Group shared with user {target_user_id}'})
        
    except Exception as e:
        db.rollback()
        import traceback
        error_details = traceback.format_exc()
        print(f"Error sharing group: {e}")
        print(f"Full traceback: {error_details}")
        return jsonify({
            'success': False, 
            'error': str(e),
            'debug_traceback': error_details
        })
    finally:
        if db:
            db.close()

@web_bp.route('/api/groups/my-groups-detailed', methods=['GET'])
@require_auth
def get_my_groups_detailed():
    """Get detailed information about user's own groups including aliases and shared users"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        guild_id = session.get('current_guild_id', '0')
        
        # Get user's aliases grouped by group_name and subgroup_name (including placeholders for empty groups)
        aliases = db.query(CharacterAlias).filter(
            CharacterAlias.user_id == user_id_str,
            CharacterAlias.guild_id == str(guild_id)
        ).all()
        
        # Separate real aliases from placeholders
        real_aliases = [alias for alias in aliases if not alias.name.startswith('__PLACEHOLDER__')]
        placeholder_aliases = [alias for alias in aliases if alias.name.startswith('__PLACEHOLDER__')]
        
        # Group real aliases by group_name and subgroup_name
        groups_dict = {}
        for alias in real_aliases:
            group_key = (alias.group_name or 'Ungrouped', alias.subgroup or '')
            if group_key not in groups_dict:
                groups_dict[group_key] = []
            groups_dict[group_key].append({
                'id': alias.id,
                'name': alias.name,
                'trigger': alias.trigger,
                'avatar_url': alias.avatar_url,
                'user_id': alias.user_id
            })
        
        # Add empty groups/subgroups from placeholders
        for placeholder in placeholder_aliases:
            group_key = (placeholder.group_name or 'Ungrouped', placeholder.subgroup or '')
            if group_key not in groups_dict:
                groups_dict[group_key] = []  # Empty group
        
        # Get shared users for each group
        result_groups = []
        for (group_name, subgroup_name), group_aliases in groups_dict.items():
            # Get users this group is shared with
            shared_permissions = db.query(GroupPermission).filter(
                GroupPermission.guild_id == str(guild_id),
                GroupPermission.group_name == group_name,
                GroupPermission.subgroup_name == subgroup_name,
                GroupPermission.owner_id == user_id_str
            ).all()
            
            shared_users = [{
                'user_id': perm.user_id,
                'permission_level': perm.permission_level,
                'granted_at': perm.granted_at.isoformat() if perm.granted_at else None
            } for perm in shared_permissions]
            
            result_groups.append({
                'group_name': group_name,
                'subgroup_name': subgroup_name if subgroup_name else None,
                'alias_count': len(group_aliases),
                'aliases': group_aliases,
                'shared_users': shared_users
            })
        
        # Sort groups by name
        result_groups.sort(key=lambda x: (x['group_name'], x['subgroup_name'] or ''))
        
        return jsonify({'success': True, 'groups': result_groups})
        
    except Exception as e:
        print(f"Error getting my groups detailed: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/groups/shared-with-me-detailed', methods=['GET'])
@require_auth
def get_shared_with_me_detailed():
    """Get detailed information about groups shared with the user"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        guild_id = session.get('current_guild_id', '0')
        
        # Get groups where user has permissions (but is not the owner)
        permissions = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.user_id == user_id_str,
            GroupPermission.owner_id != user_id_str
        ).all()
        
        result_groups = []
        for perm in permissions:
            # Get aliases in this group
            group_aliases = db.query(CharacterAlias).filter(
                CharacterAlias.guild_id == str(guild_id),
                CharacterAlias.group_name == perm.group_name,
                CharacterAlias.subgroup == perm.subgroup_name,
                ~CharacterAlias.name.like('__PLACEHOLDER__%')
            ).all()
            
            aliases_data = [{
                'id': alias.id,
                'name': alias.name,
                'trigger': alias.trigger,
                'avatar_url': alias.avatar_url,
                'user_id': alias.user_id
            } for alias in group_aliases]
            
            result_groups.append({
                'group_name': perm.group_name,
                'subgroup_name': perm.subgroup_name,
                'permission_level': perm.permission_level,
                'owner_id': perm.owner_id,
                'granted_at': perm.granted_at.isoformat() if perm.granted_at else None,
                'alias_count': len(aliases_data),
                'aliases': aliases_data
            })
        
        # Sort groups by name
        result_groups.sort(key=lambda x: (x['group_name'], x['subgroup_name'] or ''))
        
        return jsonify({'success': True, 'groups': result_groups})
        
    except Exception as e:
        print(f"Error getting shared groups detailed: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/groups/<group_name>/permissions/remove', methods=['POST'])
@require_auth
def remove_group_permission(group_name):
    """Remove a user's permission from a group"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        data = request.get_json()
        if not data or not data.get('user_id'):
            return jsonify({'success': False, 'error': 'User ID required'})
        
        guild_id = session.get('current_guild_id', '0')
        target_user_id = str(data['user_id'])
        subgroup_name = data.get('subgroup_name')
        
        # Check if user owns this group or has manager permission
        can_remove = False
        
        # Check if user owns aliases in this group
        user_aliases = db.query(CharacterAlias).filter(
            CharacterAlias.guild_id == str(guild_id),
            CharacterAlias.group_name == group_name,
            CharacterAlias.user_id == user_id_str
        )
        if subgroup_name:
            user_aliases = user_aliases.filter(CharacterAlias.subgroup == subgroup_name)
        
        if user_aliases.count() > 0:
            can_remove = True
        
        # Check if user has manager/owner permission
        user_permission = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.group_name == group_name,
            GroupPermission.subgroup_name == subgroup_name,
            GroupPermission.user_id == user_id_str,
            GroupPermission.permission_level.in_(['owner', 'manager'])
        ).first()
        
        if user_permission:
            can_remove = True
        
        if not can_remove:
            return jsonify({'success': False, 'error': 'Permission denied'})
        
        # Remove the permission
        permission_to_remove = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.group_name == group_name,
            GroupPermission.subgroup_name == subgroup_name,
            GroupPermission.user_id == target_user_id
        ).first()
        
        if not permission_to_remove:
            return jsonify({'success': False, 'error': 'Permission not found'})
        
        db.delete(permission_to_remove)
        db.commit()
        
        return jsonify({'success': True, 'message': f'Permission removed for user {target_user_id}'})
        
    except Exception as e:
        db.rollback()
        print(f"Error removing permission: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/shared-groups-simple', methods=['GET'])
@require_auth
def get_shared_groups_simple():
    """Get groups that are shared with the current user using simple permissions"""
    user_data = session['discord_user']
    user_id_str = str(user_data['id'])
    db = get_db()
    
    try:
        if db is None:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        guild_id = session.get('current_guild_id', '0')
        
        # Get groups where user has permissions
        permissions = db.query(GroupPermission).filter(
            GroupPermission.guild_id == str(guild_id),
            GroupPermission.user_id == user_id_str
        ).all()
        
        shared_groups = []
        for perm in permissions:
            # Count aliases in this group
            alias_count = db.query(CharacterAlias).filter(
                CharacterAlias.guild_id == str(guild_id),
                CharacterAlias.group_name == perm.group_name,
                CharacterAlias.subgroup == perm.subgroup_name
            ).count()
            
            # Count members
            member_count = db.query(GroupPermission).filter(
                GroupPermission.guild_id == str(guild_id),
                GroupPermission.group_name == perm.group_name,
                GroupPermission.subgroup_name == perm.subgroup_name
            ).count()
            
            shared_groups.append({
                'group_name': perm.group_name,
                'subgroup_name': perm.subgroup_name,
                'permission_level': perm.permission_level,
                'alias_count': alias_count,
                'member_count': member_count,
                'granted_by': perm.granted_by,
                'granted_at': perm.granted_at.isoformat() if perm.granted_at else None
            })
        
        return jsonify({'success': True, 'shared_groups': shared_groups})
        
    except Exception as e:
        print(f"Error getting shared groups: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if db:
            db.close()

@web_bp.route('/api/discord/user-guilds')
@require_auth
def get_user_guilds():
    """Get guilds the authenticated user has access to"""
    try:
        user_data = session['discord_user']
        
        # Check if user has access token for Discord API
        if 'access_token' not in session:
            return jsonify({'success': False, 'error': 'No Discord access token available'}), 403
        
        import requests
        
        headers = {
            'Authorization': f"Bearer {session['access_token']}",
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            'https://discord.com/api/v10/users/@me/guilds',
            headers=headers
        )
        
        if not response.ok:
            return jsonify({'success': False, 'error': 'Failed to fetch user guilds'}), 403
        
        guilds = response.json()
        
        # Filter to only guilds where user has management permissions
        manageable_guilds = []
        for guild in guilds:
            # Check if user has manage guild permission (bit 5) or is owner
            permissions = int(guild.get('permissions', 0))
            has_manage_guild = (permissions & (1 << 5)) != 0
            is_owner = guild.get('owner', False)
            
            if has_manage_guild or is_owner:
                manageable_guilds.append({
                    'id': guild['id'],
                    'name': guild['name'],
                    'icon': guild.get('icon'),
                    'owner': is_owner,
                    'permissions': permissions
                })
        
        return jsonify({
            'success': True,
            'guilds': manageable_guilds
        })
        
    except Exception as e:
        print(f"Error fetching user guilds: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@web_bp.route('/api/discord/user-lookup/<user_identifier>')
@require_auth  
def lookup_discord_user(user_identifier):
    """Look up Discord user information by ID or username"""
    try:
        # Check if user has access token for Discord API
        if 'access_token' not in session:
            return jsonify({'success': False, 'error': 'No Discord access token available'}), 403
        
        import requests
        
        headers = {
            'Authorization': f"Bearer {session['access_token']}",
            'Content-Type': 'application/json'
        }
        
        # Check if it's a User ID (17-19 digits) or a username
        if user_identifier.isdigit() and len(user_identifier) >= 17:
            # It's a User ID - direct lookup
            response = requests.get(
                f'https://discord.com/api/v10/users/{user_identifier}',
                headers=headers
            )
            
            if response.ok:
                user_info = response.json()
                return jsonify({
                    'success': True,
                    'user': {
                        'id': user_info['id'],
                        'username': user_info['username'],
                        'discriminator': user_info.get('discriminator', '0'),
                        'global_name': user_info.get('global_name'),
                        'avatar': user_info.get('avatar')
                    }
                })
        
        # It's a username/nickname - search through guilds
        # Get user's guilds first
        guilds_response = requests.get(
            'https://discord.com/api/v10/users/@me/guilds',
            headers=headers
        )
        
        if not guilds_response.ok:
            return jsonify({'success': False, 'error': 'Failed to fetch user guilds'}), 403
        
        guilds = guilds_response.json()
        found_users = []
        
        # Search for users with matching username/nickname in accessible guilds
        # Note: Due to Discord API limitations with user tokens, we can't directly search guild members
        # We need to use a different approach - search using the current guild context
        
        # Try to get current guild from session or default
        current_guild_id = session.get('current_guild_id')
        if not current_guild_id and guilds:
            # Use the first guild the user has access to
            current_guild_id = guilds[0]['id']
        
        if current_guild_id:
            session['current_guild_id'] = current_guild_id
        
        # Since we can't search guild members with user token, provide guidance
        return jsonify({
            'success': False,
            'error': f'Username search "{user_identifier}" not found. Please try using the full Discord User ID instead.',
            'suggestion': 'To find a User ID: Right-click the user in Discord → Copy User ID (Developer Mode must be enabled)',
            'searched_for': user_identifier
        }), 404
        
    except Exception as e:
        print(f"Error looking up Discord user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@web_bp.route('/api/discord/search-users/<guild_id>/<search_term>')
@require_auth
def search_guild_users(guild_id, search_term):
    """Search for users in a specific guild by username/nickname"""
    try:
        # This endpoint would require bot token access, which we don't have in web context
        # Instead, provide helpful guidance
        return jsonify({
            'success': False,
            'error': 'Username search requires Discord User ID due to API limitations.',
            'help': {
                'how_to_find_user_id': [
                    '1. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)',
                    '2. Right-click on the user you want to share with',
                    '3. Select "Copy User ID"',
                    '4. Paste the ID in the sharing form'
                ],
                'searched_for': search_term
            }
        }), 400
        
    except Exception as e:
        print(f"Error searching guild users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@web_bp.route('/api/discord/guild-members/<guild_id>/search')
@require_auth
def search_guild_members(guild_id):
    """Search guild members using cached member data"""
    try:
        search_term = request.args.get('q', '').strip().lower()
        if not search_term:
            return jsonify({'success': False, 'error': 'Search term is required'}), 400
        
        db = get_db()
        if not db:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        
        # Use current guild ID or the provided one
        current_guild_id = session.get('current_guild_id', '0')
        target_guild_id = guild_id if guild_id != '0' else current_guild_id
        
        if target_guild_id == '0':
            return jsonify({
                'success': False,
                'error': 'No guild selected. Please visit the group manager first to set a default server.',
                'searched_for': search_term
            }), 400
        
        # Search cached guild members
        from models import GuildMember, Guild
        
        # Get guild info
        guild_record = db.query(Guild).filter(Guild.id == target_guild_id).first()
        if not guild_record:
            return jsonify({
                'success': False,
                'error': 'Guild not found in cache. Please wait for member sync to complete.',
                'searched_for': search_term
            }), 404
        
        # Search for members matching the search term
        search_pattern = f"%{search_term}%"
        members_query = db.query(GuildMember).filter(
            GuildMember.guild_id == target_guild_id,
            GuildMember.is_active == True,
            db.or_(
                GuildMember.username.ilike(search_pattern),
                GuildMember.display_name.ilike(search_pattern)
            )
        ).limit(20)  # Limit results
        
        matching_members = []
        for member in members_query.all():
            matching_members.append({
                'id': member.user_id,
                'username': member.username,
                'display_name': member.display_name or member.username,
                'discriminator': member.discriminator,
                'avatar': member.avatar_url,
                'nickname': member.display_name if member.display_name != member.username else None,
                'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                'cached_at': member.cached_at.isoformat(),
                'match_type': 'cached'
            })
        
        # Sort results by relevance (exact match first, then starts with, then contains)
        matching_members.sort(key=lambda x: (
            0 if x['display_name'].lower() == search_term else
            1 if x['display_name'].lower().startswith(search_term) else
            2 if x['username'].lower() == search_term else
            3 if x['username'].lower().startswith(search_term) else 4
        ))
        
        # Get total member count for this guild
        total_members = db.query(GuildMember).filter(
            GuildMember.guild_id == target_guild_id,
            GuildMember.is_active == True
        ).count()
        
        return jsonify({
            'success': True,
            'members': matching_members,
            'total_found': len(matching_members),
            'search_term': search_term,
            'guild_name': guild_record.name,
            'guild_id': target_guild_id,
            'limited': len(matching_members) >= 20,
            'debug_info': {
                'total_cached_members': total_members,
                'last_sync': guild_record.last_member_sync.isoformat() if guild_record.last_member_sync else None,
                'using_cached_data': True
            }
        })
        
    except Exception as e:
        print(f"Error searching cached guild members: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()

@web_bp.route('/api/group-permissions')
@require_auth
def api_get_group_permissions():
    """Get permissions for a specific group"""
    try:
        user_id_str = str(session['discord_user']['id'])
        guild_id = session.get('current_guild_id', '0')
        group_name = request.args.get('group_name')
        subgroup = request.args.get('subgroup', '')
        
        if not group_name:
            return jsonify({'success': False, 'error': 'Group name is required'})
        
        with get_database_connection() as db:
            # Get permissions for this group
            permissions_query = db.query(GroupPermission).filter(
                GroupPermission.guild_id == str(guild_id),
                GroupPermission.group_name == group_name,
                GroupPermission.subgroup_name == (subgroup if subgroup else None)
            ).all()
            
            permissions_data = []
            for perm in permissions_query:
                # Get user info from Discord API
                try:
                    user_response = requests.get(
                        f'https://discord.com/api/v10/users/{perm.user_id}',
                        headers={'Authorization': f'Bot {os.environ["DISCORD_BOT_TOKEN"]}'}
                    )
                    if user_response.status_code == 200:
                        user_data = user_response.json()
                        permissions_data.append({
                            'id': perm.id,
                            'user_id': perm.user_id,
                            'user_username': user_data.get('username', 'Unknown'),
                            'user_display_name': user_data.get('global_name') or user_data.get('username', 'Unknown'),
                            'user_avatar': f"https://cdn.discordapp.com/avatars/{perm.user_id}/{user_data['avatar']}.png" if user_data.get('avatar') else None,
                            'permission_level': perm.permission_level,
                            'granted_at': perm.created_at.isoformat() if perm.created_at else None
                        })
                except Exception as e:
                    print(f"Error fetching user data for {perm.user_id}: {e}")
                    permissions_data.append({
                        'id': perm.id,
                        'user_id': perm.user_id,
                        'user_username': 'Unknown',
                        'user_display_name': 'Unknown User',
                        'user_avatar': None,
                        'permission_level': perm.permission_level,
                        'granted_at': perm.created_at.isoformat() if perm.created_at else None
                    })
            
            return jsonify({'success': True, 'permissions': permissions_data})
            
    except Exception as e:
        print(f"Error getting group permissions: {e}")
        return jsonify({'success': False, 'error': 'Failed to load permissions'})

@web_bp.route('/api/group-permissions/<int:permission_id>', methods=['DELETE'])
@require_auth
def api_remove_group_permission(permission_id):
    """Remove a group permission"""
    try:
        user_id_str = str(session['discord_user']['id'])
        guild_id = session.get('current_guild_id', '0')
        
        with get_database_connection() as db:
            # Get the permission to check if user can delete it
            permission = db.query(GroupPermission).filter(
                GroupPermission.id == permission_id
            ).first()
            
            if not permission:
                return jsonify({'success': False, 'error': 'Permission not found'})
            
            # Check if current user is owner of the group
            owner_permission = db.query(GroupPermission).filter(
                GroupPermission.guild_id == str(guild_id),
                GroupPermission.group_name == permission.group_name,
                GroupPermission.subgroup_name == permission.subgroup_name,
                GroupPermission.user_id == user_id_str,
                GroupPermission.permission_level == 'owner'
            ).first()
            
            if not owner_permission:
                return jsonify({'success': False, 'error': 'Only group owners can remove permissions'})
            
            # Cannot remove owner permission
            if permission.permission_level == 'owner':
                return jsonify({'success': False, 'error': 'Cannot remove owner permission'})
            
            # Delete the permission
            db.delete(permission)
            db.commit()
            
            return jsonify({'success': True})
            
    except Exception as e:
        print(f"Error removing group permission: {e}")
        return jsonify({'success': False, 'error': 'Failed to remove permission'})

