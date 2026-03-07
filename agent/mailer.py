from email.message import EmailMessage
from pathlib import Path
import smtplib


def send_email_with_zip(
    to_address: str,
    subject: str,
    body: str,
    zip_path: Path,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
) -> None:
    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    msg.add_attachment(
        Path(zip_path).read_bytes(),
        maintype="application",
        subtype="zip",
        filename=Path(zip_path).name,
    )

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)

