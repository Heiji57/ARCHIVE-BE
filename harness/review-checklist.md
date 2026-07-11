# 구현 후 자기검증 (Reflection)

구현이 끝나면 코드를 넘기기 전에 스스로 아래를 점검한다.
`CLAUDE.md` Pre-Implementation Workflow 의 "서브 sonnet 검증" 단계와 짝을 이룬다.

## Reflection — 다시 묻는다

- [ ] 이미 구현되어 있는 기능을 중복으로 만들지 않았는가?
- [ ] 더 작은 변경(diff)으로 가능했는가? 요청받지 않은 수정이 섞이지 않았는가?
- [ ] 기존 패턴/네이밍/레이어 컨벤션과 일치하는가?
- [ ] 기존 동작을 깨뜨리지 않았는가? (하위 호환)

## Architecture & 코드

- [ ] 레이어 의존성 방향이 올바른가? (Presentation → Application → Domain, Infrastructure 는 Domain 인터페이스 구현)
- [ ] 순환 의존(circular import)이 생기지 않았는가?
- [ ] 도메인 레이어가 인프라(SQLAlchemy/httpx 등)에 직접 의존하지 않는가?

## 배선 & 계약

- [ ] 신규 repository/use_case 가 `providers.py` 에 DI 등록되었는가?
- [ ] 신규 라우터가 `main.py` 에 include 되었는가?
- [ ] 스키마 변경이 Alembic 마이그레이션에 반영되었는가?
- [ ] 응답/에러 계약이 `api.yaml`(SST)과 일치하는가? 새 예외가 `_STATUS_MAP` + `x-error-codes` 에 반영되었는가?

## 런타임 안전

- [ ] 트랜잭션 경계가 올바른가? (부분 커밋/누락된 flush)
- [ ] 인증/권한 검사가 필요한 엔드포인트에 걸려 있는가? (`get_current_user`, 소유권 가드)
- [ ] 예외가 사용자에게 적절한 HTTP 상태로 매핑되는가?

## 정책 변경 감지

- [ ] 컨벤션/정책을 바꿨다면 **사용자 승인**을 받았는가? 받지 않았다면 여기서 멈추고 알린다.
- [ ] 변경이 `api.yaml` / `develop.md` / `CLAUDE.md` 수정을 요구하는가? 요구하면 반영(정책 변경은 승인 후).
