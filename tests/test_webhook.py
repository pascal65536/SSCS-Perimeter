import hashlib
import hmac

from collector.webhook import normalize_webhook, valid_signature


def test_github_signature_is_constant_time_contract():
    body = b'{"zen":"test"}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert valid_signature(body, signature, "secret")
    assert not valid_signature(body, signature, "wrong")
    assert not valid_signature(body, "", "secret")


def test_push_webhook_normalizes_commit_and_perimeter_root():
    payload = {
        "repository": {"full_name": "psf/requests"},
        "commits": [{"id": "ABC123", "timestamp": "2026-10-24T12:00:00Z", "message": "fix", "author": {"username": "alice"}, "added": ["a.py"]}],
    }
    events = normalize_webhook("push", payload, ingested_at="2026-10-25T00:00:00Z", package_name="requests", watchlist="monitored", roots=["app"])
    assert events[0]["event"]["id"] == "gh:psf/requests:commit:abc123"
    assert events[0]["sscs"]["perimeter_root"] == ["app"]
    assert events[0]["sscs"]["commit"]["hour_of_day"] == 12
