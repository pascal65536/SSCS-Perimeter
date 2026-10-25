from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class HttpError(RuntimeError):
    status: int
    url: str
    message: str = "HTTP request failed"

    def __str__(self) -> str:
        return f"HTTP {self.status} для {self.url}: {self.message}"


class JsonHttpClient:
    """Минимальный HTTP-клиент без секретов и глобального состояния."""

    def __init__(self, *, timeout: float = 20, min_interval: float = 0.0, retries: int = 3):
        self.timeout = timeout
        self.min_interval = min_interval
        self.retries = retries
        self._last_request = 0.0

    def get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "SSCS-Perimeter/1.2 (supply-chain research)",
            **(headers or {}),
        }
        for attempt in range(self.retries):
            delay = self.min_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            req = urllib.request.Request(url, headers=request_headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    self._last_request = time.monotonic()
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                self._last_request = time.monotonic()
                if exc.code == 404:
                    raise HttpError(404, url, "ресурс не найден") from exc
                if exc.code not in {403, 429, 500, 502, 503, 504} or attempt == self.retries - 1:
                    raise HttpError(exc.code, url, exc.reason) from exc
                retry_after = exc.headers.get("Retry-After")
                try:
                    pause = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    pause = 2**attempt
                time.sleep(max(0.0, pause))
            except (urllib.error.URLError, TimeoutError) as exc:
                self._last_request = time.monotonic()
                if attempt == self.retries - 1:
                    raise HttpError(0, url, str(exc)) from exc
                time.sleep(2**attempt)
        raise AssertionError("unreachable")


def quoted(value: str) -> str:
    return urllib.parse.quote(value, safe="")
