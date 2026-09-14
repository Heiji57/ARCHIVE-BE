# Todo 모듈 컨벤션

이 디렉토리(`src/app/todo/`)에서 작업할 때 적용되는 컨벤션. 루트 `CLAUDE.md`의 Key Conventions에서 이관됨.

- **Todo 시간 저장 정책**: `todos.start_time` / `todos.end_time` 은 UTC `TIMESTAMPTZ` 로 저장. 사용자 로컬 시각 복원을 위해 생성 시점 IANA timezone 을 `todos.timezone`(`VARCHAR(50)`) 에 함께 저장 (스냅샷). FE 는 로컬 시각을 UTC 로 변환해 전송하고, 응답의 `timezone` 으로 역변환. `start_time` 또는 `end_time` 이 non-null 이면 `timezone` 필수 (422). IANA 검증은 `shared/domain/utils/timezone.py`의 `validate_timezone` 사용.
- **Todo due_date_key 정책**: `todos.due_date_key` (`VARCHAR(10)`, nullable) — 선택적 마감일(포함, YYYY-MM-DD). `due_date_key >= date_key` 제약 (422). POST: Pydantic model_validator에서 검증. PATCH: `omit=unchanged`, `null=clear`, `string=set` 패턴(UNSET sentinel). Pydantic 레벨에서 `date_key`가 같은 요청에 포함된 경우만 체크, 나머지는 `UpdateTodoUseCase._apply_patch`에서 `RequestValidationError` 발생. 반복 Todo exception row(`_materialize_and_update`) 및 following 분리(`_update_following`) 시 source/master의 `due_date_key` 상속.
- **`GET /todos/stats?range=all`**: 전체 기간 = `2000-01-01 ~ 오늘`. 상한을 `today` 로 두는 것은 "이미 쌓인" 개수라는 의미에 맞을 뿐 아니라 **안전장치**다 — `date.max` 로 두면 종료일 없는 반복 Todo 마다 `generate_slots_from` 가상 슬롯 루프가 서기 9999년까지 수백만 번 돌아 요청이 멈춘다. `today/week/month` 동작은 불변.
