from fastapi import APIRouter , Request , HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()

@router.get("/{short_id}")
async def redirect(short_id: str, request: Request):
    redis = request.app.state.redis_client
    mongo_db = request.app.state.db
    # Check Redis cache first
    cached_url = await redis.get(short_id)
    if cached_url:
        return RedirectResponse(url=cached_url)
    # If not in cache, check MongoDB
    record = await mongo_db.urls.find_one({"short_id": short_id})
    if record:
        original_url = record["url"]
        # Cache the result in Redis for future requests
        await redis.set(short_id, original_url)
        return RedirectResponse(url=original_url)
    print("did not find in mongo")

    raise HTTPException(status_code=404, detail="URL not found")