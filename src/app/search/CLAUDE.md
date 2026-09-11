# Search 모듈 컨벤션

이 디렉토리(`src/app/search/`)에서 작업할 때 적용되는 컨벤션. 루트 `CLAUDE.md`의 Key Conventions에서 이관됨.

- **nav 통합검색 (`GET /search?q=`)**: Todo(`title_tsv`)와 daily entry(`content_tsv`)를 `asyncio.gather` 로 동시 조회, `{ todos, entries }` 로 타입별 분리 반환(관련도 점수가 서로 비교 불가능해 억지로 합치지 않음). 각 타입 상위 `limit`개(기본 5, 최대 20). `src/app/search/` 신규 모듈 — 자체 도메인/인프라 레이어 없이 기존 `ITodoRepository`/`IJournalEntryRepository` 를 조합하는 순수 aggregator.
