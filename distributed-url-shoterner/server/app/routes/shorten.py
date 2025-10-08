from fastapi import APIRouter ,  Request
from ..models import ShortenRequest ,  ShortenResponse
from ..utils.snowflake import Snowflake
from ..config import get_settings
import time

router =  APIRouter()

settings = get_settings()

snowflake_id_gen = Snowflake(node_id=settings.NODE_ID, epoch=settings.NODE_EPOCH)

@router.post("/shorten", response_model=ShortenResponse)
async def shorten_url(request: Request , payload: ShortenRequest):
    redis = request.app.state.redis_client
    mongo_db = request.app.state.db

    short_id = snowflake_id_gen.next_id_base62()

    await mongo_db.urls.insert_one({
        "short_id": short_id,
        "url": str(payload.url),
        "created_at": int(time.time())
    })

    # Optionally, cache the mapping in Redis
    await redis.set(short_id, str(payload.url))

    short_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}/{short_id}"

    return ShortenResponse(
        short_id=short_id,
        short_url=short_url,
        url=payload.url,
        created_at=int(time.time())
    )
