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
    # 캐시 미스 시 stampede 방지용 락(SETNX, redis.lock) — 같은 topic 을 동시에 여러
    # 요청(다른 탭/중복 새로고침 등)이 미스하면, 한 요청만 임베딩+DB 계산을 하고 나머지는
    # 결과가 캐시에 쓰이길 기다렸다가 재사용한다. TTL 은 락 보유자가 죽었을 때(크래시,
    # 타임아웃)의 안전장치 — 이 시간이 지나면 락이 자동 해제돼 다른 요청이 넘겨받는다.
    topic_match_lock_ttl_seconds: float = 30.0
    # 락을 못 얻은 요청이 보유자의 결과를 기다리는 상한. 넘기면 보유자가 비정상 종료한
    # 것으로 보고 직접 계산한다(안전망 — 최악의 경우에도 무한 대기하지 않는다).
    topic_match_wait_timeout_seconds: float = 5.0
    topic_match_wait_poll_interval_seconds: float = 0.1
