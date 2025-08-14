#!/usr/bin/env python3
"""
Import script designed to run inside the Docker container
"""
import csv
import json
import os
import sys
from datetime import datetime

def docker_import():
    """Import data inside Docker container"""
    print("Starting Docker container import...")
    
    # Add the app directory to Python path
    sys.path.append('/app')
    
    try:
        from database import get_db_session
        from models import CharacterAlias, Guild, PlayerStats, SharedGroup, SharedGroupPermission
    except ImportError as e:
        print(f"Failed to import modules: {e}")
        return
    
    # Check for export files in /app directory
    export_files = [
        '/app/aliases_safe_export.csv',
        '/app/guilds_safe_export.csv', 
        '/app/stats_safe_export.csv',
        '/app/shared_groups_safe_export.csv',
        '/app/permissions_safe_export.csv'
    ]
    
    available_files = []
    for file in export_files:
        if os.path.exists(file):
            available_files.append(file)
            print(f"Found: {file}")
    
    if not available_files:
        print("No export files found in /app directory")
        print("Available files:")
        for file in os.listdir('/app'):
            if file.endswith('.csv'):
                print(f"  - {file}")
        return
    
    db = get_db_session()
    try:
        # Import Character Aliases
        alias_file = '/app/aliases_safe_export.csv'
        if os.path.exists(alias_file):
            print("Importing character aliases...")
            with open(alias_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                alias_count = 0
                
                for row in reader:
                    # Check required fields
                    if not all(field in row and row[field] for field in ['user_id', 'guild_id', 'name', 'trigger']):
                        continue
                    
                    # Check if alias already exists
                    existing = db.query(CharacterAlias).filter(
                        CharacterAlias.user_id == row['user_id'],
                        CharacterAlias.guild_id == row['guild_id'],
                        CharacterAlias.name == row['name']
                    ).first()
                    
                    if not existing:
                        # Build alias data
                        alias_data = {
                            'user_id': row['user_id'],
                            'guild_id': row['guild_id'],
                            'name': row['name'],
                            'trigger': row['trigger'],
                            'avatar_url': row.get('avatar_url', 'https://cdn.discordapp.com/embed/avatars/0.png')
                        }
                        
                        # Add optional fields if they exist and have values
                        optional_fields = [
                            'group_name', 'subgroup', 'character_class', 'race', 'description',
                            'personality', 'backstory', 'pronouns', 'age', 'alignment', 
                            'goals', 'notes', 'dndbeyond_url', 'tags'
                        ]
                        
                        for field in optional_fields:
                            if field in row and row[field]:
                                alias_data[field] = row[field]
                        
                        # Handle boolean fields
                        if 'is_favorite' in row and row['is_favorite']:
                            alias_data['is_favorite'] = row['is_favorite'].lower() in ['true', '1', 'yes']
                        
                        # Handle numeric fields
                        if 'message_count' in row and row['message_count']:
                            try:
                                alias_data['message_count'] = int(row['message_count'])
                            except:
                                alias_data['message_count'] = 0
                        
                        alias = CharacterAlias(**alias_data)
                        db.add(alias)
                        alias_count += 1
                
                db.commit()
                print(f"Imported {alias_count} character aliases")
        
        # Verify import
        total_aliases = db.query(CharacterAlias).count()
        print(f"Total aliases in database: {total_aliases}")
        
    except Exception as e:
        print(f"Import failed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    docker_import()