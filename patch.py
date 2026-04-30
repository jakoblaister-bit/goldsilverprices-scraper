# patch.py
with open("scraper_v3.py", "r", encoding="utf-8") as f:
    c = f.read()

OLD = '''    except Exception as e:
        print(f"    [DB ERROR] {e}")
        return False'''

NEW = '''    except Exception as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        print(f"    [DB ERROR] {e} — {body}")
        return False'''

if OLD in c:
    c = c.replace(OLD, NEW, 1)
    with open("scraper_v3.py", "w", encoding="utf-8") as f:
        f.write(c)
    print("✅ save_to_db now prints full error body")
else:
    print("❌ Anchor not found")
