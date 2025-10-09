from contextlib import asynccontextmanager

from fastapi import FastAPI , Request
from .config import get_settings
from .db import get_mongo_client , get_redis_client
from .routes.shorten import router as shorten_router
from .routes.redirect import router as redirect_router
from fastapi.middleware.cors import CORSMiddleware

import logging
import time

# Simple console logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("uvicorn")

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Log the incoming request
    logger.info(f"→ {request.method} {request.url.path} (client: {request.client.host})")

    # Process the request
    response = await call_next(request)

    # Calculate processing time
    process_time = time.time() - start_time

    # Log the response
    logger.info(f"← {response.status_code} for {request.method} {request.url.path} ({process_time:.3f}s)")

    return response

@app.get("/health")
async def health():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router( shorten_router , prefix="/api")
app.include_router( redirect_router  , prefix="")
