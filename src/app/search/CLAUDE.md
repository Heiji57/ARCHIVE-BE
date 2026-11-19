# Search 모듈 컨벤션

이 디렉토리(`src/app/search/`)에서 작업할 때 적용되는 컨벤션. 루트 `CLAUDE.md`의 Key Conventions에서 이관됨.

- **통합검색 (`GET /search?q=&scope=`)**: `scope` = `all`(기본) | `todo` | `retro` | `topic`. Todo(`title_tsv`), 회고 전 종류(`content_tsv`, 제목+본문), 주제(이름·설명 부분 일치 ILIKE)를 순서대로 조회(세 리포지토리가 요청 세션 하나를 공유 — AsyncSession 은 동시 실행 불가), `{ todos, entries, topics }` 로 타입별 분리 반환(관련도 점수가 서로 비교 불가능해 억지로 합치지 않음). 범위 밖 종류는 빈 목록. 각 타입 상위 `limit`개(기본 5, 최대 20). 자체 도메인/인프라 레이어 없이 기존 `ITodoRepository`/`IJournalEntryRepository`/`ITopicRepository` 를 조합하는 순수 aggregator.
