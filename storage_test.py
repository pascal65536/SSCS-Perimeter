import sqlite3, sys

sys.path.insert(0, ".")
from storage import ingest, query

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.executescript(open("storage/schema.sql", encoding="utf-8").read())

ok = []


def check(name, cond, info=""):
    ok.append(cond)
    print(f"  [{'OK' if cond else 'FAIL'}] {name} {info}")


r = ingest.ingest_jsonl(conn, "storage/data/collector_fixture.jsonl")
check(
    "приём collector_fixture: accepted=4",
    r["accepted"] == 4 and r["errors"] == 0,
    str(r),
)
pkg = conn.execute("SELECT * FROM packages WHERE name='legacy-lib'").fetchone()
check(
    "packages: first_seen из created",
    pkg is not None and pkg["first_seen"] == "2020-01-15T10:00:00Z",
)
check(
    "profile: login нормализован",
    conn.execute("SELECT 1 FROM user_profiles WHERE login='right9ctrl'").fetchone()
    is not None,
)
mem = conn.execute("SELECT * FROM membership_events").fetchone()
check("membership: right9ctrl added", mem is not None and mem["change_type"] == "added")

r2 = ingest.ingest_jsonl(conn, "storage/data/collector_fixture.jsonl")
check(
    "идемпотентность: accepted=0 duplicates=4",
    r2["accepted"] == 0 and r2["duplicates"] == 4,
    str(r2),
)
check(
    "строк не прибавилось",
    conn.execute("SELECT COUNT(*) c FROM ingest_log").fetchone()["c"] == 4,
)

check(
    "PIT: релиз не виден до 06:00",
    len(query.get_as_of(conn, "v_releases", "2023-09-12T05:00:00Z")) == 0,
)
check(
    "PIT: виден ровно на 06:00 (inclusive)",
    len(query.get_as_of(conn, "v_releases", "2023-09-12T06:00:00Z")) == 1,
)
check(
    "PIT: рёбра G1 видны после event_at",
    len(query.get_as_of(conn, "v_maintainer_edges", "2023-09-11T12:00:00Z")) == 1,
)

try:
    ingest.ingest_jsonl(conn, "storage/data/sample_r9.jsonl")
    check("R3: файл с битой строкой отклонён", False)
except Exception as e:
    check("R3: исключение + rollback", "R3 violation" in str(e), str(e)[:60])
check(
    "rollback без следов",
    conn.execute("SELECT COUNT(*) c FROM ingest_log").fetchone()["c"] == 4,
)

try:
    ingest.ingest_jsonl(conn, "storage/data/future.jsonl")
    check("PIT: будущее событие отклонено", False)
except Exception as e:
    check("PIT-предвалидация ловит 2027", "PIT violation" in str(e), str(e)[:60])

print()
print("STORAGE:", "ALL PASSED" if all(ok) else "FAILURES", f"({sum(ok)}/{len(ok)})")
sys.exit(0 if all(ok) else 1)
