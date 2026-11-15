import smtplib
import ssl
from email.message import EmailMessage


def send_mail(config, recipient, subject, body, message_id=None):
    if not config.smtp_host or not config.smtp_from:
        raise ValueError("未配置 SMTP")
    if config.smtp_mode not in {"tls", "starttls"}:
        raise ValueError("SMTP_MODE 必须为 tls 或 starttls")

    message = EmailMessage()
    message["From"] = config.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    if message_id:
        message["Message-ID"] = message_id
    message.set_content(body)

    context = ssl.create_default_context()
    if config.smtp_mode == "tls":
        connection = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=8, context=context)
    else:
        connection = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=8)
    with connection:
        if config.smtp_mode == "starttls":
            connection.starttls(context=context)
        if config.smtp_user:
            connection.login(config.smtp_user, config.smtp_password)
        connection.send_message(message)
