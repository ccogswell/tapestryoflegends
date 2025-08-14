#!/usr/bin/env python3
"""
Main entry point for the Discord D&D Bot with web server for deployment
This file serves as the primary entry point for Replit deployments
"""

import asyncio
import threading
import os
import sys
import time
import logging
import discord
from flask import Flask, jsonify
from flask_session import Session
from main import main as run_discord_bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app for health checks and deployment compatibility
app = Flask(__name__, template_folder='web/templates')

# Configure Flask-Session for OAuth
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

# Global variable to track bot status
bot_status = {
    "running": False, 
    "error": None, 
    "started_at": None,
    "initialization_complete": False,
    "token_configured": False
}

@app.route('/')
def health_check():
    """Health check endpoint for deployment - returns 200 status"""
    return jsonify({
        "status": "healthy",
        "service": "Discord D&D Bot",
        "bot_running": bot_status["running"],
        "version": "1.0.0"
    }), 200

@app.route('/status')
def detailed_status():
    """Detailed status endpoint with more information"""
    return jsonify({
        "discord_bot": {
            "running": bot_status["running"],
            "error": bot_status["error"],
            "started_at": bot_status["started_at"]
        },
        "web_server": "running",
        "environment": "production" if os.getenv('REPLIT_DEPLOYMENT') else "development"
    }), 200

@app.route('/health')
def health():
    """Additional health endpoint for monitoring"""
    # Always return 200 for deployment health checks, even if bot is down
    # This prevents deployment from failing due to Discord connectivity issues
    status = "ok" if bot_status["running"] else "degraded"
    return jsonify({
        "status": status, 
        "bot_running": bot_status["running"],
        "message": bot_status["error"] if bot_status["error"] else "Service operational"
    }), 200

# Redirect root to web interface if available
@app.route('/web')
def web_redirect():
    """Redirect to web interface login"""
    try:
        from web.routes import web_bp
        from flask import redirect, url_for
        return redirect(url_for('web.dashboard'))
    except ImportError:
        return jsonify({"error": "Web interface not available"}), 404

def run_discord_bot_thread():
    """Run Discord bot in a separate thread with comprehensive error handling"""
    try:
        logger.info("Initializing Discord bot thread...")
        bot_status["running"] = False
        bot_status["error"] = None
        bot_status["started_at"] = time.time()
        
        # Check token availability before starting
        token = os.getenv('DISCORD_BOT_TOKEN')
        if not token or not token.strip():
            error_msg = "DISCORD_BOT_TOKEN is missing or empty"
            bot_status["error"] = error_msg
            bot_status["token_configured"] = False
            logger.error(error_msg)
            return
        
        bot_status["token_configured"] = True
        logger.info(f"Discord token configured (length: {len(token.strip())})")
        
        # Add startup delay for web server initialization
        logger.info("Waiting 2 seconds for web server initialization...")
        time.sleep(2)
        
        logger.info("Starting Discord bot...")
        # Don't set running=True until bot actually connects
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the bot with timeout protection
        try:
            loop.run_until_complete(run_discord_bot())
        except asyncio.TimeoutError:
            error_msg = "Discord bot startup timed out"
            logger.error(error_msg)
            bot_status["error"] = error_msg
        except discord.LoginFailure:
            error_msg = "Invalid Discord bot token - please check your DISCORD_BOT_TOKEN secret"
            logger.error(error_msg)
            bot_status["error"] = error_msg
        except discord.HTTPException as e:
            error_msg = f"Discord API error: {e}"
            logger.error(error_msg)
            bot_status["error"] = error_msg
        
    except Exception as e:
        error_msg = f"Unexpected Discord bot error: {type(e).__name__}: {e}"
        bot_status["running"] = False
        bot_status["error"] = error_msg
        logger.error(error_msg, exc_info=True)
        # Don't re-raise the exception to keep the web server running
    finally:
        bot_status["initialization_complete"] = True
        if bot_status["running"]:
            logger.info("Discord bot started successfully")
        else:
            logger.warning("Discord bot failed to start - web server will continue running")

def main():
    """Main function to start both Discord bot and web server with enhanced error handling"""
    logger.info("Initializing Discord D&D Bot with web server...")
    
    # Check environment variables
    token = os.getenv('DISCORD_BOT_TOKEN')
    session_secret = os.getenv('SESSION_SECRET')
    
    # Generate session secret if not provided
    if not session_secret:
        import secrets
        session_secret = secrets.token_hex(32)
        logger.warning("No SESSION_SECRET provided, using generated secret (sessions will not persist across restarts)")
    
    # Validate Discord token
    if not token or not token.strip():
        error_msg = "DISCORD_BOT_TOKEN environment variable not set or empty"
        logger.error(error_msg)
        logger.info("Please set your Discord bot token in the Secrets tab")
        bot_status["error"] = "Missing DISCORD_BOT_TOKEN"
        bot_status["token_configured"] = False
        # Continue with web server for health checks even without token
    else:
        bot_status["token_configured"] = True
        logger.info("Discord token configured successfully")
    
    # Configure session secret
    app.secret_key = session_secret
    logger.info("SESSION_SECRET configured")
    
    # Register web interface blueprint with error handling
    try:
        # Add current directory to Python path for imports
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
            
        from web.routes import web_bp
        from web.auth import DiscordAuth
        
        # Initialize Discord OAuth
        auth = DiscordAuth(app)
        app.config['DISCORD_AUTH'] = auth  # Store auth instance for routes to access
        
        # Register the web blueprint
        app.register_blueprint(web_bp)
        
        # Add template context processor for auth
        @app.template_global()
        def is_admin():
            from flask import session
            if 'discord_user' not in session:
                return False
            return auth.is_admin(session['discord_user']['id'])
        
        logger.info("Web interface initialized successfully")
        
        # Store bot reference for web interface access to Discord data
        app.config['DISCORD_BOT_INSTANCE'] = None
        
    except ImportError as ie:
        logger.error(f"Failed to import web interface modules: {ie}")
        import traceback
        logger.error(f"Import traceback: {traceback.format_exc()}")
        logger.info("Bot will continue running without web interface")
    except Exception as e:
        logger.error(f"Failed to initialize web interface: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        logger.info("Bot will continue running without web interface")
    
    # Start Discord bot in background thread
    logger.info("Starting Discord bot thread...")
    bot_thread = threading.Thread(target=run_discord_bot_thread, daemon=True)
    bot_thread.start()
    
    # Start Flask web server with enhanced error handling
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting web server on port {port}")
    logger.info("Bot status endpoints available at /, /status, and /health")
    
    try:
        # Configure Flask for production deployment
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=False,
            threaded=True,
            use_reloader=False  # Prevent double startup in development
        )
    except OSError as e:
        if "Address already in use" in str(e):
            logger.error(f"Port {port} is already in use. Trying port {port + 1}")
            try:
                app.run(host='0.0.0.0', port=port + 1, debug=False, threaded=True)
            except Exception as e2:
                logger.error(f"Failed to start web server on alternate port: {e2}")
                sys.exit(1)
        else:
            logger.error(f"Web server OS error: {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Web server error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()