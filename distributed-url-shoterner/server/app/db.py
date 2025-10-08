import motor.motor_asyncio
import redis.asyncio as aioredis

async def get_mongo_client(uri: str):
    client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    return client

async def get_redis_client(uri: str):
    redis = aioredis.from_url(uri , decode_responses=True)
    return redis

