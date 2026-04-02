from utils.logger import Logger, LogLevel
from .engine import Repository, init_db, delete_db
from .models import (
    Person,
    Message,
    Emotion,
    MessageEmotion,
    RiskProfile,
    GoEmotionLabel,
)
from datetime import date


import os

logger = Logger(level=LogLevel.INFO)

def delete_database():
    delete_db()
    if os.path.exists("last_saved_id.txt"):
        os.remove("last_saved_id.txt")


def populate_database():
    logger.banner("DATABASE INITIALIZATION\n[dim]Initializing core tables and demo data...[/dim]", color="bright_blue")
    logger.info("Ensuring tables are initialized...")
    init_db()

    logger.info("Seeding Emotion lookup table...")
    for label in GoEmotionLabel:
        emotion = Emotion(label=label)
        Repository.create(emotion)
    logger.success(f"Seeded {len(GoEmotionLabel)} emotions")

    logger.info("Adding English demo data...")
    new_person = Person(
        id=123456789,  # Telegram user_id (int64)
        name="John Doe",
        risk_level=3,
    )
    Repository.create(new_person)
    logger.debug(f"Saved Person: {new_person.name}")

    new_message = Message(
        id=1,  # Telegram message_id (sequential int per chat)
        text="The platform interface looks amazing, but I found a vulnerability in the login page.",
        date=date.today(),
        person_id=new_person.id,
    )
    Repository.create(new_message)
    logger.debug(f"Saved Message from {new_person.name}")

    # Link message to emotions via the join table
    for label, score in [(GoEmotionLabel.surprise, 0.92), (GoEmotionLabel.fear, 0.65)]:
        link = MessageEmotion(message_id=new_message.id, emotion_label=label, score=score)
        Repository.create(link)
    logger.debug("Saved MessageEmotion scores")

    new_risk_profile = RiskProfile(
        person_id=new_person.id,
        security_score=4.2,
        personality_type="Analytical",
        intent_type="Standard",
        emotional_trend=GoEmotionLabel.annoyance,
        assessment_date=date.today(),
    )
    Repository.create(new_risk_profile)
    logger.debug("Saved RiskProfile assessment")

    logger.success("Database population completed!")


if __name__ == "__main__":
    delete_database()
    populate_database()
