import json
import requests
from datetime import datetime


def ts():
    """Return current timestamp string for logging."""
    return (f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}")[:-5]


def post_to_discord(message, bot_name, webhook_url):
    """Post a message to Discord via webhook.
    
    Args:
        message: The message content to post
        bot_name: Name to display for the bot in Discord
        webhook_url: Discord webhook URL
        
    Raises:
        ValueError: If message exceeds Discord's 2000-character limit
        requests.RequestException: If the POST request fails
    """
    if len(message) > 2000:
        raise ValueError(
            f"Message exceeds Discord limit (2000 chars). "
            f"Current length: {len(message)} chars. "
            f"Message preview: {message[:100]}..."
        )
    
    payload = {"content": message, "username": bot_name}
    response = requests.post(webhook_url, json=payload)
    response.raise_for_status()


def parse_json_response(raw_text):
    """Parse JSON response from Claude, handling common formatting issues.
    
    Strips markdown code blocks (```json ... ```) and attempts to parse.
    
    Args:
        raw_text: Raw text response from Claude API
        
    Returns:
        dict: Parsed JSON object
        
    Raises:
        json.JSONDecodeError: If JSON cannot be parsed, includes context
    """
    raw = raw_text.strip()
    
    # Strip markdown code blocks if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first line (opening ```) and last line (closing ```)
        raw = "\n".join(lines[1:-1])
    
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Provide helpful debugging context
        start = max(0, e.pos - 50)
        end = min(len(raw), e.pos + 50)
        context = raw[start:end]
        error_msg = (
            f"JSON parse error at position {e.pos}: {e.msg}\n"
            f"Context: ...{context}...\n"
            f"Full response:\n{raw}"
        )
        raise json.JSONDecodeError(error_msg, raw, e.pos)


def post_to_discord_safe(message, bot_name, webhook_url):
    """Wrapper around post_to_discord with error handling and logging.
    
    Handles validation errors (message too long) and network errors gracefully.
    
    Args:
        message: Message to post
        bot_name: Bot name for Discord display
        webhook_url: Discord webhook URL
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        post_to_discord(message, bot_name, webhook_url)
        return True
    except ValueError as e:
        # Message too long
        print(f"[{ts()}] Discord payload validation error: {e}")
        return False
    except requests.RequestException as e:
        print(f"[{ts()}] Failed to post to Discord: {e}")
        return False