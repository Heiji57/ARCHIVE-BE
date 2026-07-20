import aiosmtplib
from email.message import EmailMessage

from app.shared.infrastructure.config.settings import get_settings


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

    await aiosmtplib.send(
        message,
        hostname=cfg.host,
        port=cfg.port,
        username=cfg.user,
        password=cfg.password,
        start_tls=cfg.use_tls,
    )
