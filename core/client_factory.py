import os
from dotenv import load_dotenv
from telethon import TelegramClient  # type: ignore
from errors.NoApiKeyError import NoApiKeyError
from utils.logger import Logger

# Load environment variables
load_dotenv()


class TelegramClientFactory:
    """Handles the initialization and authentication of the Telethon client."""

    def __init__(
        self,
        logger: Logger,
        api_id: str,
        api_hash: str,
        phone_number: str,
        session_name: str = "bot_session",
    ):
        """
        Initializes the Telegram client factory.

        Args:
            logger (Logger): Logger instance.
            api_id (str): Telegram API ID.
            api_hash (str): Telegram API Hash.
            phone_number (str): Phone number for authentication.
            session_name (str): Name of the Telethon session.

        Raises:
            ValueError: If api_id, api_hash, or phone_number is missing.
        """
        if not api_id or not api_hash:
            raise ValueError("api_id and api_hash must be explicitly provided")
        if not phone_number:
            raise ValueError("phone_number must be explicitly provided")
            
        self.session_name = session_name
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.logger = logger

    def validate_config(self) -> bool:
        """
        Checks if the required API credentials are present.
        
        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        # Checks if the required API credentials are present.
        if not self.api_id or not self.api_hash:
            return False
        return True

    async def get_authenticated_client(self) -> TelegramClient:
        """
        Returns an authenticated Telethon client.
        
        This method will start the client and perform authentication.

        Returns:
            TelegramClient: An authenticated client instance.

        Raises:
            NoApiKeyError: If API credentials fail validation.
            ConnectionError: If authentication is unsuccessful.
        """
        """Returns an authenticated Telethon client."""
        if not self.validate_config():
            raise NoApiKeyError()

        client = TelegramClient(self.session_name, int(self.api_id), self.api_hash)  # type: ignore

        self.logger.debug("Connecting to Telegram...")
        await client.start(phone=self.phone_number)  # type: ignore

        if not await client.is_user_authorized():
            self.logger.error("Unsuccessful authentication to Telegram.")
            raise ConnectionError("User not authorized.")

        self.logger.success("Telegram client authenticated successfully.")
        return client
