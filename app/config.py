"""Settings read from environment variables."""

import os
from dataclasses import dataclass

DEFAULT_DATABASE_PATH = "data/pricing.db"


@dataclass(frozen=True)
class Settings:
    database_path: str = DEFAULT_DATABASE_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(database_path=os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH))
