from datetime import datetime
from typing import Optional
from sqlmodel import Session, select, func

from database.engine import Repository
from database.models import GoEmotionLabel, Message, MessageEmotion, Person, RiskProfile
from statistics import mode
from modules.semantic_embedder import model as embedding_model
from utils.logger import Logger

# ──────────────────────────────────────────────────────────────────────
# Semantic Risk Configuration
# ──────────────────────────────────────────────────────────────────────

# Minimum cosine similarity to flag a message as semantically risky.
# Range: 0.0 (unrelated) → 1.0 (identical meaning).
SIMILARITY_THRESHOLD = 0.55

# Maximum security_score value (clamped).
MAX_SCORE = 5.0

# Risky reference topics organized by threat domain.
# Each message in the DB will be compared against all of these.
RISKY_TOPICS: dict[str, list[str]] = {
    "Ideological Radicalization": [
        "It is our absolute duty to join the righteous fight and sacrifice ourselves for the ultimate cause against the non-believers.",
        "The infidels must be eradicated to establish the true order under divine law.",
    ],
    "Tactical Planning & Weaponry": [
        "Looking for the exact chemical ratios to mix the explosive materials securely and avoid detection at the target site.",
        "We need detailed instructions on how to build an improvised explosive device from household chemicals.",
    ],
    "Incitement to Violence": [
        "We must coordinate an attack to physically eliminate the traitors at the gathering tomorrow and destroy their infrastructure.",
        "The only solution is to send armed fighters to the location and take out everyone who stands in our way.",
    ],
    "Terrorist Financing": [
        "Send the cryptocurrency funds to the secure wallet address so we can finance the upcoming operation and support the brothers.",
        "We need to set up anonymous accounts to launder money for purchasing weapons and supplies.",
    ],
    "Operational Security Evasion": [
        "Delete all chat history immediately, burn the SIM cards, and move the planning to the encrypted offline network before the authorities raid us.",
        "Switch to disposable phones and only communicate through dead drops to avoid surveillance.",
    ],
    "Cyber Attacks & Hacking": [
        "I have the zero-day exploit ready to deploy against the government infrastructure, we just need the target IP addresses.",
        "Let's launch a coordinated DDoS attack on the financial system to cause maximum disruption.",
    ],
    "Human Trafficking & Exploitation": [
        "We have a fresh shipment of people arriving at the border, we need to arrange transport and safe houses before the authorities notice.",
    ],
    "Drug Manufacturing & Distribution": [
        "The lab is ready for the next batch of methamphetamine, we just need the precursor chemicals delivered discreetly.",
    ],
}
# ──────────────────────────────────────────────────────────────────────
# Pre-cache risky topic embeddings at module load time (computed ONCE).
# ──────────────────────────────────────────────────────────────────────

# Flatten all topics into a single list with their category labels.
_all_topics: list[tuple[str, str]] = []  # (category, text)
for category, texts in RISKY_TOPICS.items():
    for text in texts:
        _all_topics.append((category, text))

# Encode all at once (batch) — much faster than one-by-one.
_topic_texts = [t[1] for t in _all_topics]
_topic_categories = [t[0] for t in _all_topics]

# Re-using the SentenceTransformer model from semantic_embedder to save RAM.
_topic_embeddings: list[list[float]] = embedding_model.encode(_topic_texts).tolist()  # type: ignore


# ──────────────────────────────────────────────────────────────────────
# Semantic Risk Scoring (Modularized)
# ──────────────────────────────────────────────────────────────────────


def run_risk_assessment(
    session: Session, logger: Logger
) -> list[tuple[Person, float, str | None, int]]:
    """
    Runs semantic risk assessment for ALL persons in the database.
    Orchestrates the counting, calculation, and database updating processes.

    Args:
        session: An active database session.
        logger: Logger instance.

    Returns:
        A list of tuples: (person, security_score, top_threat_category, message_count).
        Sorted by security_score descending (most dangerous first).
    """
    persons = Repository.get_all(Person, session=session)
    if not persons:
        return []

    person_map: dict[int, Person] = {p.id: p for p in persons}

    # 1. Gather baseline data
    msg_counts = _gather_message_counts(session)

    # 2. Execute pgvector queries to calculate raw scores
    person_scores, person_categories = _calculate_semantic_scores(session, persons)
    logger.debug(
        f"Completed {len(_topic_embeddings)} pgvector queries across {len(persons)} persons."
    )

    # 3. Update RiskProfile models in DB and build output results
    results = _update_risk_profiles(
        session, person_map, person_scores, person_categories, msg_counts
    )

    # Sort by score descending (most dangerous first)
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _gather_message_counts(session: Session) -> dict[int, int]:
    """
    Retrieves the count of embedded messages per person in a single query.
    Returns a mapping of {person_id: message_count}.
    """
    msg_count_results = session.exec(
        select(Message.person_id, func.count())  # type: ignore
        .where(Message.embedding.is_not(None))  # type: ignore
        .group_by(Message.person_id)
    ).all()

    return {pid: count for pid, count in msg_count_results}  # type: ignore


