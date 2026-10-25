import json
from pathlib import Path

root = Path("demo_fixtures")
(root / "fixtures").mkdir(parents=True, exist_ok=True)

reference = [
    "requests",
    "flask",
    "django",
    "numpy",
    "pandas",
    "sqlalchemy",
    "pytest",
    "click",
    "boto3",
    "pillow",
]
(root / "reference.json").write_text(json.dumps(reference, indent=2), encoding="utf-8")

pypi = {
    "kind": "pypi_package",
    "watchlist": "ground_truth",
    "repo": "old-dev/legacy-lib",
    "info": {
        "name": "legacy-lib",
        "version": "3.3.0",
        "uploader": "old-dev",
        "requires_dist": ["requests>=2"],
    },
    "releases": {
        "2.0.0": [
            {
                "upload_time": "2020-01-15T10:00:00Z",
                "size": 40000,
                "yanked": False,
                "digests": {"sha256": "aa11"},
            }
        ],
        "3.3.0": [
            {
                "upload_time": "2023-09-12T06:00:00Z",
                "size": 48213,
                "yanked": False,
                "digests": {"sha256": "9f2c"},
            }
        ],
    },
}
(root / "fixtures" / "pypi_legacy-lib.json").write_text(
    json.dumps(pypi, indent=2, ensure_ascii=False), encoding="utf-8"
)

gh = {
    "kind": "github_repo",
    "watchlist": "ground_truth",
    "repo": "old-dev/legacy-lib",
    "package_name": "legacy-lib",
    "commits": [
        {
            "sha": "Cafe001",
            "login": "old-dev",
            "message": "regular work",
            "additions": 10,
            "deletions": 2,
            "files_changed": 1,
            "is_merge": False,
            "committed_at": "2023-09-10T12:00:00Z",
        },
        {
            "sha": "Cafe002",
            "login": "old-dev",
            "message": "another commit",
            "additions": 5,
            "deletions": 1,
            "files_changed": 1,
            "is_merge": False,
            "committed_at": "2023-09-11T12:00:00Z",
        },
    ],
    "pull_requests": [
        {
            "number": 42,
            "author": "right9ctrl",
            "created_at": "2023-09-11T09:00:00Z",
            "merged_at": "2023-09-11T09:05:00Z",
            "merged_by": "old-dev",
            "review_count": 0,
            "touches_critical": True,
            "author_first_contrib_at": "2023-09-01T00:00:00Z",
        },
    ],
    "snapshots": [
        {
            "date": "2023-09-12",
            "stars": 220,
            "forks": 30,
            "watchers": 12,
            "open_issues": 5,
            "open_prs": 1,
        },
    ],
    "members": [
        {
            "login": "right9ctrl",
            "role": "maintainer",
            "change_type": "added",
            "event_at": "2023-09-11T10:00:00Z",
        },
    ],
    "profiles": [
        {
            "login": "right9ctrl",
            "date": "2023-09-12",
            "account_created_at": "2018-08-15T14:22:00Z",
            "followers": 2,
            "public_repos": 1,
        },
    ],
}
(root / "fixtures" / "gh_legacy-lib.json").write_text(
    json.dumps(gh, indent=2, ensure_ascii=False), encoding="utf-8"
)
print("demo_fixtures: reference.json, pypi_legacy-lib.json, gh_legacy-lib.json")
