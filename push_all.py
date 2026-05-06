"""
push_all.py
Runs all dealer scrapers in sequence — Tier 1 (every 3 hrs via CI) and
Tier 2 (HTML-scraped, same pipeline).

Run:  python push_all.py
"""

import sys
from push_ainslie import push as push_ainslie
from push_goldstackers import push as push_goldstackers
from push_gba import push as push_gba
from push_swan import push as push_swan
from push_abc import push as push_abc
from push_jaggards import push as push_jaggards
from push_guardian import push as push_guardian
from push_perth import push as push_perth
from push_kjc import push as push_kjc

dealers = [
    ("Ainslie Bullion",        push_ainslie),
    ("Gold Stackers",          push_goldstackers),
    ("Gold Bullion Australia",  push_gba),
    ("Swan Bullion",            push_swan),
    ("ABC Bullion",             push_abc),
    ("Jaggards",                push_jaggards),
    ("Guardian Gold",           push_guardian),
    ("Perth Mint",              push_perth),
    ("KJC Bullion",             push_kjc),
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
    print("All dealers updated ✅")