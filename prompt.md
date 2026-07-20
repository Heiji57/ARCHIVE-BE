# FE 작업 지시 — AI 회고 요약 표시 방식 변경 (B안 / C안)

> 이 문서는 **프런트엔드** 작업자(사람 또는 코딩 에이전트)에게 전달하는 지시 프롬프트다.
> 백엔드(ARCHIVE-BE)는 이 문서 기준으로 **변경하지 않는다** (B안은 BE 무변경). C안이 필요할 때만 BE에 별도 요청한다.

---

## 0. 한 줄 요약

주간/월간/연간 **AI 요약을 `POST /entries`로 미러링하지 말고, `GET /summaries`에서 직접 읽어서** 표시하라.
요약은 이미 `retro_summaries`에 정식 저장되어 있으며, 미러링이 모든 버그의 원인이다.

---

## 1. 배경 — 지금 무슨 일이 벌어지고 있나

회고 화면은 두 종류의 데이터를 보여준다:

- **일일(daily) 회고** — 사용자가 작성. `journal_entries` 테이블, `GET /entries`로 조회.
- **주/월/연 AI 요약** — 서버가 생성. `retro_summaries` 테이블, `GET /summaries`로 조회.

현재 FE는 AI 요약을 회고 목록에 끼워 넣으려고 **요약을 `journal_entries`에도 복사(미러링)** 한다.
이게 **이중 쓰기(dual write)** 이고, 다음 버그를 일으킨다.

### 증상

1. `POST /entries` → **409 `JOURNAL_ENTRY_ALREADY_EXISTS`**
   - `journal_entries`는 `UNIQUE(user_id, date_key, retro_type)` 제약이 있다.
   - 주간 요약을 `date_key = periodEnd`, `retro_type = weekly`로 저장하는데, **같은 주를 두 번째로 저장하면** 이미 있는 weekly entry와 충돌한다. (daily와의 충돌이 아니다 — weekly ↔ weekly 충돌이다.)
2. **새로고침하면 요약이 사라짐**
   - 미러 저장이 409로 실패 → `/entries` 응답엔 요약이 없음 → 세션 로컬 상태로만 보이다가 reload 시 소멸.
   - **단, 요약 원본(`retro_summaries`)은 멀쩡하다.** 데이터 손실 아님. FE가 잘못된 곳(`/entries`)을 읽을 뿐이다.

### 근본 원인

> "같은 요약 사실을 `retro_summaries`(정식) + `journal_entries`(미러) 두 곳에 쓴다"는 설계.
> 정식 저장소가 이미 있는데 복사본을 만드는 것 자체가 문제다. **복사를 없애야 한다.**

---

## 2. 정책 B (기본 / 즉시 적용) — 미러 제거 + `/summaries` 직접 로드

### 해야 할 일

1. **주/월/연 요약의 `POST /entries` 미러링 호출을 전부 제거**한다. (요약을 entry로 저장하는 코드 삭제)
2. 회고 데이터 소스를 **두 개로 분리**해서 로드한다:
   - 일일 회고: `GET /entries?retroType=daily&from=...&to=...`
   - 주/월/연 요약: `GET /summaries?type=weekly` / `?type=monthly` / `?type=annual`
3. 요약 카드/섹션은 `GET /summaries` 응답의 `content.sections`로 렌더한다. (entry의 `content` 문자열이 아님)
4. 재생성이 필요하면 `POST /summaries/generate?...&force=true`. (아래 §4.3 캐시 주의)
5. 새로고침(하이드레이션) 시에도 위 두 소스에서 다시 로드한다 — 요약을 `/entries`에서 찾지 않는다.

### 적용 후 기대 결과

- 409 사라짐, 새로고침 소멸 사라짐.
- 일일 = `/entries`, 요약 = `/summaries`로 책임이 명확히 분리됨.

### 적합 조건

회고 화면이 **일일 캘린더/리스트와 요약 카드를 별도 섹션/탭으로** 보여주는 경우 (대부분의 경우).
→ 클라이언트가 섹션별로 다른 엔드포인트를 읽으면 되므로 병합·페이지네이션 문제가 없다.

---

## 3. 정책 C (조건부) — 서버 집계 엔드포인트

### 언제 C가 필요한가 (결정 기준 — 반드시 먼저 판단)

> **회고 화면이 일일+주+월+연을 "하나의 끊김 없는 시간순 피드(무한 스크롤)"로 interleave해서 보여줘야 하는가?**

