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

def _get_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=_CH_HOST,
        port=_CH_PORT,
        username=_CH_USER,
        password=_CH_PASSWORD,
        connect_timeout=8,
        send_receive_timeout=60,
    )


_PURCHASES_COLS  = ["category_id", "spending", "paid_users", "price_per_day"]
_ACTIVE_COLS     = ["category_id", "active_listers"]
_CAMPAIGN_COLS   = [
    "category_id", "new_campaign_cnt", "paid_users_check",
    "refund", "campaigns_with_refund", "sum_plan_imp", "sum_fact_imp",
]
_BUDGET_DIST_COLS = ["category_id", "ppd_step", "campaign_cnt"]
_PRICE_GRID_COLS  = ["category_id", "ppd_step", "is_default", "is_vip"]


def _run(client, sql: str, fallback_cols: list[str] | None = None) -> pd.DataFrame:
    result = client.query(sql)
    cols = list(result.column_names) if result.column_names else (fallback_cols or [])
    rows = list(result.result_rows) if result.result_rows else []
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# SQL builders  (Tableau-aligned logic)
# ---------------------------------------------------------------------------

# Shared CTEs that replicate Tableau's category_cnt_for_ad filter exactly:
#   campaign_first_day — first day of each campaign (min end_day)
#   category_by_ad     — ad_ids that ever appeared in exactly one category
_TABLEAU_CTES = """
    campaign_first_day AS (
        SELECT campaign_id, toDate(min(end_day)) AS first_date
        FROM analytics_reports.spendings_distributed
        GROUP BY campaign_id
    ),
    category_by_ad AS (
        SELECT ad_id
        FROM analytics_reports.spendings_distributed s
        GLOBAL JOIN campaign_first_day f ON s.campaign_id = f.campaign_id
        GROUP BY ad_id
        HAVING uniqExact(category_id) = 1
    )
"""

# Common WHERE conditions applied to the main spendings scan
def _tableau_where(
    cats: str,
    country_id: Optional[int],
    date_from: date,
    date_to: date,
) -> str:
    country_clause = f"AND country_id = {country_id}" if country_id is not None else ""
    return f"""
        WHERE device != 'microservices'
          AND toDate(s.end_day) = f.first_date
          AND f.first_date >= '{date_from}'
          AND f.first_date <= '{date_to}'
          AND category_id IN ({cats})
          {country_clause}
          AND ad_id GLOBAL IN (SELECT ad_id FROM category_by_ad)
    """


def _purchases_sql(
    category_ids: list[int],
    country_id: Optional[int],
    date_from: date,
    date_to: date,
    exclude_ad_ids: list[int] | None = None,
) -> str:
    cats = ", ".join(str(c) for c in category_ids)
    where = _tableau_where(cats, country_id, date_from, date_to)
    return f"""
        WITH {_TABLEAU_CTES}
        SELECT
            category_id,
            uniqExact(user_id)       AS paid_users,
            SUM(spending) / 100      AS spending,
            AVG(price_per_day) / 100 AS price_per_day
        FROM analytics_reports.spendings_distributed s
        GLOBAL JOIN campaign_first_day f ON s.campaign_id = f.campaign_id
        {where}
        GROUP BY category_id
    """


def _campaign_metrics_sql(
    category_ids: list[int],
    country_id: Optional[int],
    date_from: date,
    date_to: date,
    exclude_ad_ids: list[int] | None = None,
) -> str:
    """Per-campaign first-day metrics: count, refund, impressions."""
    cats = ", ".join(str(c) for c in category_ids)
    where = _tableau_where(cats, country_id, date_from, date_to)
    return f"""
        WITH {_TABLEAU_CTES}
        SELECT
            category_id,
            COUNT(*)                              AS new_campaign_cnt,
            COUNT(DISTINCT user_id)               AS paid_users_check,
            SUM(s.refund) / 100                   AS refund,
            SUM(if(s.refund > 0, 1, 0))           AS campaigns_with_refund,
            SUM(s.plan_impression)                AS sum_plan_imp,
            SUM(s.impression)                     AS sum_fact_imp
        FROM analytics_reports.spendings_distributed s
        GLOBAL JOIN campaign_first_day f ON s.campaign_id = f.campaign_id
        {where}
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
            COUNT(DISTINCT user_id) AS active_listers
        FROM analytics_reports.active_listers_and_listings_distributed
        WHERE data_chunk_date >= '{date_from}'
          AND data_chunk_date <= '{date_to}'
          AND category_id IN ({cats})
          {country_clause}
        GROUP BY category_id
    """


