"""
Direct ClickHouse loader for PPV Decision Tool.
Fetches spending, paid users, active listers, and price_per_day
for given category IDs and date periods.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_CH_HOST = os.getenv("CH_HOST", "ch-prod.yallasvc.net")
_CH_PORT = int(os.getenv("CH_PORT", "8123"))
_CH_USER = os.getenv("CH_USER", "app_data_uploader_20250626")
_CH_PASSWORD = os.getenv("CH_PASSWORD", "XTGBs7JjcCT5XiT3L8d8HYc7KQdpAk0t")

# ---------------------------------------------------------------------------
# Country IDs
# ---------------------------------------------------------------------------

COUNTRY_ID_MAP: dict[str, Optional[int]] = {
    "KG": 12,
    "AZ": 13,
    "RS": 11,
    "default": None,
}

# ---------------------------------------------------------------------------
# PPV flow IDs (active ads — matches "Factor analysis Spending" Tableau source)
# ---------------------------------------------------------------------------

_PPV_FLOW_IDS = (
    300003, 300023, 400003, 400023, 100003, 100023, 200003, 200023,
    300005, 300025, 400005, 400025, 100005, 100025, 200005, 200025,
    300006, 300026, 400006, 400026, 100006, 100026, 200006, 200026,
    300038, 300039, 400038, 400039, 100038, 100039, 200038, 200039,
    300004, 300024, 400004, 400024, 100004, 100024, 200004, 200024,
    300045, 300046, 400045, 400046, 200045, 200046,
    300007, 300027, 400007, 400027, 100007, 100027, 200007, 200027,
)

_FLOW_IDS_SQL = ", ".join(str(f) for f in _PPV_FLOW_IDS)


def _get_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=_CH_HOST,
        port=_CH_PORT,
        username=_CH_USER,
        password=_CH_PASSWORD,
        database="analytics",
        connect_timeout=8,
        send_receive_timeout=60,
    )


_PURCHASES_COLS  = ["category_id", "spending", "paid_users", "price_per_day"]
_ACTIVE_COLS     = ["category_id", "active_listers"]


def _run(client, sql: str, fallback_cols: list[str] | None = None) -> pd.DataFrame:
    result = client.query(sql)
    cols = list(result.column_names) if result.column_names else (fallback_cols or [])
    rows = list(result.result_rows) if result.result_rows else []
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# SQL builders
# ---------------------------------------------------------------------------

def _purchases_sql(
    category_ids: list[int],
    country_id: Optional[int],
    date_from: date,
    date_to: date,
) -> str:
    cats = ", ".join(str(c) for c in category_ids)
    country_clause = f"AND country_id = {country_id}" if country_id is not None else ""
    return f"""
        SELECT
            category_id,
            SUM(calc_usd_sum)              AS spending,
            COUNT(DISTINCT user_id)        AS paid_users,
            AVG(campaign_price_per_day)    AS price_per_day
        FROM analytics.purchases
        WHERE package_name IN ('ppv', 'one_day_ppv')
          AND payment_status = 'success'
          AND flow_id IN ({_FLOW_IDS_SQL})
          AND data_chunk_date >= '{date_from}'
          AND data_chunk_date <= '{date_to}'
          AND category_id IN ({cats})
          {country_clause}
        GROUP BY category_id
    """


def _active_listers_sql(
    category_ids: list[int],
    country_id: Optional[int],
    date_from: date,
    date_to: date,
) -> str:
    cats = ", ".join(str(c) for c in category_ids)
    country_clause = f"AND country_id = {country_id}" if country_id is not None else ""
    return f"""
        SELECT
            category_id,
            COUNT(DISTINCT lister_user_id) AS active_listers
        FROM analytics.enriched_distributed
        WHERE client != 'backend'
          AND ad_status != 8
          AND data_chunk_date >= '{date_from}'
          AND data_chunk_date <= '{date_to}'
          AND category_id IN ({cats})
          {country_clause}
        GROUP BY category_id
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_from_clickhouse(
    category_ids: list[int],
    geo: str,
    before_from: date,
    before_to: date,
    after_from: date,
    after_to: date,
) -> tuple[dict, dict]:
    """
    Returns (merged_data, price_data) in the same format as ppv_data_loader.

    merged_data: {category_id: {"before": {...}, "after": {...}, "baseline": {}}}
    price_data:  {category_id: {"default": {"price_per_day": ...}, "target": {"price_per_day": ...}}}
    """
    if not category_ids:
        raise ValueError("Не указаны Category IDs")

    country_id = COUNTRY_ID_MAP.get(geo)
    client = _get_client()

    try:
        df_pb = _run(client, _purchases_sql(category_ids, country_id, before_from, before_to), _PURCHASES_COLS)
        df_ab = _run(client, _active_listers_sql(category_ids, country_id, before_from, before_to), _ACTIVE_COLS)
        df_pa = _run(client, _purchases_sql(category_ids, country_id, after_from, after_to), _PURCHASES_COLS)
        df_aa = _run(client, _active_listers_sql(category_ids, country_id, after_from, after_to), _ACTIVE_COLS)
    finally:
        client.close()

    def _get(df: pd.DataFrame, cid: int, col: str, default):
        rows = df[df["category_id"] == cid]
        if rows.empty:
            return default
        val = rows.iloc[0][col]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return val

    def _cat_ids(df: pd.DataFrame) -> list[int]:
        if "category_id" not in df.columns or df.empty:
            return []
        return list(df["category_id"].dropna().astype(int))

    all_ids = set(_cat_ids(df_pb) + _cat_ids(df_pa))

    merged: dict = {}
    price_data: dict = {}

    for cid in sorted(all_ids):
        cid = int(cid)
        before = {
            "spending":      float(_get(df_pb, cid, "spending",      0.0)),
            "paid_users":    int(_get(df_pb, cid, "paid_users",      0)),
            "active_listers": int(_get(df_ab, cid, "active_listers", 0)),
        }
        after = {
            "spending":      float(_get(df_pa, cid, "spending",      0.0)),
            "paid_users":    int(_get(df_pa, cid, "paid_users",      0)),
            "active_listers": int(_get(df_aa, cid, "active_listers", 0)),
        }
        ppd_before = _get(df_pb, cid, "price_per_day", None)
        ppd_after  = _get(df_pa, cid, "price_per_day", None)
        if ppd_before is not None:
            before["price_per_day"] = float(ppd_before)
        if ppd_after is not None:
            after["price_per_day"] = float(ppd_after)

        merged[cid] = {"baseline": {}, "before": before, "after": after}
        price_data[cid] = {
            "default": {"price_per_day": float(ppd_before)} if ppd_before is not None else {},
            "target":  {"price_per_day": float(ppd_after)}  if ppd_after  is not None else {},
        }

    return merged, price_data
