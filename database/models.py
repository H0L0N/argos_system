from typing import Optional
import enum
from datetime import date as date_t
from pgvector.sqlalchemy import Vector  # type: ignore
from sqlmodel import BigInteger, Column, Field, SQLModel, Relationship


class GoEmotionLabel(str, enum.Enum):
    """The 28 emotion labels from the Google GoEmotions dataset, used by roberta-base-go_emotions."""

    admiration = "admiration"
    amusement = "amusement"
    anger = "anger"
    annoyance = "annoyance"
    approval = "approval"
    caring = "caring"
    confusion = "confusion"
    curiosity = "curiosity"
    desire = "desire"
    disappointment = "disappointment"
    disapproval = "disapproval"
    disgust = "disgust"
    embarrassment = "embarrassment"
    excitement = "excitement"
    fear = "fear"
    gratitude = "gratitude"
    grief = "grief"
    joy = "joy"
    love = "love"
    nervousness = "nervousness"
    optimism = "optimism"
    pride = "pride"
    realization = "realization"
    relief = "relief"
    remorse = "remorse"
    sadness = "sadness"
    surprise = "surprise"
    neutral = "neutral"


class Person(SQLModel, table=True):
    """Represents a user being tracked by the bot. Holds identity and overall risk level."""

    class Config:
        validate_assignment = True

    id: int = Field(
        primary_key=True, sa_type=BigInteger
    )  # Telegram user_id: signed int64
    name: str = Field(
        min_length=1, default="Unknown"
    )  # Telegram first_name: min 1 char
    risk_level: int = Field(ge=0, le=5)

    # Relationships
    messages: list["Message"] = Relationship(back_populates="person")
    risk_profile: "RiskProfile" = Relationship(
        back_populates="person", sa_relationship_kwargs={"uselist": False}
    )


class Message(SQLModel, table=True):
    """A single chat message sent by a Person. The entry point for sentiment and emotion analysis."""

    class Config:
        validate_assignment = True

    id: int = Field(
        primary_key=True, sa_type=BigInteger
    )  # Telegram message_id: sequential int per chat
    text: str = Field(max_length=4096)  # Telegram hard limit: 4096 UTF-8 chars
    date: date_t
    person_id: int | None = Field(
        default=None, foreign_key="person.id", sa_type=BigInteger
    )
    embedding: Optional[list[float]] = Field(
        sa_column=Column(Vector(384)), default=None
    )

    # relationships
    person: Optional["Person"] = Relationship(back_populates="messages")
    message_emotions: list["MessageEmotion"] = Relationship(
        back_populates="message", sa_relationship_kwargs={"lazy": "selectin"}
    )


class Emotion(SQLModel, table=True):
    """Lookup/reference table containing the 28 fixed GoEmotions labels. Seeded once at startup."""

    label: GoEmotionLabel = Field(primary_key=True)

    # relationships
    risk_profiles: list["RiskProfile"] = Relationship(back_populates="emotion")


class MessageEmotion(SQLModel, table=True):
    """Join table linking a Message to an Emotion with the model's confidence score.

    Composite PK (message_id, emotion_label) prevents duplicate emotion entries per message.
    """

    # better readability
    __tablename__ = "message_emotion"  # type: ignore

    message_id: int = Field(
        foreign_key="message.id", primary_key=True, sa_type=BigInteger
    )
    emotion_label: GoEmotionLabel = Field(foreign_key="emotion.label", primary_key=True)
    score: float

    # relationships
    message: "Message" = Relationship(back_populates="message_emotions")


class RiskProfile(SQLModel, table=True):
    """A risk assessment record for a Person, classified by type (e.g., behavioral, security, compliance)."""

    __tablename__ = "risk_profile"  # type: ignore

    class Config:
        validate_assignment = True

    person_id: int = Field(
        primary_key=True, foreign_key="person.id", sa_type=BigInteger
    )
    emotional_trend: GoEmotionLabel = Field(foreign_key="emotion.label")
    security_score: float = Field(default=0.0)
    personality_type: Optional[str] = Field(default=None)
    intent_type: str
    assessment_date: date_t

    # relationships
    emotion: "Emotion" = Relationship(back_populates="risk_profiles")
    person: "Person" = Relationship(back_populates="risk_profile")