def _price_grid_sql(category_ids: list[int], country_id: Optional[int]) -> str:
    cats = ", ".join(str(c) for c in category_ids)
    country_clause = f"AND country_id = {country_id}" if country_id is not None else ""
    return f"""
        SELECT
            c.category_id,
            toInt32(round(p.price_per_day / 100)) AS ppd_step,
            p.default                              AS is_default,
            p.feature1                             AS is_vip
        FROM (
            SELECT id, category_id
            FROM pg_campaign_microservice.campaign_ad_category
            WHERE category_id IN ({cats})
              {country_clause}
            ORDER BY created_at DESC
            LIMIT 1 BY category_id
        ) c
        JOIN pg_campaign_microservice.campaign_ad_price p ON p.campaign_ad_category_id = c.id
        ORDER BY c.category_id, p.price_per_day
    """


def _budget_dist_sql(
    category_ids: list[int],
    country_id: Optional[int],
    date_from: date,
    date_to: date,
    exclude_ad_ids: list[int] | None = None,
) -> str:
    cats = ", ".join(str(c) for c in category_ids)
    where = _tableau_where(cats, country_id, date_from, date_to)
    return f"""
        WITH {_TABLEAU_CTES}
        SELECT
            category_id,
            toInt32(round(price_per_day / 100)) AS ppd_step,
            COUNT(*)                             AS campaign_cnt
        FROM analytics_reports.spendings_distributed s
        GLOBAL JOIN campaign_first_day f ON s.campaign_id = f.campaign_id
        {where}
        GROUP BY category_id, ppd_step
        ORDER BY category_id, ppd_step
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
) -> tuple[dict, dict, dict]:
    """
    Returns (merged_data, price_data, budget_dist).

    merged_data:  {category_id: {"before": {...}, "after": {...}, "baseline": {}}}
    price_data:   {category_id: {"default": {"price_per_day": ...}, "target": {...}}}
    budget_dist:  {category_id: {"before": {ppd_step: count}, "after": {ppd_step: count}}}
    """
    if not category_ids:
        raise ValueError("Не указаны Category IDs")

    country_id = COUNTRY_ID_MAP.get(geo)
    client = _get_client()

    df_names = pd.DataFrame(columns=["id", "name"])
    try:
        df_pb   = _run(client, _purchases_sql(category_ids, country_id, before_from, before_to), _PURCHASES_COLS)
        df_ab   = _run(client, _active_listers_sql(category_ids, country_id, before_from, before_to), _ACTIVE_COLS)
        df_cb   = _run(client, _campaign_metrics_sql(category_ids, country_id, before_from, before_to), _CAMPAIGN_COLS)
        df_pa   = _run(client, _purchases_sql(category_ids, country_id, after_from, after_to), _PURCHASES_COLS)
        df_aa   = _run(client, _active_listers_sql(category_ids, country_id, after_from, after_to), _ACTIVE_COLS)
        df_ca   = _run(client, _campaign_metrics_sql(category_ids, country_id, after_from, after_to), _CAMPAIGN_COLS)
        df_db   = _run(client, _budget_dist_sql(category_ids, country_id, before_from, before_to), _BUDGET_DIST_COLS)
        df_da   = _run(client, _budget_dist_sql(category_ids, country_id, after_from, after_to), _BUDGET_DIST_COLS)
        df_grid = _run(client, _price_grid_sql(category_ids, country_id), _PRICE_GRID_COLS)

        # Fetch category names while client is still open
        _all_ids_early = set(
            list(df_pb["category_id"].dropna().astype(int) if not df_pb.empty else []) +
            list(df_pa["category_id"].dropna().astype(int) if not df_pa.empty else [])
        )
        if _all_ids_early:
            cats_str_early = ", ".join(str(c) for c in sorted(_all_ids_early))
            try:
                df_names = _run(client, f"""
                    SELECT id, name FROM pg_catalog_microservice.category
                    WHERE id IN ({cats_str_early}) AND is_deleted = false
                """, ["id", "name"])
            except Exception:
                pass
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

    def _safe_div(a, b):
        return a / b if b and b != 0 else None

    all_ids = set(_cat_ids(df_pb) + _cat_ids(df_pa))

    merged: dict = {}
    price_data: dict = {}

    for cid in sorted(all_ids):
        cid = int(cid)

        spending_b = float(_get(df_pb, cid, "spending",       0.0))
        spending_a = float(_get(df_pa, cid, "spending",       0.0))
        paid_b     = int(_get(df_pb,   cid, "paid_users",     0))
        paid_a     = int(_get(df_pa,   cid, "paid_users",     0))
        active_b   = int(_get(df_ab,   cid, "active_listers", 0))
        active_a   = int(_get(df_aa,   cid, "active_listers", 0))

        camp_cnt_b       = int(_get(df_cb, cid, "new_campaign_cnt",     0))
        camp_cnt_a       = int(_get(df_ca, cid, "new_campaign_cnt",     0))
        refund_b         = float(_get(df_cb, cid, "refund",             0.0))
        refund_a         = float(_get(df_ca, cid, "refund",             0.0))
        camp_refund_b    = int(_get(df_cb, cid, "campaigns_with_refund", 0))
        camp_refund_a    = int(_get(df_ca, cid, "campaigns_with_refund", 0))
        plan_imp_b       = float(_get(df_cb, cid, "sum_plan_imp",        0.0))
        plan_imp_a       = float(_get(df_ca, cid, "sum_plan_imp",        0.0))
        fact_imp_b       = float(_get(df_cb, cid, "sum_fact_imp",        0.0))
        fact_imp_a       = float(_get(df_ca, cid, "sum_fact_imp",        0.0))

        def _campaign_dict(spending, paid_users, active_listers, camp_cnt,
                           refund, camp_refund, plan_imp, fact_imp):
            d: dict = {
                "spending":       spending,
                "paid_users":     paid_users,
                "active_listers": active_listers,
                "new_campaign_cnt": camp_cnt,
                "refund":         refund,
            }
            if camp_cnt > 0:
                d["campaign_per_user"]       = round(camp_cnt / paid_users, 4) if paid_users > 0 else None
                d["arp_p_campaign"]          = round(spending / camp_cnt, 4)
                d["pct_campaign_with_refund"] = round(camp_refund / camp_cnt * 100, 4)
                d["plan_imp_per_campaign"]   = round(plan_imp / camp_cnt, 4)
                d["fact_imp_per_campaign"]   = round(fact_imp / camp_cnt, 4)
                if plan_imp and plan_imp > 0:
                    d["pct_execution_inventory"] = round(fact_imp / plan_imp * 100 - 100, 4)
            return d

        before = _campaign_dict(
            spending_b, paid_b, active_b, camp_cnt_b,
            refund_b, camp_refund_b, plan_imp_b, fact_imp_b,
        )
        after = _campaign_dict(
            spending_a, paid_a, active_a, camp_cnt_a,
            refund_a, camp_refund_a, plan_imp_a, fact_imp_a,
        )

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

    # Attach category names from catalog (fetched inside try block above)
    for _, row in df_names.iterrows():
        cid = int(row["id"])
        if cid in merged:
            merged[cid]["name"] = str(row["name"])

    budget_dist: dict = {}
    for cid in sorted(all_ids):
        cid = int(cid)
        rows_b = df_db[df_db["category_id"] == cid] if not df_db.empty else pd.DataFrame()
        rows_a = df_da[df_da["category_id"] == cid] if not df_da.empty else pd.DataFrame()
        rows_g = df_grid[df_grid["category_id"] == cid] if not df_grid.empty else pd.DataFrame()
        grid: dict = {}
        if not rows_g.empty:
            steps_sorted = sorted(rows_g["ppd_step"].astype(int).tolist())
            first_step = steps_sorted[0] if steps_sorted else None
            for _, gr in rows_g.iterrows():
                step = int(gr["ppd_step"])
                grid[step] = {
                    "is_default": bool(int(gr["is_default"])),
                    "is_vip": bool(int(gr["is_vip"])),
                    "is_first": step == first_step,
                }
        budget_dist[cid] = {
            "before": dict(zip(rows_b["ppd_step"].astype(int), rows_b["campaign_cnt"].astype(int))) if not rows_b.empty else {},
            "after":  dict(zip(rows_a["ppd_step"].astype(int), rows_a["campaign_cnt"].astype(int))) if not rows_a.empty else {},
            "grid":   grid,
        }

    return merged, price_data, budget_dist


def load_py_from_clickhouse(
    category_ids: list[int],
    geo: str,
    before_from: date,
    before_to: date,
    after_from: date,
    after_to: date,
) -> dict:
    """
    Loads Previous Year data for PPV matrix (paid_users, spending, active_listers only).

    Dates should already be shifted -1 year by the caller.
    Returns merged_data dict: {category_id: {"before": {...}, "after": {...}, "baseline": {}}}
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

    for cid in sorted(all_ids):
        cid = int(cid)
        before = {
            "spending":       float(_get(df_pb, cid, "spending",       0.0)),
            "paid_users":     int(_get(df_pb,   cid, "paid_users",     0)),
            "active_listers": int(_get(df_ab,   cid, "active_listers", 0)),
        }
        after = {
            "spending":       float(_get(df_pa, cid, "spending",       0.0)),
            "paid_users":     int(_get(df_pa,   cid, "paid_users",     0)),
            "active_listers": int(_get(df_aa,   cid, "active_listers", 0)),
        }
        merged[cid] = {"baseline": {}, "before": before, "after": after}

    return merged


