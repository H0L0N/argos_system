import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from transformers import pipeline

from database.models import GoEmotionLabel, Message, MessageEmotion

# Suppress Hugging Face Hub and Transformers technical noise
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

executor = ThreadPoolExecutor(max_workers=2)

# Load the model with standard output suppressed
# top_k=None forces the pipeline to return scores for all 28 classes.
# truncation=True avoids crashing on messages larger than 512 tokens.
emotion_pipeline = pipeline(
    "text-classification",
    model="SamLowe/roberta-base-go_emotions",
    top_k=None,
    truncation=True,
    max_length=512,
)

# Minimum confidence score for an emotion to be saved
SCORE_THRESHOLD = 0.3


async def analyze_emotions(message: Message) -> Message:
    """
    Analyzes the emotions of a message using the SamLowe/roberta-base-go_emotions model.
    Runs inference in a thread pool to avoid blocking the main event loop.
    Emotions with a confidence score above SCORE_THRESHOLD are mapped to the Message.
    """
    if not message.text:
        return message

    event_loop = asyncio.get_running_loop()

    # Run the pipeline in the executor because doing inference blocks the thread
    results = await event_loop.run_in_executor(executor, emotion_pipeline, message.text)

    # Normalize the output format (can vary depending on pipeline text vs list of texts)
    if isinstance(results[0], list):
        predictions = results[0]
    else:
        predictions = results

    detected_emotions = []

    for pred in predictions:
        score = pred["score"]
        if score >= SCORE_THRESHOLD:
            try:
                # Attempt to map to the enum
                label_enum = GoEmotionLabel(pred["label"])
                detected_emotions.append(
                    MessageEmotion(
                        message_id=message.id,
                        emotion_label=label_enum,
                        score=round(score, 4),
                    )
                )
            except ValueError:
                # In case the model predicts a label not in our enum
                logging.warning(f"Unknown emotion label detected: {pred['label']}")

    message.message_emotions = detected_emotions

    return message