- **아니오 (별도 섹션)** → **B로 충분.** C 불필요.
- **예 (단일 혼합 피드 + 서버 페이지네이션)** → **C가 맞다.**

이유: 두 엔드포인트(`/entries`, `/summaries`)를 각각 페이징해서 클라이언트에서 하나의 시간순으로 병합하는 건 정확한 페이지네이션이 어렵다(over-fetch 필요). 이런 뷰는 서버가 합쳐 주는 게 정석(BFF/aggregation 패턴).

### C를 택할 경우

- FE는 단일 호출 `GET /retrospectives?from=...&to=...&cursor=...` 형태를 사용한다(요청 스펙은 BE와 합의).
- 이 엔드포인트는 **현재 BE에 없다.** 필요하면 BE에 신설을 요청하라. (읽기 전용 집계, 동일 DB JOIN/UNION이라 이중 쓰기 위험 없음.)
- **B → C는 무손실 승격이다.** 먼저 B로 가도, 나중에 C를 얹을 때 버리는 작업이 없다(요약은 그대로 `/summaries`에 남아 있으므로).

### 기본 지침

**확실하지 않으면 B로 구현하고, "interleave 단일 피드가 필요해지면 C로 승격"** 주석을 남겨라.

---

## 4. API 계약 (백엔드 코드로 검증됨 — 이대로 신뢰 가능)

모든 응답은 `ApiResponse<T>` 래퍼로 감싸진다: `{ "status": "...", "code": "...", "data": <T> }`.

### 4.1 요약 조회

**목록**: `GET /api/v1/summaries?type={weekly|monthly|annual}` → `data: SummaryResponse[]`
**상세**: `GET /api/v1/summaries/{summaryId}` → `data: SummaryResponse`

> ⚠️ `type` 값은 **`annual`** 이다 (`yearly` 아님). 주의.

`SummaryResponse` 형태 (키 케이싱 주의 — `githubPush`만 camelCase, 나머지는 snake_case):

```jsonc
{
  "id": "summ_019ef...",
  "user_id": "user_...",
  "summary_type": "weekly",            // "weekly" | "monthly" | "annual"
  "period_start": "2026-06-22",        // YYYY-MM-DD
  "period_end": "2026-06-28",          // YYYY-MM-DD
  "status": "completed",               // "pending" | "in_progress" | "completed" | "failed"
  "content": {                          // status != "completed" 이면 null
    "sections": {
      "<sectionKey>": ["문장1", "문장2"],
      "...": ["..."]
    }
  },
  "githubPush": {                       // 푸시 이력 없으면 null
    "pushedAt": "2026-06-28T...Z",
    "commitSha": "abc123",
    "htmlUrl": "https://github.com/...",
    "path": "retrospectives/2026-W26.md",
    "repositoryFullName": "owner/repo"
  },
  "created_at": "2026-06-23T07:32:12Z",
  "updated_at": null
}
```

- **`content`는 `status == "completed"` 일 때만 채워진다.** 그 외(pending/in_progress/failed)는 `null`.
- 목록(`GET /summaries`)도 상세와 동일하게 **`content` 전체를 포함**한다(잘라내지 않음). 즉 목록 한 번으로 본문까지 렌더 가능.
- **`title` 필드는 없다.** FE가 `summary_type` + `period_start`/`period_end`로 파생하라 (§4.4).

### 4.2 요약 생성 + 완료 대기 (SSE)

1. `POST /api/v1/summaries/generate?type={weekly|monthly|annual}&periodStart=YYYY-MM-DD&force={true|false}`
   → **202 Accepted**, `data: SummaryResponse` (보통 `status: "pending"`, `content: null`, `id` 포함)
   - `periodStart` 생략 시 서버가 기본 기간 계산.
2. `GET /api/v1/summaries/{id}/stream` (SSE) 구독.
   - **이 스트림은 신호만 보낸다**: `{"status": "completed" | "failed" | "timeout" | "error", "summary_id": "..."}`.
   - **본문(content)은 SSE에 없다.** 이미 완료 상태면 즉시 신호 후 종료된다.
3. `"completed"` 수신 → `GET /api/v1/summaries/{id}` 호출해 **content를 받아 렌더**.

> 즉 표준 흐름: `POST generate(202)` → `SSE stream(신호)` → `GET /summaries/{id}(본문)`.

### 4.3 캐시/재생성 주의 (매우 중요)

