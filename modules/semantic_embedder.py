import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import cast
from sentence_transformers import SentenceTransformer

# Suppress Hugging Face Hub and Transformers technical noise
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

executor = ThreadPoolExecutor(max_workers=2)

# Load the model with standard output suppressed
model = SentenceTransformer("BAAI/bge-small-en-v1.5")


# todo: solve short messages limitation (max 512 tokens).
async def get_embedding(text: str) -> list[float]:
    """
    Computes the embedding in a new thread to avoid stopping the main thread.
    Retries up to 3 times on failure.
    """
    event_loop = asyncio.get_running_loop()
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            embedding = await event_loop.run_in_executor(executor, model.encode, text)
            return cast(list[float], embedding.tolist())
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Brief pause before retry
                continue
    
    raise last_error if last_error else Exception("Unknown error during embedding")
