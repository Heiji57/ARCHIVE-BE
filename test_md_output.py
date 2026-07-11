"""
Gemini 마크다운 직접 출력 테스트.

response_schema 를 제거하고 사용자 템플릿의 블록 구조(##, -, >, **bold**)를
그대로 따라 마크다운으로 출력하는지 검증한다.

실행:
    python test_md_output.py
"""
import asyncio
import os
import textwrap

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("GOOGLE_API_KEY", "")

# ── 테스트 케이스 정의 ──────────────────────────────────────────────────────

# 케이스 1: 헤딩 + 불릿 (현재 우리 템플릿과 유사한 구조)
TEMPLATE_BASIC = """\
## 이번 주 성과
- 완료한 작업이나 구체적인 성취를 적어주세요

## 어려웠던 점
- 막혔거나 힘들었던 문제를 적어주세요

## 배운 것
- 새롭게 알게 된 것이나 인사이트를 적어주세요

## 다음 주 목표
- 다음에 집중할 것들을 적어주세요
"""

# 케이스 2: 다양한 블록 타입 (Notion 스타일)
TEMPLATE_RICH = """\
# 주간 회고

## ✅ 성과
- **완료한 것**: 구체적인 task 이름
- **임팩트**: 어떤 가치를 만들었는지

## 🚧 진행 중
> 아직 끝나지 않은 작업들

## ⚠️ 어려웠던 점
- 문제 상황을 간단히 설명

## 💡 배운 것
1. 첫 번째 인사이트
2. 두 번째 인사이트

## 🎯 다음 주 액션
- [ ] 구체적인 할 일
- [ ] 또 다른 할 일
"""

# 케이스 3: 자유 서술형 (헤딩 없음)
TEMPLATE_FREE = """\
이번 주를 돌아보면서 잘 한 것과 아쉬운 것, 그리고 다음에 더 잘 하기 위해
필요한 것들을 솔직하게 써주세요. 너무 형식에 얽매이지 말고 편하게 작성해도 됩니다.
"""

# 더미 회고 데이터 (실제 entry 내용 흉내)
DUMMY_ENTRIES = """\
2026-06-23 (월):
- FastAPI 캘린더 라우터 구현 완료
- Google OAuth callback HTML postMessage 방식으로 수정
- Celery beat 스케줄 설정 중 queue 라우팅 문제 발견

2026-06-24 (화):
- calendar 큐 분리, worker-calendar 컨테이너 추가
- docker-compose.yml 수정 완료
- response_schema vs thinking_budget 충돌 이슈 확인

2026-06-25 (수):
- Tiptap 마크다운 출력 가능성 리서치
- Gemini 2.5 flash 스트리밍 API 문서 검토
- 팀 코드리뷰 2건 완료

2026-06-26 (목):
- 사용자 설정 모달 BE 연동 완료
- JWT stale 토큰 버그 수정 (account_type 변경 시)
- GitHub OAuth link 흐름 구현
"""


def build_test_prompt(template: str, entries: str) -> str:
    """response_schema 없이 마크다운 직접 출력 요청 프롬프트."""
    return f"""You are an expert at analyzing a developer's weekly retrospective and writing insightful summaries.

LANGUAGE RULE:
- Write ALL output in Korean.

OUTPUT CONTRACT (must follow exactly):
- Respond with MARKDOWN only. No JSON. No prose outside the markdown.
- Follow the exact block structure of the USER_TEMPLATE below:
  use the same headings (##, ###), same list styles (-, 1., - [ ]), same emphasis (**bold**, *italic*), same blockquotes (>) as shown in the template.
- Fill in each section with actual insights from the journal entries.
- Do NOT add sections that are not in the template.
- Do NOT output JSON.

STYLE GUIDE — follow this template's structure exactly:
<USER_TEMPLATE>
{template.strip()}
</USER_TEMPLATE>

--- JOURNAL ENTRIES (source data) ---
{entries.strip()}
"""


