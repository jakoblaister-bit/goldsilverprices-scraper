-- ══════════════════════════════════════════════════════════════════════════════
-- Create tables required for daily snapshots and spot price archiving.
-- Paste into Supabase → SQL Editor → Run.
-- Safe to re-run (IF NOT EXISTS guards).
-- ══════════════════════════════════════════════════════════════════════════════

-- ── 1. prices_history ─────────────────────────────────────────────────────────
-- Full daily snapshot of prices_v2. Populated by snapshot_daily.py.
CREATE TABLE IF NOT EXISTS prices_history (
    id            bigserial PRIMARY KEY,
    snapshot_date date        NOT NULL,
    dealer        text        NOT NULL,
    metal         text        NOT NULL,
    category      text        NOT NULL,
    coin_type     text,
    bar_brand     text,
    bar_type      text,
    weight_oz     numeric(12,6),
    weight_g      numeric(10,4),
    weight_label  text,
    year          integer,
    buy_price     numeric(12,2),
    sell_price    numeric(12,2),
    buy_url       text,
    available     boolean,
    scraped_at    timestamptz
);

-- Prevent duplicate snapshots for the same product on the same day
CREATE UNIQUE INDEX IF NOT EXISTS prices_history_dedup
    ON prices_history (
        snapshot_date, dealer, metal, category,
        COALESCE(coin_type, ''), COALESCE(bar_brand, ''), COALESCE(bar_type, ''),
        weight_oz, COALESCE(year::text, '')
    );

-- Fast queries for analytics (filter by date + metal + weight)
CREATE INDEX IF NOT EXISTS prices_history_date_metal
    ON prices_history (snapshot_date, metal, weight_oz);

-- ── 2. spot_prices ────────────────────────────────────────────────────────────
-- Spot price per scrape run. Populated by push_all.py on every run.
CREATE TABLE IF NOT EXISTS spot_prices (
    id         bigserial PRIMARY KEY,
    metal      text        NOT NULL,
    price_aud  numeric(12,2) NOT NULL,
    scraped_at timestamptz NOT NULL DEFAULT now()
);

-- Index for fast "latest price per metal" queries
CREATE INDEX IF NOT EXISTS spot_prices_metal_time
    ON spot_prices (metal, scraped_at DESC);

-- ══════════════════════════════════════════════════════════════════════════════
-- Verify
-- ══════════════════════════════════════════════════════════════════════════════
SELECT 'prices_history' AS tbl, COUNT(*) AS rows FROM prices_history
UNION ALL
SELECT 'spot_prices',           COUNT(*)          FROM spot_prices;