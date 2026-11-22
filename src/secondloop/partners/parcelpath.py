"""ParcelPath rate client, adapted from the
partner's quick-start sample."""

from dataclasses import dataclass

import requests

from secondloop.settings import settings


@dataclass
class Rate:
    service: str
    amount_cents: int
    eta_days: int


class ParcelPathClient:
    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url
        self.timeout = timeout
        self.http = requests.Session()

    def get_rate(
        self, weight_grams: int, postcode: str
    ) -> Rate:
        resp = self.http.post(
            f"{self.base_url}/v1/rates",
            json={
                "weight_grams": weight_grams,
                "postcode": postcode,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return Rate(**resp.json())


parcelpath = ParcelPathClient(
    settings.parcelpath_url,
    settings.parcelpath_timeout_s,
)
