from dataclasses import dataclass
from typing import Optional
from utils.logger import LogLevel


@dataclass
class ScraperConfig:
    """Holds configuration for the scraping process."""

    target_group_id: int
    target_topic_id: Optional[int] = None
    tracking_file: str = "last_saved_id.txt"
    scraping_interval_seconds: int = 300
    log_level: LogLevel = LogLevel.INFO
