from __future__ import annotations

from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from fastapi_mail.errors import ConnectionErrors
from pydantic import EmailStr

from conf.config import settings
from services.auth import create_email_token

conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_FROM_NAME=settings.mail_from_name,
    MAIL_STARTTLS=settings.mail_starttls,
    MAIL_SSL_TLS=settings.mail_ssl_tls,
    USE_CREDENTIALS=settings.use_credentials,
    VALIDATE_CERTS=settings.validate_certs,
    TEMPLATE_FOLDER=Path(__file__).parent / "templates",
)


async def send_verification_email(email: EmailStr, username: str, host: str) -> None:
    """Send the email-confirmation link as a background task.

    Connection errors are swallowed so a mail outage never breaks the
    request that enqueued this task.
    """
    try:
        token = create_email_token({"sub": email})
        message = MessageSchema(
            subject="Confirm your email",
            recipients=[email],
            template_body={"host": host, "username": username, "token": token},
            subtype=MessageType.html,
        )
        fm = FastMail(conf)
        await fm.send_message(message, template_name="verify_email.html")
    except ConnectionErrors as err:
        print(err)
