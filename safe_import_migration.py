#!/usr/bin/env python3
"""
Safe import script that handles exported data from safe_export_migration.py
"""
import csv
import json
import os
from datetime import datetime
from database import get_db_session
from models import CharacterAlias, Guild, PlayerStats, SharedGroup, SharedGroupPermission

def safe_import():
    """Import data from safe export files"""
    print("Starting safe data import...")
    
    # Check for export summary to understand what was exported
    if os.path.exists('export_summary.json'):
        with open('export_summary.json', 'r') as f:
            summary = json.load(f)
        print(f"Found export summary: {summary['exported_files']}")
        available_files = summary['exported_files']
    else:
        # Check for individual files
        available_files = []
        possible_files = [
            'aliases_safe_export.csv',
            'guilds_safe_export.csv', 
            'stats_safe_export.csv',
            'shared_groups_safe_export.csv',
            'permissions_safe_export.csv'
        ]
        for file in possible_files:
            if os.path.exists(file):
                available_files.append(file)
        print(f"Found export files: {available_files}")
    
    if not available_files:
        print("❌ No export files found. Make sure you've run the export script and uploaded the files.")
        return
    
    db = get_db_session()
    try:
        # Import Guilds first (foreign key dependency)
        if 'guilds_safe_export.csv' in available_files:
            print("Importing guilds...")
            try:
                with open('guilds_safe_export.csv', 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    guild_count = 0
                    
                    for row in reader:
                        # Check if guild already exists
                        guild_id = row.get('id', '')
                        if guild_id:
                            existing = db.query(Guild).filter(Guild.id == guild_id).first()
                            if not existing:
                                # Create guild with only available fields
                                guild_data = {'id': guild_id}
                                if 'name' in row and row['name']:
                                    guild_data['name'] = row['name']
                                
                                # Add other fields if they exist
                                optional_fields = ['session_forum_id', 'announcement_channel_id', 
                                                 'dm_role_id', 'player_role_id']
                                for field in optional_fields:
                                    if field in row and row[field]:
                                        guild_data[field] = row[field]
                                
                                if 'created_at' in row and row['created_at']:
                                    try:
                                        guild_data['created_at'] = datetime.fromisoformat(row['created_at'])
                                    except:
                                        guild_data['created_at'] = datetime.now()
                                else:
                                    guild_data['created_at'] = datetime.now()
                                
                                guild = Guild(**guild_data)
                                db.add(guild)
                                guild_count += 1
                    
                    db.commit()
                    print(f"Imported {guild_count} guilds")
            except Exception as e:
                print(f"Error importing guilds: {e}")
                db.rollback()
        
        # Import Character Aliases
        if 'aliases_safe_export.csv' in available_files:
            print("Importing character aliases...")
            try:
                with open('aliases_safe_export.csv', 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    alias_count = 0
                    
                    for row in reader:
                        # Check required fields
                        if not all(field in row for field in ['user_id', 'guild_id', 'name', 'trigger']):
                            continue
                        
                        # Check if alias already exists
                        existing = db.query(CharacterAlias).filter(
                            CharacterAlias.user_id == row['user_id'],
                            CharacterAlias.guild_id == row['guild_id'],
                            CharacterAlias.name == row['name']
                        ).first()
                        
                        if not existing:
                            # Build alias data with available fields
                            alias_data = {
                                'user_id': row['user_id'],
                                'guild_id': row['guild_id'],
                                'name': row['name'],
                                'trigger': row['trigger'],
                                'avatar_url': row.get('avatar_url', 'https://cdn.discordapp.com/embed/avatars/0.png')
                            }
                            
                            # Add optional fields if they exist
                            optional_fields = [
                                'group_name', 'subgroup', 'character_class', 'race', 'description',
                                'personality', 'backstory', 'pronouns', 'age', 'alignment', 
                                'goals', 'notes', 'dndbeyond_url', 'tags'
                            ]
                            
                            for field in optional_fields:
                                if field in row and row[field]:
                                    alias_data[field] = row[field]
                            
                            # Handle boolean fields
                            if 'is_favorite' in row:
                                alias_data['is_favorite'] = row['is_favorite'].lower() in ['true', '1', 'yes']
                            
                            # Handle numeric fields
                            if 'message_count' in row and row['message_count']:
                                try:
                                    alias_data['message_count'] = int(row['message_count'])
                                except:
                                    alias_data['message_count'] = 0
                            
                            # Handle dates
                            if 'created_at' in row and row['created_at']:
                                try:
                                    alias_data['created_at'] = datetime.fromisoformat(row['created_at'])
                                except:
                                    pass
                            
                            if 'last_used' in row and row['last_used']:
                                try:
                                    alias_data['last_used'] = datetime.fromisoformat(row['last_used'])
                                except:
                                    pass
                            
                            alias = CharacterAlias(**alias_data)
                            db.add(alias)
                            alias_count += 1
                    
                    db.commit()
                    print(f"Imported {alias_count} character aliases")
            except Exception as e:
                print(f"Error importing aliases: {e}")
                db.rollback()
        
        # Import Player Stats
        if 'stats_safe_export.csv' in available_files:
            print("Importing player stats...")
            try:
                with open('stats_safe_export.csv', 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    stats_count = 0
                    
                    for row in reader:
                        if 'user_id' in row and 'guild_id' in row:
                            existing = db.query(PlayerStats).filter(
                                PlayerStats.user_id == row['user_id'],
                                PlayerStats.guild_id == row['guild_id']
                            ).first()
                            
                            if not existing:
                                stats_data = {
                                    'user_id': row['user_id'],
                                    'guild_id': row['guild_id']
                                }
                                
                                # Add numeric fields
                                numeric_fields = [
                                    'total_sessions', 'total_time_minutes', 'total_xp_earned',
                                    'total_gold_earned', 'sessions_hosted'
                                ]
                                
                                for field in numeric_fields:
                                    if field in row and row[field]:
                                        try:
                                            stats_data[field] = int(row[field])
                                        except:
                                            stats_data[field] = 0
                                
                                # Add text fields
                                if 'favorite_character' in row and row['favorite_character']:
                                    stats_data['favorite_character'] = row['favorite_character']
                                
                                # Add date fields
                                date_fields = ['last_session_date', 'created_at']
                                for field in date_fields:
                                    if field in row and row[field]:
                                        try:
                                            stats_data[field] = datetime.fromisoformat(row[field])
                                        except:
                                            if field == 'created_at':
                                                stats_data[field] = datetime.now()
                                
                                if 'created_at' not in stats_data:
                                    stats_data['created_at'] = datetime.now()
                                
                                stats = PlayerStats(**stats_data)
                                db.add(stats)
                                stats_count += 1
                    
                    db.commit()
                    print(f"Imported {stats_count} player stats")
            except Exception as e:
                print(f"Error importing stats: {e}")
                db.rollback()
        
        # Import Shared Groups
        if 'shared_groups_safe_export.csv' in available_files:
            print("Importing shared groups...")
            try:
                with open('shared_groups_safe_export.csv', 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    groups_count = 0
                    
                    for row in reader:
                        if 'id' in row and row['id']:
                            try:
                                group_id = int(row['id'])
                                existing = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
                                
                                if not existing:
                                    group_data = {'id': group_id}
                                    
                                    # Add required fields
                                    required_fields = ['guild_id', 'owner_id', 'group_name']
                                    for field in required_fields:
                                        if field in row and row[field]:
                                            group_data[field] = row[field]
                                    
                                    # Add optional fields
                                    if 'subgroup_name' in row and row['subgroup_name']:
                                        group_data['subgroup_name'] = row['subgroup_name']
                                    
                                    # Handle boolean fields
                                    if 'is_single_alias' in row:
                                        group_data['is_single_alias'] = row['is_single_alias'].lower() in ['true', '1']
                                    if 'is_active' in row:
                                        group_data['is_active'] = row['is_active'].lower() in ['true', '1']
                                    
                                    # Handle numeric fields
                                    if 'single_alias_id' in row and row['single_alias_id']:
                                        try:
                                            group_data['single_alias_id'] = int(row['single_alias_id'])
                                        except:
                                            pass
                                    
                                    # Handle dates
                                    if 'created_at' in row and row['created_at']:
                                        try:
                                            group_data['created_at'] = datetime.fromisoformat(row['created_at'])
                                        except:
                                            group_data['created_at'] = datetime.now()
                                    else:
                                        group_data['created_at'] = datetime.now()
                                    
                                    if len(group_data) > 1:  # More than just id
                                        group = SharedGroup(**group_data)
                                        db.add(group)
                                        groups_count += 1
                            except Exception as e:
                                print(f"Error with group row: {e}")
                                continue
                    
                    db.commit()
                    print(f"Imported {groups_count} shared groups")
            except Exception as e:
                print(f"Error importing shared groups: {e}")
                db.rollback()
        
        # Import Shared Group Permissions
        if 'permissions_safe_export.csv' in available_files:
            print("Importing shared group permissions...")
            try:
                with open('permissions_safe_export.csv', 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    perms_count = 0
                    
                    for row in reader:
                        required_fields = ['shared_group_id', 'user_id']
                        if all(field in row and row[field] for field in required_fields):
                            try:
                                group_id = int(row['shared_group_id'])
                                existing = db.query(SharedGroupPermission).filter(
                                    SharedGroupPermission.shared_group_id == group_id,
                                    SharedGroupPermission.user_id == row['user_id']
                                ).first()
                                
                                if not existing:
                                    perm_data = {
                                        'shared_group_id': group_id,
                                        'user_id': row['user_id']
                                    }
                                    
                                    # Add optional fields
                                    if 'permission_level' in row and row['permission_level']:
                                        perm_data['permission_level'] = row['permission_level']
                                    if 'granted_by' in row and row['granted_by']:
                                        perm_data['granted_by'] = row['granted_by']
                                    
                                    # Handle dates
                                    if 'granted_at' in row and row['granted_at']:
                                        try:
                                            perm_data['granted_at'] = datetime.fromisoformat(row['granted_at'])
                                        except:
                                            perm_data['granted_at'] = datetime.now()
                                    else:
                                        perm_data['granted_at'] = datetime.now()
                                    
                                    permission = SharedGroupPermission(**perm_data)
                                    db.add(permission)
                                    perms_count += 1
                            except Exception as e:
                                continue
                    
                    db.commit()
                    print(f"Imported {perms_count} shared group permissions")
            except Exception as e:
                print(f"Error importing permissions: {e}")
                db.rollback()
        
        # Verify import
        print("\n🔍 Verification:")
        total_aliases = db.query(CharacterAlias).count()
        total_guilds = db.query(Guild).count()
        print(f"Total aliases in database: {total_aliases}")
        print(f"Total guilds in database: {total_guilds}")
        
        print("\n✅ Import completed successfully!")
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    safe_import()