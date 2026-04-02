from dataclasses import dataclass
from datetime import timezone
from telethon.tl.types import User, Channel, Chat  # type: ignore
from telethon.tl.custom import Message as CustomMessage  # type: ignore

from database.engine import Repository, Session
from database.models import MessageEmotion, Person, Message as DbMessage, RiskProfile
from utils.logger import Logger
from typing import Awaitable, Callable, Optional, cast

# contracts that functions must fulfill
type EmotionAnalyzer = Callable[[DbMessage], Awaitable[DbMessage]]
type RiskProfiler = Callable[
    [Person, list[MessageEmotion], Session | None], Awaitable[RiskProfile]
]
type SemanticEmbedder = Callable[[str], Awaitable[list[float]]]


@dataclass
class ProcessResult:
    """
    A container for the results of a processed Telegram message.

    Attributes:
        person (Person): The SQLModel instance representing the sender.
        message (DbMessage): The SQLModel instance representing the message.
        is_new (bool): True if the message was newly created, False if it already existed in the DB.
    """

    person: Person
    message: DbMessage
    is_new: bool = True


class MessageProcessor:
    """
    Handles data extraction, transformation, and preparation for persistence.

    This class converts raw Telethon messages into database-ready objects,
    extracting sender information and formatting content according to
    database constraints.

    Attributes:
        verbose (bool): If True, enables detailed logging of the processing steps.
    """

    def __init__(
        self,
        analyze_emotions: EmotionAnalyzer,
        get_embedding: SemanticEmbedder,
        logger: Logger,
    ):
        """
        Initializes the processor.

        Args:
            verbose (bool): Whether to log processing details to the console.
        """
        self.analyze_emotions = analyze_emotions
        self.get_embedding = get_embedding
        self.logger = logger

    async def process(
        self, message: CustomMessage, session: Optional[Session] = None
    ) -> ProcessResult | None:
        """
        Transforms a raw Telethon message into a ProcessResult.

        This method:
        1. Identifies and fetches the sender (User or Channel).
        2. Normalizes text content and dates (UTC).
        3. Checks the repository for existing records to prevent duplicates.
        4. Prepares objects for subsequent analysis (Emotions, Risk, etc.).

        Args:
            message (CustomMessage): The raw message object from Telethon.
            session (Optional[Session]): The active database session.

        Returns:
            ProcessResult | None: A container with the prepared DB objects,
                                 or None if processing fails or sender is invalid.
        """
        try:
            sender_id = cast(int | None, message.sender_id)
            text = cast(str | None, message.message)

            if sender_id is None or not text or not text.strip():
                # Ignore messages with no text (e.g. only media, stickers)
                return

            sender = await message.get_sender()  # type: ignore

            # Determine the display name based on entity type
            sender_name = "Unknown"  # in case is None or Chat
            if isinstance(sender, User):
                sender_name = sender.first_name or sender.username or "No name"
            elif isinstance(sender, Channel):
                sender_name = sender.title or "Channel/Group"

            date_utc = message.date.astimezone(timezone.utc)  # type: ignore

            self.logger.info(
                f"[{message.id}] [{date_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}] {sender_name}: {text[:50]}...",
            )

            # Fetch or initialize Person
            person = Repository.get(Person, str(sender_id), session=session)
            if person is None:
                person = Person(id=sender_id, name=sender_name, risk_level=0)

            # Fetch or initialize Message
            db_message = Repository.get(DbMessage, str(message.id), session=session)
            is_new_message = db_message is None
            if is_new_message:
                db_message = DbMessage(
                    id=message.id,
                    text=text[:4096],  # Telegram's character limit
                    date=date_utc.date(),
                    person_id=sender_id,
                )

            # Emotion analysis (GoEmotions)
            try:
                db_message = await self.analyze_emotions(db_message)
            except Exception as e:
                self.logger.warning(f"Emotion analysis failed for message {message.id}: {e}")

            # embedding calculation
            try:
                embedding = await self.get_embedding(db_message.text)
                db_message.embedding = embedding
            except Exception as e:
                self.logger.warning(f"Embedding calculation failed for message {message.id}: {e}")

            return ProcessResult(person=person, message=db_message, is_new=is_new_message)

        except Exception as e:
            self.logger.error(f"Failed to process message {message.id}: {e}")
            return None

    async def save(
        self, process_result: ProcessResult, session: Optional[Session] = None
    ) -> bool:
        """
        Commits the processed result to the database.

        Args:
            process_result (ProcessResult): The container with objects to save.
            session (Optional[Session]): The active database session.

        Returns:
            bool: True if the save operation was successful, False otherwise.
        """
        try:
            # Save core entities
            Repository.upsert(process_result.person, session=session)
            Repository.create(process_result.message, session=session)

            # Save associated emotions only for new messages to avoid IntegrityError
            if process_result.is_new:
                for emotion in process_result.message.message_emotions:
                    Repository.create(emotion, session=session)

            return True
        except Exception as e:
            self.logger.error(f"Failed to save process result: {e}")
            return False
