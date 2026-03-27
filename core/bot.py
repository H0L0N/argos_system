import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import User

# Load environment variables
load_dotenv()

# Get the API credentials from .env
# You need to register on https://my.telegram.org/apps to get these

TRACKING_FILE = "last_saved_id.txt"
HISTORY_FILE = "group_history.txt"


async def scrape_history(api_id: int, api_hash: str, phone_number: str, target_group_id: int, target_topic_id: int | None) -> bool:

    print("Starting Telethon Client...")
    # 'bot_session' creates a local file to save your login session securely
    client = TelegramClient("bot_session", api_id, api_hash)

    # Start the client. It will prompt for phone/code in the terminal if needed.
    client.start(phone=phone_number)

    last_id = 0
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                last_id = int(content)

    print(
        f"Connected! Fetching new messages from {target_group_id} after message ID {last_id}..."
    )

    messages_saved = 0
    max_id_seen = last_id

    # Open file in APPEND mode ("a")
    with open(HISTORY_FILE, "a", encoding="utf-8") as file:
        # reverse=True fetches from oldest (newest after last_id) to newest (present)
        kwargs = {
            "min_id": last_id,
            "reverse": True
        }

        # ensures only msgs from this group's topic are accessed
        if target_topic_id is not None:
            kwargs["reply_to"] = target_topic_id

        async for message in client.iter_messages(
            target_group_id, min_id=last_id, reverse=True
        ):
            # Try to get the sender's display name
            sender_name = "Unknown"
            if getattr(message, "sender", None):
                if isinstance(message.sender, User):
                    sender_name = (
                        message.sender.username or message.sender.first_name or "User"
                    )
                else:
                    # If it's a channel forwarding or system message
                    sender_name = getattr(message.sender, "title", "Channel/Group")

            # Safely extract text (some messages are just photos or stickers)
            text = message.text if message.text else "[Media / Non-text message]"
            date = (
                message.date.strftime("%Y-%m-%d %H:%M:%S")
                if message.date
                else "Unknown Date"
            )

            # Format and save the log line
            # We add message.id so you can uniquely identify messages
            log_line = f"[{message.id}] [{date}] {sender_name}: {text}"
            print(log_line)
            file.write(log_line + "\n")

            messages_saved += 1
            max_id_seen = max(max_id_seen, message.id)

    # Update our tracking file with the newest ID we just downloaded
    if messages_saved > 0:
        with open(TRACKING_FILE, "w") as f:
            f.write(str(max_id_seen))

    print(f"\nFinished! Appended {messages_saved} new messages to {HISTORY_FILE}.")
    return True


def main():
    """Main entry point called by main.py"""

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    phone_number = "626522549"
    target_group = -1001234839940
    target_topic = 16864

    if not api_id or not api_hash:
        print("Error: API_ID or API_HASH not found in .env")
        print("Please add them to your .env file.")
        return False
    
    try:
        asyncio.run(scrape_history(int(api_id), api_hash, phone_number, target_group, target_topic))
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")


if __name__ == "__main__":
    main()
