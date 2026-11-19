from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    id: str
    email: str
    # 마지막으로 자격 증명을 확인한 시각(epoch 초) — 로그인 때 정해지고 refresh 로는 바뀌지 않는다.
    # 계정 삭제처럼 "최근 로그인"이 필요한 동작이 본다.
    # 없으면(옛 토큰) 최근 로그인이 아닌 것으로 본다.
    auth_time: float | None = None