async def run_test(label: str, template: str, entries: str) -> None:
    client = genai.Client(api_key=API_KEY)

    prompt = build_test_prompt(template, entries)

    print(f"\n{'='*60}")
    print(f"  케이스: {label}")
    print(f"{'='*60}")
    print("\n[템플릿]\n")
    print(textwrap.indent(template.strip(), "  "))

    print("\n[Gemini 출력]\n")

    # response_schema 없이 — 순수 마크다운 출력 요청
    config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=config,
    )

    output = response.text or "(응답 없음)"
    print(textwrap.indent(output, "  "))

    # ── 검증 ────────────────────────────────────────────────────────────────
    print("\n[검증 결과]")

    # 헤딩 보존 여부 확인
    template_headings = [
        line.strip() for line in template.splitlines()
        if line.strip().startswith("#")
    ]
    if template_headings:
        matched = sum(1 for h in template_headings if h in output)
        print(f"  헤딩 보존: {matched}/{len(template_headings)}", end="")
        print(" ✅" if matched == len(template_headings) else " ⚠️ 일부 누락")

    # JSON 혼입 여부
    has_json = "{" in output and "}" in output and '"' in output
    print(f"  JSON 혼입: {'⚠️ 발견됨' if has_json else '✅ 없음'}")

    # 블록 타입 보존
    checks = [
        ("불릿 리스트 (-)", "- " in output),
        ("번호 리스트 (1.)", "1." in output and "1." in template),
        ("블록쿼트 (>)", ">" in output and ">" in template),
        ("체크박스 (- [ ])", "- [ ]" in output and "- [ ]" in template),
        ("볼드 (**)", "**" in output and "**" in template),
    ]
    for name, result in checks:
        if name.split("(")[1].rstrip(")") in template:
            print(f"  {name}: {'✅' if result else '⚠️ 미사용'}")


# 케이스 4: 실제 DB 저장 템플릿 (GitHub Alert 콜아웃 포함)
TEMPLATE_ACTUAL = """\
# 한 일

-   (내가 한 일 - 요일)


# 진행 중인 일

-   (내가 진행중인 일 - 요일)


# 새롭게 알게 된 것

> (새롭게 알게 된 것 이름)
>
> -   (새롭게 알게 된 것 세부 내용)
>

# 공부 한 것

> [!NOTE]
> -   (공부한 것)

# 성과

> [!TIP]
> (이번주 내가 진행한 일 최종요약)

# 앞으로 진행할 일

-   (AI가 여태까지 나의 기록을 보고서 앞으로 이런것들을 하면 좋을 것 같다는 피드백 제시 필요)
"""


async def run_test_with_callout_check(label: str, template: str, entries: str) -> None:
    """GitHub Alert (> [!NOTE], > [!TIP]) 재현 여부를 추가로 검증."""
    client = genai.Client(api_key=API_KEY)
    prompt = build_test_prompt(template, entries)

    print(f"\n{'='*60}")
    print(f"  케이스: {label}")
    print(f"{'='*60}")
    print("\n[템플릿]\n")
    print(textwrap.indent(template.strip(), "  "))

    print("\n[Gemini 출력]\n")

    config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=config,
    )

    output = response.text or "(응답 없음)"
    print(textwrap.indent(output, "  "))

    print("\n[검증 결과]")

    # 헤딩 보존
    template_headings = [l.strip() for l in template.splitlines() if l.strip().startswith("#")]
    if template_headings:
        matched = sum(1 for h in template_headings if h in output)
        print(f"  헤딩 보존: {matched}/{len(template_headings)}", end="")
        print(" ✅" if matched == len(template_headings) else " ⚠️ 일부 누락")

    # JSON 혼입
    has_json = "{" in output and "}" in output and '"' in output
    print(f"  JSON 혼입: {'⚠️ 발견됨' if has_json else '✅ 없음'}")

    # GitHub Alert 콜아웃 재현 확인
    note_ok = "> [!NOTE]" in output
    tip_ok  = "> [!TIP]" in output
    print(f"  > [!NOTE] 재현: {'✅' if note_ok else '⚠️ 미재현 (일반 > 로 대체됐을 수 있음)'}")
    print(f"  > [!TIP]  재현: {'✅' if tip_ok  else '⚠️ 미재현 (일반 > 로 대체됐을 수 있음)'}")

    # 중첩 blockquote 구조 (새롭게 알게 된 것)
    nested_bullet_in_quote = any(
        "> -" in line or ">   -" in line or ">-" in line
        for line in output.splitlines()
    )
    print(f"  blockquote 내 bullet 중첩: {'✅' if nested_bullet_in_quote else '⚠️ 미재현'}")


async def main() -> None:
    if not API_KEY:
        print("❌ GOOGLE_API_KEY 가 설정되지 않았습니다. .env.local 를 확인하세요.")
        return

    print(f"모델: {MODEL}")
    print("테스트 시작...\n")

    await run_test("기본 헤딩+불릿", TEMPLATE_BASIC, DUMMY_ENTRIES)
    await run_test("다양한 블록 (Notion 스타일)", TEMPLATE_RICH, DUMMY_ENTRIES)
    await run_test("자유 서술형 (헤딩 없음)", TEMPLATE_FREE, DUMMY_ENTRIES)
    await run_test_with_callout_check("실제 DB 템플릿 (GitHub Alert 콜아웃)", TEMPLATE_ACTUAL, DUMMY_ENTRIES)

    print(f"\n{'='*60}")
    print("테스트 완료")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
