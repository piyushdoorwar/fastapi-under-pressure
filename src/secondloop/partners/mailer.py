"""Client for SecondLoop's email provider."""

import httpx2
from fastapi import Request

from secondloop.settings import settings


class MailerError(Exception):
    """The email provider didn't accept a message."""


class Mailer:
    def __init__(self, http: httpx2.AsyncClient):
        self.http = http

    async def send(
        self, to: str, subject: str, body: str
    ) -> None:
        try:
            resp = await self.http.post(
                "/v1/messages",
                json={
                    "to": to,
                    "subject": subject,
                    "body": body,
                },
            )
            resp.raise_for_status()
        except httpx2.HTTPError as exc:
            raise MailerError(str(exc)) from exc


def make_mailer_http() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=settings.mailer_url, timeout=2.0
    )


def get_mailer(request: Request) -> Mailer:
    return request.app.state.mailer
