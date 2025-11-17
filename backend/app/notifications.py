from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from threading import Thread
from typing import Any
from urllib import error, request

from .config import get_settings
from .models import AutomationRun, AutomationRunEvent


INTERESTING_EVENTS = {"success", "failed", "timeout"}


def _post_json(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=5):  # type: ignore[call-arg]
            pass
    except error.URLError:
        pass


def _send_email(subject: str, body: str) -> None:
    settings = get_settings()
    recipients = settings.notification_emails
    if not settings.smtp_host or not recipients:
        return
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_username or "soar@example.com"
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
            if settings.smtp_use_tls:
                try:
                    smtp.starttls()
                except smtplib.SMTPException:
                    pass
            if settings.smtp_username and settings.smtp_password:
                try:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                except smtplib.SMTPException:
                    pass
            smtp.send_message(message)
    except OSError:
        pass


def _build_message(run: AutomationRun, event: AutomationRunEvent) -> str:
    automation_name = event.payload.get("automation_name") or run.automation_id
    status_map = {
        "success": "başarıyla tamamlandı",
        "failed": "hata verdi",
        "timeout": "zaman aşımına uğradı",
    }
    status_label = status_map.get(event.event_type, event.event_type)
    return (
        f"Automation {automation_name} için koşum {run.id} {status_label}. "
        f"Deneme: {run.attempts}, Süre: {run.duration_ms or 'bilinmiyor'}ms"
    )


def dispatch_run_event_notification(run: AutomationRun, event: AutomationRunEvent) -> None:
    if event.event_type not in INTERESTING_EVENTS:
        return
    settings = get_settings()
    if not (
        settings.slack_webhook_url
        or settings.teams_webhook_url
        or (settings.smtp_host and settings.notification_emails)
    ):
        return
    message = _build_message(run, event)

    def worker() -> None:
        if settings.slack_webhook_url:
            _post_json(settings.slack_webhook_url, {"text": message})
        if settings.teams_webhook_url:
            _post_json(settings.teams_webhook_url, {"text": message})
        if settings.smtp_host and settings.notification_emails:
            subject = f"Automation {event.event_type}: {event.payload.get('automation_name', run.automation_id)}"
            _send_email(subject, message)

    Thread(target=worker, daemon=True).start()
