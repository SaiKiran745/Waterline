"""Send the pre-storm playbook by email (AGENTS.md section 5 rule 6: approval first, allowed recipients only).

SMTP settings come from .env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM. Port 465 uses implicit TLS;
any other port uses STARTTLS. When any setting is missing the playbook is not sent: the status is
"draft_only" ("draft only, not sent") so the UI can say so. Every attempt is appended to
data/cache/agent/dossier/<id>/sends.json; the password is never logged.
"""
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

from app.config import CACHE, demo_mode
from app.sources.cache import write_json

SETTINGS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM")
LOG_DIR = CACHE / "agent" / "dossier"


def allowed() -> set[str]:
    return {a.strip().lower() for a in os.environ.get("ALLOWED_RECIPIENTS", "").split(",") if a.strip()}


def missing_settings() -> list[str]:
    return [k for k in SETTINGS if not os.environ.get(k, "").strip()]


def _log(bid: str, rec: dict) -> None:
    import json
    path = LOG_DIR / bid / "sends.json"
    log = json.loads(path.read_text()) if path.exists() else []
    write_json(path, log + [rec])


def last(bid: str) -> dict | None:
    """The most recent delivery attempt for a building (sends.json), or None."""
    import json
    path = LOG_DIR / bid / "sends.json"
    log = json.loads(path.read_text()) if path.exists() else []
    return log[-1] if log else None


def send_playbook(bid: str, recipient: str, depth_ft: float, html: str, approved: bool) -> dict:
    r = (recipient or "").strip().lower()
    out = {"building_id": bid, "recipient": r, "depth_ft": depth_ft, "approved": bool(approved),
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not approved:
        out.update(status="refused", detail="not approved by a person")
    elif r not in allowed():
        out.update(status="refused", detail="recipient is not in ALLOWED_RECIPIENTS")
    elif demo_mode():
        out.update(status="draft_only", detail="draft only, not sent: DEMO_MODE=1 (no network in demo mode)")
    elif missing_settings():
        out.update(status="draft_only", detail=f"draft only, not sent: {', '.join(missing_settings())} not set")
    else:
        msg = EmailMessage()
        msg["Subject"] = f"Waterline pre-storm playbook ({depth_ft:g} ft scenario)"
        msg["From"] = os.environ["EMAIL_FROM"]
        msg["To"] = r
        msg.set_content("The pre-storm playbook is attached as HTML. The depth is a scenario tied to elevation, not a "
                        "forecast: Waterline does not simulate how water arrives.")
        msg.add_alternative(html, subtype="html")
        host, port = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as s:
                    s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as s:
                    s.starttls(context=ssl.create_default_context())
                    s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                    s.send_message(msg)
            out.update(status="sent", detail=f"sent through {host}:{port}")
        except (smtplib.SMTPException, OSError) as e:
            out.update(status="failed", detail=f"{type(e).__name__}: {str(e)[:200]}")
    _log(bid, out)
    return out
