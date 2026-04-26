with open(".github/workflows/scraper.yml", "r") as f:
    code = f.read()

# Increase timeout for v5 which takes longer
code = code.replace("timeout-minutes: 15", "timeout-minutes: 45")

# Remove Excel artifact upload — not used
code = code.replace("""      - name: Upload Excel as artifact
        uses: actions/upload-artifact@v4
        with:
          name: bullion-prices
          path: bullion_prices_*.xlsx
          retention-days: 7""", "")

with open(".github/workflows/scraper.yml", "w") as f:
    f.write(code)

print("Done")