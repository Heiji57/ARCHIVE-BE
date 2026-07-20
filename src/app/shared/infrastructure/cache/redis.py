from redis.asyncio import Redis

from app.shared.infrastructure.config.settings import get_settings


def build_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis.cache_url, decode_responses=True)


def build_auth_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis.auth_url, decode_responses=True)
