from contextlib import asynccontextmanager

from fastapi import FastAPI
from .config import get_settings
from .db import get_mongo_client , get_redis_client
from .routes.shorten import router as shorten_router
from .routes.redirect import router as redirect_router


settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.mongo_client = await get_mongo_client(settings.MONGO_URL)
    app.state.redis_client = await get_redis_client(settings.REDIS_URL)
    app.state.db = app.state.mongo_client[settings.MONGO_DB]
    print("Connected to MongoDB and Redis")
    yield
    # Shutdown
    if hasattr(app.state, "mongo_client"):
        app.state.mongo_client.close()
    if hasattr(app.state, "redis_client"):
        await app.state.redis_client.aclose()
    print("Disconnected from MongoDB and Redis")

app = FastAPI(title="Distributed URL Shortener", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router( shorten_router , prefix="/api")
app.include_router( redirect_router  , prefix="")