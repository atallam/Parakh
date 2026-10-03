"""Email delivery: SMTP over SSL, and the monthly email builder (ADR-008; AC-F11.11).

    mailer = SmtpMailer.from_env(bundle.notify.channels.email)
    mailer.send_html("Parakh: October review", html, text, [("results.ics", ics, "text/calendar")])

Credentials come from `get_secret` (SMTP_USER, SMTP_PASSWORD, MAIL_TO). They are never logged.
"""

from __future__ import annotations

import html as _html
import smtplib
import ssl
from email.message import EmailMessage

import structlog

from parakh.configs.notify_models import EmailChannel
from parakh.notify.telegram import Delivery

log = structlog.get_logger(__name__)


def build_message(
    sender: str,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(text or _html.unescape(html))
    msg.add_alternative(f"<html><body>{html}</body></html>", subtype="html")
    for name, data, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(
            data, maintype=maintype, subtype=subtype or "octet-stream", filename=name
        )
    return msg


class SmtpMailer:
    def __init__(self, cfg: EmailChannel, user: str, password: str, to: str) -> None:
        self.cfg, self.user, self.password, self.to = cfg, user, password, to

    @classmethod
    def from_env(cls, cfg: EmailChannel) -> SmtpMailer | None:
        from parakh.secrets import get_secret

        user, pw = get_secret("SMTP_USER"), get_secret("SMTP_PASSWORD")
        to = get_secret("MAIL_TO") or user
        if not (user and pw and to):
            return None
        return cls(cfg, user, pw, to)

    def send_html(
        self,
        subject: str,
        html: str,
        text: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> Delivery:
        msg = build_message(self.user, self.to, subject, html, text, attachments)
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self.cfg.smtp_host, self.cfg.smtp_port, context=ctx, timeout=30
            ) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            # why: the error class is enough; the message can echo the address or the login
            log.warning("email.send_failed", error=type(exc).__name__)
            return Delivery(False, error=type(exc).__name__)
        return Delivery(True, provider_msg_id=msg["Message-ID"])
