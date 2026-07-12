"""
Main entry point for Railway deployment.
Runs both the Discord bot and FastAPI server concurrently.
"""

import asyncio
import os
import threading
import uvicorn
from dotenv import load_dotenv

load_dotenv()

def run_api():
    """Run the FastAPI server."""
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

def run_bot():
    """Run the Discord bot."""
    # Import here to avoid circular imports
    from bot import bot, DISCORD_TOKEN
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("Warning: DISCORD_TOKEN not set, bot not started")

def main():
    """Run both services."""
    # Check what to run based on environment
    run_mode = os.getenv("RUN_MODE", "both").lower()
    
    if run_mode == "api":
        # Run only API (useful for testing)
        print("Starting API server only...")
        run_api()
    elif run_mode == "bot":
        # Run only bot (useful for testing)
        print("Starting Discord bot only...")
        run_bot()
    else:
        # Run both (default for production)
        print("Starting both API server and Discord bot...")
        
        # Keep the web process in the main thread so Railway health and
        # lifecycle management follow the API rather than the Discord client.
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        run_api()

if __name__ == "__main__":
    main()

