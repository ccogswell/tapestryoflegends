import os
import uuid
from werkzeug.utils import secure_filename
from google.cloud import storage

def upload_avatar(file, user_id):
    """Upload avatar file to object storage and return the URL"""
    if not file or not file.filename:
        return None
    
    try:
        # Generate unique filename
        file_extension = os.path.splitext(secure_filename(file.filename))[1]
        unique_filename = f"avatar_{user_id}_{uuid.uuid4()}{file_extension}"
        
        # Use object storage environment variables
        private_dir = os.environ.get('PRIVATE_OBJECT_DIR', '').rstrip('/')
        if not private_dir:
            return None
        
        # For now, return a placeholder URL since we need to implement full object storage
        # This would be replaced with actual object storage upload
        return f"/objects/avatars/{unique_filename}"
        
    except Exception as e:
        print(f"Error uploading avatar: {e}")
        return None

def get_default_avatar():
    """Get default avatar URL"""
    return "https://cdn.discordapp.com/embed/avatars/0.png"