- 이미 `completed`인 기간을 **`force` 없이** `POST generate` 하면, 서버는 **AI를 재호출하지 않고 기존 완료본을 그대로 202로 반환**한다(새로 생성하지 않음).
  → entry를 수정한 뒤 같은 주를 다시 요약해도 **내용이 안 바뀐다**. 이건 정상 동작이다.
- **강제 재생성하려면 반드시 `force=true`.** 단, 재생성은 사용량 제한(rate limit)을 소모한다.
- 생성 한도 초과 시 **429 `RETRO_SUMMARY_RATE_LIMIT_EXCEEDED`**, `details[0]`에 `{summaryType, limit, windowSeconds, retryAfterSeconds}`. 사전 조회는 `GET /api/v1/summaries/usage`.

### 4.4 `title` 파생 규칙 (FE에서)

요약 응답에 `title`이 없으므로 표시용 제목은 FE가 만든다. 예:

- weekly: `"{YYYY}-W{ISO주차} 주간 회고"` 또는 `"{periodStart} ~ {periodEnd} 주간 요약"`
- monthly: `"{YYYY}년 {M}월 월간 회고"`
- annual: `"{YYYY}년 연간 회고"`

(서버가 `title`을 내려주길 원하면 BE에 `SummaryResponse.title` 추가를 요청 가능 — 기본은 FE 파생.)

### 4.5 일일 회고 조회

`GET /api/v1/entries?retroType=daily&from=YYYY-MM-DD&to=YYYY-MM-DD` → `data: EntryResponse[]`

`EntryResponse` 주요 필드(역시 snake_case): `id`, `user_id`, `date_key`, `title`, `content`(마크다운 문자열), `retro_type`, `created_at`, `updated_at`. (개발자+GitHub 연결 계정은 `githubPush` 포함될 수 있음.)

---

## 5. 하지 말 것 (금지)

- ❌ 주/월/연 요약을 `POST /entries`로 저장(미러링)하지 마라. **이게 버그의 원인이다.**
- ❌ 409 `JOURNAL_ENTRY_ALREADY_EXISTS`를 "기존 weekly entry 찾아 덮어쓰기"로 우회하려 하지 마라. 충돌 상대는 이미 존재하는 weekly entry이고, 애초에 `/entries`에 쓰지 않는 게 정답이다.
- ❌ `summary_type`에 `yearly`를 보내지 마라. 이 API는 `annual`을 쓴다.
- ❌ SSE 스트림에서 본문(content)을 기대하지 마라. 신호만 온다 → 완료 후 `GET /summaries/{id}`.
- ❌ 응답 키를 전부 camelCase로 가정하지 마라. `summary_type`/`period_start`/`period_end`/`created_at`는 snake_case, `githubPush`만 camelCase다.

---

## 6. 완료 기준 (Acceptance Criteria)

- [ ] 주/월/연 요약 관련 `POST /entries` 호출이 코드에서 완전히 제거됨.
- [ ] 요약 목록/상세가 `GET /summaries`(+`/summaries/{id}`)에서 로드되어 렌더됨.
- [ ] 새로고침 후에도 요약이 유지됨(로컬 상태 의존 아님).
- [ ] 요약 생성: `POST generate(202)` → SSE 신호 → `GET /summaries/{id}` 흐름으로 본문 표시.
- [ ] 재생성은 `force=true`로 동작, 429 한도 응답을 사용자에게 안내.
- [ ] 409 `JOURNAL_ENTRY_ALREADY_EXISTS`가 더 이상 발생하지 않음.
- [ ] (C 채택 시) 단일 interleave 피드는 `GET /retrospectives` 단일 호출로 처리. 그 외에는 B로 구현.

---

## 7. 참고 — 왜 이 방향인가 (설계 근거 요약)

- **이중 쓰기는 안티패턴**: 두 곳에 쓰면 한쪽 실패 시 조용히 불일치(지금의 reload 소멸 버그). 정식 저장소가 있으면 복사하지 말고 거기서 읽는다.
- **리소스 분리 + 읽기 합성**: 유명 API 설계 규약(Stripe `expand`, OpenAI/Anthropic의 분리 리소스)은 리소스를 복제하지 않고 읽을 때 합성한다. 합성 위치가 클라이언트면 B, 서버면 C.
- **과설계 회피**: 이 앱 규모에선 서버 집계(C)도 단순 읽기 JOIN이면 충분하고, 비동기 read-model/CQRS는 불필요.
