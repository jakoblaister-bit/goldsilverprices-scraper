"""
patch_scraper.py — apply 3 fixes to scraper_v3.py:
1. delete_existing: also clean up stale null weight_oz rows (prevents duplicates after old scraper runs)
2. save_to_db: gracefully retry without buy_url if column doesn't exist yet
3. Add buy_url to row dicts in all three scrapers (direct, Jaggards, Swan)
"""
with open("scraper_v3.py", "r", encoding="utf-8") as f:
    c = f.read().replace("\r\n", "\n")

errors = []

# ── 1. delete_existing: clean up null weight_oz rows ────────────────────────
OLD1 = \
        'if row.get("weight_oz") is not None:\n' \
        '            filters.append(f"weight_oz=eq.{row[\'weight_oz\']}")\n' \
        '        url = f"{SUPABASE_URL}/rest/v1/prices_v2?{\'&\'.join(filters)}"\n' \
        '        req = urllib.request.Request(url, headers=DB_HEADERS, method="DELETE")\n' \
        '        urllib.request.urlopen(req, timeout=10)\n' \
        '    except:\n' \
        '        pass'

NEW1 = \
        'if row.get("weight_oz") is not None:\n' \
        '            filters.append(f"weight_oz=eq.{row[\'weight_oz\']}")\n' \
        '        url = f"{SUPABASE_URL}/rest/v1/prices_v2?{\'&\'.join(filters)}"\n' \
        '        req = urllib.request.Request(url, headers=DB_HEADERS, method="DELETE")\n' \
        '        urllib.request.urlopen(req, timeout=10)\n' \
        '        # Also remove stale rows with weight_oz=null for same product (left by old scraper)\n' \
        '        if row.get("weight_g") and row.get("weight_oz") is not None:\n' \
        '            null_filters = [f for f in filters if "weight_oz" not in f]\n' \
        '            null_filters.append("weight_oz=is.null")\n' \
        '            null_url = f"{SUPABASE_URL}/rest/v1/prices_v2?{\'&\'.join(null_filters)}"\n' \
        '            urllib.request.urlopen(\n' \
        '                urllib.request.Request(null_url, headers=DB_HEADERS, method="DELETE"),\n' \
        '                timeout=10\n' \
        '            )\n' \
        '    except:\n' \
        '        pass'

if OLD1 in c:
    c = c.replace(OLD1, NEW1)
    print("✅ delete_existing null weight_oz cleanup added")
else:
    errors.append("❌ delete_existing anchor not found")

# ── 2. save_to_db: graceful retry without buy_url if column missing ──────────
OLD2 = \
    'def save_to_db(row):\n' \
    '    if NO_SAVE:\n' \
    '        return True\n' \
    '    try:\n' \
    '        delete_existing(row)\n' \
    '        payload = json.dumps(row).encode("utf-8")\n' \
    '        req = urllib.request.Request(\n' \
    '            f"{SUPABASE_URL}/rest/v1/prices_v2",\n' \
    '            data=payload, headers=DB_HEADERS, method="POST",\n' \
    '        )\n' \
    '        with urllib.request.urlopen(req, timeout=10) as resp:\n' \
    '            return resp.status in (200, 201)\n' \
    '    except Exception as e:\n' \
    '        body = e.read().decode() if hasattr(e, "read") else ""\n' \
    '        print(f"    [DB ERROR] {e} — {body}")\n' \
    '        return False'

NEW2 = \
    'def save_to_db(row):\n' \
    '    if NO_SAVE:\n' \
    '        return True\n' \
    '    try:\n' \
    '        delete_existing(row)\n' \
    '        payload = json.dumps(row).encode("utf-8")\n' \
    '        req = urllib.request.Request(\n' \
    '            f"{SUPABASE_URL}/rest/v1/prices_v2",\n' \
    '            data=payload, headers=DB_HEADERS, method="POST",\n' \
    '        )\n' \
    '        with urllib.request.urlopen(req, timeout=10) as resp:\n' \
    '            return resp.status in (200, 201)\n' \
    '    except Exception as e:\n' \
    '        body = e.read().decode() if hasattr(e, "read") else ""\n' \
    '        if row.get("buy_url") and "buy_url" in body:\n' \
    '            # buy_url column not yet added — retry without it\n' \
    '            row_copy = {k: v for k, v in row.items() if k != "buy_url"}\n' \
    '            try:\n' \
    '                payload = json.dumps(row_copy).encode("utf-8")\n' \
    '                req = urllib.request.Request(\n' \
    '                    f"{SUPABASE_URL}/rest/v1/prices_v2",\n' \
    '                    data=payload, headers=DB_HEADERS, method="POST",\n' \
    '                )\n' \
    '                with urllib.request.urlopen(req, timeout=10) as resp:\n' \
    '                    return resp.status in (200, 201)\n' \
    '            except Exception as e2:\n' \
    '                body2 = e2.read().decode() if hasattr(e2, "read") else ""\n' \
    '                print(f"    [DB ERROR] {e2} — {body2}")\n' \
    '                return False\n' \
    '        print(f"    [DB ERROR] {e} — {body}")\n' \
    '        return False'

if OLD2 in c:
    c = c.replace(OLD2, NEW2)
    print("✅ save_to_db buy_url graceful fallback added")
else:
    errors.append("❌ save_to_db anchor not found")

