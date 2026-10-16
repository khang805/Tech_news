"""Sends email over SMTP (Gmail App Password by default) to one or more recipients.
Credentials come only from environment variables / GitHub Secrets."""
import logging
import os
import smtplib
import time
from email.message import EmailMessage

log = logging.getLogger(__name__)


def parse_recipients(value) -> list[str]:
    items = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    return [x.strip() for x in items if x and str(x).strip()]


def load_email_config(settings: dict) -> dict:
    recipients = parse_recipients(os.environ.get("EMAIL_TO")) or parse_recipients(settings["email"]["to"])
    return {
        "host": os.environ.get("SMTP_HOST") or "smtp.gmail.com",
        "port": int(os.environ.get("SMTP_PORT") or 587),
        "username": os.environ.get("SMTP_USERNAME") or "",
        "password": os.environ.get("SMTP_PASSWORD") or "",
        "sender": os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USERNAME") or "",
        "recipients": recipients,
    }


def is_configured(cfg: dict) -> bool:
    return bool(cfg["username"] and cfg["password"] and cfg["sender"] and cfg["recipients"])


def _message(cfg: dict, recipient: str, subject: str, text: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = recipient
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send_email(cfg: dict, subject: str, text: str, html: str, dry_run: bool = False,
               sleep=time.sleep, smtp_class=smtplib.SMTP) -> bool:
    """Send to every recipient (one message each, so addresses are not shown to each other). True if all sent."""
    subject = " ".join(subject.split())
    if dry_run:
        log.info("[no-send] would email %d recipient(s): %s", len(cfg["recipients"]), subject)
        return True
    if not is_configured(cfg):
        log.warning("email not configured (SMTP_USERNAME, SMTP_PASSWORD, recipients); skipped: %s", subject)
        return False
    pending = list(cfg["recipients"])
    for attempt in range(3):
        try:
            with smtp_class(cfg["host"], cfg["port"], timeout=30) as server:
                server.starttls()
                server.login(cfg["username"], cfg["password"])
                while pending:
                    server.send_message(_message(cfg, pending[0], subject, text, html))
                    pending.pop(0)
            log.info("emailed %d recipient(s): %s", len(cfg["recipients"]), subject)
            return True
        except smtplib.SMTPAuthenticationError:
            log.error("SMTP login failed. Check SMTP_USERNAME and use a Gmail App Password for SMTP_PASSWORD.")
            return False
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("email attempt %d failed (%s); %d recipient(s) still pending",
                        attempt + 1, type(exc).__name__, len(pending))
            sleep(2 ** attempt)
    log.error("giving up on email to %d recipient(s): %s", len(pending), subject)
    return False
