"""
backend/config.py — Application Settings & Environment Configuration
"""
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)
DATA_DIR = BASE_DIR / "data"
SUBJECTS_DIR = DATA_DIR / "subjects"


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AttendAI"
    DEBUG: bool = True
    AUTH_PASSWORD: str = "admin123"  # Basic single-user auth hook

    # Storage Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    SUBJECTS_DIR: Path = SUBJECTS_DIR
    CACHE_DIR: Path = DATA_DIR / "cache"
    TRAINING_DIR: Path = DATA_DIR / "training"
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'app.db'}"

    # Engine Architecture
    ENGINE_ORDER: str = "gemini,claude"

    # Google GenAI Vision API
    GEMINI_API_KEY: str = ""
    VISION_API_KEY: str = ""  # alias fallback
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Anthropic Claude Vision API
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    # Privacy Mode: 'columns_only' (crops date/sign columns locally) or 'full_page'
    PRIVACY_MODE: str = "columns_only"
    # Send printed Sr/Roll/Name columns to AI once for roster bootstrap
    SEND_NAMES_TO_AI: bool = True

    # ML & CV
    USE_YOLO: bool = False
    YOLO_WEIGHTS_PATH: Path = BASE_DIR / "weights" / "tsr_yolo_retrained.pt"

    # Regex for VIT Roll Numbers: regular (24108B...) + DSE (25108B...)
    ROLL_NO_REGEX: str = r"^2[45]108[Bb]\d{4}$"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def effective_api_key(self) -> str:
        return self.GEMINI_API_KEY or self.VISION_API_KEY

    def verify_gemini_model(self) -> tuple[bool, str]:
        """Verify configured Gemini model against Google GenAI endpoint."""
        key = self.effective_api_key
        if not key:
            return False, "No GEMINI_API_KEY or VISION_API_KEY configured."

        try:
            from google import genai
            client = genai.Client(api_key=key)
            models = [m.name.replace("models/", "") for m in client.models.list()]
            target = self.GEMINI_MODEL.replace("models/", "")
            if target in models or self.GEMINI_MODEL in [m.name for m in client.models.list()]:
                return True, f"Model '{self.GEMINI_MODEL}' is active and verified."
            return False, f"Model '{self.GEMINI_MODEL}' not found. Available: {', '.join(models[:10])}..."
        except Exception as exc:
            return False, f"Failed to connect to Google GenAI API: {exc}"


# Ensure critical folders exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SUBJECTS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "training").mkdir(parents=True, exist_ok=True)

settings = Settings()
