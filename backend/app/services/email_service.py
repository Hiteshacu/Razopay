"""Outbound email for admin approval requests.

Sent over plain SMTP so the only setup is an account and an app password —
no extra service to sign up for. When SMTP is not configured the service
quietly does nothing: a missing notification must never stop someone
creating an account, and approval still works from the console.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from ..config import settings


class EmailService:
    @property
    def configured(self) -> bool:
        return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)

    def send(self, to: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
        if not self.configured:
            print(f"WARNING: SMTP not configured, no email sent to {to} ({subject})")
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from or settings.smtp_username
        message["To"] = to
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        try:
            context = ssl.create_default_context()
            if settings.smtp_port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=20) as server:
                    server.login(settings.smtp_username, settings.smtp_password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                    server.starttls(context=context)
                    server.login(settings.smtp_username, settings.smtp_password)
                    server.send_message(message)
            return True
        except Exception as exc:
            # A failed notification is not a failed signup.
            print(f"WARNING: could not send approval email to {to}: {exc}")
            return False

    def send_approval_request(self, *, owner_email: str, requester_email: str, approve_url: str) -> bool:
        """Ask an owner to approve a newly created account."""
        safe_requester = escape(requester_email)
        safe_url = escape(approve_url, quote=True)

        text = (
            "Someone created a Digital Trust Shield account and is waiting to be "
            "approved as an authority.\n\n"
            f"Account: {requester_email}\n\n"
            "Approving lets this account sign documents in your authority's name. "
            "Only approve it if you recognise the address.\n\n"
            f"Review the request:\n{approve_url}\n\n"
            "The link opens a page where you confirm the decision. It can be used "
            "once and expires in 7 days. If you were not expecting this, ignore "
            "this email and the account stays locked out."
        )

        html = f"""\
<div style="font-family:-apple-system,'Segoe UI',sans-serif;line-height:1.6;color:#16201f;
            max-width:520px;margin:0 auto;padding:24px">
  <p style="font-size:0.72rem;letter-spacing:0.14em;text-transform:uppercase;
            color:#0f766e;font-weight:700;margin:0 0 6px">Digital Trust Shield</p>
  <h1 style="font-size:1.35rem;margin:0 0 16px">An account is waiting for approval</h1>
  <p style="margin:0 0 16px">
    <strong>{safe_requester}</strong> created an account and is asking to act as an
    issuing authority.
  </p>
  <p style="margin:0 0 22px;padding:12px 14px;background:#f6ecd4;border-radius:8px;
            color:#6b5210;font-size:0.92rem">
    Approving lets this account <strong>sign documents in your authority's name</strong>.
    Only approve it if you recognise the address.
  </p>
  <p style="margin:0 0 24px">
    <a href="{safe_url}"
       style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;
              font-weight:700;padding:13px 26px;border-radius:9px">Review this request</a>
  </p>
  <p style="margin:0;font-size:0.85rem;color:#677874">
    The link opens a page where you confirm the decision. It works once and expires in
    seven days. If you were not expecting this, ignore this email — the account stays
    locked out.
  </p>
</div>"""

        return self.send(
            to=owner_email,
            subject=f"Approve access for {requester_email}?",
            text_body=text,
            html_body=html,
        )
