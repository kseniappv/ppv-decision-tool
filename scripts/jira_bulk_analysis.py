"""
PPV Experiment → Jira Analysis Script
======================================
Fetches ClickHouse data, runs Y2Y decision analysis, posts results to Jira.

Usage
-----
1. Fill in the EXPERIMENT config below.
2. Run from the project root:
       cd /Users/kseniamorozova/Desktop/ppv-decision-tool
       python3 scripts/jira_bulk_analysis.py

Config fields
-------------
  ticket      : Jira issue key, e.g. "ME-18950"
  cat_ids     : list of category IDs to analyse
  geo         : "KG" | "AZ" | "RS"
  start_date  : experiment launch date as "YYYY-MM-DD"
  days        : comparison window (default 30; use fewer if experiment ran < 30 days)
  transition  : where to move the ticket after posting results
                  "decision"  → Analysis → Ready to discuss results → Decision  (bulk)
                  "positive"  → Decision → Good for business
                  "negative"  → Decision → Negative impact
                  "noimpact"  → Decision → Don't see any impact
                  None        → don't transition
  country_id  : used in active_listers query (KG=12, AZ=13); derived from geo if omitted

Period logic
------------
  before_from = start_date - days
  before_to   = start_date - 1 day
  after_from  = start_date
  after_to    = start_date + days - 1

  PY periods  = same dates shifted -1 year (for Y2Y comparison)
"""

import sys
import os
import io
import csv
import json
import math
import base64
import urllib.request
import urllib.error
from datetime import date, timedelta

# ── project root on sys.path so we can import existing modules ──────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from decision_engine import GEO_THRESHOLDS
from clickhouse_loader import (
    _get_client,
    _purchases_sql,
    _campaign_metrics_sql,
    _active_listers_sql,
    _run,
    COUNTRY_ID_MAP,
    _PURCHASES_COLS,
    _CAMPAIGN_COLS,
    _ACTIVE_COLS,
)

# ══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT CONFIG  ← edit this block before each run
# ══════════════════════════════════════════════════════════════════════════════
EXPERIMENT = {
    "ticket":     "ME-18950",
    "cat_ids":    [4832, 4833, 4834, 4835, 4836, 4837, 4838],
    "geo":        "KG",
    "start_date": "2026-04-16",   # experiment launch date
    "days":       30,             # comparison window; reduce if < 30 days elapsed
    "transition": "decision",     # "decision" | "positive" | "negative" | "noimpact" | None
}
# ══════════════════════════════════════════════════════════════════════════════

JIRA_BASE  = os.getenv("JIRA_BASE", "https://yallaclassifieds.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_USER", "ksenia.morozova@lalafo.com")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")
JIRA_AUTH  = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()

# Transition name fragments → transition IDs (discovered at runtime)
_TRANSITION_KEYWORDS = {
    "experiment finished":       "experiment_finished",
    "ready to discuss results":  "ready",
    "good for business":         "positive",
    "don't see any impact":      "noimpact",
    "negative impact":           "negative",
    "not analysed":              "not_analysed",
}

# Long-CSV metric specs: (display_name, data_field, is_money)
METRIC_SPECS = [
    ("Paid users",            "paid_users",            False),
    ("Spending",              "spending",              True),
    ("CR",                    "cr",                    False),
    ("Active listers",        "active_listers",        False),
    ("Campaign per User",     "campaign_per_user",     False),
    ("New campaign cnt",      "new_campaign_cnt",      False),
    ("Price per day",         "price_per_day",         True),
    ("ARPpCampaign",          "arp_p_campaign",        True),
    ("Refund",                "refund",                True),
    ("%Campaign with refund", "pct_campaign_with_refund", False),
    ("Plan Imp per Campaign", "plan_imp_per_campaign", False),
    ("Fact Imp per Campaign", "fact_imp_per_campaign", False),
    ("%Execution Inventory",  "pct_execution_inventory", False),
]

LONG_COLS = [
    "category_id", "category_name", "scenario", "decision", "next_step",
    "metric", "Before", "After", "Diff %",
    "PY Before", "PY After", "PY Diff %", "Y2Y Diff %",
]

