from pydantic_settings import BaseSettings, SettingsConfigDict


class TopicConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    topic_max_per_user: int = 20
    topic_similarity_threshold: float = 0.75
    topic_chunk_max_chars: int = 500
    topic_chunk_min_chars: int = 20
    topic_embed_batch_size: int = 20
    topic_search_limit: int = 50  # max chunks returned per vector search
