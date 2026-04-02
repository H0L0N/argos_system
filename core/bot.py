import asyncio
from core.client_factory import TelegramClientFactory
from core.config import ScraperConfig
from core.processor import MessageProcessor
from core.scanner import TelegramScanner
from database.engine import init_db, seed_emotions, Session, engine
from errors.NoApiKeyError import NoApiKeyError
from modules.emotion_analysis import analyze_emotions
from modules.risk_profiling import update_all_risk_profiles
from modules.semantic_embedder import get_embedding
from utils.logger import Logger


class Bot:
    """Orchestrates the Telegram scraping process."""

    def __init__(
        self, config: ScraperConfig, factory: TelegramClientFactory, logger: Logger
    ):
        """
        Initializes the Bot with configuration and dependencies.

        Args:
            config (ScraperConfig): Configuration for the scraper.
            factory (TelegramClientFactory): Factory to create and authenticate the Telegram client.
            logger (Logger): Logger instance for status reporting.
        """
        self.config = config
        self.factory = factory
        self.logger = logger

    async def start(self):
        """
        Initializes dependencies and starts the scraping process.
        
        This method will seed the database, authenticate the client, and enter
        a periodic scraping loop.

        Raises:
            NoApiKeyError: If API credentials are missing.
            KeyboardInterrupt: If the user interrupts the operation.
            Exception: For any fatal error during bot execution.
        """
        # Initializes dependencies and starts the scraping process.
        seed_emotions()

        try:
            client = await self.factory.get_authenticated_client()
            async with client:
                processor = MessageProcessor(
                    analyze_emotions=analyze_emotions,
                    get_embedding=get_embedding,
                    logger=self.logger,
                )
                scanner = TelegramScanner(client, self.config, processor, self.logger)

                # First complete scrape
                await scanner.run()

                self.logger.success(
                    f"Initial scrape complete. Starting periodic tasks every {self.config.scraping_interval_seconds}s."
                )

                while True:
                    await asyncio.sleep(self.config.scraping_interval_seconds)

                    self.logger.debug(
                        "Starting periodic scrape and risk profile update..."
                    )
                    try:
                        # 1. Scrape new messages
                        await scanner.run()

                        # 2. Update risk profiles
                        with Session(engine) as session:
                            await update_all_risk_profiles(session)
                            session.commit()

                        self.logger.success("Periodic tasks completed successfully.")
                    except Exception as e:
                        self.logger.error("Error during periodic tasks", exc=e)
        except NoApiKeyError as e:
            # this should never be possible if the correct UI flow is followed
            raise e
        except KeyboardInterrupt:
            raise
        except Exception as e:
            raise e
