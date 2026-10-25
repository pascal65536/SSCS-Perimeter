import json
from pathlib import Path

ING = "2026-10-19T10:00:00Z"


def created(name, author, ts, watchlist, ref):
    return {
        "@timestamp": ts,
        "event": {
            "id": f"pypi:{name}:{ts}",
            "kind": "event",
            "category": "package",
            "type": "creation",
            "action": "package.created",
            "ingested": ING,
            "outcome": "success",
        },
        "source": {"service": "pypi-api", "component": "pypi-json"},
        "package": {"name": name, "author": author, "registry": "pypi"},
        "sscs": {
            "schema_version": "1.0",
            "watchlist": watchlist,
            "repo": None,
            "point_in_time": True,
            "reference": ref,
            "created": {"first_release_at": ts, "levenshtein_hits": []},
        },
    }


def release(name, version, ts, author="mallory"):
    return {
        "@timestamp": ts,
        "event": {
            "id": f"pypi:{name}:{version}:{ts}",
            "kind": "event",
            "category": "package",
            "type": "creation",
            "action": "package.release",
            "ingested": ING,
            "outcome": "success",
        },
        "source": {"service": "pypi-api", "component": "pypi-json"},
        "package": {
            "name": name,
            "version": version,
            "author": author,
            "registry": "pypi",
        },
        "sscs": {
            "schema_version": "1.0",
            "watchlist": "ground_truth",
            "repo": None,
            "point_in_time": True,
        },
    }


def profile(login, ts, date, followers):
    return {
        "@timestamp": ts,
        "event": {
            "id": f"github-api:{login}:metric:{date}",
            "kind": "metric",
            "category": "user",
            "type": "info",
            "action": "user.profile_snapshot",
            "ingested": ING,
            "outcome": "success",
        },
        "source": {"service": "github-api", "component": "github-rest"},
        "user": {"name": login},
        "sscs": {
            "schema_version": "1.0",
            "watchlist": "ground_truth",
            "repo": None,
            "point_in_time": True,
            "user": {
                "followers": followers,
                "public_repos": 1,
                "account_created_at": "2023-12-01T00:00:00Z",
            },
        },
    }


def commit(repo, sha, ts, login):
    return {
        "@timestamp": ts,
        "event": {
            "id": f"gh:{repo}:commit:{sha}",
            "kind": "event",
            "category": "code_change",
            "type": "change",
            "action": "repo.commit",
            "ingested": ING,
            "outcome": "success",
        },
        "source": {"service": "github-api", "component": "github-rest"},
        "user": {"name": login},
        "sscs": {
            "schema_version": "1.0",
            "watchlist": "ground_truth",
            "repo": repo,
            "point_in_time": True,
            "commit": {
                "sha": sha,
                "message": "update deps",
                "additions": 12,
                "deletions": 3,
                "files_changed": 2,
                "is_merge": False,
                "anonymous": False,
                "committed_at": ts,
            },
        },
    }


REF_NAMES = [
    "numpy-lite",
    "pandas-helper",
    "flask-utils",
    "django-tools",
    "sqlalchemy-x",
    "pytest-plus",
    "clickx",
    "boto3x",
    "pillow-x",
    "aiohttp-x",
    "requests",
]
AUTHORS = [
    "alice",
    "bob",
    "carol",
    "dave",
    "erin",
    "frank",
    "gina",
    "helen",
    "ivan",
    "judy",
    "kate",
]

docs = [
    created(n, a, f"2024-01-{i+1:02d}T10:00:00Z", "reference", True)
    for i, (n, a) in enumerate(zip(REF_NAMES, AUTHORS))
]

docs.append(
    created("burst-pkg", "mallory", "2024-01-01T00:00:00Z", "ground_truth", False)
)
for v, ts in [
    ("1.0.0", "2024-01-01T00:00:00Z"),
    ("1.0.1", "2024-01-31T00:00:00Z"),
    ("1.0.2", "2024-03-01T00:00:00Z"),
    ("1.0.3", "2024-03-02T06:00:00Z"),
    ("1.0.4", "2024-03-02T18:00:00Z"),
]:
    docs.append(release("burst-pkg", v, ts))

docs.append(created("junk-a", "mallory", "2024-02-01T00:00:00Z", "ground_truth", False))
docs.append(profile("mallory", "2024-02-15T00:00:00Z", "2024-02-15", 2))
docs.append(created("junk-b", "mallory", "2024-02-20T00:00:00Z", "ground_truth", False))
docs.append(created("reqeusts", "eve", "2024-03-01T09:00:00Z", "ground_truth", False))