DECISION_MATRIX = {
    "GGG": ("Positive", "Close experiment"),
    "GGS": ("Positive", "Close experiment"),
    "GGD": ("Positive", "Close experiment"),
    "GSG": ("Positive", "Close experiment"),
    "GSS": ("Positive", "Close experiment"),
    "GSD": ("No impact", "Close experiment"),
    "GDG": ("No impact", "Close experiment"),
    "GDS": ("No impact", "Close experiment"),
    "GDD": ("Negative", "Rollback"),
    "SGG": ("Positive", "Close experiment"),
    "SGS": ("Positive", "Close experiment"),
    "SGD": ("No impact", "Close experiment"),
    "SSG": ("No impact", "Close experiment"),
    "SSS": ("No impact", "Close experiment"),
    "SSD": ("No impact", "Close experiment"),
    "SDG": ("No impact", "Close experiment"),
    "SDS": ("Negative", "Rollback"),
    "SDD": ("Negative", "Rollback"),
    "DGG": ("No impact", "Close experiment"),
    "DGS": ("No impact", "Close experiment"),
    "DGD": ("Negative", "Rollback"),
    "DSG": ("Negative", "Rollback"),
    "DSS": ("Negative", "Rollback"),
    "DSD": ("Negative", "Rollback"),
    "DDG": ("Negative", "Rollback"),
    "DDS": ("Negative", "Rollback"),
    "DDD": ("Negative", "Rollback"),
}

COUNTRY_FROM_GEO = {"KG": 12, "AZ": 13, "RS": 11}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct(a, b):
    try:
        if b is None or b == 0:
            return None
        return (a - b) / abs(b) * 100
    except Exception:
        return None


def _classify(v, growth, decline):
    if v is None:
        return "S"
    if v >= growth:
        return "G"
    if v <= decline:
        return "D"
    return "S"


def _fmt(v, is_money=False):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}" if is_money else f"{v:.4f}"
    return str(v)


def _fmt_pct(v):
    return f"{v:+.2f}%" if v is not None else ""


def _fmt2(v, is_money=False):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}" if is_money else f"{v:,.4f}"
    return str(v)


def _fmt_pct2(v):
    return f"{v:+.2f}%" if v is not None else "-"


# ─────────────────────────────────────────────────────────────────────────────
# ClickHouse data fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetch_period_data(cat_ids: list, country_id, date_from: date, date_to: date) -> dict:
    """
    Returns {cat_id: {paid_users, spending, price_per_day, active_listers,
                       new_campaign_cnt, refund, pct_campaign_with_refund,
                       campaign_per_user, arp_p_campaign,
                       plan_imp_per_campaign, fact_imp_per_campaign,
                       pct_execution_inventory, cr}}
    """
    client = _get_client()
    try:
        df_p = _run(client, _purchases_sql(cat_ids, country_id, date_from, date_to), _PURCHASES_COLS)
        df_c = _run(client, _campaign_metrics_sql(cat_ids, country_id, date_from, date_to), _CAMPAIGN_COLS)
        df_a = _run(client, _active_listers_sql(cat_ids, country_id, date_from, date_to), _ACTIVE_COLS)
    finally:
        client.close()

    result = {}
    for cid in cat_ids:
        def g(df, col, default=0):
            rows = df[df["category_id"] == cid] if not df.empty else df
            if rows.empty:
                return default
            v = rows.iloc[0][col]
            if v is None:
                return default
            try:
                return type(default)(v)
            except Exception:
                return default

        paid   = g(df_p, "paid_users", 0)
        sp     = g(df_p, "spending",   0.0)
        ppd    = g(df_p, "price_per_day", None) if not df_p.empty and "price_per_day" in df_p.columns else None
        al     = g(df_a, "active_listers", 0)
        nc     = g(df_c, "new_campaign_cnt", 0)
        ref    = g(df_c, "refund",           0.0)
        cref   = g(df_c, "campaigns_with_refund", 0)
        plan   = g(df_c, "sum_plan_imp",     0.0)
        fact   = g(df_c, "sum_fact_imp",     0.0)

        cr     = paid / al if al > 0 else None
        cpu    = nc / paid if paid > 0 and nc > 0 else None
        arp    = sp / nc if nc > 0 else None
        pcr    = cref / nc * 100 if nc > 0 else None
        pipc   = plan / nc if nc > 0 else None
        fipc   = fact / nc if nc > 0 else None
        pei    = fact / plan * 100 - 100 if plan and plan > 0 else None

        row: dict = {
            "paid_users":            paid,
            "spending":              sp,
            "price_per_day":         float(ppd) if ppd is not None else None,
            "active_listers":        al,
            "new_campaign_cnt":      nc,
            "refund":                ref,
            "pct_campaign_with_refund": pcr,
            "campaign_per_user":     cpu,
            "arp_p_campaign":        arp,
            "plan_imp_per_campaign": pipc,
            "fact_imp_per_campaign": fipc,
            "pct_execution_inventory": pei,
            "cr":                    cr,
        }
        result[cid] = row
    return result


