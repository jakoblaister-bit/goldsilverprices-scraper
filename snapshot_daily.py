"""
snapshot_daily.py
Copies current prices_v2 state into prices_history once per UTC day.
Called automatically by push_all.py after all dealers are updated.
"""

import json, urllib.request, urllib.error
from datetime import datetime, timezone

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

HISTORY_URL = f"{SUPABASE_URL}/rest/v1/prices_history"
CURRENT_URL = f"{SUPABASE_URL}/rest/v1/prices_v2"


def _request(method, url, data=None, extra_headers=None):
    headers = {**HEADERS, **(extra_headers or {})}
    body = json.dumps(data).encode() if data is not None else None
    req  = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _snapshot_exists(today_str):
    url = f"{HISTORY_URL}?snapshot_date=eq.{today_str}&select=id&limit=1"
    status, body = _request("GET", url)
    if status == 200:
        return len(json.loads(body)) > 0
    raise RuntimeError(f"Snapshot check failed {status}: {body[:200]}")


def _fetch_current():
    # Supabase default page size is 1000; we have ~500 rows so this is safe.
    # Add Range header as a belt-and-suspenders guard.
    url = f"{CURRENT_URL}?select=*&limit=2000"
    status, body = _request("GET", url, extra_headers={"Range": "0-1999"})
    if status in (200, 206):
        return json.loads(body)
    raise RuntimeError(f"Fetch prices_v2 failed {status}: {body[:200]}")


def _insert_snapshot(rows, today_str):
    history_rows = []
    for r in rows:
        h = {k: v for k, v in r.items() if k != "id"}
        h["snapshot_date"] = today_str
        history_rows.append(h)

    # Batch in 500s to stay within Supabase payload limits
    for i in range(0, len(history_rows), 500):
        batch = history_rows[i : i + 500]
        status, body = _request("POST", HISTORY_URL, batch)
        if status not in (200, 201):
            raise RuntimeError(f"INSERT history failed {status}: {body[:300]}")

    print(f"  ✓ {len(history_rows)} rows saved to prices_history for {today_str}")


def run():
    today_str = datetime.now(timezone.utc).date().isoformat()
    print(f"\nDaily snapshot check ({today_str} UTC)…")

    if _snapshot_exists(today_str):
        print(f"  ✓ Snapshot already exists for {today_str}, skipping")
        return

    print("  No snapshot yet — copying prices_v2…")
    rows = _fetch_current()
    print(f"  {len(rows)} rows fetched")
    _insert_snapshot(rows, today_str)
    print("Snapshot done ✅")


if __name__ == "__main__":
    run()