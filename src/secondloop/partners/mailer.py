"""Client for SecondLoop's email provider."""

import httpx2
from fastapi import Request

from secondloop.settings import settings


class MailerError(Exception):
    """The email provider didn't accept a message.

    `permanent` means trying again won't help: the
    provider said no (a 4xx), not "not now"."""

    def __init__(self, reason: str, permanent=False):
        super().__init__(reason)
        self.permanent = permanent


class Mailer:
    def __init__(self, http: httpx2.AsyncClient):
        self.http = http

    async def send(
        self, to: str, subject: str, body: str,
        key: str | None = None,
    ) -> None:
        """Send one message. With a key, the provider
        sends at most one message per key, however many
        times this is called."""
        headers = {"Idempotency-Key": key} if key else {}
        try:
            resp = await self.http.post(
                "/v1/messages",
                json={
                    "to": to,
                    "subject": subject,
                    "body": body,
                },
                headers=headers,
            )
            resp.raise_for_status()
        except httpx2.HTTPStatusError as exc:
            status = exc.response.status_code
            raise MailerError(
                f"provider answered {status}",
                permanent=status in PERMANENT,
            ) from exc
        except httpx2.HTTPError as exc:
            # A timeout has an empty message; the type
            # says what happened.
            raise MailerError(type(exc).__name__) from exc


# 408 and 429 are 4xx but mean "try again later".
PERMANENT = set(range(400, 500)) - {408, 429}


def make_mailer_http() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=settings.mailer_url,
        timeout=settings.mailer_timeout_s,
    )


def get_mailer(request: Request) -> Mailer:
    return request.app.state.mailer