def fetch_cat_names(cat_ids: list) -> dict:
    cats_str = ", ".join(str(c) for c in cat_ids)
    client = _get_client()
    try:
        rows = client.query(
            f"SELECT id, name FROM pg_catalog_microservice.category "
            f"WHERE id IN ({cats_str}) AND is_deleted = false"
        ).result_rows
        return {int(r[0]): str(r[1]) for r in rows}
    except Exception:
        return {}
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Decision logic  (Y2Y-based for Regular scenario)
# ─────────────────────────────────────────────────────────────────────────────

def decide(cid, cy_b, cy_a, py_b, py_a, thr):
    paid_b = cy_b.get("paid_users", 0)
    if paid_b < thr["min_npl"]:
        return "Insufficient", "Need more data", None

    npl_cy = _pct(cy_a["paid_users"], cy_b["paid_users"])
    sp_cy  = _pct(cy_a["spending"],   cy_b["spending"])
    cr_cy  = _pct(cy_a["cr"],         cy_b["cr"])

    npl_py = _pct(py_a["paid_users"], py_b["paid_users"]) if py_b else None
    sp_py  = _pct(py_a["spending"],   py_b["spending"])   if py_b else None
    cr_py  = _pct(py_a["cr"],         py_b["cr"])         if py_b else None

    y2y_npl = (npl_cy - npl_py) if (npl_cy is not None and npl_py is not None) else npl_cy
    y2y_sp  = (sp_cy  - sp_py)  if (sp_cy  is not None and sp_py  is not None) else sp_cy
    y2y_cr  = (cr_cy  - cr_py)  if (cr_cy  is not None and cr_py  is not None) else cr_cy

    code = (
        _classify(y2y_npl, thr["npl"]["growth"], thr["npl"]["decline"]) +
        _classify(y2y_sp,  thr["sp"]["growth"],  thr["sp"]["decline"]) +
        _classify(y2y_cr,  thr["cr"]["growth"],  thr["cr"]["decline"])
    )
    decision, next_step = DECISION_MATRIX.get(code, ("No impact", "Close experiment"))
    return decision, next_step, code


def maybe_parent_fallback(cat_ids, decisions, cy_b_all, cy_a_all, py_b_all, py_a_all, thr, threshold=0.80):
    """
    If ≥ threshold % of categories are Insufficient, aggregate all their data
    and re-run decision at parent level.  Returns updated decisions dict.
    """
    insuf = [c for c in cat_ids if decisions[c][0] == "Insufficient"]
    if len(insuf) / len(cat_ids) < threshold:
        return decisions

    print(f"  {len(insuf)}/{len(cat_ids)} Insufficient → parent fallback")

    def agg(data_dict, cids):
        totals: dict = {}
        for cid in cids:
            d = data_dict.get(cid, {})
            for k, v in d.items():
                if v is None:
                    continue
                if k in ("cr", "campaign_per_user", "arp_p_campaign",
                         "pct_campaign_with_refund", "plan_imp_per_campaign",
                         "fact_imp_per_campaign", "pct_execution_inventory",
                         "price_per_day"):
                    continue           # derived; recomputed after
                totals[k] = totals.get(k, 0) + v
        # recompute derived fields
        paid = totals.get("paid_users", 0)
        al   = totals.get("active_listers", 0)
        nc   = totals.get("new_campaign_cnt", 0)
        sp   = totals.get("spending", 0)
        plan = totals.get("plan_imp_per_campaign", 0)  # keep 0 if not present
        fact = totals.get("fact_imp_per_campaign", 0)
        cref = totals.get("pct_campaign_with_refund", 0)
        ref  = totals.get("refund", 0)
        totals["cr"]                    = paid / al if al > 0 else None
        totals["campaign_per_user"]     = nc / paid if paid > 0 and nc > 0 else None
        totals["arp_p_campaign"]        = sp / nc if nc > 0 else None
        totals["pct_campaign_with_refund"] = cref / nc * 100 if nc > 0 else None
        totals["plan_imp_per_campaign"] = plan / nc if nc > 0 else None
        totals["fact_imp_per_campaign"] = fact / nc if nc > 0 else None
        totals["pct_execution_inventory"] = fact / plan * 100 - 100 if plan and plan > 0 else None
        return totals

    agg_cy_b = agg(cy_b_all, insuf)
    agg_cy_a = agg(cy_a_all, insuf)
    agg_py_b = agg(py_b_all, insuf) if py_b_all else None
    agg_py_a = agg(py_a_all, insuf) if py_a_all else None

    parent_dec, parent_ns, parent_code = decide(
        "parent", agg_cy_b, agg_cy_a, agg_py_b, agg_py_a, thr
    )
    print(f"  Parent-level: {parent_code} → {parent_dec}")

    updated = dict(decisions)
    for cid in insuf:
        updated[cid] = (parent_dec, parent_ns, f"{parent_code} (parent)")
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# CSV / Jira output builders
# ─────────────────────────────────────────────────────────────────────────────

