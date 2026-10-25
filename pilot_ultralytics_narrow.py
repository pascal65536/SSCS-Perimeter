import json, os, time, urllib.request
from pathlib import Path

H = {
    "User-Agent": "sscs-monitor/0.1 (narrow rebuild)",
    "Accept": "application/vnd.github+json",
}
if os.environ.get("GITHUB_TOKEN"):
    H["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

REPO = "ultralytics/ultralytics"
D1, D2 = "2024-12-07", "2024-12-12"


def gh(path, params=None, search=False):
    url = (
        ("https://api.github.com/search" + path)
        if search
        else ("https://api.github.com" + path)
    )
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=30) as resp:
        time.sleep(2.2 if search else 0.3)
        return json.loads(resp.read().decode("utf-8"))


items, page = [], 1
while True:
    r = gh(
        "/issues",
        {
            "q": f"repo:{REPO} is:pr created:{D1}..{D2}",
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
print(f"PR за {D1}..{D2}: {len(items)}", flush=True)

first_contrib, logins = {}, set()
fx_path = Path("pilot/gh_fixtures/ultralytics__ultralytics.json")
fx = json.loads(fx_path.read_text(encoding="utf-8"))
for c in fx.get("commits") or []:
    if c.get("login"):
        logins.add(c["login"])
        if (
            c["login"] not in first_contrib
            or c["committed_at"] < first_contrib[c["login"]]
        ):
            first_contrib[c["login"]] = c["committed_at"]

old = {p["number"]: p for p in fx.get("pull_requests") or []}
found_wf = []
for it in items:
    num = it["number"]
    pr = gh(f"/repos/{REPO}/pulls/{num}")
    reviews = gh(f"/repos/{REPO}/pulls/{num}/reviews")
    files = gh(f"/repos/{REPO}/pulls/{num}/files")
    wf = [f["filename"] for f in files if ".github/workflows/" in f.get("filename", "")]
    author = (pr.get("user") or {}).get("login")
    logins.add(author)
    rec = {
        "number": num,
        "author": author,
        "created_at": pr["created_at"],
        "merged_at": pr.get("merged_at"),
        "merged_by": (pr.get("merged_by") or {}).get("login"),
        "review_count": len(reviews),
        "touches_critical": (
            True
            if (
                wf
                or any(
                    k in (f.get("filename", "").lower())
                    for f in files
                    for k in ("pyproject.toml", "setup.py", "package.json")
                )
            )
            else False
        ),
        "author_first_contrib_at": first_contrib.get(author),
        "workflow_files": wf,
    }
    old[num] = rec
    if wf:
        found_wf.append(rec)
        print(
            f"  ! #{num} {author} created={pr['created_at'][:10]} "
            f"merged={str(pr.get('merged_at'))[:10]} workflow={wf}",
            flush=True,
        )

fx["pull_requests"] = [old[k] for k in sorted(old)]
fx_path.write_text(json.dumps(fx, ensure_ascii=False), encoding="utf-8")
print(
    f"фикстура обновлена: всего PR {len(fx['pull_requests'])}; "
    f"с workflow-файлами в окне: {len(found_wf)}",
    flush=True,
)
