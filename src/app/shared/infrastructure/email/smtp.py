import aiosmtplib
from email.message import EmailMessage

from app.shared.infrastructure.config.settings import get_settings


async def send_email(to: str, subject: str, body: str) -> None:
    cfg = get_settings().email
    message = EmailMessage()
    message["From"] = cfg.from_email
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=cfg.host,
        port=cfg.port,
        username=cfg.user,
        password=cfg.password,
        use_tls=cfg.use_tls,
    )