# ── 3a. buy_url in scrape_product row dict ────────────────────────────────────
OLD3 = \
    '        row = {\n' \
    '            "dealer":     dealer,\n' \
    '            "metal":      metal,\n' \
    '            "category":   product_def["category"],\n' \
    '            "coin_type":  product_def.get("coin_type"),\n' \
    '            "bar_brand":  product_def.get("bar_brand"),\n' \
    '            "bar_type":   product_def.get("bar_type"),\n' \
    '            "weight_oz":  weight_oz,\n' \
    '            "weight_g":   weight_g,\n' \
    '            "available":  available,\n' \
    '            "status":     "OK",\n' \
    '            "scraped_at": datetime.now(timezone.utc).isoformat(),\n' \
    '        }'

NEW3 = \
    '        row = {\n' \
    '            "dealer":     dealer,\n' \
    '            "metal":      metal,\n' \
    '            "category":   product_def["category"],\n' \
    '            "coin_type":  product_def.get("coin_type"),\n' \
    '            "bar_brand":  product_def.get("bar_brand"),\n' \
    '            "bar_type":   product_def.get("bar_type"),\n' \
    '            "weight_oz":  weight_oz,\n' \
    '            "weight_g":   weight_g,\n' \
    '            "available":  available,\n' \
    '            "status":     "OK",\n' \
    '            "buy_url":    url,\n' \
    '            "scraped_at": datetime.now(timezone.utc).isoformat(),\n' \
    '        }'

if OLD3 in c:
    c = c.replace(OLD3, NEW3)
    print("✅ buy_url added to scrape_product row")
else:
    errors.append("❌ scrape_product row anchor not found")

# ── 3b. buy_url in scrape_jaggards_buy row dict ──────────────────────────────
OLD4 = \
    '                    row = {\n' \
    '                        "dealer":     "Jaggards",\n' \
    '                        "metal":      metal,\n' \
    '                        "category":   category,\n' \
    '                        "coin_type":  product_def.get("coin_type"),\n' \
    '                        "bar_brand":  product_def.get("bar_brand"),\n' \
    '                        "bar_type":   product_def.get("bar_type"),\n' \
    '                        "weight_oz":  woz,\n' \
    '                        "weight_g":   wg,\n' \
    '                        "available":  available,\n' \
    '                        "status":     "OK",\n' \
    '                        "scraped_at": datetime.now(timezone.utc).isoformat(),\n' \
    '                    }'

NEW4 = \
    '                    jag_url = next((d["url"] for d in product_def.get("dealers", []) if d["dealer"] == "Jaggards"), None)\n' \
    '                    row = {\n' \
    '                        "dealer":     "Jaggards",\n' \
    '                        "metal":      metal,\n' \
    '                        "category":   category,\n' \
    '                        "coin_type":  product_def.get("coin_type"),\n' \
    '                        "bar_brand":  product_def.get("bar_brand"),\n' \
    '                        "bar_type":   product_def.get("bar_type"),\n' \
    '                        "weight_oz":  woz,\n' \
    '                        "weight_g":   wg,\n' \
    '                        "available":  available,\n' \
    '                        "status":     "OK",\n' \
    '                        "buy_url":    jag_url,\n' \
    '                        "scraped_at": datetime.now(timezone.utc).isoformat(),\n' \
    '                    }'

if OLD4 in c:
    c = c.replace(OLD4, NEW4)
    print("✅ buy_url added to scrape_jaggards_buy row")
else:
    errors.append("❌ scrape_jaggards_buy row anchor not found")

# ── 3c. buy_url in scrape_swan_buy row dict ───────────────────────────────────
OLD5 = \
    '                    row = {\n' \
    '                        "dealer":     "Swan Bullion",\n' \
    '                        "metal":      metal,\n' \
    '                        "category":   product_def["category"],\n' \
    '                        "coin_type":  product_def.get("coin_type"),\n' \
    '                        "bar_brand":  product_def.get("bar_brand"),\n' \
    '                        "bar_type":   product_def.get("bar_type"),\n' \
    '                        "weight_oz":  woz,\n' \
    '                        "weight_g":   wg,\n' \
    '                        "available":  available,\n' \
    '                        "status":     "OK",\n' \
    '                        "scraped_at": datetime.now(timezone.utc).isoformat(),\n' \
    '                    }'

NEW5 = \
    '                    swan_url = next((d["url"] for d in product_def.get("dealers", []) if d["dealer"] == "Swan Bullion"), None)\n' \
    '                    row = {\n' \
    '                        "dealer":     "Swan Bullion",\n' \
    '                        "metal":      metal,\n' \
    '                        "category":   product_def["category"],\n' \
    '                        "coin_type":  product_def.get("coin_type"),\n' \
    '                        "bar_brand":  product_def.get("bar_brand"),\n' \
    '                        "bar_type":   product_def.get("bar_type"),\n' \
    '                        "weight_oz":  woz,\n' \
    '                        "weight_g":   wg,\n' \
    '                        "available":  available,\n' \
    '                        "status":     "OK",\n' \
    '                        "buy_url":    swan_url,\n' \
    '                        "scraped_at": datetime.now(timezone.utc).isoformat(),\n' \
    '                    }'

if OLD5 in c:
    c = c.replace(OLD5, NEW5)
    print("✅ buy_url added to scrape_swan_buy row")
else:
    errors.append("❌ scrape_swan_buy row anchor not found")

if errors:
    for e in errors:
        print(e)
    import sys; sys.exit(1)

with open("scraper_v3.py", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ scraper_v3.py written")