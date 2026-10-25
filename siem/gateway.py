from __future__ import annotations

import base64
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

LOG = logging.getLogger(__name__)


class SIEMError(RuntimeError):
    pass


class OpenSearchGateway:
    """Bulk-доставка с _id=event.id и повторами; секреты берутся только из окружения."""

    def __init__(
        self,
        url: str,
        *,
        index: str = "sscs-events",
        verify_tls: bool = True,
        timeout: float = 30,
        retries: int = 3,
    ):
        self.url = url.rstrip("/")
        self.index = index
        self.timeout = timeout
        self.retries = max(3, retries)
        self.context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()

    def send(self, events: list[dict[str, Any]]) -> dict[str, int]:
        if not events:
            return {"accepted": 0, "duplicates": 0, "errors": 0}
        lines = []
        for event in events:
            event_id = event["event"]["id"]
            lines.append(json.dumps({"create": {"_index": self.index, "_id": event_id}}, separators=(",", ":")))
            lines.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        response = self._request("POST", "/_bulk", ("\n".join(lines) + "\n").encode("utf-8"), "application/x-ndjson")
        items = response.get("items", [])
        if len(items) != len(events):
            raise SIEMError(f"Неполный bulk-ответ: {len(items)} из {len(events)}")
        accepted = duplicates = errors = 0
        for item in items:
            result = item.get("create") or item.get("index") or {}
            status = int(result.get("status", 500))
            if status in {200, 201}:
                accepted += 1
            elif status == 409:
                duplicates += 1
            else:
                errors += 1
                LOG.error("OpenSearch отклонил документ: status=%s, type=%s", status, (result.get("error") or {}).get("type"))
        return {"accepted": accepted, "duplicates": duplicates, "errors": errors}

    def ping(self) -> bool:
        try:
            self._request("GET", "/", None, None, attempts=1)
            return True
        except SIEMError:
            return False

    def write_feedback(self, finding_id: str, label: str, *, index: str = "sscs-feedback", comment: str = "") -> None:
        if label not in {"true_positive", "false_positive"}:
            raise ValueError("label должен быть true_positive или false_positive")
        from datetime import datetime, timezone
        document = {
            "finding_id": finding_id,
            "label": label,
            "comment": comment,
            "labeled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "sscs-gui",
        }
        body = json.dumps(document, ensure_ascii=False).encode("utf-8")
        self._request("PUT", f"/{index}/_doc/{urllib.parse.quote(finding_id, safe='')}", body, "application/json")

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        content_type: str | None,
        *,
        attempts: int | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "SSCS-Perimeter/1.2"}
        if content_type:
            headers["Content-Type"] = content_type
        token = os.environ.get("SSCS_OPENSEARCH_TOKEN")
        username = os.environ.get("SSCS_OPENSEARCH_USERNAME")
        password = os.environ.get("SSCS_OPENSEARCH_PASSWORD")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            raw = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {raw}"
        attempts = attempts or self.retries
        url = f"{self.url}{path}"
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=self.timeout, context=self.context) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    raise SIEMError(f"OpenSearch HTTP {exc.code} для {method} {path}") from exc
                if attempt == attempts - 1:
                    raise SIEMError(f"OpenSearch недоступен: HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After")
                try:
                    pause = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    pause = 2**attempt
                time.sleep(max(0.0, pause))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == attempts - 1:
                    raise SIEMError(f"OpenSearch недоступен: {type(exc).__name__}") from exc
                time.sleep(2**attempt)
        raise AssertionError("unreachable")
