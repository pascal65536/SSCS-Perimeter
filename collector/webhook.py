from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from collector import normalize
from collector.collectors import github as gh
from settings_manager import SettingsManager
from spool import DiskSpool

LOG = logging.getLogger(__name__)


def valid_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256=") or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def normalize_webhook(kind: str, payload: dict[str, Any], *, ingested_at: str, package_name: str | None, watchlist: str, roots: list[str]) -> list[dict]:
    repo = (payload.get("repository") or {}).get("full_name")
    if not repo:
        raise ValueError("repository.full_name обязателен")
    events = []
    if kind == "push":
        for commit in payload.get("commits") or []:
            author = commit.get("author") or {}
            src = gh.collect_repo_commit({"repo": repo, "package_name": package_name, "commit": {
                "sha": commit["id"], "login": author.get("username") or author.get("name"),
                "message": commit.get("message"), "additions": None, "deletions": None,
                "files_changed": len(set((commit.get("added") or []) + (commit.get("modified") or []) + (commit.get("removed") or []))),
                "is_merge": False, "committed_at": commit["timestamp"],
            }})
            events.append(normalize.normalize_github_commit(src, watchlist=watchlist, ingested_at=ingested_at))
    elif kind == "pull_request":
        pr = payload["pull_request"]
        src = gh.collect_repo_pull_request({"repo": repo, "package_name": package_name, "pull_request": {
            "number": pr["number"], "author": (pr.get("user") or {}).get("login"), "created_at": pr["created_at"],
            "merged_at": pr.get("merged_at"), "merged_by": (pr.get("merged_by") or {}).get("login"),
            "review_count": pr.get("review_count"), "touches_critical": bool(pr.get("_sscs_touches_critical")),
            "author_first_contrib_at": pr.get("_sscs_author_first_contrib_at"),
        }})
        events.append(normalize.normalize_github_pr(src, watchlist=watchlist, ingested_at=ingested_at))
    elif kind == "member":
        if payload.get("action") not in {"added", "removed"}:
            raise ValueError("member.action должен быть added или removed")
        member = payload["member"]
        src = gh.collect_repo_membership_change({"repo": repo, "package_name": package_name, "membership": {
            "login": member["login"], "role": payload.get("permission", "maintainer"),
            "change_type": payload["action"], "event_at": ingested_at,
        }})
        events.append(normalize.normalize_membership_change(src, watchlist=watchlist, ingested_at=ingested_at))
    elif kind in {"release", "workflow_run"}:
        obj = payload.get("release") or payload.get("workflow_run") or {}
        object_id = obj.get("id") or obj.get("tag_name")
        action = "repo.release" if kind == "release" else "repo.workflow_run"
        events.append({
            "@timestamp": obj.get("published_at") or obj.get("created_at") or ingested_at,
            "event": {"id": f"gh:{repo.lower()}:{kind}:{object_id}", "kind": "event", "category": "code_change", "type": "creation", "action": action, "ingested": ingested_at, "outcome": "success"},
            "source": {"service": "github-api", "component": "github-webhook"},
            "package": {"name": package_name, "registry": "pypi" if package_name else None},
            "sscs": {"schema_version": "1.0", "watchlist": watchlist, "repo": repo, "point_in_time": True, "perimeter_root": sorted(set(roots)), "webhook": {"delivery_kind": kind, "object_id": object_id}},
        })
    else:
        raise ValueError(f"Неподдерживаемый GitHub event: {kind}")
    return [normalize.with_perimeter_root(event, roots) for event in events]


class WebhookApplication:
    def __init__(self, settings: dict, spool: DiskSpool):
        self.settings = settings
        self.spool = spool
        self.by_repo = {p.get("repo"): p for p in settings["perimeter"]["packages"] if p.get("repo")}

    def handle(self, kind: str, payload: dict) -> dict[str, int]:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        repo = (payload.get("repository") or {}).get("full_name")
        package = self.by_repo.get(repo, {})
        events = normalize_webhook(kind, payload, ingested_at=stamp, package_name=package.get("name"), watchlist="monitored", roots=package.get("perimeter_root") or [self.settings["project"]["name"]])
        return self.spool.extend(events)


class Handler(BaseHTTPRequestHandler):
    application: WebhookApplication
    secret: str

    def do_POST(self):
        if self.path != "/github":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2 * 1024 * 1024:
                raise ValueError("invalid content length")
            body = self.rfile.read(length)
            if not valid_signature(body, self.headers.get("X-Hub-Signature-256", ""), self.secret):
                self.send_error(401, "invalid signature")
                return
            result = self.application.handle(self.headers["X-GitHub-Event"], json.loads(body))
            response = json.dumps(result).encode()
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            LOG.warning("Webhook отклонён: %s", exc)
            self.send_error(400, "invalid event")

    def log_message(self, fmt, *args):
        LOG.info("webhook: " + fmt, *args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-github-webhook")
    parser.add_argument("--settings", type=Path, default=Path("settings.json"))
    parser.add_argument("--spool", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if not os.environ.get("GITHUB_WEBHOOK_SECRET"):
        parser.error("Задайте GITHUB_WEBHOOK_SECRET в окружении")
    settings = SettingsManager(args.settings).load()
    spool = DiskSpool(args.spool or settings["spool"]["path"], max_bytes=settings["spool"]["max_bytes"])
    Handler.application = WebhookApplication(settings, spool)
    Handler.secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    logging.basicConfig(level=logging.INFO)
    print(f"GitHub webhook: http://{args.host}:{args.port}/github; при недоступности endpoint используется collector.service polling")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
