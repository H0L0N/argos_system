import os
from typing import Optional, Type, TypeVar
from sqlmodel import SQLModel, Session, create_engine, select, text
from database.models import *
from modules.semantic_embedder import get_embedding
from utils.logger import Logger

logger = Logger()

# Ideally, you'd load this from a config file or .env using python-dotenv or pydantic-settings
# Format: postgresql://user:password@localhost:5432/dbname
# If using async: postgresql+asyncpg://...
POSTGRES_URL = os.getenv(
    "DATABASE_URL", "postgresql://argos:argos@localhost:5432/argos_system"
)

AGENT_POSTGRES_URL = os.getenv(
    "AGENT_DATABASE_URL", "postgresql://sql_agent:sql_agent@localhost:5432/argos_system"
)

# Create the engine. echo=True is useful for debugging SQL queries.
engine = create_engine(
    POSTGRES_URL,
    # connect_args={"options": "-c search_path=app"},  # activate if search_path not previously set in psql
    echo=False,
)

agent_engine = create_engine(
    AGENT_POSTGRES_URL,
    echo=False,
)


def init_db():
    """
    Creates all tables based on the models defined in schema.py.
    In a production app, you might want to use Alembic for migrations instead.
    """
    SQLModel.metadata.create_all(engine)


def seed_emotions():
    """
    Seeds the Emotion lookup table with all 28 GoEmotions labels.
    This is idempotent: it only inserts rows that are not already present.
    """
    from sqlmodel import select
    from database.models import (
        Emotion,
        GoEmotionLabel,
    )  # avoid circular import at module level

    with Session(engine) as session:
        existing = {e.label for e in session.exec(select(Emotion)).all()}
        missing = [
            Emotion(label=label) for label in GoEmotionLabel if label not in existing
        ]
        if missing:
            for emotion in missing:
                session.add(emotion)
            session.commit()
            logger.success(f"Seeded {len(missing)} emotion labels into the Emotion table.")
        else:
            logger.debug("Emotion table already seeded, skipping.")


def delete_db():
    """
    Deletes all tables based on the models defined in schema.py
    """
    SQLModel.metadata.drop_all(engine)


def get_session():
    """
    Dependency to provide a database session.
    """
    with Session(engine) as session:
        yield session


T = TypeVar("T", bound=SQLModel)