def build_long_rows(cat_ids, cat_names, decisions, cy_b, cy_a, py_b, py_a):
    rows = []
    for cid in cat_ids:
        dec, ns, _ = decisions[cid]
        for mname, field, is_money in METRIC_SPECS:
            bv  = cy_b.get(cid, {}).get(field)
            av  = cy_a.get(cid, {}).get(field)
            pbv = py_b.get(cid, {}).get(field) if py_b else None
            pav = py_a.get(cid, {}).get(field) if py_a else None

            diff     = _pct(av,  bv)
            py_diff  = _pct(pav, pbv)
            y2y      = (diff - py_diff) if (diff is not None and py_diff is not None) else None

            rows.append({
                "category_id":   cid,
                "category_name": cat_names.get(cid, str(cid)),
                "scenario":      "Regular",
                "decision":      dec,
                "next_step":     ns,
                "metric":        mname,
                "Before":        _fmt(bv,  is_money),
                "After":         _fmt(av,  is_money),
                "Diff %":        _fmt_pct(diff),
                "PY Before":     _fmt(pbv, is_money),
                "PY After":      _fmt(pav, is_money),
                "PY Diff %":     _fmt_pct(py_diff),
                "Y2Y Diff %":    _fmt_pct(y2y),
            })
    return rows


def build_wiki_table(cat_ids, cat_names, decisions, cy_b, cy_a, py_b, py_a, max_metrics=13):
    specs = METRIC_SPECS[:max_metrics]
    lines = [
        "|| Category ID || Category Name || Scenario || Decision || Next Step "
        "|| Metric || Before || After || Diff % "
        "|| PY Before || PY After || PY Diff % || Y2Y Diff % ||"
    ]
    for cid in cat_ids:
        dec, ns, _ = decisions[cid]
        for mname, field, is_money in specs:
            bv  = cy_b.get(cid, {}).get(field)
            av  = cy_a.get(cid, {}).get(field)
            pbv = py_b.get(cid, {}).get(field) if py_b else None
            pav = py_a.get(cid, {}).get(field) if py_a else None

            diff    = _pct(av,  bv)
            py_diff = _pct(pav, pbv)
            y2y     = (diff - py_diff) if (diff is not None and py_diff is not None) else None

            lines.append(
                f"| {cid} | {cat_names.get(cid, str(cid))} | Regular | {dec} | {ns} | {mname} "
                f"| {_fmt2(bv,is_money)} | {_fmt2(av,is_money)} | {_fmt_pct2(diff)} "
                f"| {_fmt2(pbv,is_money)} | {_fmt2(pav,is_money)} | {_fmt_pct2(py_diff)} "
                f"| {_fmt_pct2(y2y)} |"
            )
    return "\n".join(lines)


