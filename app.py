import asyncio
import threading
from flask import Flask, jsonify
import os
from main import main as run_discord_bot

# Create Flask app for health checks
app = Flask(__name__)

# Global variable to track bot status
bot_status = {"running": False, "error": None}

@app.route('/')
def health_check():
    """Health check endpoint for deployment"""
    return jsonify({
        "status": "healthy",
        "service": "Discord D&D Bot",
        "bot_running": bot_status["running"]
    }), 200

@app.route('/status')
def status():
    """Detailed status endpoint"""
    return jsonify({
        "discord_bot": {
            "running": bot_status["running"],
            "error": bot_status["error"]
        },
        "web_server": "running"
    }), 200

def run_discord_bot_thread():
    """Run Discord bot in a separate thread"""
    try:
        bot_status["running"] = True
        bot_status["error"] = None
        print("Starting Discord bot...")
        asyncio.run(run_discord_bot())
    except Exception as e:
        bot_status["running"] = False
        bot_status["error"] = str(e)
        print(f"Discord bot error: {e}")

def start_services():
    """Start both Discord bot and web server"""
    # Start Discord bot in background thread
    bot_thread = threading.Thread(target=run_discord_bot_thread, daemon=True)
    bot_thread.start()
    
    # Start Flask web server
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting web server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    start_services()