from telethon import TelegramClient  # type: ignore
from core.config import ScraperConfig
from core.processor import MessageProcessor
from database.engine import engine, Session
from utils.logger import Logger
import os


class TelegramScanner:
    """
    Orchestrates the Telegram scraping lifecycle and client interactions.

    This class manages the high-level workflow: loading state from tracking files,
    configuring the Telethon iterator, and delegating message analysis to the
    MessageProcessor.

    Attributes:
        client (TelegramClient): An authorized Telethon client instance.
        config (ScraperConfig): Configuration object containing group IDs and file paths.
        processor (MessageProcessor): The engine responsible for parsing and saving messages.
    """

    def __init__(
        self,
        client: TelegramClient,
        config: ScraperConfig,
        processor: MessageProcessor,
        logger: Logger,
    ):
        """
        Initializes the scanner with a client and a specific configuration.

        Args:
            client (TelegramClient): The authenticated Telegram client.
            config (ScraperConfig): Configuration settings including target group and verbosity.
        """
        self.client = client
        self.config = config
        self.processor = processor
        self.logger = logger

    async def run(self):
        """
        Executes the main scraping loop asynchronously.

        The method performs the following steps:
        1. Loads the last processed message ID to avoid duplicates.
        2. Configures Telethon's iter_messages with 'min_id' and 'reply_to' filters.
        3. Iterates through new messages, passing them to the processor.
        4. Updates the local tracking file with the latest message ID seen.
        """
        last_id = self._load_last_id()
        self.logger.debug(f"Connected! Fetching new messages after ID {last_id}...")

        messages_saved = 0
        max_id_seen = last_id

        # Prepare iterator arguments
        kwargs = {"min_id": last_id, "reverse": True}  # type: ignore
        if self.config.target_topic_id:
            kwargs["reply_to"] = self.config.target_topic_id

        # Process messages from oldest to newest
        try:
            async for message in self.client.iter_messages(  # type: ignore
                self.config.target_group_id, **kwargs
            ):
                # Create a new session for each message iteration to ensure data integrity
                # and avoid DetachedInstanceErrors.
                with Session(engine) as session:
                    try:
                        # Analyze and extract data (sentiment, risk, etc.)
                        processor_result = await self.processor.process(
                            message, session=session
                        )

                        if processor_result is not None:
                            # Persist the processed data to the database
                            if await self.processor.save(processor_result, session=session):
                                session.commit()  # Commit the transaction for this message
                                messages_saved += 1
                                max_id_seen = max(max_id_seen, message.id)
                    except Exception as e:
                        self.logger.error(f"Error processing message {message.id}: {e}")
                        # Continue to next message even if one fails
                        continue
        except Exception as e:
            self.logger.error(f"Fatal error during message iteration: {e}")
            # If the iterator itself fails (connection drop), we still save what we got.
            pass

        # Update state and log summary
        if messages_saved > 0:
            self._save_last_id(max_id_seen)
            self.logger.success(
                f"Finished! Retrieved and saved {messages_saved} new messages."
            )
        else:
            self.logger.debug("No new messages found.")

    def _load_last_id(self) -> int:
        """
        Retrieves the last saved message ID from the tracking file.

        Returns:
            int: The message ID if found and valid; otherwise 0.
        """
        try:
            if os.path.exists(self.config.tracking_file):
                with open(self.config.tracking_file, "r") as f:
                    content = f.read().strip()
                    return int(content) if content.isdigit() else 0
        except Exception as e:
            self.logger.warning(f"Could not load tracking state from {self.config.tracking_file}: {e}")
        return 0

    def _save_last_id(self, last_id: int):
        """
        Writes the most recent message ID to the tracking file for future runs.

        Args:
            last_id (int): The numerical ID of the latest message processed.
        """
        try:
            with open(self.config.tracking_file, "w") as f:
                f.write(str(last_id))
        except Exception as e:
            self.logger.error(f"Failed to save tracking state to {self.config.tracking_file}: {e}")
