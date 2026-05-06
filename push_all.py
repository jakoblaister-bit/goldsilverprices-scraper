"""
push_all.py
Runs all three Tier 1 dealer scrapers in sequence.
Non-Tier 1 dealer data is manually curated — do not run scraper_v3.py on a schedule.

Run:  python push_all.py
"""

import sys
from push_ainslie import push as push_ainslie
from push_goldstackers import push as push_goldstackers
from push_gba import push as push_gba

dealers = [
    ("Ainslie Bullion",       push_ainslie),
    ("Gold Stackers",         push_goldstackers),
    ("Gold Bullion Australia", push_gba),
]

errors = []
for name, fn in dealers:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    try:
        fn()
    except Exception as e:
        print(f"  ERROR: {e}")
        errors.append(name)

print(f"\n{'='*60}")
if errors:
    print(f"FAILED: {', '.join(errors)}")
    sys.exit(1)
else:
    print("All Tier 1 dealers updated ✅")