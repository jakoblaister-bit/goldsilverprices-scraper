"""
Delete all bar rows where weight_oz IS NULL — stale data from old scraper runs.
These coexist with new rows (weight_oz = 0.0322 etc.) causing duplicate entries in the FE.
Run once, then let the scraper rebuild with clean data.
"""
import urllib.request, json

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

url = f"{SUPABASE_URL}/rest/v1/prices_v2?category=eq.bar&weight_oz=is.null"
req = urllib.request.Request(url, headers=HEADERS, method="DELETE")

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        deleted = json.loads(body) if body else []
        print(f"✅ Deleted {len(deleted)} stale bar rows (weight_oz=null)")
except Exception as e:
    body = e.read().decode() if hasattr(e, "read") else str(e)
    print(f"❌ Error: {e} — {body}")