def _calculate_semantic_scores(
    session: Session, persons: list[Person]
) -> tuple[dict[int, float], dict[int, dict[str, float]]]:
    """
    Executes native pgvector cosine_distance queries against the DB.
    Returns two dictionaries: [person_id -> total_score] and [person_id -> category_scores].
    """
    person_scores: dict[int, float] = {p.id: 0.0 for p in persons}
    person_categories: dict[int, dict[str, float]] = {p.id: {} for p in persons}
    distance_threshold = 1.0 - SIMILARITY_THRESHOLD

    for i, topic_emb in enumerate(_topic_embeddings):
        category = _topic_categories[i]

        distance_expr = Message.embedding.cosine_distance(topic_emb)  # type: ignore

        matches = session.exec(
            select(Message.person_id, distance_expr.label("distance"))  # type: ignore
            .where(Message.embedding.is_not(None))  # type: ignore
            .where(distance_expr <= distance_threshold)  # type: ignore
        ).all()

        for person_id, distance in matches:
            if person_id not in person_scores:
                continue

            similarity = 1.0 - distance

            person_scores[person_id] += similarity

            cat_scores = person_categories[person_id]
            cat_scores[category] = cat_scores.get(category, 0.0) + similarity

    return person_scores, person_categories


def _update_risk_profiles(
    session: Session,
    person_map: dict[int, Person],
    person_scores: dict[int, float],
    person_categories: dict[int, dict[str, float]],
    person_msg_counts: dict[int, int],
) -> list[tuple[Person, float, str | None, int]]:
    """
    Normalizes the raw scores, updates the RiskProfile tables, and
    returns the structured results for presentation.
    """
    results: list[tuple[Person, float, str | None, int]] = []

    for pid, person in person_map.items():
        total_score = person_scores[pid]
        msg_count = person_msg_counts.get(pid, 0)
        cat_scores = person_categories[pid]

        # Absolute Cumulative Risk: Every threatening message adds directly to the score.
        security_score = min(round(total_score, 2), MAX_SCORE)

        # Identify the most dangerous threat category for this person
        top_category = None
        if cat_scores:
            top_category = max(cat_scores, key=cat_scores.get)  # type: ignore

        # Update or create risk profile in the database
        risk_profile = Repository.get(RiskProfile, str(pid), session=session)
        if risk_profile is not None:
            risk_profile.security_score = security_score
            risk_profile.assessment_date = datetime.now().date()
            if top_category:
                risk_profile.intent_type = top_category
            Repository.upsert(risk_profile, session=session)
        else:
            emotional_trend = _calculate_trend(
                [
                    me.emotion_label
                    for msg in person.messages
                    for me in msg.message_emotions
                ]
            )
            new_profile = RiskProfile(
                person_id=pid,
                emotional_trend=emotional_trend or GoEmotionLabel.neutral,
                security_score=security_score,
                intent_type=top_category or "Standard",
                personality_type="Initial",
                assessment_date=datetime.now().date(),
            )
            Repository.upsert(new_profile, session=session)

        results.append((person, security_score, top_category, msg_count))

    return results


# ──────────────────────────────────────────────────────────────────────
# Existing Risk Profile Functions (emotion-based)
# ──────────────────────────────────────────────────────────────────────


async def update_all_risk_profiles(session: Session):
    """
    Updates the risk profile of each person in the database.
    """
    persons = Repository.get_all(Person, session=session)
    for person in persons:
        messages_emotions = [
            me for msg in person.messages for me in msg.message_emotions
        ]
        risk_profile = await get_risk_profile(
            person, messages_emotions, session=session
        )
        Repository.upsert(risk_profile, session=session)


async def get_risk_profile(
    person: Person,
    message_emotions: list[MessageEmotion],
    session: Optional[Session] = None,
) -> RiskProfile:
    risk_profile = Repository.get(RiskProfile, str(person.id), session=session)

    if risk_profile is None:
        emotional_trend = _calculate_trend(
            [m_e.emotion_label for m_e in message_emotions]
        )

        if emotional_trend is None:
            return RiskProfile(
                person_id=person.id,
                emotional_trend=GoEmotionLabel.neutral,
                intent_type="Standard",
                personality_type="Initial",
                assessment_date=datetime.now().date(),
            )

        return RiskProfile(
            person_id=person.id,
            emotional_trend=emotional_trend,
            intent_type="Standard",
            personality_type="Initial",
            assessment_date=datetime.now().date(),
        )
    else:
        emotional_trend = _calculate_trend(
            [
                emotion.emotion_label
                for msg in risk_profile.person.messages
                for emotion in msg.message_emotions
            ]
        )

        if emotional_trend is not None:
            risk_profile.emotional_trend = emotional_trend
        return risk_profile


def _calculate_trend(emotions: list[GoEmotionLabel]) -> Optional[GoEmotionLabel]:
    """Calculates the emotional trend based on the most frequent emotion."""
    if not emotions:
        return None
    try:
        return mode(emotions)
    except Exception:
        return emotions[0] if emotions else None
