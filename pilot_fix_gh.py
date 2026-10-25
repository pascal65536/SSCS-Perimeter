import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

TOKEN = os.environ.get("GITHUB_TOKEN", "")
H = {
    "User-Agent": "sscs-monitor/0.1 (phase2 fix)",
    "Accept": "application/vnd.github+json",
}
if TOKEN:
    H["Authorization"] = f"Bearer {TOKEN}"

WINDOWS = {
    "dominictarr/event-stream": ("2018-08-01", "2018-12-31"),
    "faisalman/ua-parser-js": ("2021-09-01", "2021-11-30"),
    "ultralytics/ultralytics": ("2024-11-01", "2024-12-31"),
}
CRIT = (
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "__init__.py",
    ".github/workflows/",
    "package.json",
    "requirements",
    "publish",
    "release",
)


def gh(path, params=None, search=False):
    url = (
        ("https://api.github.com/search" + path)
        if search
        else ("https://api.github.com" + path)
    )
    if params:
        url += "?" + urlencode(params)  # пробелы/двоеточия в q — только через urlencode
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        time.sleep(2.2 if search else 0.3)  # search: 30 req/min
        return body


def search_prs(repo, d1, d2):
    items, page = [], 1
    while page <= 5:
        r = gh(
            "/issues",
            {
                "q": f"repo:{repo} is:pr created:{d1}..{d2}",
                "sort": "created",
                "order": "asc",
                "per_page": 100,
                "page": page,
            },
            search=True,
        )
        batch = r.get("items", [])
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def pr_enrich(repo, number, first_contrib):
    pr = gh(f"/repos/{repo}/pulls/{number}")
    reviews = gh(f"/repos/{repo}/pulls/{number}/reviews")
    files = gh(f"/repos/{repo}/pulls/{number}/files")
    return {
        "number": number,
        "author": (pr.get("user") or {}).get("login"),
        "created_at": pr["created_at"],
        "merged_at": pr.get("merged_at"),
        "merged_by": (pr.get("merged_by") or {}).get("login"),
        "review_count": len(reviews),
        "touches_critical": any(
            any(c in f.get("filename", "").lower() for c in CRIT) for f in files
        ),
        "author_first_contrib_at": first_contrib.get(
            (pr.get("user") or {}).get("login")
        ),
    }


def main():
    for path in sorted(Path("pilot/gh_fixtures").glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        repo = fx.get("repo")
        if repo not in WINDOWS:
            continue
        d1, d2 = WINDOWS[repo]
        first_contrib, logins = {}, set()
        for c in fx.get("commits") or []:
            login = c.get("login")
            if login:
                logins.add(login)
                if (
                    login not in first_contrib
                    or c["committed_at"] < first_contrib[login]
                ):
                    first_contrib[login] = c["committed_at"]
        for p in fx.get("pull_requests") or []:
            if p.get("author"):
                logins.add(p["author"])

        print(f"[{repo}] PR search {d1}..{d2} ...", flush=True)
        new_prs = []
        for it in search_prs(repo, d1, d2):
            try:
                new_prs.append(pr_enrich(repo, it["number"], first_contrib))
            except Exception as e:
                print(f"  ! PR {it['number']}: {type(e).__name__}", flush=True)
        old = {p["number"]: p for p in fx.get("pull_requests") or []}
        old.update({p["number"]: p for p in new_prs})
        fx["pull_requests"] = [old[k] for k in sorted(old)]
        for p in fx["pull_requests"]:
            if p.get("author") and not p.get("author_first_contrib_at"):
                p["author_first_contrib_at"] = first_contrib.get(p["author"])

        have = {pr["login"] for pr in fx.get("profiles") or []}
        for login in sorted(logins - have):
            try:
                u = gh(f"/users/{login}")
                fx.setdefault("profiles", []).append(
                    {
                        "login": login,
                        "date": d2,
                        "account_created_at": u.get("created_at"),
                        "followers": u.get("followers"),
                        "public_repos": u.get("public_repos"),
                    }
                )
            except Exception as e:
                print(f"  ! user {login}: {type(e).__name__}", flush=True)

        path.write_text(json.dumps(fx, ensure_ascii=False), encoding="utf-8")
        print(
            f"  итого: commits={len(fx['commits'])} prs={len(fx['pull_requests'])} "
            f"profiles={len(fx['profiles'])}",
            flush=True,
        )
    print("готово", flush=True)


if __name__ == "__main__":
    main()
