---
name: deploy
description: ARCHIVE-BE 프로덕션 배포 절차 — docker-compose.prod.yml 오버레이로 GHCR 이미지 pull/up
---

# 배포 (Production)

로컬 `docker-compose.yml`(build+bind mount+`--reload`+DB 포트 노출)은 그대로 두고, `docker-compose.prod.yml` 오버레이로 배포 차이점만 병합한다:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

- 이미지는 `.github/workflows/build-and-push.yml`(main push / `v*` 태그 push 시 트리거)이 GHCR(`ghcr.io/heiji57/archive-be`)로 빌드·push. `IMAGE_REPO`/`IMAGE_TAG` env var로 다른 레지스트리/태그 지정 가능.
- `docker-compose.prod.yml`은 `!reset`(Compose merge 문법)으로 `build`/`volumes`/`command`(api)/`ports`(postgres, redis)를 제거한다 — 소스 bind mount 없이 이미지에 baked-in 된 코드만 실행되고, DB/Redis 포트는 호스트에 노출되지 않는다(archive-net 내부에서만 api/worker 가 접근).
- `env_file`은 `.env.production` — protected file(`.env.*`)이라 `.env.example`을 복사해 직접 채워야 한다.