def fetch_category_parents(
    category_ids: list[int],
) -> tuple[dict[int, int], dict[int, str]]:
    """
    Query pg_catalog_microservice.category for the parent_id of each given category.

    Returns:
      child_to_parent : {child_id: parent_id}
      cat_names       : {cat_id: name}  — covers both children and their parents
    """
    if not category_ids:
        return {}, {}

    cats_str = ", ".join(str(c) for c in category_ids)
    client = _get_client()
    child_to_parent: dict[int, int] = {}
    cat_names: dict[int, str] = {}
    try:
        rows = client.query(f"""
            SELECT id, parent_id, name
            FROM pg_catalog_microservice.category
            WHERE id IN ({cats_str})
              AND is_deleted = false
        """).result_rows
        parent_ids_needed: set[int] = set()
        for row in rows:
            cid, pid, nm = int(row[0]), row[1], str(row[2])
            cat_names[cid] = nm
            if pid is not None:
                try:
                    pid_i = int(pid)
                    child_to_parent[cid] = pid_i
                    parent_ids_needed.add(pid_i)
                except (TypeError, ValueError):
                    pass

        # Fetch names for parent categories (may not be in original list)
        missing_parents = parent_ids_needed - set(cat_names.keys())
        if missing_parents:
            par_str = ", ".join(str(p) for p in missing_parents)
            par_rows = client.query(f"""
                SELECT id, name
                FROM pg_catalog_microservice.category
                WHERE id IN ({par_str})
                  AND is_deleted = false
            """).result_rows
            for row in par_rows:
                cat_names[int(row[0])] = str(row[1])
    except Exception:
        pass
    finally:
        client.close()

    return child_to_parent, cat_names
