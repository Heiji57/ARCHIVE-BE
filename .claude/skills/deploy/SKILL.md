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

## 파일 저장소 (Cloudflare R2)

운영 컨테이너에는 볼륨이 없어서 프로필 사진·내보내기 zip 은 객체 저장소에 둔다. `APP_ENV=production` 인데 `STORAGE_BACKEND=s3` 가 아니면 API·워커가 시작하지 않는다.

1. R2 버킷 두 개를 만든다.
   - 사진(예: `archive-avatars`) — 사진 전용(고아 정리가 버킷 전체를 훑어 아무도 안 가리키는 파일을 지운다). **Custom Domain** 연결(예: `cdn.<도메인>`). `r2.dev` 주소는 요청 제한이 있는 개발용이라 쓰지 않는다.
   - 내보내기(예: `archive-exports`) — 공개하지 않는다. **Object lifecycle rule: 8일 뒤 삭제**(워커가 7일에 지우고, 빠졌을 때 받쳐 준다).
2. R2 **API 토큰**: 권한 *Object Read & Write*, 대상은 위 두 버킷만. Access Key ID / Secret Access Key 를 받아 둔다.
3. `.env.production` 에 넣는다:

   ```
   STORAGE_BACKEND=s3
   STORAGE_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
   STORAGE_REGION=auto
   STORAGE_ACCESS_KEY_ID=...
   STORAGE_SECRET_ACCESS_KEY=...
   STORAGE_AVATAR_BUCKET=archive-avatars
   STORAGE_AVATAR_PUBLIC_URL=https://cdn.<도메인>
   STORAGE_EXPORT_BUCKET=archive-exports
   ```

4. 내보내기 내려받기는 API 가 R2 서명 URL(5분)로 307 을 보낸다. FE 가 브라우저 이동(`<a href>`)으로 열면 설정할 것이 없고, `fetch` 로 받는다면 내보내기 버킷 CORS 에 FE origin 의 `GET` 을 허용한다.
