import os
from dotenv import load_dotenv

load_dotenv()


class EnvConfig:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    MAX_MESSAGE_BEFRORRE_TERMINATION: int = 20
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")
