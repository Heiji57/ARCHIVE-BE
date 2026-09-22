import aiosmtplib
from email.message import EmailMessage

from app.shared.domain.exceptions.external import EmailDeliveryFailedException
from app.shared.infrastructure.config.settings import get_settings

# aiosmtplib 기본값(60s)이면 SMTP 서버가 멈췄을 때 인증 메일 요청이 1분간 매달린다.
_SMTP_TIMEOUT_SECONDS = 15


async def send_email(
    to: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    cfg = get_settings().email
    message = EmailMessage()
    message["From"] = cfg.from_email or cfg.user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=cfg.host,
            port=cfg.port,
            username=cfg.user,
            password=cfg.password,
            start_tls=cfg.use_tls,
            timeout=_SMTP_TIMEOUT_SECONDS,
        )
    except (aiosmtplib.SMTPException, OSError) as e:
        # 수신자 주소 전체는 남기지 않는다(PII) — 도메인만.
        domain = to.rsplit("@", 1)[-1]
        raise EmailDeliveryFailedException(
            f"SMTP send to *@{domain} failed: {type(e).__name__}"
        ) from e