def build_description(cfg, decisions, cat_names, cy_b, cy_a, py_b, py_a,
                       before_from, before_to, after_from, after_to, max_metrics=13):
    geo = cfg["geo"]
    ticket = cfg["ticket"]

    all_decs = [decisions[c][0] for c in cfg["cat_ids"]]
    if "Negative" in all_decs:
        overall = "Negative"
    elif all(d == "Insufficient" for d in all_decs):
        overall = "Insufficient"
    elif all_decs.count("Positive") >= all_decs.count("No impact"):
        overall = "Positive"
    else:
        overall = "No impact"

    py_before_from = before_from.replace(year=before_from.year - 1)
    py_before_to   = before_to.replace(year=before_to.year - 1)
    py_after_from  = after_from.replace(year=after_from.year - 1)
    py_after_to    = after_to.replace(year=after_to.year - 1)

    insuf_cats = [c for c in cfg["cat_ids"] if "Insufficient" in decisions[c][0]]
    notes = []
    if insuf_cats:
        names = ", ".join(f"{c} {cat_names.get(c,'?')}" for c in insuf_cats)
        notes.append(f"Insufficient data (paid_b < {GEO_THRESHOLDS.get(geo, GEO_THRESHOLDS['default'])['min_npl']}): {names}.")
    if max_metrics < 13:
        notes.append(f"Showing {max_metrics}/13 metrics. Full data in attached CSV.")

    note_str = ("_" + " ".join(notes) + "_\n\n") if notes else ""

    header = (
        f"h2. PPV Analysis\n\n"
        f"*Country:* {geo}\n"
        f"*Period Before:* {before_from} — {before_to}\n"
        f"*Period After:* {after_from} — {after_to}\n"
        f"*PY Period Before:* {py_before_from} — {py_before_to}\n"
        f"*PY Period After:* {py_after_from} — {py_after_to}\n"
        f"*Overall Decision:* {overall}\n\n"
        f"{note_str}"
        f"Full data with all metrics is attached as CSV.\n\n"
    )

    table = build_wiki_table(cfg["cat_ids"], cat_names, decisions,
                             cy_b, cy_a, py_b, py_a, max_metrics)
    return header + table, overall


# ─────────────────────────────────────────────────────────────────────────────
# Jira API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _jira(method, path, data=None):
    url = JIRA_BASE + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Basic {JIRA_AUTH}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:300]}")
        raise


def _attach_csv(ticket, filename, content):
    url = f"{JIRA_BASE}/rest/api/2/issue/{ticket}/attachments"
    boundary = "----ppvBoundary42"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: text/csv\r\n\r\n"
        f"{content}\r\n"
        f"--{boundary}--"
    ).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Basic {JIRA_AUTH}",
        "X-Atlassian-Token": "no-check",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _get_transitions(ticket):
    resp = _jira("GET", f"/rest/api/3/issue/{ticket}/transitions")
    return {t["name"]: t["id"] for t in resp.get("transitions", [])}


def _do_transition(ticket, keyword):
    """Find a transition whose name contains `keyword` (case-insensitive) and apply it."""
    trans = _get_transitions(ticket)
    for name, tid in trans.items():
        if keyword.lower() in name.lower():
            print(f"    → {name} (id={tid})")
            _jira("POST", f"/rest/api/3/issue/{ticket}/transitions",
                  {"transition": {"id": tid}})
            return True
    print(f"    ! No transition matching '{keyword}'. Available: {list(trans.keys())}")
    return False


