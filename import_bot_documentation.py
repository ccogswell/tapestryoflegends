#!/usr/bin/env python3
"""
Import bot documentation for VPS deployment
"""
import os
import json
from datetime import datetime

def import_bot_documentation():
    """Import bot documentation from export file"""
    print("Starting bot documentation import...")
    
    export_filename = 'bot_documentation_export.json'
    
    if not os.path.exists(export_filename):
        print(f"❌ Export file not found: {export_filename}")
        print("Make sure you've uploaded the documentation export file to the VPS.")
        return False
    
    try:
        with open(export_filename, 'r', encoding='utf-8') as f:
            export_data = json.load(f)
        
        print(f"📄 Found export from: {export_data.get('export_timestamp', 'Unknown')}")
        
        imported_count = 0
        skipped_count = 0
        
        # Import each documentation file
        for filename, file_info in export_data['documentation_files'].items():
            try:
                # Skip if file already exists (optional - could add overwrite option)
                if os.path.exists(filename):
                    print(f"! {filename} already exists, skipping")
                    skipped_count += 1
                    continue
                
                # Create directories if needed
                dir_path = os.path.dirname(filename)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                
                # Write the file content
                content = file_info['content']
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                lines = file_info.get('lines', len(content.splitlines()))
                print(f"✓ Imported {filename} ({lines} lines)")
                imported_count += 1
                
            except Exception as e:
                print(f"✗ Failed to import {filename}: {e}")
        
        print(f"\n✅ Documentation import completed!")
        print(f"📄 Imported: {imported_count} files")
        print(f"⏭️  Skipped: {skipped_count} files (already exist)")
        
        # Verify key files exist
        key_files = ['DISCORD_BOT_COMMANDS.md', 'README.md']
        print(f"\n🔍 Verification:")
        for key_file in key_files:
            if os.path.exists(key_file):
                print(f"✓ {key_file} is available")
            else:
                print(f"✗ {key_file} is missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import documentation: {e}")
        return False

if __name__ == "__main__":
    import_bot_documentation()