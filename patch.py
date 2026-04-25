"""patch.py — replace hardcoded keys with environment variables"""

with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [
    (
        '# ── Supabase ──────────────────────────────────────────────────────────────────\nSUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"\nSUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"',
        '# ── Supabase ──────────────────────────────────────────────────────────────────\nimport os\nSUPABASE_URL = os.environ.get("SUPABASE_URL", "https://cjxkhvkvhgnlnviykoad.supabase.co")\nSUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0")',
    ),
]

for i, (old, new) in enumerate(changes, 1):
    if old in code:
        code = code.replace(old, new)
        print(f"  ✓ Change {i} applied")
    else:
        print(f"  ✗ Change {i} not found")

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Done.")