docs.append(
    {
        "@timestamp": None,
        "event": {
            "id": "broken-ts",
            "kind": "event",
            "category": "package",
            "type": "creation",
            "action": "package.created",
            "outcome": "failure",
        },
        "source": {"service": "pypi-api", "component": "pypi-json"},
        "package": {"name": "broken-pkg", "registry": "pypi"},
        "sscs": {
            "schema_version": "1.0",
            "watchlist": "monitored",
            "repo": None,
            "point_in_time": True,
        },
    }
)

out = Path("tests/fixtures")
out.mkdir(parents=True, exist_ok=True)
(out / "reference.jsonl").write_text(
    "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs), encoding="utf-8"
)
print(f"tests/fixtures/reference.jsonl: {len(docs)} строк")

cf = [
    created("legacy-lib", "old-dev", "2020-01-15T10:00:00Z", "ground_truth", False),
    release("legacy-lib", "3.3.0", "2023-09-12T06:00:00Z", author="old-dev"),
    {
        "@timestamp": "2023-09-11T10:00:00Z",
        "event": {
            "id": "gh:old-dev/legacy-lib:member:right9ctrl:20230911:added",
            "kind": "event",
            "category": "iam",
            "type": "creation",
            "action": "repo.membership_change",
            "ingested": ING,
            "outcome": "success",
        },
        "source": {"service": "github-api", "component": "github-rest"},
        "user": {"name": "right9ctrl"},
        "package": {"name": "legacy-lib", "registry": None, "author": None},
        "sscs": {
            "schema_version": "1.0",
            "watchlist": "ground_truth",
            "repo": "old-dev/legacy-lib",
            "point_in_time": True,
            "member": {
                "login": "right9ctrl",
                "role": "maintainer",
                "event_at": "2023-09-11T10:00:00Z",
                "change_type": "added",
            },
        },
    },
    {
        "@timestamp": "2023-09-12T00:00:00Z",
        "event": {
            "id": "github-api:right9ctrl:metric:2023-09-12",
            "kind": "metric",
            "category": "user",
            "type": "info",
            "action": "user.profile_snapshot",
            "ingested": ING,
            "outcome": "success",
        },
        "source": {"service": "github-api", "component": "github-rest"},
        "user": {"name": "right9ctrl"},
        "package": {"name": None, "registry": None, "author": None},
        "sscs": {
            "schema_version": "1.0",
            "watchlist": "ground_truth",
            "repo": None,
            "point_in_time": True,
            "user": {
                "account_created_at": "2018-08-15T14:22:00Z",
                "followers": 2,
                "public_repos": 1,
            },
        },
    },
]
cf[1]["sscs"]["release"] = {
    "released_at": "2023-09-12T06:00:00Z",
    "size": 48213,
    "yanked": False,
    "requires_dist": ["requests>=2"],
    "digests": {"sha256": "9f2c"},
}
cf[0]["sscs"]["repo"] = "old-dev/legacy-lib"
sd = Path("storage/data")
sd.mkdir(parents=True, exist_ok=True)
(sd / "collector_fixture.jsonl").write_text(
    "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in cf), encoding="utf-8"
)
print(f"storage/data/collector_fixture.jsonl: {len(cf)} строк")

s9_valid = [
    release("legacy-lib", "3.3.0", "2023-09-12T06:00:00Z", author="old-dev"),
    commit("dominictarr/event-stream", "abc123", "2023-09-12T07:00:00Z", "right9ctrl"),
    profile("right9ctrl", "2023-09-12T08:00:00Z", "2023-09-12", 12),
]
broken = {
    "@timestamp": None,
    "event": {
        "id": "github-api:user:emptyprof:metric:2023-09-12",
        "kind": "metric",
        "category": "user",
        "type": "info",
        "action": "user.profile_snapshot",
        "ingested": ING,
        "outcome": "success",
    },
    "source": {"service": "github-api", "component": "github-graphql"},
    "user": {"name": "EmptyProf"},
    "sscs": {
        "schema_version": "1.0",
        "watchlist": "monitored",
        "repo": None,
        "point_in_time": True,
        "user": {
            "account_created_at": "2020-01-01T00:00:00Z",
            "followers": 0,
            "public_repos": 1,
        },
    },
}
(sd / "sample_r9_valid.jsonl").write_text(
    "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in s9_valid),
    encoding="utf-8",
)
(sd / "sample_r9.jsonl").write_text(
    "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in s9_valid + [broken]),
    encoding="utf-8",
)
print("storage/data/sample_r9_valid.jsonl: 3 строки; sample_r9.jsonl: 4 строки")

fut = release("future-pkg", "9.9.9", "2027-01-01T00:00:00Z")
(sd / "future.jsonl").write_text(
    json.dumps(fut, ensure_ascii=False) + "\n", encoding="utf-8"
)
print("storage/data/future.jsonl: 1 строка")
