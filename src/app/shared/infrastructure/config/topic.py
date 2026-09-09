from pydantic_settings import BaseSettings, SettingsConfigDict


class TopicConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    topic_max_per_user: int = 20
    topic_similarity_threshold: float = 0.75
    topic_chunk_max_chars: int = 500
    topic_chunk_min_chars: int = 20
    topic_embed_batch_size: int = 20
    # digest 프롬프트에 넣을 소스 상한(종류별). 유사도 내림차순으로 자르므로 잘리더라도
    # 가장 주제에 가까운 것부터 남는다. 재생성이 증분이 아니라 주제 전체를 다시 읽게 되면서
    # 이 값이 곧 "문서가 커버하는 범위"가 됐다 — 단위가 회고가 아니라 **청크**(한 회고가 여러
    # 청크로 쪼개짐)라 50 이면 회고 15~25건 수준이라 부족해 200 으로 올렸다.
    topic_search_limit: int = 200
    # 통계/소스 목록용 매칭 상한. digest 프롬프트용(topic_search_limit)과 분리 —
    # 프롬프트 길이 제약과 "이 주제에 묶인 전체 개수"는 서로 다른 요구이기 때문.
    topic_stats_match_limit: int = 1000
    topic_stats_cache_ttl_seconds: int = 300
    topic_digest_progress_batch_size: int = 5