def run_transitions(ticket, target):
    """
    Walk the ticket to its target status:
      "decision"  → Experiment finished → Analysis → Ready to discuss results → Decision
      "positive"  → ... → Decision → Good for business
      "negative"  → ... → Decision → Negative impact
      "noimpact"  → ... → Decision → Don't see any impact
    """
    if target is None:
        return

    issue = _jira("GET", f"/rest/api/3/issue/{ticket}?fields=status")
    status = issue["fields"]["status"]["name"]
    print(f"  Status: {status}")

    if status == "Running":
        _do_transition(ticket, "experiment finished")
        status = _jira("GET", f"/rest/api/3/issue/{ticket}?fields=status")["fields"]["status"]["name"]
        print(f"  Status: {status}")

    if status == "Analysis":
        _do_transition(ticket, "ready to discuss")
        status = _jira("GET", f"/rest/api/3/issue/{ticket}?fields=status")["fields"]["status"]["name"]
        print(f"  Status: {status}")

    if target == "decision":
        print(f"  Done → {status}")
        return

    # from Decision → final
    keyword_map = {
        "positive":  "good for business",
        "negative":  "negative impact",
        "noimpact":  "don't see",
    }
    kw = keyword_map.get(target)
    if kw:
        _do_transition(ticket, kw)
        status = _jira("GET", f"/rest/api/3/issue/{ticket}?fields=status")["fields"]["status"]["name"]
    print(f"  Final status: {status}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(cfg=None):
    if cfg is None:
        cfg = EXPERIMENT

    ticket   = cfg["ticket"]
    cat_ids  = cfg["cat_ids"]
    geo      = cfg["geo"]
    days     = cfg.get("days", 30)
    target   = cfg.get("transition", "decision")

    start   = date.fromisoformat(cfg["start_date"])
    after_from  = start
    after_to    = start + timedelta(days=days - 1)
    before_from = start - timedelta(days=days)
    before_to   = start - timedelta(days=1)

    py_before_from = before_from.replace(year=before_from.year - 1)
    py_before_to   = before_to.replace(year=before_to.year - 1)
    py_after_from  = after_from.replace(year=after_from.year - 1)
    py_after_to    = after_to.replace(year=after_to.year - 1)

    country_id = cfg.get("country_id") or COUNTRY_FROM_GEO.get(geo) or COUNTRY_ID_MAP.get(geo)
    thr = GEO_THRESHOLDS.get(geo, GEO_THRESHOLDS["default"])

    print(f"\n{'='*60}")
    print(f"  {ticket}  |  {geo}  |  {before_from} / {after_from}  |  {days}d")
    print(f"{'='*60}")

    # ── Fetch data ────────────────────────────────────────────────────────────
    print("Fetching CY data...")
    cy_b = fetch_period_data(cat_ids, country_id, before_from, before_to)
    cy_a = fetch_period_data(cat_ids, country_id, after_from,  after_to)

    print("Fetching PY data...")
    py_b = fetch_period_data(cat_ids, country_id, py_before_from, py_before_to)
    py_a = fetch_period_data(cat_ids, country_id, py_after_from,  py_after_to)

    print("Fetching category names...")
    cat_names = fetch_cat_names(cat_ids)

    # ── Decisions ─────────────────────────────────────────────────────────────
    print("Computing decisions...")
    decisions = {}
    for cid in cat_ids:
        dec, ns, code = decide(cid, cy_b[cid], cy_a[cid], py_b.get(cid), py_a.get(cid), thr)
        decisions[cid] = (dec, ns, code)
        paid_b = cy_b[cid]["paid_users"]
        print(f"  {cid} ({cat_names.get(cid, '?')}): paid_b={paid_b} | {code} → {dec}")

    # Parent fallback if needed
    decisions = maybe_parent_fallback(
        cat_ids, decisions, cy_b, cy_a, py_b, py_a, thr
    )

    # ── Long CSV ──────────────────────────────────────────────────────────────
    long_rows = build_long_rows(cat_ids, cat_names, decisions, cy_b, cy_a, py_b, py_a)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=LONG_COLS)
    writer.writeheader()
    writer.writerows(long_rows)
    csv_str = buf.getvalue()

    csv_path = f"/tmp/{ticket}_analysis_long.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_str)
    print(f"CSV: {csv_path}  ({len(long_rows)} rows)")

    # ── Jira description ──────────────────────────────────────────────────────
    max_m = 13
    desc, overall = build_description(cfg, decisions, cat_names,
                                       cy_b, cy_a, py_b, py_a,
                                       before_from, before_to, after_from, after_to,
                                       max_metrics=max_m)
    while len(desc) > 30000 and max_m > 3:
        max_m -= 1
        desc, overall = build_description(cfg, decisions, cat_names,
                                           cy_b, cy_a, py_b, py_a,
                                           before_from, before_to, after_from, after_to,
                                           max_metrics=max_m)
    print(f"Description: {len(desc)} chars, {max_m}/13 metrics shown, overall={overall}")

    print("Updating Jira description...")
    _jira("PUT", f"/rest/api/2/issue/{ticket}", {"fields": {"description": desc}})

    print("Attaching CSV...")
    try:
        _attach_csv(ticket, f"{ticket}_analysis_long.csv", csv_str)
        print("  Attached!")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Transitions ───────────────────────────────────────────────────────────
    print(f"Transitioning → {target}...")
    run_transitions(ticket, target)

    print("\nDone!")
    return decisions


if __name__ == "__main__":
    main()