class Repository:
    """Class to access to crud methods"""

    @staticmethod
    def create(instance: T, session: Optional[Session] = None) -> T:
        """
        Saves a new instance in the repository.

        Args:
            instance (T): The SQLModel instance to save.
            session (Session, optional): An existing session to use.

        Returns:
            T: The saved instance.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            if session:
                session.add(instance)
                session.flush()
                session.refresh(instance)
                return instance

            with Session(engine) as session:
                session.add(instance)
                session.commit()
                session.refresh(instance)
                return instance
        except Exception as e:
            logger.error(f"Failed to save {type(instance).__name__}", exc=e)
            raise

    @staticmethod
    def upsert(instance: T, session: Optional[Session] = None) -> T:
        """
        Updates an instance that already exists in the repository. Also inserts if it doesn't exist.

        Args:
            instance (T): The SQLModel instance to upsert.
            session (Session, optional): An existing session to use.

        Returns:
            T: The merged instance.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            if session:
                merged = session.merge(instance)
                session.flush()
                session.refresh(merged)
                return merged

            with Session(engine) as session:
                merged = session.merge(instance)
                session.commit()
                session.refresh(merged)
                return merged
        except Exception as e:
            logger.error(f"Failed to upsert {type(instance).__name__}", exc=e)
            raise

    @staticmethod
    def get(model: Type[T], id: str, session: Optional[Session] = None) -> Optional[T]:
        """
        Retrieves a single instance by its ID.

        Args:
            model (Type[T]): The SQLModel class.
            id (str): The primary key ID.
            session (Session, optional): An existing session to use.

        Returns:
            Optional[T]: The instance if found, None otherwise.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            if session:
                return session.get(model, id)

            with Session(engine) as session:
                instance = session.get(model, id)
                return instance
        except Exception as e:
            logger.error(f"Failed to get {model.__name__} with id={id}", exc=e)
            raise

    @staticmethod
    def get_all(model: Type[T], session: Optional[Session] = None) -> list[T]:
        """
        Retrieves all instances of a model.

        Args:
            model (Type[T]): The SQLModel class.
            session (Session, optional): An existing session to use.

        Returns:
            list[T]: A list of all instances found.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            if session:
                return list(session.exec(select(model)).all())

            with Session(engine) as session:
                return list(session.exec(select(model)).all())
        except Exception as e:
            logger.error(f"Failed to get all {model.__name__}", exc=e)
            raise

    @staticmethod
    async def buscar_mensajes_similares(
        texto_busqueda: str, session: Session | None = None, limite: int = 5
    ) -> list[Message]:
        """
        Performs a semantic search for messages similar to the provided text.

        Args:
            texto_busqueda (str): The text to search for.
            session (Session, optional): An existing session to use.
            limite (int): Maximum number of results to return.

        Returns:
            list[Message]: A list of similar messages.

        Raises:
            Exception: If the embedding generation or database query fails.
        """

        try:
            if session:
                # 1. Convertimos la frase que buscas en un vector (usando tu función actual)
                vector_busqueda = await get_embedding(texto_busqueda)

                # 2. Creamos la consulta SQL
                statement = (
                    select(Message)
                    # Es buena idea filtrar los que no tienen vector (los de las fotos, etc)
                    .where(Message.embedding.is_not(None))  # type: ignore
                    # Ordenamos por los que tengan la menor "distancia coseno"
                    .order_by(Message.embedding.cosine_distance(vector_busqueda)).limit(limite)  # type: ignore
                )

                # 3. Ejecutamos la consulta
                resultados = session.exec(statement)
                return list(resultados.all())

            with Session(engine) as session:
                # 1. Convertimos la frase que buscas en un vector (usando tu función actual)
                vector_busqueda = await get_embedding(texto_busqueda)

                # 2. Creamos la consulta SQL
                statement = (
                    select(Message)
                    # Es buena idea filtrar los que no tienen vector (los de las fotos, etc)
                    .where(Message.embedding.is_not(None))  # type: ignore
                    # Ordenamos por los que tengan la menor "distancia coseno"
                    .order_by(Message.embedding.cosine_distance(vector_busqueda)).limit(limite)  # type: ignore
                )

                # 3. Ejecutamos la consulta
                resultados = session.exec(statement)
                return list(resultados.all())
        except Exception as e:
            logger.error(f"Failed to get messages similar to {texto_busqueda}", exc=e)
            raise

    @staticmethod
    def get_messages_by_person(
        person_id: int, session: Optional[Session] = None, with_embeddings_only: bool = False
    ) -> list[Message]:
        """
        Retrieves all messages for a given person.

        Args:
            person_id (int): The Telegram user ID.
            session (Session, optional): An existing session to use.
            with_embeddings_only (bool): If True, only returns messages that have embeddings.

        Returns:
            list[Message]: A list of messages for the person.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            stmt = select(Message).where(Message.person_id == person_id)
            if with_embeddings_only:
                stmt = stmt.where(Message.embedding.is_not(None))  # type: ignore

            if session:
                return list(session.exec(stmt).all())

            with Session(engine) as session:
                return list(session.exec(stmt).all())
        except Exception as e:
            logger.error(f"Failed to get messages for person {person_id}", exc=e)
            raise

class AgentRepository:
    """Repository specifically for executing read-only Agent queries securely."""

    @staticmethod
    def execute_query(query: str) -> list[dict]:
        """
        Executes a raw SQL query and returns the results as a list of dictionaries.

        Args:
            query (str): The raw SQL query string.

        Returns:
            list[dict]: A list of result rows as mappings.

        Raises:
            Exception: If the SQL query execution fails.
        """
        try:
            with Session(agent_engine) as session:
                result = session.exec(text(query)).mappings().all()
                return list(result)
        except Exception as e:
            logger.error(f"Failed to execute agent query", exc=e)
            raise
