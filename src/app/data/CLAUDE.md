# data 모듈 컨벤션

이 디렉토리(`src/app/data/`)에서 작업할 때 적용되는 컨벤션. 휴지통(12 §1)과 내보내기(12 §2).

- **휴지통**: 각 모듈이 자기 테이블을 다룬다(`todo/application/use_cases/trash.py`, `retrospective/application/use_cases/entry_trash.py`) — 이 모듈은 목록 합치기와 kind 라우팅만. 목록은 30일치라 합친 뒤 메모리에서 자른다. 30일 정리는 `worker.purge_trash`(하루). soft delete 전반 규칙은 루트 `CLAUDE.md` "휴지통(soft delete)".
- **내보내기**: `POST /exports` → 202, BackgroundTasks 로 `worker.build_export` 를 넘긴다 — BackgroundTasks 는 이 스택에서 요청 커밋보다 먼저 돌 수 있어, 워커는 행이 안 보이면 1초 간격 5번 다시 시도한다. 사용자당 진행 중 하나는 부분 유니크 인덱스 `uq_exports_user_pending` 로도 막는다(동시 요청). 1시간 넘게 pending 이면 워커가 죽은 것으로 보고 새 요청 때 failed 로 닫는다. 하루 3번은 최근 24시간(롤링). zip 은 비공개 디렉토리(`EXPORT_DIR`, 기본 `exports/` — `/static` 아님)에 두고, 내려받기는 24시간 서명 토큰이 붙은 `GET /exports/{id}/download` 만. 파일은 7일 뒤 `worker.purge_exports` 가 지우고 행은 남겨 GET 이 410. 빌더(`infrastructure/export/builder.py`)는 ORM 으로 읽어 휴지통이 자동으로 빠지고, `yield_per` 로 나눠 읽어 zip 에 바로 쓴다(큰 데이터에서 메모리). 계정 완전 삭제 때 파일도 지운다(`worker.purge_deleted_accounts`).
- **운영 주의**: 프로필 사진(`AVATAR_DIR`)과 내보내기(`EXPORT_DIR`)는 로컬 파일이다 — API 와 워커 컨테이너가 같은 볼륨을 봐야 하고(워커가 만든 zip 을 API 가 내려준다), 재배포에도 남아야 한다. 운영에서 객체 저장소로 옮기면 저장 구현만 바꾼다.
