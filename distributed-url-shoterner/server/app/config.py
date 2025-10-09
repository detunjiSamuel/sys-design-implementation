import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    APP_NAME: str = os.environ.get("APP_NAME", "Distributed URL Shortener")
    ENV: str = os.environ.get("ENV", "development")

    MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017/mongodemo")
    MONGO_DB: str = os.environ.get("MONGO_DB", "mongodemo")
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    APP_HOST: str = os.environ.get("APP_HOST", "0.0.0.0")
    APP_PORT: int = os.environ.get("APP_PORT", 8000)

    NODE_ID: int | None = os.environ.get("NODE_ID")#override in env for manual node id
    NODE_EPOCH: int | None = os.environ.get("NODE_EPOCH")



@lru_cache()
def get_settings() -> Settings:
    settings = Settings()

    node_info = f"Manual NODE_ID={settings.NODE_ID}" if settings.NODE_ID is not None else "Node ID will be auto-generated"
    print(f"[CONFIG] {settings.APP_NAME} starting ({settings.ENV}) — {node_info}")

    return settings
