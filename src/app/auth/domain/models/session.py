"""Session 도메인 모델.

서버 측 신뢰 기준점(server-side trust anchor).
Client는 RT(`{sessionId}.{secret}`)만 들고 다니며, 모든 판단은 이 레코드를 근거로 한다.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:
    session_id: str
    user_id: str
    rt_hash: str                          # 현재 유효 refresh token secret 의 SHA-256
    prev_rt_hash: str | None              # 직전 RT secret hash (grace 윈도 동안)
    prev_at: datetime | None              # 직전 rotation 시각 (grace 판정용)
    device_info: str | None               # UA 원문
    device_label: str | None              # UA 파싱 결과 (e.g. "Chrome on Windows")
    ip_prefix: str | None                 # /24 마스킹된 IP (통계용)
    issued_at: datetime
    last_used_at: datetime
    rotation_counter: int
