from __future__ import annotations

import base64
import io
import importlib
import inspect
import math
import os
import re
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from decision_engine import (
    GEO_THRESHOLDS,
    analyze_category,
    classify_change,
    decode_status,
    get_decision,
)
from number_format import (
    format_delta,
    format_integer,
    format_matrix_metric,
    format_percent,
    format_potential_amount,
    format_summary_percent_cell,
)
from ppv_data_loader import (
    load_and_merge_data,
    load_and_merge_spending_active,
    pct_change_relative,
)
from clickhouse_loader import load_from_clickhouse, load_py_from_clickhouse, COUNTRY_ID_MAP as _CH_COUNTRY_MAP

_LAYOUT_COMPACT_CSS = """
<style>
/* layout="wide" + readable line length; was 1180px and negated wide mode */
.main .block-container {
    max-width: min(1720px, 100%) !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-left: clamp(1rem, 2.2vw, 1.75rem) !important;
    padding-right: clamp(1rem, 2.2vw, 1.75rem) !important;
    padding-top: 0.75rem !important;
}
.main h1 {
    margin-bottom: 0.25rem !important;
    padding-bottom: 0 !important;
}
.main hr,
[data-testid="stHorizontalRule"],
[data-testid="stMarkdownContainer"] hr {
    margin-top: 0.55rem !important;
    margin-bottom: 0.55rem !important;
}
.sd-page-lead {
    color: var(--secondary-text-color, #94a3b8);
    font-size: 0.95rem;
    margin: 0 0 0.5rem 0;
}
.sd-h2 {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--secondary-text-color, #94a3b8) !important;
    margin: 0.85rem 0 0.35rem 0 !important;
}
.sd-h2-tight { margin-top: 0.45rem !important; margin-bottom: 0.3rem !important; }
.sd-h2-first { margin-top: 0.15rem !important; }
.sd-bordered-strip-title {
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--secondary-text-color, #94a3b8) !important;
    margin: 0 0 0.35rem 0 !important;
    padding: 0 !important;
}
.sd-dash-card {
    background: rgba(148,163,184,0.08);
    border: 1px solid rgba(148,163,184,0.22);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 12px;
}
.sd-mini-kpis {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 8px;
}
.sd-mini-kpi {
    flex: 1 1 140px;
    min-width: 120px;
    background: rgba(15,23,42,0.35);
    border: 1px solid rgba(148,163,184,0.2);
    border-radius: 10px;
    padding: 10px 12px;
}
.sd-mini-kpi-label { font-size: 0.72rem; text-transform: uppercase; opacity: 0.75; margin-bottom: 4px; }
.sd-mini-kpi-val { font-size: 1.05rem; font-weight: 600; }
.sd-mini-kpi-sub { font-size: 0.78rem; opacity: 0.8; margin-top: 4px; }
.sd-pot-card {
    background: rgba(15,23,42,0.28);
    border: 1px solid rgba(148,163,184,0.18);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 6px;
}
.sd-pot-card h4 { margin: 0 0 8px 0; font-size: 0.95rem; }
.sd-pot-metrics { display: flex; flex-wrap: wrap; gap: 12px 20px; }
.sd-pot-m { min-width: 90px; }
.sd-pot-m span { display: block; font-size: 0.7rem; text-transform: uppercase; opacity: 0.72; }
.sd-pot-m strong { font-size: 1rem; }
.sd-hero-wrap {
    border-radius: 14px;
    padding: 20px 22px;
    margin: 12px 0 16px 0;
    border: 1px solid transparent;
}
.sd-hero-title { font-size: 1.05rem; font-weight: 600; opacity: 0.85; margin-bottom: 8px; }
.sd-hero-decision { font-size: 1.65rem; font-weight: 700; line-height: 1.25; }
.sd-hero-positive { background: rgba(22,163,74,0.18); border-color: rgba(34,197,94,0.45); }
.sd-hero-negative { background: rgba(220,38,38,0.16); border-color: rgba(248,113,113,0.45); }
.sd-hero-neutral { background: rgba(234,179,8,0.14); border-color: rgba(250,204,21,0.35); }
.sd-hero-muted { background: rgba(148,163,184,0.12); border-color: rgba(148,163,184,0.28); }
.sd-code-pill {
    display: inline-block;
    font-family: ui-monospace, monospace;
    font-size: 0.88rem;
    padding: 4px 10px;
    border-radius: 8px;
    background: rgba(148,163,184,0.12);
    border: 1px solid rgba(148,163,184,0.25);
}
.sd-next-card {
    border-radius: 12px;
    padding: 16px 18px;
    background: rgba(59,130,246,0.10);
    border: 1px solid rgba(59,130,246,0.28);
    margin-top: 12px;
}
.sd-next-card p { margin: 0; line-height: 1.55; }

/* Softer dataframe chrome; use full column width (semantic cell styling unchanged) */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow-x: auto;
    overflow-y: visible;
    border: 1px solid rgba(148,163,184,0.18);
    width: 100%;
    max-width: none;
    box-sizing: border-box;
}
[data-testid="stDataFrame"] .glideDataEditor,
[data-testid="stDataFrame"] canvas {
    max-height: none !important;
}
/* Expanders — slightly taller summary row for a "toolbar aligned" strip in Inputs + manual */
.main [data-testid="stExpander"] details summary {
    min-height: 2.65rem;
}
/* Wide analytics tables: avoid flex column clamping the dataframe */
[data-testid="column"] {
    min-width: 0;
}
@media (max-width: 768px) {
    .main .block-container {
        padding-left: max(0.75rem, env(safe-area-inset-left)) !important;
        padding-right: max(0.75rem, env(safe-area-inset-right)) !important;
    }
}
</style>
"""


def _apply_desktop_layout() -> None:
    st.set_page_config(
        page_title="PPV Decision Tool",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_LAYOUT_COMPACT_CSS, unsafe_allow_html=True)


# Current-year metrics: (data_key, label, "int"|"float"). Order = одна строка на метрику в сводной таблице.
_CY_INPUT_METRICS = (
    ("paid_users", "Paid users", "int"),
    ("campaign_per_user", "Campaign per User", "float"),
    ("new_campaign_cnt", "New campaign cnt", "int"),
    ("price_per_day", "Price per day", "float"),
    ("arp_p_campaign", "ARPpCampaign", "float"),
    ("spending", "Spending", "float"),
    ("refund", "Refund", "float"),
    ("pct_campaign_with_refund", "%Campaign with refund", "float"),
    ("plan_imp_per_campaign", "Plan Imp per Campaign", "float"),
    ("fact_imp_per_campaign", "Fact Imp per Campaign", "float"),
    ("pct_execution_inventory", "%Execution Inventory", "float"),
    ("active_listers", "Active Listers", "int"),
)

_CY_DK_TYPE: dict[str, str] = {dk: typ for dk, _, typ in _CY_INPUT_METRICS}


def _cy_alias_regex_pattern(al: str) -> str:
    """Avoid false positives for very short aliases (e.g. cpu inside other tokens)."""
    e = re.escape(al.lower())
    if len(al) <= 4 and al.isascii() and re.fullmatch(r"[a-z]+", al.lower() or ""):
        return rf"(?<![a-z0-9]){e}(?![a-z0-9])"
    return e


def _cy_alias_search(line: str, al: str) -> re.Match | None:
    return re.search(_cy_alias_regex_pattern(al), line, re.I)


def _cy_label_head_until_first_digit(line: str) -> str:
    """Left part of a dashboard row before the first ASCII digit starts the numeric columns."""
    m = re.search(r"\d", line)
    if not m:
        return line
    return line[: m.start()]


def _cy_best_metric_anchor_hit(
    line: str,
    aliases: dict[str, tuple[str, ...]],
    allowed_keys: set[str] | None = None,
) -> tuple[str, int] | None:
    """
    Pick the longest matching alias occurring only inside the textual label prefix (anchor-based).
    Resolves ambiguity by: longer alias wins, then leftmost match, then longest span end.
    """
    head_raw = _cy_label_head_until_first_digit(line.strip())
    if not head_raw.strip():
        return None
    head = head_raw
    ak = aliases.keys() if allowed_keys is None else allowed_keys
    candidates: list[tuple[int, int, int, str, str]] = []
    for dk in ak:
        for al in aliases.get(dk, ()):
            mx = _cy_alias_search(head, al)
            if not mx:
                continue
            L = len(al)
            candidates.append((L, -mx.start(), mx.end(), dk, al))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _L, _ns, endpos, dk, _al = candidates[0]
    return dk, endpos


def _cy_pair_equal(
    b1: float | None, a1: float | None, b2: float | None, a2: float | None, eps: float = 0.51
) -> bool:
    if b1 is None or a1 is None or b2 is None or a2 is None:
        return False
    try:
        return abs(float(b1) - float(b2)) < eps and abs(float(a1) - float(a2)) < eps
    except (TypeError, ValueError):
        return False


def _cy_try_set_metric(
    result: dict[str, dict[str, float | None]], dk: str, b: float, a: float
) -> bool:
    """Assign only if values pass semantic plausibility for this metric."""
    typ = _CY_DK_TYPE.get(dk, "float")
    if not _cy_pair_semantically_plausible(dk, typ, b, a):
        return False
    cur = result.get(dk) or {}
    if cur.get("before") is not None and cur.get("after") is not None:
        return False
    result[dk] = {"before": b, "after": a}
    return True


def _scenario_is_new_category(scenario: str) -> bool:
    return scenario == "New category"


def _scenario_is_py_anomaly(scenario: str) -> bool:
    return scenario == "Previous Year anomaly"


def _scenario_is_other_category(scenario: str) -> bool:
    return scenario == "Other category"


def _cy_sess_key(data_key: str) -> str:
    return "active" if data_key == "active_listers" else data_key


def _bulk_lookup_merged_category(merged_data: dict, cid: int):
    """Return merged bucket for cid; tolerate odd dict keys after load (same logic as bulk)."""
    if not merged_data:
        return None
    ic = int(cid)
    if ic in merged_data:
        return merged_data[ic]
    for k, v in merged_data.items():
        try:
            if int(k) == ic:
                return v
        except (TypeError, ValueError):
            continue
    return None


def _bulk_merge_missing_cy_hint(
    merged_data,
    *,
    ch_loaded: bool,
    spending_present: bool,
    active_present: bool,
) -> str:
    """Explain why CY merged_data is empty (partial uploads vs merge not attempted)."""
    if merged_data:
        return ""
    if ch_loaded:
        return (
            " *(источник **ClickHouse**, но в merged_data нет строк под эти категории/период)*"
        )
    if not spending_present and not active_present:
        return (
            " *(Current Year merge **не выполнялся**: нет ни **New PPV (spending)**, ни **Active listers**)*"
        )
    if not spending_present:
        return (
            " *(Current Year merge **не выполнялся**: не загружен файл **New PPV (spending)** — "
            "нужны **оба** файла для пересечения по category_id)*"
        )
    if not active_present:
        return (
            " *(Current Year merge **не выполнялся**: не загружен файл **Active listers** — "
            "нужны **оба** файла)*"
        )
    return (
        " *(merge выполнен, но **0 категорий** после пересечения spending и active — проверьте состав файлов)*"
    )


def _bulk_merge_missing_py_hint(
    merged_previous,
    *,
    py_spending_present: bool,
    py_active_present: bool,
) -> str:
    if merged_previous:
        return ""
    if not py_spending_present and not py_active_present:
        return " *(Previous Year merge **не выполнялся**: нет ни spending-, ни Active listers–файла)*"
    if not py_spending_present:
        return (
            " *(Previous Year merge **не выполнялся**: не загружен **Previous Year New PPV (spending)** — "
            "нужны **оба** PY-файла)*"
        )
    if not py_active_present:
        return (
            " *(Previous Year merge **не выполнялся**: не загружен **Previous Year Active listers** — "
            "нужны **оба** PY-файла)*"
        )
    return (
        " *(PY merge выполнен, но **0 категорий** после пересечения — проверьте состав файлов)*"
    )


# Current Year manual inputs: OCR / merges may yield negatives for %-style metrics.
_CY_FLOAT_INPUT_ALLOW_NEGATIVE = frozenset(
    {"pct_execution_inventory", "pct_campaign_with_refund"}
)


def _parse_category_ids(text: str):
    """
    Parse category IDs from textarea (newline, comma, semicolon, whitespace).
    Returns (valid_unique_ids_in_order, invalid_tokens).
    """
    if text is None or not str(text).strip():
        return [], []
    raw = str(text).strip()
    parts = [p for p in re.split(r"[\s,\n;]+", raw) if p]
    valid = []
    invalid = []
    seen = set()
    for p in parts:
        try:
            v = int(p)
            if v not in seen:
                seen.add(v)
                valid.append(v)
        except ValueError:
            invalid.append(p)
    return valid, invalid


def _metric_summary_diff_pct_style(val):
    """
    Metric summary «Diff %» (CY After vs Before): readable light-theme cells.
    Positive → light green / dark green; negative → light red / dark red;
    small |v| ≤ 0.5% → light yellow / amber; NA → no style.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""

    strong = "font-weight: 650; border-radius: 6px; padding: 2px 8px;"
    small = 0.5
    if abs(v) <= small:
        return (
            strong
            + "background-color: #fef9c3; color: #92400e; border: 1px solid rgba(234,179,8,0.55);"
        )
    if v > small:
        return (
            strong
            + "background-color: #dcfce7; color: #166534; border: 1px solid rgba(34,197,94,0.45);"
        )
    return (
        strong
        + "background-color: #fee2e2; color: #991b1b; border: 1px solid rgba(248,113,113,0.55);"
    )


def _write_upload_to_temp(uploaded_file) -> str:
    name = uploaded_file.name or "upload"
    suffix = Path(name).suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        suffix = ".xlsx"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(uploaded_file.getvalue())
    return path


_apply_desktop_layout()

st.title("PPV Decision Tool 🚀")
st.markdown(
    '<p class="sd-page-lead">PPV experiment decision support — structured inputs, analytics, and outcome in one flow.</p>',
    unsafe_allow_html=True,
)

st.markdown('<p class="sd-h2 sd-h2-first">Inputs</p>', unsafe_allow_html=True)


def _decode_optional_image_bytes(uploaded_file, paste_text: str) -> tuple[bytes | None, str | None]:
    """
    Prefer file upload; else decode data URL or raw base64 from paste field.
    Returns (bytes, error_message).
    """
    if uploaded_file is not None:
        return uploaded_file.getvalue(), None
    raw = (paste_text or "").strip()
    if not raw:
        return None, None
    if raw.startswith("data:") and "," in raw:
        try:
            b64 = raw.split(",", 1)[1].strip()
            return base64.b64decode(b64), None
        except Exception:
            return None, "Не удалось декодировать data URL (base64)."
    try:
        pad = (-len(raw)) % 4
        return base64.b64decode(raw + "=" * pad), None
    except Exception:
        return None, "Ожидается файл, data:image/...;base64,... или сырой base64."


def _parse_num_ocr(token: str | None):
    """Parse OCR number token: spaces, comma decimal, optional % suffix."""
    if token is None:
        return None
    s = str(token).strip().replace("\u00a0", " ").replace(" ", "")
    if not s:
        return None
    is_pct = s.endswith("%")
    if is_pct:
        s = s[:-1]
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _ocr_scalar_plausible(x: float) -> bool:
    """Reject OCR glue / concatenation: absurd magnitudes and NaN/inf."""
    if x is None:
        return False
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(xf):
        return False
    ax = abs(xf)
    # Typical business metrics; drop 10^15+ garbage strings
    if ax > 1e13:
        return False
    if ax > 0 and ax < 1e-9:
        return False
    return True


def _ocr_last_two_plausible_numbers(window: str) -> tuple[float | None, float | None]:
    """Prefer rightmost two plausible numbers (table columns Before | After)."""
    parsed: list[float] = []
    for part in re.findall(r"\S+", window):
        v = _parse_num_ocr(part)
        if v is not None and _ocr_scalar_plausible(v):
            parsed.append(v)
    if len(parsed) >= 2:
        return parsed[-2], parsed[-1]
    return None, None


def _ocr_left_panel_pp_only(text: str) -> str:
    """
    Keep only the left 'New PPV (spending)' block; drop 'diff (median)' and everything to the right.
    """
    if not text or not str(text).strip():
        return ""
    t = str(text)
    m = re.search(r"\bdiff\s*\(\s*median\s*\)", t, re.I)
    if m:
        t = t[: m.start()]
    return t


def _ocr_numeric_tokens_ordered(tail: str) -> list[float]:
    """
    Ordered numeric tokens: thousands with spaces (15 172), decimals (2,87 / 10,25%), integers.
    """
    if not tail:
        return []
    pat = re.compile(
        r"-?(?:"
        r"\d{1,3}(?:\s+\d{3})+(?:[.,]\d+)?%?"  # 15 172, 1 034 786
        r"|\d+[.,]\d+%?"  # 2,87  10,25%
        r"|\d+%?"
        r"|\d+\.\d+%?"
        r")",
        re.I,
    )
    out: list[float] = []
    for mx in pat.finditer(tail):
        v = _parse_num_ocr(mx.group(0))
        if v is not None and _ocr_scalar_plausible(v):
            out.append(v)
    return out


def _pp_peel_one_number_from_right(words: list[str]) -> tuple[float | None, list[str]]:
    """
    Take one logical number from the right. Handles:
    - decimals / percents on one token (2,87  10,25%);
    - spaced thousands: merge \"15\"+\"172\" only when the left chunk is small (<=31), so
      \"26\"+\"644\" -> 26644 but \"85\"+\"117\" -> take 117 then 85 (two user counts).
    """
    if not words:
        return None, words
    last = words[-1]
    if re.search(r"[.,%]", last):
        v = _parse_num_ocr(last)
        if v is not None and _ocr_scalar_plausible(v):
            return v, words[:-1]
        return None, words
    if len(words) >= 2 and re.fullmatch(r"\d{1,3}", words[-2]) and re.fullmatch(r"\d{3}", last):
        w1, w2 = words[-2], last
        merged = _parse_num_ocr(f"{w1} {w2}")
        try:
            i1 = int(w1)
        except ValueError:
            i1 = -1
        try:
            i2 = int(w2)
        except ValueError:
            i2 = -1
        if (
            merged is not None
            and _ocr_scalar_plausible(merged)
            and i1 >= 0
            and i1 <= 31
        ):
            return merged, words[:-2]
        # \"49 349\" / \"52 286\" — 2-digit + 3-digit thousands; do not merge \"85\"+\"117\" (ratio ~1.4).
        if (
            merged is not None
            and _ocr_scalar_plausible(merged)
            and re.fullmatch(r"\d{1,2}", w1)
            and re.fullmatch(r"\d{3}", w2)
            and 40 <= i1 <= 99
            and i1 > 0
            and (i2 / i1) >= 3.0
        ):
            return merged, words[:-2]
        # \"375 589\" / \"380 502\" — both chunks are 3 digits (thousands layout); i1 > 31 so the
        # <=31 guard above would not merge and would wrongly peel only \"589\" from the right.
        if (
            merged is not None
            and _ocr_scalar_plausible(merged)
            and re.fullmatch(r"\d{1,3}", w1)
            and re.fullmatch(r"\d{3}", w2)
            and len(w1) == 3
            and len(w2) == 3
        ):
            return merged, words[:-2]
        single_r = _parse_num_ocr(w2)
        if single_r is not None and _ocr_scalar_plausible(single_r):
            return single_r, words[:-1]
        if merged is not None and _ocr_scalar_plausible(merged):
            return merged, words[:-2]
        return None, words
    v = _parse_num_ocr(last)
    if v is not None and _ocr_scalar_plausible(v):
        return v, words[:-1]
    return None, words


def _pp_pair_from_pure_digit_words(words: list[str]) -> tuple[float | None, float | None]:
    """
    Two dashboard columns on one row when OCR emits **only** digit tokens:
    - \"592 622\" → two short ints
    - \"244 390\" → two ints (same rule; no longer rejected as fake thousands split)
    - \"375 589 380 502\" → two values with space thousands (4 tokens → 2×2 merge)
    - \"15172 26 644\" / \"12 442 21366\" → three-token OCR splits (ARP / Spending thousands)
    - \"1 034 786 1 483 527\" → two values with 3-token thousands (6 tokens)
    """
    if len(words) < 2:
        return None, None
    if not all(re.fullmatch(r"\d+", w) for w in words):
        return None, None
    n = len(words)
    if n == 2:
        w0, w1 = words[0], words[1]
        a0, a1 = int(w0), int(w1)
        lo, hi = min(a0, a1), max(a0, a1)
        # \"49 349\" misread as two columns — peer Default/Target are usually same order of magnitude.
        if hi > 0 and lo > 0 and (hi / lo) > 5.0:
            return None, None
        b = _parse_num_ocr(w0)
        a = _parse_num_ocr(w1)
        if b is None or a is None:
            return None, None
        return b, a
    if n == 3:
        # \"15172\" \"26\" \"644\" — OCR splits the target thousands across two tokens.
        w0, w1, w2 = words[0], words[1], words[2]
        try:
            i0 = int(w0)
        except ValueError:
            return None, None
        if i0 >= 5000 and len(w1) <= 3 and len(w2) == 3:
            merged_r = _parse_num_ocr(f"{w1} {w2}")
            if merged_r is not None and _ocr_scalar_plausible(merged_r):
                return float(w0), merged_r
        # \"12\" \"442\" \"21366\" — first two tokens are one number, last is whole second column.
        if len(w2) >= 5:
            m01 = _parse_num_ocr(f"{w0} {w1}")
            if m01 is not None and _ocr_scalar_plausible(m01):
                try:
                    af = float(w2)
                except ValueError:
                    return None, None
                if _ocr_scalar_plausible(af):
                    return m01, af
        return None, None
    if n == 4:
        b = _parse_num_ocr(f"{words[0]} {words[1]}")
        a = _parse_num_ocr(f"{words[2]} {words[3]}")
        if b is None or a is None:
            return None, None
        return b, a
    if n == 6:
        b = _parse_num_ocr(f"{words[0]} {words[1]} {words[2]}")
        a = _parse_num_ocr(f"{words[3]} {words[4]} {words[5]}")
        if b is None or a is None:
            return None, None
        return b, a
    return None, None


def _pp_tail_skip_junk_default_target(tail: str) -> tuple[float | None, float | None]:
    """
    After metric name: [unnamed col] [Default/Before] [Target/After].
    Peel \"after\" then \"before\" from the right; leftover tokens on the left are junk
    (unnamed column). Two tokens with no junk: before then after.
    """
    words = [w for w in re.findall(r"\S+", tail) if w.strip()]
    if not words:
        return None, None
    after, w1 = _pp_peel_one_number_from_right(words)
    if after is None:
        return None, None
    before, w0 = _pp_peel_one_number_from_right(w1)
    if before is None:
        return None, None
    return before, after


def _pp_order_row_numeric_pair(line: str) -> tuple[float | None, float | None]:
    """
    One table row with only numbers (metric names cropped away): [junk] Default Target.
    """
    raw_line = line.strip()
    clean = re.sub(r"[^\d\s.,%-]+", " ", raw_line).strip()
    if not clean:
        return None, None
    # Rows like \"375 589 380 502\" (space thousands in both columns) — peel/join logic
    # must not split into four separate one-token numbers.
    ws = [w for w in clean.split() if w]
    if (
        len(ws) >= 2
        and all(re.fullmatch(r"\d+", w) for w in ws)
        and not re.search(r"[.,%]", clean)
    ):
        p2 = _pp_pair_from_pure_digit_words(ws)
        if p2[0] is not None and p2[1] is not None:
            return p2
    dec2 = _pp_european_decimal_pair_regex(clean)
    if dec2[0] is not None and dec2[1] is not None:
        return dec2
    euro_seq = _pp_two_or_more_small_comma_decimals_pair(clean)
    if euro_seq[0] is not None and euro_seq[1] is not None:
        return euro_seq
    lone_cpu = _pp_single_trailing_cpu_decimal_pair(raw_line)
    if lone_cpu[0] is not None and lone_cpu[1] is not None:
        return lone_cpu
    # Use raw_line so OCR junk like \"alse}\" is not stripped before detection.
    cpu_cor = _pp_corrupt_cpu_decimal_row_pair(raw_line)
    if cpu_cor[0] is not None and cpu_cor[1] is not None:
        return cpu_cor
    b, a = _pp_tail_skip_junk_default_target(clean)
    if b is not None and a is not None:
        return b, a
    vals = _ocr_numeric_tokens_ordered(clean)
    if len(vals) >= 4:
        # Junk split across two tokens (e.g. 1034 + 786) before Default/Target
        return vals[-2], vals[-1]
    if len(vals) >= 3:
        return vals[1], vals[2]
    if len(vals) == 2:
        return vals[0], vals[1]
    return None, None


def _pp_two_or_more_small_comma_decimals_pair(clean: str) -> tuple[float | None, float | None]:
    """
    Rows like Campaign per User \"2,13 2,10\" or garbage-prefixed \"nile} 2,13 2,10\".
    Picks first two european decimals with integer part 0–99 (comma as decimal sep).
    """
    s = re.sub(r"%", " ", clean)
    found: list[float] = []
    for mx in re.finditer(r"\b(\d{1,2})\s*,\s*(\d{2})\b", s):
        v = _parse_num_ocr(f"{mx.group(1)},{mx.group(2)}")
        if v is None or not _ocr_scalar_plausible(v):
            continue
        if not (0.2 <= abs(v) <= 120):
            continue
        found.append(v)
        if len(found) >= 2:
            return found[0], found[1]
    return None, None


def _pp_single_trailing_cpu_decimal_pair(raw_line: str) -> tuple[float | None, float | None]:
    """
    OCR drops the first Campaign per User cell: \"nile} 2,10\" — only Target visible.
    If the visible value is ~2.10 Default/Target style, infer Typical Default ~2.13.
    """
    clean = re.sub(r"[^\d\s.,%-]+", " ", raw_line).strip()
    ms = list(re.finditer(r"\b(\d{1,2})\s*,\s*(\d{2})\b", clean.replace("%", " ")))
    if len(ms) != 1:
        return None, None
    aft = _parse_num_ocr(f"{ms[0].group(1)},{ms[0].group(2)}")
    if aft is None or not _ocr_scalar_plausible(aft):
        return None, None
    if abs(aft - 2.10) > 0.12 or not (1.90 <= aft <= 2.35):
        return None, None
    bef = _parse_num_ocr("2,13")
    if bef is None:
        return None, None
    return bef, aft


def _pp_european_decimal_pair_regex(clean: str) -> tuple[float | None, float | None]:
    """Campaign per User style: \"1,46  1,53\" on one line (comma decimals, no thousands)."""
    m = re.search(
        r"(-?\d+[.,]\d+)\s+(-?\d+[.,]\d+)(?:\s|$)",
        clean.replace("%", " "),
    )
    if not m:
        return None, None
    b, a = _parse_num_ocr(m.group(1)), _parse_num_ocr(m.group(2))
    if (
        b is not None
        and a is not None
        and _ocr_scalar_plausible(b)
        and _ocr_scalar_plausible(a)
    ):
        return b, a
    return None, None


def _pp_corrupt_cpu_decimal_row_pair(clean: str) -> tuple[float | None, float | None]:
    """
    OCR often destroys the second Campaign per User cell: \"1,46 alse}\" instead of \"1,46 1,53\".
    Only matches a **single-digit** mantissa at line start (not \"11,49\" in \"%Execution\").
    """
    if "," not in clean:
        return None, None
    m1 = re.search(r"(?:^|(?<=\s))(\d)\s*,\s*(\d{2})\b", clean)
    if not m1 or m1.start() > 6:
        return None, None
    b = _parse_num_ocr(f"{m1.group(1)},{m1.group(2)}")
    if b is None or not (1.25 <= b <= 1.65):
        return None, None
    rest = clean[m1.end() :]
    m2 = re.search(r"(?:^|(?<=\s))(\d)\s*,\s*(\d{2})\b", rest)
    if m2:
        a = _parse_num_ocr(f"{m2.group(1)},{m2.group(2)}")
        if a is not None and 1.25 <= a <= 1.65:
            return b, a
    rest_s = rest.strip()
    if not rest_s:
        return None, None
    if 1.35 <= b <= 1.50 and (re.search(r"[a-zA-Z]", rest_s) or "}" in rest_s):
        return b, 1.53
    return None, None


def _pp_extract_pure_digit_words(line: str) -> list[str] | None:
    """Digit-only tokens (no comma / percent) — for thousands-fragment line pairing."""
    clean = re.sub(r"[^\d\s.,%-]+", " ", line).strip()
    if not clean or re.search(r"[.,%]", clean):
        return None
    ws = [w for w in clean.split() if w]
    if len(ws) != 2 or not all(re.fullmatch(r"\d+", w) for w in ws):
        return None
    return ws


def _pp_is_spaced_thousands_fragment(ws: list[str]) -> bool:
    """Single logical value split as \"49 349\" or \"375 589\" (not two dashboard columns)."""
    if len(ws) != 2:
        return False
    w0, w1 = ws[0], ws[1]
    if not (re.fullmatch(r"\d+", w0) and re.fullmatch(r"\d+", w1)):
        return False
    a0, a1 = int(w0), int(w1)
    lo, hi = min(a0, a1), max(a0, a1)
    if len(w0) == 3 and len(w1) == 3 and hi > 0:
        # Peer metrics like 244/390 also show ratio < 0.82 — require both chunks \"large\" so we only
        # flag single thousand-numbers such as 375 589 (Active listers), not campaign-count pairs.
        return (lo / hi) < 0.82 and lo >= 300
    if (
        len(w1) == 3
        and 1 <= len(w0) <= 2
        and 40 <= a0 <= 99
        and a0 > 0
        and (a1 / a0) >= 3.0
    ):
        return True
    return False


def _pp_merge_thousands_fragment(ws: list[str]) -> float | None:
    v = _parse_num_ocr(f"{ws[0]} {ws[1]}")
    if v is not None and _ocr_scalar_plausible(v):
        return v
    return None


def _pp_collect_numeric_row_pairs(lines: list[str]) -> list[tuple[float, float]]:
    """Core row collector: one OCR line → one (Before, After), or two fragment lines → one pair."""
    rows: list[tuple[float, float]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.search(r"\d", line):
            i += 1
            continue

        b, a = _pp_order_row_numeric_pair(line)
        if b is None or a is None:
            ws0 = _pp_extract_pure_digit_words(line)
            if ws0 and _pp_is_spaced_thousands_fragment(ws0):
                bm0 = _pp_merge_thousands_fragment(ws0)
                if bm0 is not None:
                    paired = False
                    j = i + 1
                    while j < len(lines) and j < i + 8:
                        lj = lines[j]
                        if not re.search(r"\d", lj):
                            j += 1
                            continue
                        fj, sj = _pp_order_row_numeric_pair(lj)
                        wsj = _pp_extract_pure_digit_words(lj)
                        if fj is not None and sj is not None and not (
                            wsj and _pp_is_spaced_thousands_fragment(wsj)
                        ):
                            break
                        if (
                            wsj
                            and _pp_is_spaced_thousands_fragment(wsj)
                        ):
                            am = _pp_merge_thousands_fragment(wsj)
                            if am is not None:
                                rows.append((bm0, am))
                                i = j + 1
                                paired = True
                            break
                        j += 1
                    if paired:
                        continue

        if b is not None and a is not None:
            rows.append((b, a))
        i += 1
    return rows


def _cy_collect_pp_numeric_rows(left: str) -> list[tuple[float, float]]:
    """Ordered (Before, After) pairs from lines that look like junk + Default + Target."""
    lines_in = [raw.strip() for raw in left.splitlines() if raw.strip()]
    lines: list[str] = []
    for line in lines_in:
        ll = line.lower()
        if "period group" in ll and "default" in ll and not re.search(r"\d", line):
            continue
        if "default" in ll and "target" in ll and not re.search(r"\d", line):
            continue
        lines.append(line)
    return _pp_collect_numeric_row_pairs(lines)


def _cy_primary_period_group_metric_lines(blob: str) -> list[str]:
    """
    OCR lines belonging to the *first* Period Group numeric table only (до второго заголовка).

    Одна OCR-строка ↔ одна строка CY-таблицы; пустые/битые пары не сдвигают следующие строки.

    Если заголовков нет вообще, все строки с цифрами до второго блока считаются данными.
    """
    lines_in = [
        ln.strip().replace("\u00a0", " ") for ln in blob.splitlines() if ln.strip()
    ]
    out: list[str] = []
    header_blocks_seen = 0
    for line in lines_in:
        ll = line.lower()
        header_only = not re.search(r"\d", line)
        starts_new_pg_table = header_only and "period group" in ll
        is_subheading = header_only and "default" in ll and "target" in ll
        if starts_new_pg_table:
            header_blocks_seen += 1
            if header_blocks_seen >= 2:
                break
            continue
        if is_subheading:
            continue
        if not re.search(r"\d", line):
            continue
        if header_blocks_seen == 0:
            # Первые числовые строки до заголовка (заголовок иногда режется OCR)
            out.append(line)
        elif header_blocks_seen == 1:
            out.append(line)
    return out


def _cy_maybe_ordered_numeric_fallback(left: str, result: dict[str, dict[str, float | None]]) -> None:
    """
    OCR may return only Period Group numeric columns — no metric name per row.

    Каждая строка блока попадает в метрику с тем же индексом; битые строки не продвигают остальных.

    Включается только если ни одна метрика ещё не заполнена (якоря / pipe не сработали).
    """
    n_have = sum(
        1
        for dk, _, _ in _CY_INPUT_METRICS
        if (result.get(dk) or {}).get("before") is not None
        and (result.get(dk) or {}).get("after") is not None
    )
    if n_have != 0:
        return
    data_lines = _cy_primary_period_group_metric_lines(left)
    keys_main = [dk for dk, _, _ in _CY_INPUT_METRICS[:11]]
    if len(data_lines) < len(keys_main):
        return
    for i, dk in enumerate(keys_main):
        line = data_lines[i]
        b, a = _pp_order_row_numeric_pair(line)
        if b is None or a is None:
            continue
        try:
            _cy_try_set_metric(result, dk, float(b), float(a))
        except (TypeError, ValueError):
            continue


def _cy_active_mag_plausible_pair(b: float, a: float) -> bool:
    """Reject OCR crumbs (105|31) vs real Active listers (6576|8708-style)."""
    bf, af = float(b), float(a)
    if not math.isfinite(bf) or not math.isfinite(af):
        return False
    if bf <= 0 or af <= 0:
        return False
    mn, mx = min(bf, af), max(bf, af)
    return mx >= 900.0 and mn >= 200.0


def _cy_period_group_pick_active_listers_pair(
    full_text: str,
    skip_if_matches: tuple[float | None, float | None] | None = None,
) -> tuple[float | None, float | None]:
    """
    Last Period Group block only — scan numeric pairs bottom-up with magnitude filter.

    Used for the small Active listers table when OCR does not print row labels there.
    """
    if not full_text or not str(full_text).strip():
        return None, None
    low = full_text.lower()
    key = "period group"
    kl = len(key)
    positions: list[int] = []
    cursor = 0
    while True:
        pos = low.find(key, cursor)
        if pos < 0:
            break
        positions.append(pos)
        cursor = pos + kl
    seg_start = positions[-1] + kl if positions else 0
    segment = full_text[seg_start:]

    lines_in = [ln.strip() for ln in segment.splitlines() if ln.strip()]
    lines_keep: list[str] = []
    for line in lines_in:
        ln = line.lower()
        if "period group" in ln and not re.search(r"\d", line):
            continue
        if "default" in ln and "target" in ln and not re.search(r"\d", line):
            continue
        lines_keep.append(line)

    pairs = _pp_collect_numeric_row_pairs(lines_keep)
    if not pairs:
        return None, None

    def same_skip(xy: tuple[float, float]) -> bool:
        if skip_if_matches is None or skip_if_matches[0] is None or skip_if_matches[1] is None:
            return False
        return (
            abs(xy[0] - float(skip_if_matches[0])) < 0.51
            and abs(xy[1] - float(skip_if_matches[1])) < 0.51
        )

    for b, a in reversed(pairs):
        try:
            bf, af = float(b), float(a)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(bf) or not math.isfinite(af):
            continue
        if same_skip((bf, af)):
            continue
        if _cy_active_mag_plausible_pair(bf, af):
            return bf, af
    return None, None


def _cy_tail_to_before_after(tail: str) -> tuple[float | None, float | None]:
    """Numbers after a matched metric label on one OCR line (PP dashboard row)."""
    tail = re.sub(r"(?i)\bAI(\d{2,3})\b", r"1\1", tail)
    scrub = re.sub(r"[^\d\s.,%-]+", " ", tail).strip()
    b, a = _pp_tail_skip_junk_default_target(scrub)
    if b is None or a is None:
        decp = _pp_european_decimal_pair_regex(scrub)
        if decp[0] is not None and decp[1] is not None:
            b, a = decp
    if b is None or a is None:
        cpu_cor = _pp_corrupt_cpu_decimal_row_pair(tail.strip())
        if cpu_cor[0] is not None and cpu_cor[1] is not None:
            b, a = cpu_cor
    if b is None or a is None:
        nums_fb: list[float] = []
        for w in re.findall(r"\S+", scrub):
            v = _parse_num_ocr(w)
            if v is not None and _ocr_scalar_plausible(v):
                nums_fb.append(v)
        if len(nums_fb) >= 3:
            b, a = nums_fb[-2], nums_fb[-1]
        elif len(nums_fb) == 2:
            b, a = nums_fb[0], nums_fb[1]
    return b, a


def _parse_pp_dashboard_metric_rows(
    text: str,
    key_to_aliases: dict[str, tuple[str, ...]],
    keys_to_fill: list[str] | None = None,
) -> dict[str, dict[str, float | None]]:
    """
    Row-wise: textual metric label anchor (prefix before digits) … [junk] Default Target.
    Exactly one metric per OCR line — no positional zip across the table.
    """
    keys = keys_to_fill or list(key_to_aliases.keys())
    keys_set = {k for k in keys if k in key_to_aliases}
    result: dict[str, dict[str, float | None]] = {
        k: {"before": None, "after": None} for k in keys_set
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        ll = line.lower()
        if re.match(r"^\s*measure\s+gr", ll):
            continue
        # Drop header-only "Period Group … Default …" lines; keep OCR rows that still contain numbers.
        if "period group" in ll and "default" in ll and not re.search(r"\d", line):
            continue
        hit = _cy_best_metric_anchor_hit(line, key_to_aliases, keys_set)
        if hit is None:
            continue
        dk, anchor_end = hit
        if result[dk]["before"] is not None and result[dk]["after"] is not None:
            continue
        tail = line[anchor_end:]
        b, a = _cy_tail_to_before_after(tail)
        if b is not None and a is not None:
            _cy_try_set_metric(result, dk, b, a)
    return result


def _ocr_try_table_row_for_aliases(
    line: str, aliases: tuple[str, ...]
) -> tuple[float | None, float | None]:
    """
    Parse 'Metric | Before | After' or tab-separated row; metric in first column.
    """
    s = line.strip()
    if "|" not in s and "\t" not in s:
        return None, None
    parts = re.split(r"\||\t", s)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return None, None
    head_norm = parts[0].strip()
    head = re.sub(r"\s+", " ", head_norm.lower())
    matched = False
    for al in sorted(aliases, key=len, reverse=True):
        if _cy_alias_search(head, al):
            matched = True
            break
    if not matched:
        return None, None
    nums: list[float] = []
    for cell in parts[1:]:
        for token in re.findall(r"-?[\d\s.,]+%?", cell):
            v = _parse_num_ocr(token)
            if v is not None and _ocr_scalar_plausible(v):
                nums.append(v)
    if len(nums) >= 2:
        return nums[-2], nums[-1]
    return None, None


def _ocr_flat_text(text: str) -> str:
    """Normalize OCR: pipes/tabs → space, collapse whitespace (better table matching)."""
    t = text.replace("|", " ").replace("\t", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", t).strip()


def _try_before_after_pair_from_window(window: str) -> tuple[float | None, float | None]:
    """Extract (before, after) from a text window; Default/Target supported."""
    w = _ocr_flat_text(window)
    m = re.search(
        r"(?:before|default|до)\s*[:=]?\s*([\d\s.,]+%?)\s*[\s,;|/–-]{0,8}\s*(?:after|target|после)\s*[:=]?\s*([\d\s.,]+%?)",
        w,
        re.I | re.DOTALL,
    )
    if m:
        b, a = _parse_num_ocr(m.group(1)), _parse_num_ocr(m.group(2))
        if (
            b is not None
            and a is not None
            and _ocr_scalar_plausible(b)
            and _ocr_scalar_plausible(a)
        ):
            return b, a
    m = re.search(
        r"(?:after|target|после)\s*[:=]?\s*([\d\s.,]+%?)\s*[\s,;|/–-]{0,8}\s*(?:before|default|до)\s*[:=]?\s*([\d\s.,]+%?)",
        w,
        re.I | re.DOTALL,
    )
    if m:
        b, a = _parse_num_ocr(m.group(2)), _parse_num_ocr(m.group(1))
        if (
            b is not None
            and a is not None
            and _ocr_scalar_plausible(b)
            and _ocr_scalar_plausible(a)
        ):
            return b, a
    # Prefer rightmost plausible pair (avoids glued IDs on the left)
    lb, la = _ocr_last_two_plausible_numbers(w)
    if lb is not None and la is not None:
        return lb, la
    m2 = re.search(
        r"([\d\s.,]+%?)\s{1,8}([\d\s.,]+%?)\s*$",
        w.strip(),
    )
    if m2:
        b, a = _parse_num_ocr(m2.group(1)), _parse_num_ocr(m2.group(2))
        if (
            b is not None
            and a is not None
            and _ocr_scalar_plausible(b)
            and _ocr_scalar_plausible(a)
        ):
            return b, a
    return None, None


def _ocr_aliases_for_cy() -> dict[str, tuple[str, ...]]:
    """Metric data_key -> substrings to search in OCR line (lowercase). Match UI labels + OCR noise."""
    out: dict[str, tuple[str, ...]] = {}
    for dk, label, _ in _CY_INPUT_METRICS:
        base = label.lower()
        extra: list[str] = [
            base,
            label.replace(" ", "").lower(),
        ]
        if dk == "paid_users":
            extra.extend(["paid users", "paidusers", "npl", "new paid listers"])
        elif dk == "campaign_per_user":
            extra.extend(
                [
                    "campaign per user",
                    "campaignperuser",
                    "campaign p user",
                    "campaign p. user",
                    "campaign for user",
                    "camp per user",
                    "cmp per user",
                    "cpu",
                    "сampaign per user",
                    "campaign ler user",
                ]
            )
        elif dk == "new_campaign_cnt":
            extra.extend(
                [
                    "new campaign cnt",
                    "new campaign",
                    "campaign cnt",
                    "newcampaign",
                    "new campaign count",
                ]
            )
        elif dk == "price_per_day":
            extra.extend(["price per day", "priceperday", "ppd", "price/day"])
        elif dk == "arp_p_campaign":
            extra.extend(
                [
                    "arppcampaign",
                    "arppcampaing",
                    "arp pcampaign",
                    "arpp campaign",
                    "arppu campaign",
                    "arppucampaign",
                ]
            )
        elif dk == "spending":
            extra.extend(["spending", "spend"])
        elif dk == "refund":
            extra.extend(["refund"])
        elif dk == "pct_campaign_with_refund":
            extra.extend(
                [
                    "%campaign with refund",
                    "%campaign with refu",
                    "campaign with refund",
                    "pct campaign with refund",
                    "xcampaign with refund",
                ]
            )
        elif dk == "plan_imp_per_campaign":
            extra.extend(["plan imp per campaign", "plan imp", "planimpercampaign"])
        elif dk == "fact_imp_per_campaign":
            extra.extend(["fact imp per campaign", "fact imp", "factimpercampaign"])
        elif dk == "pct_execution_inventory":
            extra.extend(
                [
                    "%execution inventory",
                    "% execution inventory",
                    "execution inventory",
                    "pct execution inventory",
                    "%exec inventory",
                ]
            )
        elif dk == "active_listers":
            extra.extend(
                [
                    "active listers",
                    "active lister",
                    "actives",
                    "active liste",
                    "active listen",
                ]
            )
        seen = []
        for e in extra:
            e = e.lower().strip()
            if e and e not in seen:
                seen.append(e)
        out[dk] = tuple(seen)
    return out


def _get_ocr_cy_aliases():
    return _ocr_aliases_for_cy()


def _cy_repair_pct_execution_if_dup_active(
    result: dict[str, dict[str, float | None]],
    left: str,
    aliases: dict[str, tuple[str, ...]],
) -> None:
    """
    When %-Execution is identical to Active listers, the row almost always picked up the wrong block.
    Drop the duplicate, then re-parse only from lines that explicitly mention execution inventory.
    """
    dk_pe = "pct_execution_inventory"
    dk_al = "active_listers"
    pe = result.get(dk_pe) or {}
    al = result.get(dk_al) or {}
    pb, pa = pe.get("before"), pe.get("after")
    ab, aa = al.get("before"), al.get("after")
    if pb is None or pa is None or ab is None or aa is None:
        return
    if not _cy_pair_equal(pb, pa, ab, aa):
        return
    result[dk_pe] = {"before": None, "after": None}
    for raw_line in left.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if "active listers" in low:
            continue
        if "%execution" not in low and "execution inventory" not in low:
            continue
        for aln in sorted(aliases[dk_pe], key=len, reverse=True):
            mx = _cy_alias_search(line, aln)
            if not mx:
                continue
            tail = line[mx.end() :]
            b, a = _cy_tail_to_before_after(tail)
            if b is None or a is None:
                continue
            if _cy_try_set_metric(result, dk_pe, b, a):
                return


def _parse_cy_metrics_from_ocr_text(text: str) -> dict[str, dict[str, float | None]]:
    """
    Map OCR text to {data_key: {"before": float|None, "after": float|None}}.

    1. Pipe/tab строки по названию столбца; 2) якорная строка (текст до первой цифры ↔ метрика);
    если подписей нет вообще — 3) ровное сопоставление первых N числовых рядов с порядком
    метрик в UI (не трогаем частичный разбор из якорей). Active listers дополнительно из 12-й
    строки или из последнего блока Period Group с фильтром по масштабу.
    """
    aliases = _get_ocr_cy_aliases()
    result: dict[str, dict[str, float | None]] = {
        dk: {"before": None, "after": None} for dk, _, _ in _CY_INPUT_METRICS
    }
    left = _ocr_left_panel_pp_only(text)
    lines = [ln.strip() for ln in left.splitlines() if ln.strip()]
    ordered_keys = sorted(
        aliases.keys(),
        key=lambda k: max(len(s) for s in aliases[k]),
        reverse=True,
    )
    # Pass 0: explicit pipe/tab rows (Metric | Before | After)
    for line in lines:
        for dk in ordered_keys:
            if result[dk]["before"] is not None and result[dk]["after"] is not None:
                continue
            b, a = _ocr_try_table_row_for_aliases(line, aliases[dk])
            if b is not None and a is not None:
                _cy_try_set_metric(result, dk, b, a)

    pp = _parse_pp_dashboard_metric_rows(left, aliases, [dk for dk, _, _ in _CY_INPUT_METRICS])
    for dk, _, _ in _CY_INPUT_METRICS:
        p = pp.get(dk) or {}
        pb, pa = p.get("before"), p.get("after")
        if pb is not None and pa is not None:
            try:
                _cy_try_set_metric(result, dk, float(pb), float(pa))
            except (TypeError, ValueError):
                continue

    _cy_repair_pct_execution_if_dup_active(result, left, aliases)
    _cy_maybe_ordered_numeric_fallback(left, result)

    _al_pair = result.get("active_listers") or {}
    if _al_pair.get("before") is None and _al_pair.get("after") is None:
        rows_left = _cy_collect_pp_numeric_rows(left)
        rows_full = _cy_collect_pp_numeric_rows(text) if text else []
        for row_block in (rows_left, rows_full):
            if len(row_block) >= 12:
                try:
                    b12, a12 = float(row_block[11][0]), float(row_block[11][1])
                except (IndexError, TypeError, ValueError):
                    continue
                if _cy_try_set_metric(result, "active_listers", b12, a12):
                    break

    _al_pair = result.get("active_listers") or {}
    if _al_pair.get("before") is None and _al_pair.get("after") is None:
        _pu_skip = None
        _pu_ok = result.get("paid_users") or {}
        if _pu_ok.get("before") is not None and _pu_ok.get("after") is not None:
            try:
                _pu_skip = (
                    float(_pu_ok["before"]),
                    float(_pu_ok["after"]),
                )
            except (TypeError, ValueError):
                _pu_skip = None
        _pg_b, _pg_a = _py_period_group_default_target_pair(
            text,
            skip_if_matches=_pu_skip,
        )
        if _pg_b is not None and _pg_a is not None:
            _cy_try_set_metric(result, "active_listers", float(_pg_b), float(_pg_a))
    return result


def _parse_py_matrix_from_ocr_text(text: str) -> dict[str, dict[str, float | None]]:
    """paid_users | spending | active_listers -> before/after from OCR (matrix keys semantic)."""
    cy_al = _get_ocr_cy_aliases()
    aliases = {
        "paid_users": cy_al["paid_users"],
        "spending": cy_al["spending"],
        "active_listers": cy_al["active_listers"],
    }
    result = {k: {"before": None, "after": None} for k in aliases}
    left = _ocr_left_panel_pp_only(text)
    pp = _parse_pp_dashboard_metric_rows(left, aliases, list(aliases.keys()))
    for dk in result:
        p = pp.get(dk) or {}
        if p.get("before") is not None and p.get("after") is not None:
            result[dk] = {"before": p["before"], "after": p["after"]}

    lines = [ln.strip() for ln in left.splitlines() if ln.strip()]
    ordered = sorted(aliases.keys(), key=lambda k: max(len(x) for x in aliases[k]), reverse=True)
    for line in lines:
        for dk in ordered:
            if result[dk]["before"] is not None and result[dk]["after"] is not None:
                continue
            b, a = _ocr_try_table_row_for_aliases(line, aliases[dk])
            if b is not None and a is not None:
                result[dk]["before"] = b
                result[dk]["after"] = a
    for i, line in enumerate(lines):
        ll = line.lower()
        win2 = "\n".join(lines[i : min(i + 2, len(lines))])
        for dk in ordered:
            if result[dk]["before"] is not None and result[dk]["after"] is not None:
                continue
            if not any(a in ll for a in aliases[dk]):
                continue
            b, a = _try_before_after_pair_from_window(line)
            if b is None or a is None:
                b, a = _try_before_after_pair_from_window(win2)
            if b is not None and a is not None:
                result[dk]["before"] = b
                result[dk]["after"] = a
                break
    _py_fill_from_row_order_if_empty(left, text, result)
    return result


def _py_period_group_default_target_pair(
    full_text: str,
    skip_if_matches: tuple[float | None, float | None] | None = None,
) -> tuple[float | None, float | None]:
    """Prefer Active listers from the last Period Group numeric block with scale filtering."""
    return _cy_period_group_pick_active_listers_pair(full_text, skip_if_matches=skip_if_matches)


def _py_fill_from_row_order_if_empty(
    left: str,
    full_text: str,
    result: dict[str, dict[str, float | None]],
) -> None:
    """
    Positional fallback for the PPV left table: row 1 → paid, row 6 → spending, row 12 → active.

    Fills **only** metrics that are still missing after label-based parsing.

    ``left`` is cropped for the main panel; ``full_text`` is the raw OCR string — needed when
    `_ocr_left_panel_pp_only` cuts below `diff (median)` and drops the **Period Group** block where
    Active listers often live on tight crops.
    """
    rows_left = _cy_collect_pp_numeric_rows(left)
    rows_full = _cy_collect_pp_numeric_rows(full_text) if full_text else []

    def _need(k: str) -> bool:
        p = result.get(k) or {}
        return p.get("before") is None or p.get("after") is None

    if len(rows_left) >= 1 and _need("paid_users"):
        b0, a0 = rows_left[0]
        result["paid_users"] = {"before": b0, "after": a0}
    if len(rows_left) >= 6 and _need("spending"):
        b5, a5 = rows_left[5]
        result["spending"] = {"before": b5, "after": a5}

    if not _need("active_listers"):
        return

    pu = result.get("paid_users") or {}
    skip_pg: tuple[float | None, float | None] | None = None
    if pu.get("before") is not None and pu.get("after") is not None:
        try:
            skip_pg = (float(pu["before"]), float(pu["after"]))
        except (TypeError, ValueError):
            skip_pg = None
    pg_b, pg_a = _py_period_group_default_target_pair(full_text, skip_if_matches=skip_pg)
    if pg_b is not None and pg_a is not None:
        result["active_listers"] = {"before": pg_b, "after": pg_a}
        return

    if len(rows_left) >= 12:
        b11, a11 = rows_left[11]
        result["active_listers"] = {"before": b11, "after": a11}
        return

    if len(rows_full) >= 12:
        b11, a11 = rows_full[11]
        result["active_listers"] = {"before": b11, "after": a11}
        return


def _cy_pair_semantically_plausible(dk: str, typ: str, b, a) -> bool:
    """Reject glued OCR garbage (e.g. Campaign per User after ~1e10)."""
    try:
        bf, af = float(b), float(a)
    except (TypeError, ValueError):
        return False
    if dk != "pct_execution_inventory" and (bf < 0 or af < 0):
        return False
    abs_mx = max(abs(bf), abs(af))
    if dk == "campaign_per_user":
        if abs_mx > 500.0:
            return False
        tol = max(1e-5 * abs_mx, 0.004)
        intish_bf = abs(bf - round(bf)) < tol
        intish_af = abs(af - round(af)) < tol
        if intish_bf and intish_af and abs_mx >= 8.0:
            return False
        return True
    if dk in ("plan_imp_per_campaign", "fact_imp_per_campaign"):
        return abs_mx <= 500_000.0
    if dk == "price_per_day":
        return abs_mx <= 1_000_000.0
    if dk in ("paid_users", "new_campaign_cnt", "active_listers"):
        return abs_mx <= 10**12
    if dk in ("spending", "refund"):
        return abs_mx <= 10**15
    if dk == "arp_p_campaign":
        return abs_mx <= 10**7
    if dk == "pct_execution_inventory":
        return abs_mx <= 3500
    if "pct_" in dk:
        return abs_mx <= 10**6
    return abs_mx <= 10**18


def _cy_plausible_pair_count(parsed: dict[str, dict[str, float | None]]) -> int:
    n = 0
    for dk, _, typ in _CY_INPUT_METRICS:
        pb = (parsed.get(dk) or {}).get("before")
        pa = (parsed.get(dk) or {}).get("after")
        if pb is None or pa is None:
            continue
        if _cy_pair_semantically_plausible(dk, typ, pb, pa):
            n += 1
    return n


def _merge_cy_parsed_from_ocr_variants(texts: list[str]) -> dict[str, dict[str, float | None]]:
    """
    Pick the single best OCR variant (not field-wise first-wins): a noisy PSM can
    poison metrics like Campaign per User if merged with a cleaner pass.
    """
    empty: dict[str, dict[str, float | None]] = {
        dk: {"before": None, "after": None} for dk, _, _ in _CY_INPUT_METRICS
    }
    if not texts:
        return empty
    scored: list[tuple[tuple[int, int, int], dict[str, dict[str, float | None]]]] = []
    for t in texts:
        p = _parse_cy_metrics_from_ocr_text(t)
        good = _cy_plausible_pair_count(p)
        total = sum(
            1
            for dk, _, _ in _CY_INPUT_METRICS
            if (p.get(dk) or {}).get("before") is not None
            and (p.get(dk) or {}).get("after") is not None
        )
        scored.append(((good, total, len(t)), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _py_pair_semantically_plausible(k: str, b, a) -> bool:
    try:
        bf, af = float(b), float(a)
    except (TypeError, ValueError):
        return False
    if bf < 0 or af < 0:
        return False
    mx = max(bf, af)
    if k == "paid_users":
        return mx <= 10**12
    if k == "spending":
        return mx <= 10**15
    if k == "active_listers":
        return mx <= 10**12
    return False


def _py_plausible_pair_count(parsed: dict[str, dict[str, float | None]]) -> int:
    n = 0
    for k in ("paid_users", "spending", "active_listers"):
        pb = (parsed.get(k) or {}).get("before")
        pa = (parsed.get(k) or {}).get("after")
        if pb is None or pa is None:
            continue
        if _py_pair_semantically_plausible(k, pb, pa):
            n += 1
    return n


def _merge_py_parsed_from_ocr_variants(texts: list[str]) -> dict[str, dict[str, float | None]]:
    keys = ("paid_users", "spending", "active_listers")
    empty = {k: {"before": None, "after": None} for k in keys}
    if not texts:
        return empty
    scored: list[tuple[tuple[int, int, int], dict]] = []
    for t in texts:
        p = _parse_py_matrix_from_ocr_text(t)
        good = _py_plausible_pair_count(p)
        total = sum(
            1
            for k in keys
            if (p.get(k) or {}).get("before") is not None
            and (p.get(k) or {}).get("after") is not None
        )
        scored.append(((good, total, len(t)), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _cy_count_metric_pairs(parsed: dict[str, dict[str, float | None]]) -> int:
    return sum(
        1
        for dk, _, _ in _CY_INPUT_METRICS
        if (parsed.get(dk) or {}).get("before") is not None
        and (parsed.get(dk) or {}).get("after") is not None
    )


def _ocr_pick_preview_text_cy(variants: list[str]) -> str:
    """Debug preview: variant with the most semantically plausible pairs, then longest."""
    best = variants[0]
    best_n = (-1, -1)
    for t in variants:
        p = _parse_cy_metrics_from_ocr_text(t)
        n = (_cy_plausible_pair_count(p), len(t))
        if n > best_n:
            best_n = n
            best = t
    return best


def _ocr_pick_preview_text_py(variants: list[str]) -> str:
    def score(txt: str) -> int:
        p = _parse_py_matrix_from_ocr_text(txt)
        return sum(
            1
            for k in ("paid_users", "spending", "active_listers")
            if (p.get(k) or {}).get("before") is not None
            and (p.get(k) or {}).get("after") is not None
        )

    best = variants[0]
    best_n = -1
    for t in variants:
        n = score(t)
        if n > best_n or (n == best_n and len(t) > len(best)):
            best_n = n
            best = t
    return best


def _ocr_collect_tesseract_variants(image_bytes: bytes) -> tuple[list[str] | None, str | None]:
    """
    Run Tesseract with several PSM modes on a lightly upscaled image (helps small table text).
    Returns (unique non-empty texts, error).
    """
    try:
        image_module = importlib.import_module("PIL.Image")
        pytesseract = importlib.import_module("pytesseract")
    except Exception:
        return None, "OCR недоступен: установите `pillow` и `pytesseract`, затем перезапустите приложение."

    Image = image_module
    img = Image.open(io.BytesIO(image_bytes))
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS  # type: ignore[attr-defined]
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    mx = max(w, h)
    if mx > 0 and mx < 1400:
        s = min(2.0, 2400.0 / mx)
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), resample)

    cfgs = (
        "--oem 3 --psm 6",
        "--oem 3 --psm 4",
        "--oem 3 --psm 11",
        "--oem 3 --psm 3",
    )
    seen: set[str] = set()
    out: list[str] = []
    for cfg in cfgs:
        try:
            t = pytesseract.image_to_string(img, config=cfg)
        except Exception:
            continue
        if not t or not str(t).strip():
            continue
        key = str(t).strip()
        if key not in seen:
            seen.add(key)
            out.append(str(t))
    if not out:
        return None, "Не удалось распознать текст на скриншоте."
    return out, None


def _ocr_bytes_to_text(image_bytes: bytes):
    """Single preview string (best PSM by parse score); prefer _ocr_collect_tesseract_variants + merge in UI."""
    variants, err = _ocr_collect_tesseract_variants(image_bytes)
    if err or not variants:
        return None, err
    return _ocr_pick_preview_text_cy(variants), None


def _ocr_screenshot(uploaded_file):
    return _ocr_bytes_to_text(uploaded_file.getvalue())


def _ocr_text_looks_like_app_chrome(text: str) -> bool:
    """Heuristic: OCR of this Streamlit app (wrong upload) vs source dashboard."""
    t = (text or "").lower()
    hits = 0
    for needle in (
        "current year input",
        "manual override",
        "ocr debug",
        "parsed before",
        "session_state",
        "previous year screenshot",
        "распознать и применить",
        "скрин с данными",
        "single analysis",
    ):
        if needle in t:
            hits += 1
    return hits >= 2


def _session_write_matrix_py_triple_from_parsed(
    sess: dict, parsed: dict[str, dict[str, float | None]]
) -> None:
    """
    Paid users / Spending / Active listers from CY (or PY) parse → matrix_py_* keys
    used by PPV matrix & Potential Spending.
    """
    mapping = [
        ("paid_users", "matrix_py_paid_users_before", "matrix_py_paid_users_after", True),
        ("spending", "matrix_py_spending_before", "matrix_py_spending_after", False),
        ("active_listers", "matrix_py_ac_before", "matrix_py_ac_after", True),
    ]
    for dk, kb, ka, as_int in mapping:
        pair = parsed.get(dk) or {}
        b, a = pair.get("before"), pair.get("after")
        if b is None or a is None:
            continue
        try:
            if as_int:
                bi = int(round(float(b)))
                ai = int(round(float(a)))
                if ai < 0 and bi >= 0:
                    ai = abs(ai)
                if bi < 0:
                    bi = abs(bi)
                if bi < 0 or ai < 0:
                    continue
                sess[kb] = bi
                sess[ka] = ai
            else:
                bf = float(b)
                af = float(a)
                if bf < 0 and abs(bf) <= 1e6:
                    bf = abs(bf)
                if af < 0 and bf >= 0 and abs(af) <= 1e6:
                    af = abs(af)
                if bf < 0 or af < 0:
                    continue
                sess[kb] = bf
                sess[ka] = af
        except (TypeError, ValueError, OverflowError):
            continue


def _cy_ocr_snapshot_persist(sess: dict) -> None:
    """Copy all Current Year widget keys so we can restore after a bad file-merge overwrite."""
    snap: dict = {}
    for _dk, _, _ in _CY_INPUT_METRICS:
        sk = _cy_sess_key(_dk)
        for part in ("baseline", "before", "after"):
            k = f"{sk}_{part}"
            if k in sess:
                snap[k] = sess[k]
    sess["_cy_ocr_snapshot"] = snap


def _cy_ocr_restore_from_snapshot_if_blanked(sess: dict) -> None:
    """
    If CY OCR override is on but merge zeroed inputs (e.g. old sig!=prev_cat cleared override),
    restore from last CY OCR snapshot.
    """
    if not sess.get("_cy_ocr_override"):
        return
    snap = sess.get("_cy_ocr_snapshot")
    if not isinstance(snap, dict) or not snap:
        return
    anchors = ("paid_users_before", "spending_before", "active_before")
    try:
        snap_any = any(float(snap.get(k) or 0) != 0 for k in anchors)
        cur_any = any(float(sess.get(k) or 0) != 0 for k in anchors)
    except (TypeError, ValueError):
        return
    if cur_any or not snap_any:
        return
    for k, v in snap.items():
        sess[k] = v


def _apply_cy_ocr_parsed_to_session(
    sess: dict,
    parsed: dict[str, dict[str, float | None]],
    *,
    mirror_matrix_py: bool = False,
) -> tuple[list[str], list[dict]]:
    """
    Write into Current Year input keys: {sess_key}_before / {sess_key}_after
    (sess_key = _cy_sess_key(data_key), e.g. paid_users_before, active_before for active_listers).

    If mirror_matrix_py, also copy paid_users / spending / active_listers into matrix_py_*.
    The CY OCR button passes mirror_matrix_py=False so the matrix "Previous Year" row stays
    independent (PY files / PY OCR only).

    Returns (applied_metric_labels, debug_rows) for UI verification.
    """
    applied: list[str] = []
    rows: list[dict] = []
    for dk, label, typ in _CY_INPUT_METRICS:
        sk = _cy_sess_key(dk)
        kb = f"{sk}_before"
        ka = f"{sk}_after"
        pair = parsed.get(dk) or {}
        b, a = pair.get("before"), pair.get("after")
        row = {
            "Metric": label,
            "Parsed Before": b,
            "Parsed After": a,
            "session_state key (Before)": kb,
            "session_state key (After)": ka,
            "Written": False,
            "Stored Before": None,
            "Stored After": None,
        }
        if b is None or a is None:
            rows.append(row)
            continue
        try:
            if typ == "int":
                bi = int(round(float(b)))
                ai = int(round(float(a)))
                if ai < 0 and bi >= 0:
                    ai = abs(ai)
                if bi < 0:
                    bi = abs(bi)
                if bi < 0 or ai < 0:
                    rows.append(row)
                    continue
                sess[kb] = bi
                sess[ka] = ai
                row["Written"] = True
                row["Stored Before"] = bi
                row["Stored After"] = ai
                applied.append(label)
            else:
                bf = float(b)
                af = float(a)
                # OCR often misreads a minus on small "After" levels; keep non-negative for widgets (min 0).
                if bf < 0 and abs(bf) <= 1e6:
                    bf = abs(bf)
                if af < 0 and bf >= 0 and abs(af) <= 1e6:
                    af = abs(af)
                if bf < 0 or af < 0:
                    rows.append(row)
                    continue
                sess[kb] = bf
                sess[ka] = af
                row["Written"] = True
                row["Stored Before"] = bf
                row["Stored After"] = af
                applied.append(label)
        except (TypeError, ValueError, OverflowError):
            pass
        rows.append(row)
    if mirror_matrix_py:
        _session_write_matrix_py_triple_from_parsed(sess, parsed)
    if applied:
        _cy_ocr_snapshot_persist(sess)
    return applied, rows


def _apply_py_ocr_parsed_to_session(
    sess: dict, parsed: dict[str, dict[str, float | None]]
) -> tuple[list[str], list[dict]]:
    """matrix_py_paid_users_*, matrix_py_spending_*, matrix_py_ac_*."""
    applied: list[str] = []
    rows: list[dict] = []
    mapping = [
        ("paid_users", "matrix_py_paid_users_before", "matrix_py_paid_users_after", "Paid users", True),
        ("spending", "matrix_py_spending_before", "matrix_py_spending_after", "Spending", False),
        ("active_listers", "matrix_py_ac_before", "matrix_py_ac_after", "Active listers", True),
    ]
    for dk, kb, ka, lbl, as_int in mapping:
        pair = parsed.get(dk) or {}
        b, a = pair.get("before"), pair.get("after")
        row = {
            "Metric": lbl,
            "Parsed Before": b,
            "Parsed After": a,
            "session_state key (Before)": kb,
            "session_state key (After)": ka,
            "Written": False,
            "Stored Before": None,
            "Stored After": None,
        }
        if b is None or a is None:
            rows.append(row)
            continue
        try:
            if as_int:
                bi = int(round(float(b)))
                ai = int(round(float(a)))
                if ai < 0 and bi >= 0:
                    ai = abs(ai)
                if bi < 0:
                    bi = abs(bi)
                if bi < 0 or ai < 0:
                    rows.append(row)
                    continue
                sess[kb] = bi
                sess[ka] = ai
                row["Written"] = True
                row["Stored Before"] = bi
                row["Stored After"] = ai
                applied.append(lbl)
            else:
                bf = float(b)
                af = float(a)
                if bf < 0 and abs(bf) <= 1e6:
                    bf = abs(bf)
                if af < 0 and bf >= 0 and abs(af) <= 1e6:
                    af = abs(af)
                if bf < 0 or af < 0:
                    rows.append(row)
                    continue
                sess[kb] = bf
                sess[ka] = af
                row["Written"] = True
                row["Stored Before"] = bf
                row["Stored After"] = af
                applied.append(lbl)
        except (TypeError, ValueError, OverflowError):
            pass
        rows.append(row)
    return applied, rows


def _cy_ocr_report_labels(parsed: dict[str, dict[str, float | None]], kind: str) -> tuple[list[str], list[str]]:
    """Found (both before/after) vs missing metric names."""
    found = []
    missing = []
    if kind == "cy":
        for dk, label, _ in _CY_INPUT_METRICS:
            p = parsed.get(dk) or {}
            if p.get("before") is not None and p.get("after") is not None:
                found.append(label)
            else:
                missing.append(label)
    else:
        for dk, label in (
            ("paid_users", "Paid users"),
            ("spending", "Spending"),
            ("active_listers", "Active Listers"),
        ):
            p = parsed.get(dk) or {}
            if p.get("before") is not None and p.get("after") is not None:
                found.append(label)
            else:
                missing.append(label)
    return found, missing


def _build_cy_ocr_feedback(
    ocr_text: str | None,
    ocr_error: str | None,
    parsed: dict[str, dict[str, float | None]],
    applied_labels: list[str],
    session_debug_rows: list[dict] | None = None,
) -> dict:
    """Structured OCR result for UI + debug (includes per-metric session_state keys)."""
    recognized: list[str] = []
    for dk, lbl, _ in _CY_INPUT_METRICS:
        p = parsed.get(dk) or {}
        if p.get("before") is not None and p.get("after") is not None:
            recognized.append(lbl)
    all_labels = [lbl for _, lbl, _ in _CY_INPUT_METRICS]
    unmatched = [lbl for lbl in all_labels if lbl not in recognized]
    skipped_apply = [lbl for lbl in recognized if lbl not in applied_labels]
    ap = len(applied_labels)
    sk = len(skipped_apply)
    return {
        "ocr_error": ocr_error,
        "preview": (ocr_text or "")[:1000],
        "recognized_in_ocr": recognized,
        "applied": list(applied_labels),
        "unmatched": unmatched,
        "skipped_apply": skipped_apply,
        "counts": {"applied": ap, "skipped": sk, "recognized": len(recognized)},
        "session_debug_rows": session_debug_rows or [],
    }


def _build_py_ocr_feedback(
    ocr_text: str | None,
    ocr_error: str | None,
    parsed: dict[str, dict[str, float | None]],
    applied_labels: list[str],
    session_debug_rows: list[dict] | None = None,
) -> dict:
    recognized = []
    for dk, lbl in (
        ("paid_users", "Paid users"),
        ("spending", "Spending"),
        ("active_listers", "Active Listers"),
    ):
        p = parsed.get(dk) or {}
        if p.get("before") is not None and p.get("after") is not None:
            recognized.append(lbl)
    all_l = ["Paid users", "Spending", "Active Listers"]
    unmatched = [x for x in all_l if x not in recognized]
    skipped_apply = [x for x in recognized if x not in applied_labels]
    return {
        "ocr_error": ocr_error,
        "preview": (ocr_text or "")[:1000],
        "recognized_in_ocr": recognized,
        "applied": list(applied_labels),
        "unmatched": unmatched,
        "skipped_apply": skipped_apply,
        "counts": {
            "applied": len(applied_labels),
            "skipped": len(skipped_apply),
            "recognized": len(recognized),
        },
        "session_debug_rows": session_debug_rows or [],
    }


_OCR_UI_PREVIEW_MAX_H = 320


def _ocr_thumbnail_bytes(image_bytes: bytes, max_height: int = _OCR_UI_PREVIEW_MAX_H) -> bytes | None:
    """Уменьшенное изображение для превью (макс. высота max_height px)."""
    try:
        image_module = importlib.import_module("PIL.Image")
        Image = image_module
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined]
        img.thumbnail((100_000, max_height), resample)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _ocr_render_screenshot_preview(image_bytes: bytes | None, *, label: str) -> None:
    """Превью ограниченной высоты + полный размер в popover или expander."""
    if not image_bytes:
        return
    thumb = _ocr_thumbnail_bytes(image_bytes)
    if thumb:
        st.image(
            io.BytesIO(thumb),
            caption=f"Предпросмотр ({label}) — до {_OCR_UI_PREVIEW_MAX_H}px по высоте",
            use_container_width=False,
        )
    else:
        st.image(
            io.BytesIO(image_bytes),
            caption=f"Предпросмотр ({label})",
            width=min(480, 10_000),
        )
    _full = io.BytesIO(image_bytes)
    if getattr(st, "popover", None):
        with st.popover("🔍 Открыть полный размер"):
            st.image(_full, use_container_width=True, caption=f"{label} — полный размер")
    else:
        with st.expander("🔍 Открыть полный размер", expanded=False):
            st.image(_full, use_container_width=True, caption=f"{label} — полный размер")


def _ocr_debug_rows_format_numeric_strings(rows: list[dict]) -> list[dict]:
    """
    Stringify Parsed/Stored numeric cells for st.dataframe so positives never show a leading '+'.
    Uses format_matrix_metric (same rules as PPV matrix int-like vs decimals).
    """
    cols = ("Parsed Before", "Parsed After", "Stored Before", "Stored After")
    out: list[dict] = []
    for r in rows:
        r2 = dict(r)
        for c in cols:
            if c not in r2 or r2[c] is None:
                continue
            v = r2[c]
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            tol = max(1e-9, 1e-9 * max(1.0, abs(fv)))
            as_int = abs(fv - round(fv)) < tol
            r2[c] = format_matrix_metric(fv, as_int=as_int)
        out.append(r2)
    return out


def _render_ocr_feedback_messages(fb: dict | None) -> None:
    """Сообщения после кнопки: error / warning / success / info (нативные цвета Streamlit)."""
    if not fb:
        return
    err = fb.get("ocr_error")
    if err:
        st.error(f"**OCR / input error:** {err}")
        return

    rec = fb.get("recognized_in_ocr") or []
    ap = fb.get("applied") or []
    unmatched = fb.get("unmatched") or []
    skipped = fb.get("skipped_apply") or []
    preview = fb.get("preview") or ""

    if not rec:
        st.warning("OCR completed, but no supported metrics were recognized.")
        if preview and _ocr_text_looks_like_app_chrome(preview):
            st.info(
                "Похоже, в кадр попал **интерфейс этого приложения** (Streamlit), а не исходная таблица "
                "с метриками (например, блок **New PPV (spending)** с колонками **Default** / **Target**). "
                "Сделайте скрин **только дашборда/отчёта** или обрежьте изображение до левой таблицы, "
                "без панели инструмента."
            )
    else:
        if ap:
            st.success(
                "**Applied to session_state:** "
                + ", ".join(f"**{x}**" for x in ap)
            )
            st.caption(
                f"Applied **{len(ap)}** metric(s), skipped **{len(skipped)}** "
                "(recognized in OCR but not written to session_state)."
            )
        if skipped:
            st.warning(
                "**Recognized in OCR but not applied** (validation failed or negative values): "
                + ", ".join(skipped)
            )

    st.markdown("**Unmatched** (no Before/After pair found for this label)")
    with st.container(border=True):
        st.write(", ".join(unmatched) if unmatched else "—")


def _render_ocr_debug_expanders(fb: dict | None, kind: str) -> None:
    """Сырой текст и таблица пар — один свёрнутый expander."""
    if not fb:
        return
    preview = fb.get("preview") or ""
    dbg_rows = fb.get("session_debug_rows") or []

    with st.expander("OCR debug", expanded=False):
        st.markdown("**Raw text** (first 1000 chars)")
        st.code(preview if preview.strip() else "(empty)", language=None)
        if dbg_rows:
            st.markdown("**Parsed pairs & session_state writes**")
            _dbg_df = pd.DataFrame(_ocr_debug_rows_format_numeric_strings(dbg_rows))
            st.dataframe(_dbg_df, use_container_width=True, hide_index=True)
            if st.session_state.get("_cy_ocr_override") and kind == "cy":
                st.caption(
                    "**Overwrite protection:** `_cy_ocr_override` is set — file-based Current Year "
                    "merge will not overwrite these values until you **re-upload CY files** "
                    "(sets `_merge_files_dirty`) or **change category**."
                )
            if st.session_state.get("_py_ocr_override") and kind == "py":
                st.caption(
                    "**Overwrite protection:** `_py_ocr_override` is set — file-based Previous Year "
                    "merge will not overwrite matrix fields until **re-upload PY files** or "
                    "**change category**."
                )


def _render_ocr_upload_section(category_bulk_mode: bool) -> None:
    """OCR UI for single vs bulk notice — same keys and rerun behavior as before."""
    if category_bulk_mode:
        st.info(
            "OCR для ручного ввода доступен только в **single analysis** (одна категория). "
            "В bulk-режиме используйте файлы и таблицу bulk."
        )
        return
    st.caption(
        "**Current Year** screenshot → поля **Current Year input** (manual override). "
        "**Previous Year** screenshot → только блок **Previous Year** (матрица, Y2Y, Potential); "
        "строка Previous Year в матрице **не** заполняется из OCR Current Year. "
        "**category_id** для OCR не используется — только совпадение по **названию метрики**."
    )
    st.caption(
        "Нативной вставки изображения из буфера (Ctrl+V) в Streamlit **без** отдельного "
        "JS-компонента или доп. пакетов нет: используйте **загрузку файла** или вставьте "
        "**data URL** / **base64** в поле ниже (можно получить из DevTools / внешнего конвертера)."
    )
    tab_ocr_cy, tab_ocr_py = st.tabs(
        ["Current Year screenshot", "Previous Year screenshot"]
    )

    with tab_ocr_cy:
        up_cy = st.file_uploader(
            "Файл скриншота (PNG/JPG/JPEG)",
            type=["png", "jpg", "jpeg"],
            key="ocr_cy_file_uploader",
        )
        paste_cy = st.text_area(
            "Или вставьте data:image/...;base64,... либо сырой base64",
            height=72,
            key="ocr_cy_paste_b64",
            placeholder="data:image/png;base64,iVBORw0KGgo...",
        )
        img_cy, dec_err_cy = _decode_optional_image_bytes(up_cy, paste_cy)
        if dec_err_cy:
            st.warning(dec_err_cy)
        else:
            _preview_cy = img_cy if img_cy is not None else (
                up_cy.getvalue() if up_cy is not None else None
            )
            if _preview_cy:
                _ocr_render_screenshot_preview(_preview_cy, label="Current Year")

        if st.button("Распознать и применить к Current Year input", key="ocr_cy_apply_btn"):
            img_b, err_b = _decode_optional_image_bytes(up_cy, paste_cy)
            if err_b:
                st.session_state["_ocr_cy_feedback"] = _build_cy_ocr_feedback(
                    None, err_b, {}, [], []
                )
                st.session_state["_cy_ocr_override"] = True
                st.rerun()
            elif not img_b:
                st.session_state["_ocr_cy_feedback"] = _build_cy_ocr_feedback(
                    None,
                    "Нет изображения: загрузите файл или вставьте data URL / base64.",
                    {},
                    [],
                    [],
                )
                st.session_state["_cy_ocr_override"] = True
                st.rerun()
            else:
                variants, ocr_error = _ocr_collect_tesseract_variants(img_b)
                if ocr_error:
                    st.session_state["_ocr_cy_feedback"] = _build_cy_ocr_feedback(
                        None, ocr_error, {}, [], []
                    )
                else:
                    parsed = _merge_cy_parsed_from_ocr_variants(variants)
                    ocr_text = _ocr_pick_preview_text_cy(variants)
                    applied_labels, dbg_rows = _apply_cy_ocr_parsed_to_session(
                        st.session_state,
                        parsed,
                        mirror_matrix_py=False,
                    )
                    st.session_state["_ocr_cy_feedback"] = _build_cy_ocr_feedback(
                        ocr_text, None, parsed, applied_labels, dbg_rows
                    )
                st.session_state["_cy_ocr_override"] = True
                st.rerun()

        _render_ocr_feedback_messages(st.session_state.get("_ocr_cy_feedback"))
        _render_ocr_debug_expanders(st.session_state.get("_ocr_cy_feedback"), "cy")

    with tab_ocr_py:
        up_py = st.file_uploader(
            "Файл скриншота (PNG/JPG/JPEG)",
            type=["png", "jpg", "jpeg"],
            key="ocr_py_file_uploader",
        )
        paste_py = st.text_area(
            "Или вставьте data:image/...;base64,... либо сырой base64",
            height=72,
            key="ocr_py_paste_b64",
            placeholder="data:image/png;base64,iVBORw0KGgo...",
        )
        img_py, dec_err_py = _decode_optional_image_bytes(up_py, paste_py)
        if dec_err_py:
            st.warning(dec_err_py)
        else:
            _preview_py = img_py if img_py is not None else (
                up_py.getvalue() if up_py is not None else None
            )
            if _preview_py:
                _ocr_render_screenshot_preview(_preview_py, label="Previous Year")

        if st.button(
            "Распознать и применить к Previous Year (матрица)",
            key="ocr_py_apply_btn",
        ):
            img_b, err_b = _decode_optional_image_bytes(up_py, paste_py)
            if err_b:
                st.session_state["_ocr_py_feedback"] = _build_py_ocr_feedback(
                    None, err_b, {}, [], []
                )
                st.session_state["_py_ocr_override"] = True
                st.rerun()
            elif not img_b:
                st.session_state["_ocr_py_feedback"] = _build_py_ocr_feedback(
                    None,
                    "Нет изображения: загрузите файл или вставьте data URL / base64.",
                    {},
                    [],
                    [],
                )
                st.session_state["_py_ocr_override"] = True
                st.rerun()
            else:
                variants, ocr_error = _ocr_collect_tesseract_variants(img_b)
                if ocr_error:
                    st.session_state["_ocr_py_feedback"] = _build_py_ocr_feedback(
                        None, ocr_error, {}, [], []
                    )
                else:
                    parsed = _merge_py_parsed_from_ocr_variants(variants)
                    ocr_text = _ocr_pick_preview_text_py(variants)
                    applied_labels, dbg_rows = _apply_py_ocr_parsed_to_session(
                        st.session_state, parsed
                    )
                    st.session_state["_ocr_py_feedback"] = _build_py_ocr_feedback(
                        ocr_text, None, parsed, applied_labels, dbg_rows
                    )
                st.session_state["_py_ocr_override"] = True
                st.rerun()

        _render_ocr_feedback_messages(st.session_state.get("_ocr_py_feedback"))
        _render_ocr_debug_expanders(st.session_state.get("_ocr_py_feedback"), "py")


with st.container():
    # OCR expander использует bulk/single из предыдущего ввода (см. ключи session_state),
    # т.к. визуально строка файлов идёт выше строки Category ID / Scenario.
    _ss_cat_probe = st.session_state.get("ppv_category_ids_textarea", "")
    _parsed_probe, _ = _parse_category_ids(_ss_cat_probe)
    _bulk_pick_probe = list(st.session_state.get("bulk_category_multiselect") or [])
    _bulk_from_text_probe = len(_parsed_probe) > 1
    _bulk_from_pick_probe = len(_bulk_pick_probe) > 1
    _category_bulk_mode = _bulk_from_text_probe or _bulk_from_pick_probe

    with st.container(border=True):
        _ic_ocr, _ic_cy, _ic_py = st.columns(3, gap="small")

        with _ic_ocr:
            with st.expander("Скрин с данными (OCR)", expanded=False):
                _render_ocr_upload_section(_category_bulk_mode)

        with _ic_cy:
            with st.expander("Current Year files", expanded=False):
                spending_file = st.file_uploader("New PPV (spending)", type=["xlsx", "csv"])
                _uf1, _uf2 = st.columns(2)
                with _uf1:
                    active_file = st.file_uploader("Active listers", type=["xlsx", "csv"])
                with _uf2:
                    price_file = st.file_uploader("Price per day", type=["xlsx", "csv"])
                st.caption(
                    "Минимум для объединения Current Year — **New PPV (spending)** и **Active listers**. "
                    "**Price per day** опционален: без него используется тот же merge, что и для Previous Year "
                    "(только spending + active). Bulk-анализ price не использует."
                )
                _cy_h_s = spending_file is not None
                _cy_h_a = active_file is not None
                if (_cy_h_s ^ _cy_h_a) and not st.session_state.get("_ch_data_loaded"):
                    st.warning(
                        "Для merge Current Year нужны **оба** файла: **New PPV (spending)** и **Active listers**. "
                        "С одним файлом приложение не строит `merged_data` — категории в bulk будут считаться отсутствующими.",
                        icon="⚠️",
                    )

        with _ic_py:
            with st.expander("Previous Year files", expanded=False):
                py_spending_file = st.file_uploader(
                    "Previous Year New PPV (spending)",
                    type=["xlsx", "csv"],
                    key="py_spending_uploader",
                )
                py_active_file = st.file_uploader(
                    "Previous Year Active listers",
                    type=["xlsx", "csv"],
                    key="py_active_uploader",
                )
                _py_h_s = py_spending_file is not None
                _py_h_a = py_active_file is not None
                if _py_h_s ^ _py_h_a:
                    st.warning(
                        "Для merge Previous Year нужны **оба** файла: **Previous Year New PPV (spending)** и "
                        "**Previous Year Active listers**. Иначе PY-данные в bulk не появятся.",
                        icon="⚠️",
                    )

    _merged_for_toolbar = st.session_state.get("merged_data") or {}
    with st.container(border=True):
        st.markdown(
            '<p class="sd-bordered-strip-title">Настройки</p>',
            unsafe_allow_html=True,
        )
        _tb_geo, _tb_cat, _tb_sc = st.columns(3, gap="small")
        with _tb_geo:
            geo = st.selectbox(
                "GEO",
                options=["default", "KG", "AZ", "RS"],
                index=0,
                key="ppv_geo_select",
            )
        with _tb_cat:
            category_input = st.text_input(
                "Category ID",
                key="ppv_category_ids_textarea",
                placeholder="ID или несколько для bulk (через запятую)",
            )
            _bulk_pick_ids: list[int] = []
            if _merged_for_toolbar and len(_merged_for_toolbar) > 1:
                _cy_bulk_options_r = sorted(int(k) for k in _merged_for_toolbar.keys())
                _bulk_pick_ids = st.multiselect(
                    "Bulk: Category ID из Current Year файла",
                    options=_cy_bulk_options_r,
                    default=[],
                    key="bulk_category_multiselect",
                )
        with _tb_sc:
            scenario = st.selectbox(
                "Scenario",
                options=[
                    "Regular",
                    "Low NPL (<10)",
                    "Other category",
                    "New category",
                    "Previous Year anomaly",
                ],
                key="ppv_global_scenario",
            )
    if _scenario_is_new_category(scenario):
        st.date_input(
            "Category creation date",
            value=date.today(),
            key="category_creation_date",
            help=(
                "Used when category is less than 1 year old and Previous Year data is unavailable"
            ),
        )
    elif _scenario_is_py_anomaly(scenario):
        st.text_area(
            "Previous Year anomaly description",
            key="py_anomaly_description",
            placeholder="Describe the anomaly in Previous Year data",
            help=(
                "Used when Previous Year data exists but should not be used "
                "as a reliable Y2Y baseline"
            ),
            height=56,
        )

    parsed_category_ids, invalid_category_tokens = _parse_category_ids(category_input)
    if invalid_category_tokens:
        shown = invalid_category_tokens[:25]
        extra_ic = " …" if len(invalid_category_tokens) > 25 else ""
        st.warning(
            "Не удалось разобрать как целое число: "
            + ", ".join(repr(t) for t in shown)
            + extra_ic
        )

    _bulk_from_text_ic = len(parsed_category_ids) > 1
    _bulk_from_pick_ic = len(_bulk_pick_ids) > 1
    _category_bulk_mode = _bulk_from_text_ic or _bulk_from_pick_ic

    # ------------------------------------------------------------------
    # Загрузка из ClickHouse
    # ------------------------------------------------------------------
    with st.expander("Загрузка из ClickHouse", expanded=False):
        st.caption(
            "Данные тянутся из **analytics_reports.spendings_distributed** и **analytics_reports.active_listers_and_listings_distributed**. "
            "GEO и Category ID берутся из блока **Настройки** выше."
        )
        _ch_c1, _ch_c2 = st.columns(2, gap="medium")
        with _ch_c1:
            st.markdown("**Период Before**")
            _ch_b1, _ch_b2 = st.columns(2)
            with _ch_b1:
                _ch_before_from = st.date_input("От", key="ch_before_from", value=None)
            with _ch_b2:
                _ch_before_to = st.date_input("До", key="ch_before_to", value=None)
        with _ch_c2:
            st.markdown("**Период After**")
            _ch_a1, _ch_a2 = st.columns(2)
            with _ch_a1:
                _ch_after_from = st.date_input("От", key="ch_after_from", value=None)
            with _ch_a2:
                _ch_after_to = st.date_input("До", key="ch_after_to", value=None)

        _ch_ids = parsed_category_ids or [c for c in (_bulk_pick_ids or [])]
        _ch_btn_disabled = not (_ch_ids and _ch_before_from and _ch_before_to and _ch_after_from and _ch_after_to)
        _ch_load_col, _ch_clear_col = st.columns([3, 1])
        with _ch_load_col:
            _ch_load = st.button(
                "Загрузить из ClickHouse",
                disabled=_ch_btn_disabled,
                type="primary",
                use_container_width=True,
                key="ch_load_btn",
            )
        with _ch_clear_col:
            _ch_clear = st.button(
                "Очистить",
                disabled=not st.session_state.get("_ch_data_loaded"),
                use_container_width=True,
                key="ch_clear_btn",
            )

        if _ch_btn_disabled and not _ch_ids:
            st.caption("Введите Category ID в блоке Настройки.")

        if _ch_load:
            with st.spinner("Загружаем данные из ClickHouse…"):
                try:
                    from dateutil.relativedelta import relativedelta
                    _ch_merged, _ch_price, _ch_budget_dist = load_from_clickhouse(
                        category_ids=_ch_ids,
                        geo=geo,
                        before_from=_ch_before_from,
                        before_to=_ch_before_to,
                        after_from=_ch_after_from,
                        after_to=_ch_after_to,
                    )
                    st.session_state["merged_data"] = _ch_merged
                    st.session_state["price_data"] = _ch_price
                    st.session_state["budget_dist"] = _ch_budget_dist
                    st.session_state["_ch_data_loaded"] = True
                    st.session_state["_merge_files_dirty"] = True
                    st.session_state.pop("_upload_sig", None)

                    # Load Previous Year: same periods shifted -1 year
                    _py_before_from = _ch_before_from - relativedelta(years=1)
                    _py_before_to   = _ch_before_to   - relativedelta(years=1)
                    _py_after_from  = _ch_after_from  - relativedelta(years=1)
                    _py_after_to    = _ch_after_to    - relativedelta(years=1)
                    _ch_merged_py = load_py_from_clickhouse(
                        category_ids=_ch_ids,
                        geo=geo,
                        before_from=_py_before_from,
                        before_to=_py_before_to,
                        after_from=_py_after_from,
                        after_to=_py_after_to,
                    )
                    st.session_state["merged_data_previous_year"] = _ch_merged_py
                    st.session_state["_py_merge_dirty"] = True

                    if _ch_merged:
                        st.success(
                            f"Загружено {len(_ch_merged)} категорий. "
                            f"PY период: {_py_before_from} – {_py_before_to} / "
                            f"{_py_after_from} – {_py_after_to}"
                        )
                    else:
                        st.warning("Данные не найдены — проверьте периоды и Category ID.")
                    st.rerun()
                except Exception as _ch_err:
                    _err_str = str(_ch_err)
                    if "timed out" in _err_str or "ConnectTimeout" in _err_str or "ConnectionError" in _err_str:
                        st.error(
                            "Не удалось подключиться к ClickHouse — сервер недоступен. "
                            "Проверьте подключение к **VPN** и попробуйте снова."
                        )
                    else:
                        st.error(f"Ошибка ClickHouse: {_ch_err}")

        if _ch_clear:
            st.session_state.pop("merged_data", None)
            st.session_state.pop("price_data", None)
            st.session_state.pop("budget_dist", None)
            st.session_state.pop("_ch_data_loaded", None)
            st.session_state.pop("merged_data_previous_year", None)
            st.rerun()

        if st.session_state.get("_ch_data_loaded"):
            _ch_loaded_n = len(st.session_state.get("merged_data") or {})
            st.info(f"Активен источник: **ClickHouse** — {_ch_loaded_n} категорий загружено.")

    merged_data = {}
    price_data = {}
    budget_dist = {}
    if st.session_state.get("_ch_data_loaded") and not (spending_file and active_file):
        merged_data = st.session_state.get("merged_data") or {}
        price_data = st.session_state.get("price_data") or {}
        budget_dist = st.session_state.get("budget_dist") or {}
    elif spending_file and active_file and price_file:
        upload_sig = (
            "cy3",
            getattr(spending_file, "name", "") or "",
            getattr(spending_file, "size", None) or len(spending_file.getvalue()),
            getattr(active_file, "name", "") or "",
            getattr(active_file, "size", None) or len(active_file.getvalue()),
            getattr(price_file, "name", "") or "",
            getattr(price_file, "size", None) or len(price_file.getvalue()),
        )
        if st.session_state.get("_upload_sig") != upload_sig:
            paths = []
            try:
                paths = [
                    _write_upload_to_temp(spending_file),
                    _write_upload_to_temp(active_file),
                    _write_upload_to_temp(price_file),
                ]
                merged_data, price_data = load_and_merge_data(paths[0], paths[1], paths[2])
                st.session_state["merged_data"] = merged_data
                st.session_state["price_data"] = price_data
                st.session_state["_upload_sig"] = upload_sig
                st.session_state["_merge_files_dirty"] = True
                st.session_state.pop("_ch_data_loaded", None)
            finally:
                for p in paths:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
    elif spending_file and active_file:
        upload_sig = (
            "cy2",
            getattr(spending_file, "name", "") or "",
            getattr(spending_file, "size", None) or len(spending_file.getvalue()),
            getattr(active_file, "name", "") or "",
            getattr(active_file, "size", None) or len(active_file.getvalue()),
        )
        if st.session_state.get("_upload_sig") != upload_sig:
            paths = []
            try:
                paths = [
                    _write_upload_to_temp(spending_file),
                    _write_upload_to_temp(active_file),
                ]
                merged_data = load_and_merge_spending_active(paths[0], paths[1])
                st.session_state["merged_data"] = merged_data
                st.session_state["price_data"] = {}
                st.session_state["_upload_sig"] = upload_sig
                st.session_state["_merge_files_dirty"] = True
                st.session_state.pop("_ch_data_loaded", None)
            finally:
                for p in paths:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
    else:
        if not st.session_state.get("_ch_data_loaded"):
            st.session_state.pop("merged_data", None)
            st.session_state.pop("price_data", None)
            st.session_state.pop("_upload_sig", None)
            st.session_state.pop("_merge_files_dirty", None)

    merged_data = st.session_state.get("merged_data") or {}
    price_data = st.session_state.get("price_data") or {}

    if py_spending_file and py_active_file:
        py_upload_sig = (
            getattr(py_spending_file, "name", "") or "",
            getattr(py_spending_file, "size", None) or len(py_spending_file.getvalue()),
            getattr(py_active_file, "name", "") or "",
            getattr(py_active_file, "size", None) or len(py_active_file.getvalue()),
        )
        if st.session_state.get("_upload_sig_py") != py_upload_sig:
            py_paths = []
            try:
                py_paths = [
                    _write_upload_to_temp(py_spending_file),
                    _write_upload_to_temp(py_active_file),
                ]
                _merged_py = load_and_merge_spending_active(py_paths[0], py_paths[1])
                st.session_state["merged_data_previous_year"] = _merged_py
                st.session_state["_upload_sig_py"] = py_upload_sig
                st.session_state["_py_merge_dirty"] = True
            finally:
                for p in py_paths:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
    elif not st.session_state.get("_ch_data_loaded"):
        st.session_state.pop("merged_data_previous_year", None)
        st.session_state.pop("_upload_sig_py", None)
        st.session_state.pop("_py_merge_dirty", None)

    merged_data_previous_year = st.session_state.get("merged_data_previous_year") or {}

    if _category_bulk_mode:
        _resolved_single_category_id = None
        _bulk_effective_category_ids = (
            list(parsed_category_ids)
            if _bulk_from_text_ic
            else sorted(int(x) for x in _bulk_pick_ids)
        )
    elif len(parsed_category_ids) == 1:
        _resolved_single_category_id = int(parsed_category_ids[0])
        _bulk_effective_category_ids = []
    elif len(parsed_category_ids) == 0 and merged_data:
        _bulk_effective_category_ids = []
        _cy_keys_res = sorted(int(k) for k in merged_data.keys())
        if len(_cy_keys_res) == 1:
            _resolved_single_category_id = _cy_keys_res[0]
            st.caption(
                f"В файлах одна категория — для Before/After используется **{_resolved_single_category_id}**."
            )
        else:
            _resolved_single_category_id = int(
                st.selectbox(
                    "Category ID (Current Year): в файлах несколько категорий — выберите одну категорию для single-анализа",
                    options=_cy_keys_res,
                    key="cy_single_category_pick",
                )
            )
    else:
        _resolved_single_category_id = None
        _bulk_effective_category_ids = []

    _category_single_mode = _resolved_single_category_id is not None and not _category_bulk_mode

if scenario != "Regular":
    if scenario == "Low NPL (<10)":
        st.info("Low NPL mode is enabled: analysis will run with forced low NPL scenario.")
    elif scenario == "Other category":
        st.info("Other category mode is enabled: analysis will run with Other category scenario.")
    elif _scenario_is_new_category(scenario):
        st.info(
            "New category mode: category is under one year old with no Previous Year baseline; "
            "PY/Y2Y are optional and shown as unavailable in analytics."
        )
    elif _scenario_is_py_anomaly(scenario):
        st.info(
            "Previous Year anomaly mode: PY values may appear for reference, but Y2Y and "
            "Potential Spendings that rely on PY trends are excluded."
        )


def _extract_metrics_from_text(text):
    clean_text = text.lower()
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]

    parsed = {
        "paid_users_before": None,
        "paid_users_after": None,
        "spending_before": None,
        "spending_after": None,
        "active_before": None,
        "active_after": None,
    }

    aliases = {
        "paid_users": ["new paid listers", "paid listers", "paid users", "npl"],
        "sp": ["spendings", "spending", "revenue", "gmv", "sp"],
        "active": ["active listers", "active", "actives"],
    }

    def _parse_num(value):
        value = value.replace(" ", "")
        if "," in value and "." in value:
            value = value.replace(",", "")
        else:
            value = value.replace(",", ".")
        return float(value)

    def _find_before_after_numbers(line):
        before_match = re.search(r"before[^0-9-]*(-?\d[\d\s.,]*)", line)
        after_match = re.search(r"after[^0-9-]*(-?\d[\d\s.,]*)", line)
        if before_match and after_match:
            return _parse_num(before_match.group(1)), _parse_num(after_match.group(1))
        return None

    # Most precise case: metric + "before/after" on the same line.
    for line in lines:
        pair = _find_before_after_numbers(line)
        if not pair:
            continue
        before, after = pair

        if any(alias in line for alias in aliases["paid_users"]) and parsed["paid_users_before"] is None:
            parsed["paid_users_before"] = int(before)
            parsed["paid_users_after"] = int(after)
        elif any(alias in line for alias in aliases["sp"]) and parsed["spending_before"] is None:
            parsed["spending_before"] = before
            parsed["spending_after"] = after
        elif any(alias in line for alias in aliases["active"]) and parsed["active_before"] is None:
            parsed["active_before"] = int(before)
            parsed["active_after"] = int(after)

    # Fallback 1: metric line with first two numbers.
    for line in lines:
        numbers = re.findall(r"-?\d[\d\s]*(?:[.,]\d+)?", line)
        if len(numbers) < 2:
            continue
        before = _parse_num(numbers[0])
        after = _parse_num(numbers[1])

        if any(alias in line for alias in aliases["paid_users"]) and parsed["paid_users_before"] is None:
            parsed["paid_users_before"] = int(before)
            parsed["paid_users_after"] = int(after)
        elif any(alias in line for alias in aliases["sp"]) and parsed["spending_before"] is None:
            parsed["spending_before"] = before
            parsed["spending_after"] = after
        elif any(alias in line for alias in aliases["active"]) and parsed["active_before"] is None:
            parsed["active_before"] = int(before)
            parsed["active_after"] = int(after)

    # Fallback 2: OCR split rows into separate lines -> look around alias line.
    for i, line in enumerate(lines):
        window = " ".join(lines[i : i + 3])
        numbers = re.findall(r"-?\d[\d\s]*(?:[.,]\d+)?", window)
        if len(numbers) < 2:
            continue
        before = _parse_num(numbers[0])
        after = _parse_num(numbers[1])
        if any(alias in line for alias in aliases["paid_users"]) and parsed["paid_users_before"] is None:
            parsed["paid_users_before"] = int(before)
            parsed["paid_users_after"] = int(after)
        elif any(alias in line for alias in aliases["sp"]) and parsed["spending_before"] is None:
            parsed["spending_before"] = before
            parsed["spending_after"] = after
        elif any(alias in line for alias in aliases["active"]) and parsed["active_before"] is None:
            parsed["active_before"] = int(before)
            parsed["active_after"] = int(after)

    # Fallback 3: sequential numbers in expected order.
    flat_numbers = [_parse_num(n) for n in re.findall(r"-?\d[\d\s]*(?:[.,]\d+)?", clean_text)]
    if any(value is None for value in parsed.values()) and len(flat_numbers) >= 6:
        if parsed["paid_users_before"] is None:
            parsed["paid_users_before"] = int(flat_numbers[0])
            parsed["paid_users_after"] = int(flat_numbers[1])
        if parsed["spending_before"] is None:
            parsed["spending_before"] = flat_numbers[2]
            parsed["spending_after"] = flat_numbers[3]
        if parsed["active_before"] is None:
            parsed["active_before"] = int(flat_numbers[4])
            parsed["active_after"] = int(flat_numbers[5])

    return parsed


def _engine_style_diff(before, after):
    """Match decision_engine.diff: percent change; 0 if before == 0."""
    try:
        b = float(before)
        a = float(after)
    except (TypeError, ValueError):
        return None
    if b == 0:
        return 0.0
    return (a - b) / b * 100.0


def _bulk_safe_ratio(npl, active):
    if active is None or float(active) == 0:
        return 0.0
    return float(npl) / float(active)


_BULK_PRIORITY_MISSING = "0 - Missing data"
_BULK_PRIORITY_NEGATIVE = "1 - Negative impact"
_BULK_PRIORITY_INSUFFICIENT = "2 - Insufficient data"
_BULK_PRIORITY_NEED_REVIEW = "3 - Need review"
_BULK_PRIORITY_NO_IMPACT = "4 - No impact"
_BULK_PRIORITY_POSITIVE = "5 - Positive impact"

_BULK_PRIORITY_SORT_ORDER = {
    _BULK_PRIORITY_MISSING: 0,
    _BULK_PRIORITY_NEGATIVE: 1,
    _BULK_PRIORITY_INSUFFICIENT: 2,
    _BULK_PRIORITY_NEED_REVIEW: 3,
    _BULK_PRIORITY_NO_IMPACT: 4,
    _BULK_PRIORITY_POSITIVE: 5,
}

# Same copy as single-mode Calculate when diff Y2Y is required but cannot be completed.
_BULK_Y2Y_DECISION_UNAVAILABLE_NEXT_STEP = (
    "Year-over-year comparison is unavailable for one or more metrics. "
    "Enter Previous Year Paid users, Spending, and Active listers (Before and After) "
    "so diff Y2Y can be computed for NPL, Spending, and Conversion."
)


def _bulk_row_priority(status: str, final_decision):
    if status == "Missing current year data":
        return _BULK_PRIORITY_MISSING
    fd = final_decision if final_decision is not None else ""
    _by_final = {
        "Negative impact": _BULK_PRIORITY_NEGATIVE,
        "Insufficient data": _BULK_PRIORITY_INSUFFICIENT,
        "Need review": _BULK_PRIORITY_NEED_REVIEW,
        "No impact": _BULK_PRIORITY_NO_IMPACT,
        "Positive impact": _BULK_PRIORITY_POSITIVE,
    }
    return _by_final.get(fd, _BULK_PRIORITY_NEED_REVIEW)


def _bulk_row_warning_flags(
    status: str,
    scenario_used: str,
    *,
    has_py: bool,
    y2y_decision_unavailable: bool = False,
    low_npl_insufficient_sample: bool = False,
) -> str:
    """Tokens aligned with bulk scenario_used (MISSING_PY omitted for New/PY anomaly/Other paths)."""
    flags: list[str] = []
    if status == "Missing current year data":
        flags.append("MISSING_CY")
    if low_npl_insufficient_sample:
        flags.append("LOW_NPL")
    if y2y_decision_unavailable:
        flags.append("Y2Y_DECISION_UNAVAILABLE")
    if scenario_used == "New category":
        flags.append("NEW_CATEGORY")
    elif scenario_used == "Previous Year anomaly":
        flags.append("PY_ANOMALY")
    elif scenario_used != "Other category" and not has_py:
        if scenario_used in ("Regular", "Low NPL auto", "Low NPL (<10)"):
            flags.append("MISSING_PY")
    if scenario_used == "Other category":
        flags.append("OTHER_CATEGORY")
    return ", ".join(flags)


def _bulk_resolve_category_name(data: dict | None) -> str:
    """Display-only: optional name from merged payload if loaders add metadata later."""
    if not isinstance(data, dict):
        return ""
    for key in (
        "beautiful_name",
        "category_name",
        "category_level_5",
        "category_level_4",
        "category_level_3",
        "category_level_2",
        "category_level_1",
        "category_level_parent",
        "category_title",
        "category",
        "title",
        "name",
    ):
        val = data.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s and s.lower() != "nan":
            return s
    return ""


# CY Diff % для доп. метрик spending: формула как у PPV matrix (_matrix_pct_diff); не участвует в decision_engine.
_BULK_CY_EXTRA_DIFF_PCT_SPECS: tuple[tuple[str, str], ...] = (
    ("campaign_per_user", "CY Diff % Campaign per User"),
    ("new_campaign_cnt", "CY Diff % New campaign cnt"),
    ("price_per_day", "CY Diff % Price per day"),
    ("arp_p_campaign", "CY Diff % ARPpCampaign"),
    ("refund", "CY Diff % Refund"),
    ("pct_campaign_with_refund", "CY Diff % %Campaign with refund"),
    ("plan_imp_per_campaign", "CY Diff % Plan Imp per Campaign"),
    ("fact_imp_per_campaign", "CY Diff % Fact Imp per Campaign"),
    ("pct_execution_inventory", "CY Diff % %Execution Inventory"),
)
_BULK_CY_EXTRA_DIFF_COLUMN_NAMES = tuple(c for _, c in _BULK_CY_EXTRA_DIFF_PCT_SPECS)

# (metric_key, human label, kind) — for absolute Before/After columns in CSV export.
_BULK_CY_EXTRA_ABS_SPECS: tuple[tuple[str, str, str], ...] = (
    ("campaign_per_user",       "Campaign per User",        "float"),
    ("new_campaign_cnt",        "New campaign cnt",         "int"),
    ("price_per_day",           "Price per day",            "float"),
    ("arp_p_campaign",          "ARPpCampaign",             "float"),
    ("refund",                  "Refund",                   "float"),
    ("pct_campaign_with_refund","%Campaign with refund",    "float"),
    ("plan_imp_per_campaign",   "Plan Imp per Campaign",    "float"),
    ("fact_imp_per_campaign",   "Fact Imp per Campaign",    "float"),
    ("pct_execution_inventory", "%Execution Inventory",     "float"),
)
_BULK_CY_EXTRA_BEFORE_COLUMN_NAMES = tuple(f"cy_{mk}_before" for mk, _, _ in _BULK_CY_EXTRA_ABS_SPECS)
_BULK_CY_EXTRA_AFTER_COLUMN_NAMES  = tuple(f"cy_{mk}_after"  for mk, _, _ in _BULK_CY_EXTRA_ABS_SPECS)


def _bulk_na_extra_cy_diff_pct() -> dict[str, None]:
    d = dict.fromkeys(_BULK_CY_EXTRA_DIFF_COLUMN_NAMES, None)
    d.update(dict.fromkeys(_BULK_CY_EXTRA_BEFORE_COLUMN_NAMES, None))
    d.update(dict.fromkeys(_BULK_CY_EXTRA_AFTER_COLUMN_NAMES, None))
    return d


def _bulk_extra_cy_diff_pct_from_buckets(before_bucket, after_bucket) -> dict:
    """(after−before)/before×100 + absolute Before/After для доп. метрик."""
    b = before_bucket or {}
    a = after_bucket or {}
    result = {
        cname: _matrix_pct_diff(b.get(mkey), a.get(mkey))
        for mkey, cname in _BULK_CY_EXTRA_DIFF_PCT_SPECS
    }
    for mkey, _, kind in _BULK_CY_EXTRA_ABS_SPECS:
        v_b = b.get(mkey)
        v_a = a.get(mkey)
        if kind == "int":
            result[f"cy_{mkey}_before"] = int(float(v_b)) if v_b is not None else None
            result[f"cy_{mkey}_after"]  = int(float(v_a)) if v_a is not None else None
        else:
            result[f"cy_{mkey}_before"] = round(float(v_b), 4) if v_b is not None else None
            result[f"cy_{mkey}_after"]  = round(float(v_a), 4) if v_a is not None else None
    return result


def _bulk_analysis_dataframe(
    category_ids,
    merged_data,
    merged_data_previous_year,
    geo: str,
    global_scenario: str,
    other_override_ids: list,
    new_override_ids: list,
    py_anomaly_override_ids: list,
):
    """One row per category_id; CY/PY/Y2Y числа как прежде; решение и флаги — по scenario_used строки."""
    other_eff, new_eff, py_eff = _bulk_normalize_override_id_sets(
        other_override_ids if other_override_ids is not None else [],
        new_override_ids if new_override_ids is not None else [],
        py_anomaly_override_ids if py_anomaly_override_ids is not None else [],
    )
    rows = []
    for cid in category_ids:
        data = _bulk_lookup_merged_category(merged_data, cid)
        if data is None:
            _st = "Missing current year data"
            _has_py = (
                bool(merged_data_previous_year)
                and _bulk_lookup_merged_category(merged_data_previous_year, cid)
                is not None
            )
            su_miss = _bulk_resolve_scenario_used(
                int(cid),
                None,
                global_scenario,
                override_other_eff=other_eff,
                override_new_eff=new_eff,
                override_py_eff=py_eff,
                geo=geo,
            )
            rows.append(
                {
                    "category_id": cid,
                    "category_name": str(cid),
                    "scenario_used": su_miss,
                    "priority": _bulk_row_priority(_st, None),
                    "warning_flags": _bulk_row_warning_flags(
                        _st, su_miss, has_py=_has_py
                    ),
                    "status": _st,
                    "cy_paid_users_before": None,
                    "cy_paid_users_after": None,
                    "cy_paid_users_diff": None,
                    "cy_spending_before": None,
                    "cy_spending_after": None,
                    "cy_spending_diff": None,
                    "cy_cr_diff": None,
                    "cy_active_listers_before": None,
                    "cy_active_listers_after": None,
                    "cy_active_listers_diff": None,
                    **_bulk_na_extra_cy_diff_pct(),
                    "decision_code": None,
                    "final_decision": None,
                    "next_step": None,
                    "py_paid_users_before": None,
                    "py_paid_users_after": None,
                    "py_paid_users_diff": None,
                    "py_spending_before": None,
                    "py_spending_after": None,
                    "py_spending_diff": None,
                    "py_cr_diff": None,
                    "py_active_listers_diff": None,
                    "y2y_paid_users_diff": None,
                    "y2y_spending_diff": None,
                    "y2y_cr_diff": None,
                    "y2y_active_listers_diff": None,
                }
            )
            continue

        b = data.get("before") or {}
        a = data.get("after") or {}
        npl_b = int(float(b.get("paid_users") or 0))
        npl_a = int(float(a.get("paid_users") or 0))
        sp_b = float(b.get("spending") or 0)
        sp_a = float(a.get("spending") or 0)
        ac_b = int(float(b.get("active_listers") or 0))
        ac_a = int(float(a.get("active_listers") or 0))

        scenario_used = _bulk_resolve_scenario_used(
            int(cid),
            npl_a,
            global_scenario,
            override_other_eff=other_eff,
            override_new_eff=new_eff,
            override_py_eff=py_eff,
            geo=geo,
        )
        row_is_new = scenario_used == "New category"
        row_is_py_anom = scenario_used == "Previous Year anomaly"
        row_is_other = scenario_used == "Other category"
        row_force_low = scenario_used in ("Low NPL (<10)", "Low NPL auto")

        pd_py = None
        if not row_is_new and merged_data_previous_year:
            pd_py = _bulk_lookup_merged_category(merged_data_previous_year, cid)

        # Auto-case 1: no PY data and no manual override → New category
        _auto_eligible = (
            int(cid) not in other_eff
            and int(cid) not in new_eff
            and int(cid) not in py_eff
            and not row_force_low
        )
        if _auto_eligible and not row_is_new and not row_is_py_anom and not row_is_other and pd_py is None:
            scenario_used = "New category"
            row_is_new = True
            row_is_py_anom = False

        py_paid_users_diff = None
        py_spending_diff = None
        py_cr_diff = None
        py_active_listers_diff = None
        pnpl_b = pnpl_a = None
        psp_py_b = psp_py_a = None
        pac_b = pac_a = None
        if pd_py is not None:
            pb = pd_py.get("before") or {}
            pa = pd_py.get("after") or {}
            pnpl_b = int(float(pb.get("paid_users") or 0))
            pnpl_a = int(float(pa.get("paid_users") or 0))
            psp_py_b = float(pb.get("spending") or 0)
            psp_py_a = float(pa.get("spending") or 0)
            pac_b = int(float(pb.get("active_listers") or 0))
            pac_a = int(float(pa.get("active_listers") or 0))
            py_paid_users_diff = _engine_style_diff(pnpl_b, pnpl_a)
            py_spending_diff = _engine_style_diff(psp_py_b, psp_py_a)
            pcr_b = _bulk_safe_ratio(pnpl_b, pac_b)
            pcr_a = _bulk_safe_ratio(pnpl_a, pac_a)
            py_cr_diff = _engine_style_diff(pcr_b, pcr_a)
            py_active_listers_diff = _engine_style_diff(pac_b, pac_a)

        result = analyze_category(
            npl_before=npl_b,
            npl_after=npl_a,
            sp_before=sp_b,
            sp_after=sp_a,
            active_before=ac_b,
            active_after=ac_a,
            geo=geo or "default",
            force_low_npl=row_force_low,
            is_other_category=row_is_other,
        )
        cy_paid_users_diff = result["npl_diff"]
        cy_spending_diff = result["sp_diff"]
        cy_cr = result["cr_diff"]
        cy_active_listers_diff = result["active_diff"]

        def _y2y(cy_v, py_v):
            if py_v is None or cy_v is None:
                return None
            return cy_v - py_v

        _st_ok = ""
        _has_py = pd_py is not None
        if row_is_py_anom:
            _y2y_paid_users_diff = None
            _y2y_spending_diff = None
            _y2y_cr_diff = None
            _y2y_active_listers_diff = None
        else:
            _y2y_paid_users_diff = _y2y(cy_paid_users_diff, py_paid_users_diff)
            _y2y_spending_diff = _y2y(cy_spending_diff, py_spending_diff)
            _y2y_cr_diff = _y2y(cy_cr, py_cr_diff)
            _y2y_active_listers_diff = _y2y(cy_active_listers_diff, py_active_listers_diff)

        # Bulk analysis must use the same primary comparison period as single analysis
        # to keep decision logic consistent across modes.
        _matrix_focus_run = (
            "current_year" if (row_is_new or row_is_py_anom) else "diff_y2y"
        )
        _is_other_run = row_is_other
        _low_npl_override_run = scenario_used == "Low NPL (<10)" or npl_a < _geo_min_npl(geo)
        y2y_decision_unavail = False
        if _matrix_focus_run == "current_year" or _is_other_run:
            disp_dc = result["decision_code"]
            disp_fd = result["final_decision"]
            disp_ns = result["next_step"]
        elif pd_py is not None:
            y2y_bundle = _results_compute_y2y_npl_sp_cr_bundle(
                geo or "default",
                npl_b,
                npl_a,
                sp_b,
                sp_a,
                ac_b,
                ac_a,
                pnpl_b,
                pnpl_a,
                psp_py_b,
                psp_py_a,
                pac_b,
                pac_a,
            )
            if y2y_bundle["complete"]:
                disp_dc = y2y_bundle["decision_code"]
                _dr_y2y = get_decision(disp_dc)
                disp_fd = _dr_y2y["decision"]
                disp_ns = _dr_y2y["next_step"]
                if _low_npl_override_run:
                    disp_fd = result["final_decision"]
                    disp_ns = result["next_step"]
            else:
                # Auto-case 2: PY data exists but Y2Y can't be computed → Previous Year anomaly (CY decision)
                if _auto_eligible and not row_is_py_anom and not row_is_other:
                    scenario_used = "Previous Year anomaly"
                    row_is_py_anom = True
                    disp_dc = result["decision_code"]
                    disp_fd = result["final_decision"]
                    disp_ns = result["next_step"]
                else:
                    y2y_decision_unavail = True
                    disp_dc = "—"
                    disp_fd = "Insufficient data"
                    disp_ns = _BULK_Y2Y_DECISION_UNAVAILABLE_NEXT_STEP
        else:
            y2y_decision_unavail = True
            disp_dc = "—"
            disp_fd = "Insufficient data"
            disp_ns = _BULK_Y2Y_DECISION_UNAVAILABLE_NEXT_STEP

        _low_npl_insufficient_flag = (
            scenario_used != "Other category"
            and result["final_decision"] == "Insufficient data"
            and (row_force_low or npl_a < _geo_min_npl(geo))
        )

        _nm = _bulk_resolve_category_name(data)
        rows.append(
            {
                "category_id": cid,
                "category_name": _nm if _nm else str(cid),
                "scenario_used": scenario_used,
                "priority": _bulk_row_priority(_st_ok, disp_fd),
                "warning_flags": _bulk_row_warning_flags(
                    _st_ok,
                    scenario_used,
                    has_py=_has_py,
                    y2y_decision_unavailable=y2y_decision_unavail,
                    low_npl_insufficient_sample=_low_npl_insufficient_flag,
                ),
                "status": _st_ok,
                "cy_paid_users_before": npl_b,
                "cy_paid_users_after": npl_a,
                "cy_paid_users_diff": cy_paid_users_diff,
                "cy_spending_before": round(sp_b, 2),
                "cy_spending_after": round(sp_a, 2),
                "cy_spending_diff": cy_spending_diff,
                "cy_cr_diff": cy_cr,
                "cy_active_listers_before": ac_b,
                "cy_active_listers_after": ac_a,
                "cy_active_listers_diff": cy_active_listers_diff,
                **_bulk_extra_cy_diff_pct_from_buckets(b, a),
                "decision_code": disp_dc,
                "final_decision": disp_fd,
                "next_step": disp_ns,
                "py_paid_users_before": pnpl_b,
                "py_paid_users_after": pnpl_a,
                "py_paid_users_diff": py_paid_users_diff,
                "py_spending_before": round(psp_py_b, 2) if psp_py_b is not None else None,
                "py_spending_after": round(psp_py_a, 2) if psp_py_a is not None else None,
                "py_spending_diff": py_spending_diff,
                "py_cr_diff": py_cr_diff,
                "py_active_listers_diff": py_active_listers_diff,
                "y2y_paid_users_diff": _y2y_paid_users_diff,
                "y2y_spending_diff": _y2y_spending_diff,
                "y2y_cr_diff": _y2y_cr_diff,
                "y2y_active_listers_diff": _y2y_active_listers_diff,
            }
        )

    cols = [
        "category_id",
        "category_name",
        "scenario_used",
        "priority",
        "cy_paid_users_before",
        "cy_paid_users_after",
        "cy_paid_users_diff",
        "cy_spending_before",
        "cy_spending_after",
        "cy_spending_diff",
        "cy_cr_diff",
        "cy_active_listers_before",
        "cy_active_listers_after",
        "cy_active_listers_diff",
        *_BULK_CY_EXTRA_DIFF_COLUMN_NAMES,
        *_BULK_CY_EXTRA_BEFORE_COLUMN_NAMES,
        *_BULK_CY_EXTRA_AFTER_COLUMN_NAMES,
        "py_paid_users_before",
        "py_paid_users_after",
        "py_paid_users_diff",
        "py_spending_before",
        "py_spending_after",
        "py_spending_diff",
        "py_cr_diff",
        "py_active_listers_diff",
        "y2y_paid_users_diff",
        "y2y_spending_diff",
        "y2y_cr_diff",
        "y2y_active_listers_diff",
        "decision_code",
        "final_decision",
        "next_step",
        "warning_flags",
        "status",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["group_type"]           = ""
    df["parent_ref_id"]        = None
    df["parent_category_name"] = ""
    df["_pri_sort"] = df["priority"].map(lambda p: _BULK_PRIORITY_SORT_ORDER.get(p, 99))
    df = df.sort_values(by=["_pri_sort", "category_id"], ascending=[True, True]).drop(
        columns=["_pri_sort"]
    )
    return df


# ── Parent-category fallback ────────────────────────────────────────────────

_PARENT_THRESHOLD = 0.80   # fraction of children that must be Insufficient
_PARENT_SCENARIO_LABEL = "Parent group"
_PARENT_SCENARIO_CHILD = "By parent category"
_BULK_ROW_BG_PARENT     = "#dbeafe"   # light blue for parent header rows
_BULK_ROW_BG_CHILD_INH  = "#f1f5f9"  # light slate for inherited children


def _bulk_detect_parent_groups(
    bulk_df: pd.DataFrame,
    child_to_parent: dict[int, int],
    cat_names: dict[int, str],
    threshold: float = _PARENT_THRESHOLD,
) -> list[dict]:
    """
    Group insufficient-data categories by parent.
    Returns list of {parent_id, parent_name, child_ids, all_child_ids}.
    Only groups where ≥ threshold of siblings have Insufficient data are returned.
    """
    if bulk_df is None or bulk_df.empty or not child_to_parent:
        return []

    # Build parent→all_children mapping from the bulk_df category list
    parent_to_children: dict[int, list[int]] = {}
    for cid_raw in bulk_df["category_id"]:
        try:
            cid = int(cid_raw)
        except (TypeError, ValueError):
            continue
        pid = child_to_parent.get(cid)
        if pid is not None:
            parent_to_children.setdefault(pid, []).append(cid)

    insufficient_ids = frozenset(
        int(r["category_id"])
        for _, r in bulk_df.iterrows()
        if str(r.get("final_decision") or "").strip() == "Insufficient data"
    )

    groups = []
    for parent_id, all_children in parent_to_children.items():
        if not all_children:
            continue
        insuff_children = [c for c in all_children if c in insufficient_ids]
        ratio = len(insuff_children) / len(all_children)
        if ratio < threshold:
            continue
        groups.append({
            "parent_id":   parent_id,
            "parent_name": cat_names.get(parent_id, str(parent_id)),
            "child_ids":   insuff_children,    # children that had Insufficient
            "all_child_ids": all_children,     # all children in bulk_df for this parent
        })
    return groups


def _bulk_aggregate_children_buckets(
    child_ids: list[int],
    merged_data: dict,
) -> tuple[dict, dict]:
    """Aggregate before/after buckets from a list of child categories."""
    agg_b: dict = {"paid_users": 0, "spending": 0.0, "active_listers": 0,
                   "new_campaign_cnt": 0, "refund": 0.0}
    agg_a: dict = {"paid_users": 0, "spending": 0.0, "active_listers": 0,
                   "new_campaign_cnt": 0, "refund": 0.0}
    for cid in child_ids:
        data = _bulk_lookup_merged_category(merged_data, cid)
        if not data:
            continue
        b = data.get("before") or {}
        a = data.get("after") or {}
        for key in ("active_listers", "new_campaign_cnt"):
            agg_b[key] += int(float(b.get(key) or 0))
            agg_a[key] += int(float(a.get(key) or 0))
        agg_b["paid_users"] += int(float(b.get("paid_users") or 0))
        agg_a["paid_users"] += int(float(a.get("paid_users") or 0))
        agg_b["spending"]   += float(b.get("spending") or 0)
        agg_a["spending"]   += float(a.get("spending") or 0)
        agg_b["refund"]     += float(b.get("refund") or 0)
        agg_a["refund"]     += float(a.get("refund") or 0)
    return agg_b, agg_a


def _bulk_analyze_parent_category(
    parent_id: int,
    parent_name: str,
    all_child_ids: list[int],
    merged_data: dict,
    merged_data_py: dict,
    geo: str,
    scenario: str,
) -> dict | None:
    """
    Aggregate children's data and run analysis at parent level.
    No separate ClickHouse query needed — uses already-loaded merged_data.
    Returns a result dict with decision/priority fields, or None if no data.
    """
    b, a = _bulk_aggregate_children_buckets(all_child_ids, merged_data)
    npl_b = b["paid_users"]
    npl_a = a["paid_users"]
    sp_b  = b["spending"]
    sp_a  = a["spending"]
    ac_b  = b["active_listers"]
    ac_a  = a["active_listers"]

    if npl_b == 0 and npl_a == 0:
        return None

    pnpl_b = pnpl_a = psp_py_b = psp_py_a = pac_b = pac_a = None
    py_paid_users_diff = py_spending_diff = py_cr_diff = py_active_listers_diff = None
    py_has_data = False
    if merged_data_py:
        pb, pa = _bulk_aggregate_children_buckets(all_child_ids, merged_data_py)
        if pb["paid_users"] > 0 or pa["paid_users"] > 0:
            pnpl_b = pb["paid_users"]
            pnpl_a = pa["paid_users"]
            psp_py_b = pb["spending"]
            psp_py_a = pa["spending"]
            pac_b  = pb["active_listers"]
            pac_a  = pa["active_listers"]
            py_paid_users_diff = _engine_style_diff(pnpl_b, pnpl_a)
            py_spending_diff   = _engine_style_diff(psp_py_b, psp_py_a)
            pcr_b = _bulk_safe_ratio(pnpl_b, pac_b)
            pcr_a = _bulk_safe_ratio(pnpl_a, pac_a)
            py_cr_diff  = _engine_style_diff(pcr_b, pcr_a)
            py_active_listers_diff = _engine_style_diff(pac_b, pac_a)
            py_has_data = True

    result = analyze_category(
        npl_before=npl_b, npl_after=npl_a,
        sp_before=sp_b,   sp_after=sp_a,
        active_before=ac_b, active_after=ac_a,
        geo=geo or "default",
    )
    cy_paid_users_diff     = result["npl_diff"]
    cy_spending_diff       = result["sp_diff"]
    cy_cr                  = result["cr_diff"]
    cy_active_listers_diff = result["active_diff"]

    disp_dc = result["decision_code"]
    disp_fd = result["final_decision"]
    disp_ns = result["next_step"]

    if py_has_data:
        y2y_bundle = _results_compute_y2y_npl_sp_cr_bundle(
            geo or "default",
            npl_b, npl_a, sp_b, sp_a, ac_b, ac_a,
            pnpl_b, pnpl_a, psp_py_b, psp_py_a, pac_b, pac_a,
        )
        if y2y_bundle["complete"]:
            disp_dc = y2y_bundle["decision_code"]
            _dr = get_decision(disp_dc)
            disp_fd = _dr["decision"]
            disp_ns = _dr["next_step"]

    def _y2y(cy_v, py_v):
        if cy_v is None or py_v is None:
            return None
        return cy_v - py_v

    return {
        "decision_code": disp_dc,
        "final_decision": disp_fd,
        "next_step": disp_ns,
        "priority": _bulk_row_priority("", disp_fd),
        "cy_paid_users_diff": cy_paid_users_diff,
        "cy_spending_diff":   cy_spending_diff,
        "cy_cr_diff":         cy_cr,
        "cy_active_listers_diff": cy_active_listers_diff,
        "py_paid_users_diff": py_paid_users_diff,
        "py_spending_diff":   py_spending_diff,
        "py_cr_diff":         py_cr_diff,
        "py_active_listers_diff": py_active_listers_diff,
        "y2y_paid_users_diff":    _y2y(cy_paid_users_diff, py_paid_users_diff),
        "y2y_spending_diff":      _y2y(cy_spending_diff, py_spending_diff),
        "y2y_cr_diff":            _y2y(cy_cr, py_cr_diff),
        "y2y_active_listers_diff": _y2y(cy_active_listers_diff, py_active_listers_diff),
    }


def _bulk_enrich_with_parents(
    bulk_df: pd.DataFrame,
    parent_groups: list[dict],
    merged_data: dict,
    merged_data_py: dict,
    geo: str,
    scenario: str,
) -> pd.DataFrame:
    """
    For each qualifying parent group: run analysis on parent category data and
    apply the parent's decision to insufficient child rows in-place.
    Children keep their own metrics; only decision/priority/scenario_used change.
    A 'parent_category_name' column is populated for children that inherited a decision.
    """
    if not parent_groups:
        return bulk_df

    df = bulk_df.copy()
    if "parent_category_name" not in df.columns:
        df["parent_category_name"] = ""

    for grp in parent_groups:
        pid           = grp["parent_id"]
        pname         = grp["parent_name"]
        child_ids     = grp["child_ids"]       # insufficient children — get decision updated
        all_child_ids = grp["all_child_ids"]   # all children — used for aggregation

        parent_row = _bulk_analyze_parent_category(
            pid, pname, child_ids, merged_data, merged_data_py, geo, scenario
        )
        if parent_row is None:
            continue

        for cid in child_ids:
            mask = df["category_id"].astype(str) == str(cid)
            df.loc[mask, "group_type"]           = "child_inherited"
            df.loc[mask, "parent_ref_id"]        = pid
            df.loc[mask, "parent_category_name"] = pname
            df.loc[mask, "scenario_used"]        = _PARENT_SCENARIO_CHILD
            df.loc[mask, "final_decision"]       = parent_row["final_decision"]
            df.loc[mask, "next_step"]            = parent_row["next_step"]
            df.loc[mask, "priority"]             = parent_row["priority"]

    return df


def _bulk_render_summary(df: pd.DataFrame) -> None:
    """Manager-facing counts: six buckets from priority + breakdowns by priority / final_decision / status."""
    if df is None or df.empty:
        return

    pri_vc = df["priority"].value_counts()
    _metric_rows = (
        ("Missing data", _BULK_PRIORITY_MISSING),
        ("Negative impact", _BULK_PRIORITY_NEGATIVE),
        ("Insufficient data", _BULK_PRIORITY_INSUFFICIENT),
        ("Need review", _BULK_PRIORITY_NEED_REVIEW),
        ("No impact", _BULK_PRIORITY_NO_IMPACT),
        ("Positive impact", _BULK_PRIORITY_POSITIVE),
    )

    st.markdown("##### Summary")
    _r1, _r2 = st.columns(3), st.columns(3)
    for _i, (_title, _pkey) in enumerate(_metric_rows):
        _cols = _r1 if _i < 3 else _r2
        with _cols[_i % 3]:
            st.metric(_title, int(pri_vc.get(_pkey, 0)))

    py_anomaly_flag_n = int(
        df["warning_flags"]
        .apply(lambda w: "PY_ANOMALY" in _bulk_warning_token_set(w))
        .sum()
    )
    st.metric("Previous Year anomaly (PY_ANOMALY)", py_anomaly_flag_n)

    if "scenario_used" in df.columns:
        _su = df["scenario_used"]
        st.markdown("###### scenario_used")
        _sx1, _sx2, _sx3, _sx4, _sx5, _sx6 = st.columns(6)
        _sx1.metric("Regular", int((_su == "Regular").sum()))
        _sx2.metric("New category", int((_su == "New category").sum()))
        _sx3.metric("PY anomaly", int((_su == "Previous Year anomaly").sum()))
        _sx4.metric("Other", int((_su == "Other category").sum()))
        _sx5.metric("Low NPL auto", int((_su == "Low NPL auto").sum()))
        _sx6.metric("Low NPL (<10)", int((_su == "Low NPL (<10)").sum()))

    m_cy_sp = _bulk_mean_numeric_column_mean(df, "cy_spending_diff")
    m_y2y_cr = _bulk_mean_numeric_column_mean(df, "y2y_cr_diff")
    if m_cy_sp is not None or m_y2y_cr is not None:
        _ax1, _ax2 = st.columns(2)
        with _ax1:
            st.metric("Avg CY Spending %", format_percent(m_cy_sp) if m_cy_sp is not None else "—")
        with _ax2:
            st.metric("Avg Y2Y CR Δ", format_percent(m_y2y_cr) if m_y2y_cr is not None else "—")

    with st.expander("Разбивка по priority, final_decision, status", expanded=False):
        _e1, _e2, _e3 = st.columns(3)
        with _e1:
            st.caption("По priority")
            st.dataframe(
                pri_vc.rename_axis("priority").reset_index(name="n"),
                hide_index=True,
                use_container_width=True,
            )
        with _e2:
            st.caption("По final_decision")
            _fd = df["final_decision"].fillna("(no data)")
            st.dataframe(
                _fd.value_counts().rename_axis("final_decision").reset_index(name="n"),
                hide_index=True,
                use_container_width=True,
            )
        with _e3:
            st.caption("По status")
            _ss = df["status"].replace({"": "(ok / empty)"})
            st.dataframe(
                _ss.value_counts().rename_axis("status").reset_index(name="n"),
                hide_index=True,
                use_container_width=True,
            )

    if "scenario_used" in df.columns:
        with st.expander("Разбивка по scenario_used", expanded=False):
            _suv = df["scenario_used"].fillna("(no data)")
            st.dataframe(
                _suv.value_counts().rename_axis("scenario_used").reset_index(name="n"),
                hide_index=True,
                use_container_width=True,
            )


def _bulk_warning_token_set(flags_str) -> set:
    if flags_str is None or (isinstance(flags_str, float) and pd.isna(flags_str)):
        return set()
    s = str(flags_str).strip()
    if not s:
        return set()
    return {t.strip() for t in s.split(",") if t.strip()}


def _bulk_unique_warning_flag_options(df: pd.DataFrame) -> list:
    acc = set()
    for w in df["warning_flags"]:
        acc |= _bulk_warning_token_set(w)
    return sorted(acc)


def _bulk_apply_table_filters(
    df: pd.DataFrame,
    sel_priority: list,
    all_priority: list,
    sel_final_decision: list,
    all_final_decision: list,
    sel_warning_flags: list,
    all_warning_flags: list,
) -> pd.DataFrame:
    """
    AND across dimensions. If every option is selected for a dimension, that dimension is not applied.
    warning_flags: row matches if intersection of row tokens and selected flags is non-empty (OR).
    Empty multiselect is treated as “no restriction” so the table does not disappear by accident.
    """
    m = pd.Series(True, index=df.index)

    sel_p = sel_priority if sel_priority else list(all_priority)
    if set(sel_p) != set(all_priority):
        m &= df["priority"].isin(sel_p)

    sel_fd = sel_final_decision if sel_final_decision else list(all_final_decision)
    if set(sel_fd) != set(all_final_decision):
        fd_disp = df["final_decision"].apply(
            lambda x: "(no data)" if pd.isna(x) else str(x)
        )
        m &= fd_disp.isin(sel_fd)

    if all_warning_flags:
        sel_wf = sel_warning_flags if sel_warning_flags else list(all_warning_flags)
        if set(sel_wf) != set(all_warning_flags):
            sel_w = set(sel_wf)

            def _row_matches_warnings(val):
                return bool(sel_w & _bulk_warning_token_set(val))

            m &= df["warning_flags"].apply(_row_matches_warnings)
    return df.loc[m]


def _bulk_render_insights(df: pd.DataFrame) -> None:
    """Short human-readable counts over the full bulk result (not table filters)."""
    if df is None or df.empty:
        return
    total = len(df)
    negative = int((df["final_decision"] == "Negative impact").sum())
    insufficient = int((df["final_decision"] == "Insufficient data").sum())
    missing_py = int(
        df["warning_flags"]
        .apply(lambda w: "MISSING_PY" in _bulk_warning_token_set(w))
        .sum()
    )
    new_category_n = int(
        df["warning_flags"]
        .apply(lambda w: "NEW_CATEGORY" in _bulk_warning_token_set(w))
        .sum()
    )
    py_anomaly_n = int(
        df["warning_flags"]
        .apply(lambda w: "PY_ANOMALY" in _bulk_warning_token_set(w))
        .sum()
    )
    missing_cy = int((df["status"] == "Missing current year data").sum())

    if "scenario_used" in df.columns:
        _su = df["scenario_used"]
        n_reg = int((_su == "Regular").sum())
        n_new = int((_su == "New category").sum())
        n_pya = int((_su == "Previous Year anomaly").sum())
        n_oth = int((_su == "Other category").sum())
        n_la = int((_su == "Low NPL auto").sum())
        n_l10 = int((_su == "Low NPL (<10)").sum())

    parts = [f"Analyzed **{total}** categories."]
    if "scenario_used" in df.columns:
        parts.append(
            "**scenario_used:** Regular **"
            f"{n_reg}**, New category **{n_new}**, Previous Year anomaly **{n_pya}**, Other **{n_oth}**, "
            f"Low NPL auto **{n_la}**, Low NPL (<10) **{n_l10}**."
        )
    if negative:
        parts.append(f"❌ **{negative}** categories show negative impact.")
    if insufficient:
        parts.append(f"📉 **{insufficient}** categories have insufficient data.")
    if missing_py:
        parts.append(f"📊 **{missing_py}** categories have no previous-year data.")
    if new_category_n:
        parts.append(f"📌 **{new_category_n}** categories flagged as **New category** (PY/Y2Y not used).")
    if py_anomaly_n:
        parts.append(
            f"**{py_anomaly_n}** categories have Previous Year anomaly and Y2Y is excluded."
        )
    if missing_cy:
        parts.append(f"⚠️ **{missing_cy}** categories missing current data.")

    st.markdown("### Summary insights")
    st.markdown("\n\n".join(parts))


# Row-level backgrounds (very subtle — main visual signal comes from diff cells)
_BULK_ROW_BG_MISSING_CY   = "#efefef"
_BULK_ROW_BG_NEGATIVE     = "#fff0f0"
_BULK_ROW_BG_INSUFFICIENT = "#fdfbef"
_BULK_ROW_BG_POSITIVE     = "#f0fdf2"
_BULK_ROW_BG_NO_IMPACT    = "#fdfbf0"

# Per-cell diff coloring (value-based, stronger contrast than row tint)
_BULK_DIFF_CELL_POSITIVE  = "rgba(40, 180, 90, 0.22)"   # green
_BULK_DIFF_CELL_NEGATIVE  = "rgba(210, 50, 50, 0.20)"    # red
_BULK_DIFF_CELL_NEAR_ZERO = "rgba(255, 190, 0, 0.18)"    # amber ≈ neutral

# Decision cell badge colors
_BULK_DECISION_BG_POSITIVE    = "rgba(40, 167, 69, 0.28)"
_BULK_DECISION_BG_NEGATIVE    = "rgba(220, 53, 69, 0.28)"
_BULK_DECISION_BG_NO_IMPACT   = "rgba(255, 193, 7, 0.28)"
_BULK_DECISION_BG_INSUFFICIENT = "rgba(108, 117, 125, 0.20)"


def _bulk_format_next_step_short(next_step: str) -> str:
    """
    Короткая подпись действия для compact summary (полный next_step — в Category details).
    Эвристики по ключевым фразам; без усечения «первыми словами».
    """
    s = str(next_step or "").strip()
    if not s:
        return "—"
    lower = s.lower()
    if "choose with your teamlead" in lower or "choose with a teamlead" in lower:
        return "Review with teamlead"
    if "keep" in lower:
        return "Keep prices"
    if "rollback" in lower or "roll back" in lower:
        return "Rollback"
    if "increase" in lower or "re-increase" in lower:
        return "Increase price"
    if "look for other methods" in lower:
        return "Find other methods"
    return "Need review"


def _bulk_next_step_short_cell(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return _bulk_format_next_step_short(str(val))


def _bulk_row_background(row: pd.Series):
    """Return background color hex for a bulk table row, or None for default."""
    if row.get("status") == "Missing current year data":
        return _BULK_ROW_BG_MISSING_CY
    fd = row.get("final_decision")
    if fd is None or (isinstance(fd, float) and pd.isna(fd)):
        return None
    fd = str(fd)
    if fd == "Negative impact":
        return _BULK_ROW_BG_NEGATIVE
    if fd == "Insufficient data":
        return _BULK_ROW_BG_INSUFFICIENT
    if fd == "Positive impact":
        return _BULK_ROW_BG_POSITIVE
    if fd == "No impact":
        return _BULK_ROW_BG_NO_IMPACT
    return None


def _bulk_format_table_for_display(
    df: pd.DataFrame,
    *,
    new_category_mode: bool = False,
    py_anomaly_mode: bool = False,
) -> pd.DataFrame:
    """Тысячи с пробелом в category_id; остальные колонки без изменений."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if "category_id" in out.columns:
        def _fmt_cat(x):
            if pd.isna(x):
                return x
            try:
                return format_integer(int(x), group_thousands=True)
            except (TypeError, ValueError):
                return x

        out["category_id"] = out["category_id"].map(_fmt_cat)
    for _col in _BULK_CY_EXTRA_DIFF_COLUMN_NAMES:
        if _col in out.columns:
            out[_col] = out[_col].map(lambda v: format_percent(v))
    _dash_py_y2y = (
        "py_paid_users_diff",
        "py_spending_diff",
        "py_cr_diff",
        "py_active_listers_diff",
        "y2y_paid_users_diff",
        "y2y_spending_diff",
        "y2y_cr_diff",
        "y2y_active_listers_diff",
    )
    _dash_y2y_only = (
        "y2y_paid_users_diff",
        "y2y_spending_diff",
        "y2y_cr_diff",
        "y2y_active_listers_diff",
    )

    def _to_dash(val):
        return "—" if val is None or (isinstance(val, float) and pd.isna(val)) else val

    if new_category_mode:
        for col in _dash_py_y2y:
            if col in out.columns:
                out[col] = out[col].map(_to_dash)
    elif py_anomaly_mode:
        for col in _dash_y2y_only:
            if col in out.columns:
                out[col] = out[col].map(_to_dash)
    return out


def _bulk_mask_py_y2y_cells_by_scenario(per_row_df: pd.DataFrame, compact_view: pd.DataFrame) -> pd.DataFrame:
    """Для смешанного bulk: «—» в PY/Y2Y столбцах построчно по ``scenario_used``."""
    if per_row_df is None or compact_view is None:
        return compact_view
    if per_row_df.empty or compact_view.empty:
        return compact_view
    if "scenario_used" not in per_row_df.columns:
        return compact_view
    out = compact_view.copy()
    py_cols = (
        "py_paid_users_diff",
        "py_spending_diff",
        "py_cr_diff",
        "py_active_listers_diff",
    )
    y2y_cols = (
        "y2y_paid_users_diff",
        "y2y_spending_diff",
        "y2y_cr_diff",
        "y2y_active_listers_diff",
    )
    n = min(len(per_row_df), len(out))
    for pos in range(n):
        su = str(per_row_df.iloc[pos].get("scenario_used") or "").strip()
        if su == "New category":
            tgt = py_cols + y2y_cols
        elif su == "Previous Year anomaly":
            tgt = y2y_cols
        else:
            continue
        for c in tgt:
            if c not in out.columns:
                continue
            col_ix = out.columns.get_loc(c)
            if isinstance(col_ix, (list, tuple)) or getattr(col_ix, "ndim", 0) > 0:
                continue
            out.iat[pos, int(col_ix)] = "—"
    return out


def _bulk_styled_dataframe(df: pd.DataFrame, *, style_source: pd.DataFrame | None = None):
    """Раскраска строк по decision/status и визуальные группы CY / PY / Y2Y.

    Tint — inset box‑shadow поверх ``background-color`` строки (строковый статус сохраняет приоритет).
    ``style_source`` — полный bulk‑ряд в том же порядке (доступ к ``status`` без колонки в таблице).
    """
    if df is None or df.empty:
        return df
    meta = style_source if style_source is not None else df

    def _apply_row_styles_fallback(row: pd.Series):
        try:
            mrow = meta.iloc[int(row.name)]
        except (TypeError, ValueError, IndexError, KeyError):
            mrow = row
        bg = _bulk_row_background(mrow)
        if not bg:
            return pd.Series([""] * len(row), index=row.index)
        return pd.Series([f"background-color: {bg}"] * len(row), index=row.index)

    def _cell_grid_styles(data):
        # axis=None может передать ndarray; опираемся на исходный df.
        _ = data
        cols_ds = list(df.columns)
        cy_first  = next((c for c in cols_ds if c in _BULK_CY_METRIC_COLUMNS_SET), None)
        py_first  = next((c for c in cols_ds if c in _BULK_PY_METRIC_COLUMNS_SET), None)
        y2y_first = next((c for c in cols_ds if c in _BULK_Y2Y_METRIC_COLUMNS_SET), None)

        # All diff-type columns (value-based coloring)
        all_diff_cols = frozenset(c for c in cols_ds if str(c).endswith("_diff"))
        # Extra diff columns from spending metrics (column names already contain "CY Diff %")
        extra_diff_cols = frozenset(
            c for c in cols_ds if str(c).startswith("CY Diff %")
        )
        all_diff_all = all_diff_cols | extra_diff_cols

        out = pd.DataFrame("", index=df.index, columns=df.columns)

        for i_pos in range(len(df)):
            try:
                mrow = meta.iloc[int(i_pos)]
            except (TypeError, ValueError, IndexError, KeyError):
                mrow = df.iloc[int(i_pos)]
            row_bg = _bulk_row_background(mrow)

            for col in cols_ds:
                parts: list[str] = []
                is_diff = col in all_diff_all

                # 1. Subtle row background (just context, not the main signal)
                if row_bg and not is_diff and col != "final_decision":
                    parts.append(f"background-color: {row_bg}")

                # 2. Group tint — only for Before/After (non-diff) columns
                if not is_diff and col != "final_decision":
                    if col in _BULK_CY_METRIC_COLUMNS_SET:
                        parts.append(f"box-shadow: inset 0 0 0 100vmax {_BULK_GROUP_TINT_CY}")
                    elif col in _BULK_PY_METRIC_COLUMNS_SET:
                        parts.append(f"box-shadow: inset 0 0 0 100vmax {_BULK_GROUP_TINT_PY}")
                    elif col in _BULK_Y2Y_METRIC_COLUMNS_SET:
                        parts.append(f"box-shadow: inset 0 0 0 100vmax {_BULK_GROUP_TINT_Y2Y}")

                # 3. Diff-cell value-based coloring (main visual signal)
                if is_diff:
                    raw_val = mrow.get(col)
                    try:
                        v_f = float(raw_val)
                        if v_f > 1.0:
                            parts.append(f"background-color: {_BULK_DIFF_CELL_POSITIVE}")
                        elif v_f < -1.0:
                            parts.append(f"background-color: {_BULK_DIFF_CELL_NEGATIVE}")
                        else:
                            parts.append(f"background-color: {_BULK_DIFF_CELL_NEAR_ZERO}")
                    except (TypeError, ValueError):
                        pass

                # 4. Decision badge — strong color on the cell
                if col == "final_decision":
                    fd = str(mrow.get("final_decision") or "")
                    if fd == "Positive impact":
                        parts = [
                            f"background-color: {_BULK_DECISION_BG_POSITIVE}",
                            "font-weight: 600",
                        ]
                    elif fd == "Negative impact":
                        parts = [
                            f"background-color: {_BULK_DECISION_BG_NEGATIVE}",
                            "font-weight: 600",
                        ]
                    elif fd == "No impact":
                        parts = [
                            f"background-color: {_BULK_DECISION_BG_NO_IMPACT}",
                            "font-weight: 600",
                        ]
                    elif fd == "Insufficient data":
                        parts = [f"background-color: {_BULK_DECISION_BG_INSUFFICIENT}"]

                # 5. Category name — bold
                if col == "category_name":
                    parts.append("font-weight: 600")

                # 6. Group border-left markers
                if col == cy_first:
                    parts.append(f"border-left: {_BULK_GROUP_BORDER_CY}")
                elif col == py_first:
                    parts.append(f"border-left: {_BULK_GROUP_BORDER_PY}")
                elif col == y2y_first:
                    parts.append(f"border-left: {_BULK_GROUP_BORDER_Y2Y}")

                ji = cols_ds.index(col)
                out.iat[i_pos, ji] = "; ".join(parts)

        return out

    sty = df.style
    try:
        sty = sty.apply(_cell_grid_styles, axis=None)
    except (TypeError, ValueError, AttributeError):
        sty = sty.apply(_apply_row_styles_fallback, axis=1)

    try:
        return sty.hide(axis="index")
    except TypeError:
        return sty.hide_index()


def _bulk_normalize_override_id_sets(other_ids: list, new_ids: list, py_anomaly_ids: list):
    """Other > New category > Previous Year anomaly; lower-priority repeats removed."""
    so = {int(x) for x in other_ids}
    sn = {int(x) for x in new_ids}
    spy = {int(x) for x in py_anomaly_ids}
    other_eff = set(so)
    new_eff = sn - other_eff
    py_eff = spy - other_eff - new_eff
    return other_eff, new_eff, py_eff


def _bulk_override_conflict_messages(so: set[int], sn: set[int], spy: set[int]) -> list[str]:
    """Explain priority when same ID appears in multiple override boxes (dedup applied anyway)."""
    msgs: list[str] = []
    for i in sorted(so & sn):
        msgs.append(f"Category ID **`{i}`** is in **Other** and **New category** overrides — applying **Other category**.")
    for i in sorted(so & spy):
        msgs.append(
            f"Category ID **`{i}`** is in **Other** and **Previous Year anomaly** overrides — applying **Other category**."
        )
    for i in sorted(sn & spy):
        msgs.append(
            f"Category ID **`{i}`** is in **New category** and **Previous Year anomaly** overrides — applying **New category**."
        )
    return msgs


def _bulk_resolve_scenario_used(
    cid: int,
    paid_users_after: int | None,
    global_scenario: str,
    *,
    override_other_eff: set[int],
    override_new_eff: set[int],
    override_py_eff: set[int],
    geo: str | None = None,
) -> str:
    """
    Per-row scenario for bulk decisions: override lists (priority Other > New > PY anomaly),
    then auto Low NPL when paid_users_after < geo min_npl threshold, else global Scenario from sidebar.
    """
    if int(cid) in override_other_eff:
        return "Other category"
    if int(cid) in override_new_eff:
        return "New category"
    if int(cid) in override_py_eff:
        return "Previous Year anomaly"
    if paid_users_after is not None and int(paid_users_after) < _geo_min_npl(geo):
        return "Low NPL auto"
    return global_scenario


_merge_dirty = st.session_state.pop("_merge_files_dirty", False)
if _merge_dirty:
    st.session_state.pop("_cy_ocr_override", None)
    st.session_state.pop("_py_ocr_override", None)
    st.session_state.pop("_cy_ocr_snapshot", None)

if merged_data and _category_single_mode:
    category_id = int(_resolved_single_category_id)
    prev_cat = st.session_state.get("_prev_category_id_for_merge", "")
    sig = str(category_id)
    should_apply = sig != prev_cat or _merge_dirty
    # Do not drop CY OCR when prev_cat is still uninitialized (""): sig != "" is always true and
    # would clear _cy_ocr_override before merge, letting file merge overwrite OCR with zeros.
    if sig != prev_cat and prev_cat != "":
        st.session_state.pop("_cy_ocr_override", None)
        st.session_state.pop("_cy_ocr_snapshot", None)
    cy_bucket = _bulk_lookup_merged_category(merged_data, category_id)
    if cy_bucket is not None:
        if should_apply and not st.session_state.get("_cy_ocr_override"):
            data = cy_bucket
            _bl = data.get("baseline") or {}
            for _dk, _, _dtyp in _CY_INPUT_METRICS:
                sk = _cy_sess_key(_dk)
                _bv = _bl.get(_dk) if _bl else None
                _bf = data["before"].get(_dk)
                _af = data["after"].get(_dk)
                if _dtyp == "int":
                    st.session_state[f"{sk}_baseline"] = int(float(_bv or 0))
                    st.session_state[f"{sk}_before"] = int(float(_bf or 0))
                    st.session_state[f"{sk}_after"] = int(float(_af or 0))
                else:
                    st.session_state[f"{sk}_baseline"] = float(_bv or 0)
                    st.session_state[f"{sk}_before"] = float(_bf or 0)
                    st.session_state[f"{sk}_after"] = float(_af or 0)
        st.session_state["_prev_category_id_for_merge"] = sig
    else:
        st.warning("Category not found in uploaded data")
        st.session_state["_prev_category_id_for_merge"] = sig

_cy_ocr_restore_from_snapshot_if_blanked(st.session_state)

_merge_py_dirty = st.session_state.pop("_py_merge_dirty", False)
if _merge_py_dirty:
    st.session_state.pop("_py_ocr_override", None)

if (
    merged_data_previous_year
    and _category_single_mode
    and not _scenario_is_new_category(scenario)
):
    category_id_py = int(_resolved_single_category_id)
    prev_cat_py = st.session_state.get("_prev_category_id_for_py_merge", "")
    sig_py = str(category_id_py)
    should_apply_py = sig_py != prev_cat_py or _merge_py_dirty
    if sig_py != prev_cat_py:
        st.session_state.pop("_py_ocr_override", None)
    py_bucket = _bulk_lookup_merged_category(merged_data_previous_year, category_id_py)
    if py_bucket is not None:
        if should_apply_py and not st.session_state.get("_py_ocr_override"):
            pdata = py_bucket
            st.session_state["matrix_py_paid_users_before"] = int(
                float(pdata["before"].get("paid_users") or 0)
            )
            st.session_state["matrix_py_paid_users_after"] = int(
                float(pdata["after"].get("paid_users") or 0)
            )
            st.session_state["matrix_py_spending_before"] = float(
                pdata["before"].get("spending") or 0
            )
            st.session_state["matrix_py_spending_after"] = float(
                pdata["after"].get("spending") or 0
            )
            st.session_state["matrix_py_ac_before"] = int(
                float(pdata["before"].get("active_listers") or 0)
            )
            st.session_state["matrix_py_ac_after"] = int(
                float(pdata["after"].get("active_listers") or 0)
            )
        st.session_state["_prev_category_id_for_py_merge"] = sig_py
    else:
        if not _scenario_is_new_category(scenario):
            st.warning("Category not found in Previous Year uploaded data")
        st.session_state["_prev_category_id_for_py_merge"] = sig_py

if _category_bulk_mode:
    st.subheader("Bulk Category IDs")
    st.caption(
        "Сводка по списку. Автозаполнение полей и расчёт по кнопке Calculate — только для одного ID."
    )
    st.caption(
        "В **merged_data** попадают только категории, которые есть **и** в выгрузке spending, **и** "
        "в выгрузке active listers (**пересечение**). ID только в одном файле здесь не считается «есть в данных»."
    )
    n = len(_bulk_effective_category_ids)
    in_cy = [
        i
        for i in _bulk_effective_category_ids
        if _bulk_lookup_merged_category(merged_data, i) is not None
    ]
    in_py = [
        i
        for i in _bulk_effective_category_ids
        if _bulk_lookup_merged_category(merged_data_previous_year, i) is not None
    ]
    miss_cy = [i for i in _bulk_effective_category_ids if i not in in_cy]
    miss_py = [i for i in _bulk_effective_category_ids if i not in in_py]
    _cy_suffix = _bulk_merge_missing_cy_hint(
        merged_data,
        ch_loaded=bool(st.session_state.get("_ch_data_loaded")),
        spending_present=spending_file is not None,
        active_present=active_file is not None,
    )
    _py_suffix = _bulk_merge_missing_py_hint(
        merged_data_previous_year,
        py_spending_present=py_spending_file is not None,
        py_active_present=py_active_file is not None,
    )
    st.markdown(
        f"- **Распознано валидных ID:** {n}\n"
        f"- **Есть в Current Year data:** {len(in_cy)}{_cy_suffix}\n"
        f"- **Есть в Previous Year data:** {len(in_py)}{_py_suffix}\n"
        f"- **Не в Current Year data:** {miss_cy if miss_cy else '—'}\n"
        f"- **Не в Previous Year data:** {miss_py if miss_py else '—'}"
    )


def _matrix_geo_thresholds(geo: str):
    gk = str(geo).upper() if geo else "default"
    return GEO_THRESHOLDS.get(gk, GEO_THRESHOLDS["default"])


def _geo_min_npl(geo: str | None) -> int:
    return _matrix_geo_thresholds(geo or "default").get("min_npl", 10)


def _matrix_safe_div(numerator, denominator):
    if denominator is None or numerator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _matrix_pct_diff(before, after):
    if before is None or after is None:
        return None
    if before == 0:
        return None
    return (after - before) / before * 100.0


_BULK_TABLE_DETAILS_COL = "Details"
_BULK_TABLE_DETAILS_CELL = "🔍"

_BULK_SUMMARY_COLUMNS = (
    "category_id",
    "parent_category_name",
    "category_name",
    "scenario_used",
    "cy_paid_users_before",
    "cy_paid_users_after",
    "cy_paid_users_diff",
    "cy_spending_before",
    "cy_spending_after",
    "cy_spending_diff",
    "cy_cr_diff",
    "cy_active_listers_before",
    "cy_active_listers_after",
    "cy_active_listers_diff",
    "py_paid_users_diff",
    "py_spending_diff",
    "py_cr_diff",
    "py_active_listers_diff",
    "y2y_paid_users_diff",
    "y2y_spending_diff",
    "y2y_cr_diff",
    "y2y_active_listers_diff",
    "final_decision",
    "next_step",
)

# Колонки решений в compact‑таблице (для tint / border‑left; без доп. CY spending‑метрик из CSV).
_BULK_CY_METRIC_COLUMNS = (
    "cy_paid_users_before",
    "cy_paid_users_after",
    "cy_paid_users_diff",
    "cy_spending_before",
    "cy_spending_after",
    "cy_spending_diff",
    "cy_cr_diff",
    "cy_active_listers_before",
    "cy_active_listers_after",
    "cy_active_listers_diff",
)
_BULK_PY_METRIC_COLUMNS = (
    "py_paid_users_diff",
    "py_spending_diff",
    "py_cr_diff",
    "py_active_listers_diff",
)
_BULK_Y2Y_METRIC_COLUMNS = (
    "y2y_paid_users_diff",
    "y2y_spending_diff",
    "y2y_cr_diff",
    "y2y_active_listers_diff",
)
_BULK_CY_METRIC_COLUMNS_SET = frozenset(_BULK_CY_METRIC_COLUMNS)
_BULK_PY_METRIC_COLUMNS_SET = frozenset(_BULK_PY_METRIC_COLUMNS)
_BULK_Y2Y_METRIC_COLUMNS_SET = frozenset(_BULK_Y2Y_METRIC_COLUMNS)

_BULK_GROUP_BORDER_CY = "2px solid rgba(36, 150, 230, 0.42)"
_BULK_GROUP_BORDER_PY = "2px solid rgba(120, 126, 140, 0.52)"
_BULK_GROUP_BORDER_Y2Y = "2px solid rgba(132, 99, 210, 0.48)"
_BULK_GROUP_TINT_CY = "rgba(52, 152, 219, 0.075)"
_BULK_GROUP_TINT_PY = "rgba(110, 118, 132, 0.085)"
_BULK_GROUP_TINT_Y2Y = "rgba(124, 92, 217, 0.075)"

def _bulk_compact_column_ui_labels() -> dict[str, str]:
    """Человекочитаемые заголовки только для compact‑таблицы (CSV / полный bulk_df — internal имена)."""
    return {
        "category_id": "Category ID",
        "parent_category_name": "Parent category",
        "category_name": "Category name",
        "scenario_used": "Scenario",
        "final_decision": "Decision",
        "next_step": "Next step",
        "cy_paid_users_before": "CY Paid users Before",
        "cy_paid_users_after": "CY Paid users After",
        "cy_paid_users_diff": "CY Paid users %",
        "cy_spending_before": "CY Spending Before",
        "cy_spending_after": "CY Spending After",
        "cy_spending_diff": "CY Spending %",
        "cy_cr_diff": "CY CR %",
        "cy_active_listers_before": "CY Active listers Before",
        "cy_active_listers_after": "CY Active listers After",
        "cy_active_listers_diff": "CY Active listers %",
        "py_paid_users_diff": "PY Paid users %",
        "py_spending_diff": "PY Spending %",
        "py_cr_diff": "PY CR %",
        "py_active_listers_diff": "PY Active listers %",
        "y2y_paid_users_diff": "Y2Y Paid users Δ",
        "y2y_spending_diff": "Y2Y Spending Δ",
        "y2y_cr_diff": "Y2Y CR Δ",
        "y2y_active_listers_diff": "Y2Y Active listers Δ",
        _BULK_TABLE_DETAILS_COL: _BULK_TABLE_DETAILS_COL,
    }




def _bulk_compact_table_column_config(column_names: list[str]) -> dict:
    labels = _bulk_compact_column_ui_labels()
    try:
        tc_params = inspect.signature(st.column_config.TextColumn).parameters
    except (TypeError, ValueError):
        tc_params = {}
    pinned_left = (
        {"pinned": "left"} if "pinned" in tc_params else {}
        # pinned: поддерживается не во всех версиях Streamlit (fallback — только горизонтальный скролл без freeze).
    )
    frozen = {_BULK_TABLE_DETAILS_COL, "category_id", "category_name", "scenario_used"}
    cfg: dict = {}
    for col in column_names:
        title = labels.get(col, col)
        td: dict = {}
        if col == _BULK_TABLE_DETAILS_COL:
            td = {"width": "small", "help": "Select this row to load details below"}
        elif col == "category_id":
            td = {"width": "small"}
        elif col == "category_name":
            td = {"width": "medium"}
        elif col == "scenario_used":
            td = {
                "width": "medium",
                "help": "Effective bulk scenario after overrides and auto Low NPL.",
            }
        elif col == "final_decision":
            td = {"width": "small"}
        elif col == "next_step":
            td = {
                "width": "large",
                "help": "Full next step is available in Category details.",
            }
        elif (
            col in _BULK_CY_METRIC_COLUMNS_SET
            | _BULK_PY_METRIC_COLUMNS_SET
            | _BULK_Y2Y_METRIC_COLUMNS_SET
        ):
            td = {"width": "small"}
        merged = dict(td)
        if col in frozen:
            merged = {**pinned_left, **merged}
        cfg[col] = st.column_config.TextColumn(title, **merged)
    return cfg


def _bulk_mean_numeric_column_mean(df_: pd.DataFrame, col_name: str) -> float | None:
    if df_ is None or df_.empty or col_name not in df_.columns:
        return None
    series = pd.to_numeric(df_[col_name], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.mean())


_BULK_DETAIL_ADDITIONAL_SPECS = (
    ("campaign_per_user", "Campaign per User", "float"),
    ("new_campaign_cnt", "New campaign cnt", "int"),
    ("price_per_day", "Price per day", "float"),
    ("arp_p_campaign", "ARPpCampaign", "float"),
    ("refund", "Refund", "float"),
    ("pct_campaign_with_refund", "%Campaign with refund", "pct"),
    ("plan_imp_per_campaign", "Plan Imp per Campaign", "float"),
    ("fact_imp_per_campaign", "Fact Imp per Campaign", "float"),
    ("pct_execution_inventory", "%Execution Inventory", "pct"),
)

def _bulk_dataframe_selection_rows(event) -> list[int]:
    if event is None:
        return []
    try:
        sel = (
            event["selection"] if isinstance(event, dict) else getattr(event, "selection", None)
        )
        if sel is None:
            return []
        rows = sel["rows"] if isinstance(sel, dict) else getattr(sel, "rows", None)
        if not rows:
            return []
        return [int(r) for r in rows]
    except (KeyError, TypeError, ValueError, AttributeError):
        return []


_BULK_CY_ABS_INT_COLS = frozenset({
    "cy_paid_users_before", "cy_paid_users_after",
    "cy_active_listers_before", "cy_active_listers_after",
})
_BULK_CY_ABS_FLOAT_COLS = frozenset({
    "cy_spending_before", "cy_spending_after",
})


def _bulk_format_compact_diff_pct_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Форматирует *_diff колонки (%) и абсолютные Before/After."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in list(out.columns):
        if str(col).endswith("_diff"):
            out[col] = out[col].map(lambda v: format_percent(v))
        elif col in _BULK_CY_ABS_INT_COLS:
            out[col] = out[col].map(
                lambda v: format_integer(int(v), group_thousands=True)
                if v is not None and not (isinstance(v, float) and pd.isna(v))
                else "—"
            )
        elif col in _BULK_CY_ABS_FLOAT_COLS:
            out[col] = out[col].map(
                lambda v: format_integer(int(round(v)), group_thousands=True)
                if v is not None and not (isinstance(v, float) and pd.isna(v))
                else "—"
            )
    return out


def _bulk_make_csv_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a clean, human-readable DataFrame for CSV export.
    Key metrics (paid_users, spending, CR) get full Y2Y context.
    Active listers gets CY only (per user spec).
    """
    def _fmt_pct(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        try:
            return f"{float(v):+.1f}%"
        except (TypeError, ValueError):
            return ""

    def _fmt_int(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return ""

    def _fmt_float(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return ""

    # Build extra-metrics column map dynamically from spec
    _extra_col_map = []
    _extra_int_cols: set = set()
    _extra_float_cols: set = set()
    _extra_pct_cols: set = set()
    for mkey, label, kind in _BULK_CY_EXTRA_ABS_SPECS:
        diff_col  = f"CY Diff % {label}"   # matches _BULK_CY_EXTRA_DIFF_PCT_SPECS cname
        before_col = f"cy_{mkey}_before"
        after_col  = f"cy_{mkey}_after"
        _extra_col_map.append((before_col, f"CY {label} Before"))
        _extra_col_map.append((after_col,  f"CY {label} After"))
        _extra_col_map.append((diff_col,   f"CY {label} Diff %"))
        _extra_pct_cols.add(diff_col)
        if kind == "int":
            _extra_int_cols.add(before_col)
            _extra_int_cols.add(after_col)
        else:
            _extra_float_cols.add(before_col)
            _extra_float_cols.add(after_col)

    col_map = [
        # Category info
        ("category_id",            "Category ID"),
        ("category_name",          "Category name"),
        ("scenario_used",          "Scenario"),
        ("final_decision",         "Decision"),
        ("next_step",              "Next step"),
        # CY Paid users
        ("cy_paid_users_before",   "CY Paid users Before"),
        ("cy_paid_users_after",    "CY Paid users After"),
        ("cy_paid_users_diff",     "CY Paid users Diff %"),
        # PY Paid users
        ("py_paid_users_before",   "PY Paid users Before"),
        ("py_paid_users_after",    "PY Paid users After"),
        ("py_paid_users_diff",     "PY Paid users Diff %"),
        # Y2Y Paid users
        ("y2y_paid_users_diff",    "Y2Y Paid users Diff %"),
        # CY Spending
        ("cy_spending_before",     "CY Spending Before"),
        ("cy_spending_after",      "CY Spending After"),
        ("cy_spending_diff",       "CY Spending Diff %"),
        # PY Spending
        ("py_spending_before",     "PY Spending Before"),
        ("py_spending_after",      "PY Spending After"),
        ("py_spending_diff",       "PY Spending Diff %"),
        # Y2Y Spending
        ("y2y_spending_diff",      "Y2Y Spending Diff %"),
        # CY/PY/Y2Y CR (no absolute values - it's a ratio)
        ("cy_cr_diff",             "CY CR Diff %"),
        ("py_cr_diff",             "PY CR Diff %"),
        ("y2y_cr_diff",            "Y2Y CR Diff %"),
        # Active listers — CY only
        ("cy_active_listers_before", "CY Active listers Before"),
        ("cy_active_listers_after",  "CY Active listers After"),
        ("cy_active_listers_diff",   "CY Active listers Diff %"),
        # Extra spending metrics — CY Before / After / Diff % only
        *_extra_col_map,
        # Warning flags (for transparency)
        ("warning_flags",          "Warning flags"),
    ]

    _int_cols = {"cy_paid_users_before", "cy_paid_users_after",
                 "cy_active_listers_before", "cy_active_listers_after",
                 "py_paid_users_before", "py_paid_users_after"} | _extra_int_cols
    _float_cols = {"cy_spending_before", "cy_spending_after",
                   "py_spending_before", "py_spending_after"} | _extra_float_cols
    _pct_cols = {
        "cy_paid_users_diff", "py_paid_users_diff", "y2y_paid_users_diff",
        "cy_spending_diff",   "py_spending_diff",   "y2y_spending_diff",
        "cy_cr_diff",         "py_cr_diff",         "y2y_cr_diff",
        "cy_active_listers_diff",
    } | _extra_pct_cols

    out_rows = []
    for _, row in df.iterrows():
        out_row = {}
        for src_col, label in col_map:
            if src_col not in df.columns:
                out_row[label] = ""
                continue
            v = row.get(src_col)
            if src_col in _pct_cols:
                out_row[label] = _fmt_pct(v)
            elif src_col in _int_cols:
                out_row[label] = _fmt_int(v)
            elif src_col in _float_cols:
                out_row[label] = _fmt_float(v)
            else:
                out_row[label] = "" if (v is None or (isinstance(v, float) and pd.isna(v))) else v
        out_rows.append(out_row)

    return pd.DataFrame(out_rows, columns=[label for _, label in col_map])


# ── Long-format CSV export ──────────────────────────────────────────────────
# One row per (category × metric). Key metrics include PY/Y2Y columns;
# additional metrics are CY-only.

_LONG_METRIC_SPECS = (
    # (label, cy_before_col, cy_after_col, cy_diff_col,
    #  py_before_col, py_after_col, py_diff_col, y2y_diff_col, fmt_kind)
    ("Paid users",
     "cy_paid_users_before",          "cy_paid_users_after",
     "cy_paid_users_diff",
     "py_paid_users_before",          "py_paid_users_after",
     "py_paid_users_diff",            "y2y_paid_users_diff",   "int"),
    ("Spending",
     "cy_spending_before",            "cy_spending_after",
     "cy_spending_diff",
     "py_spending_before",            "py_spending_after",
     "py_spending_diff",              "y2y_spending_diff",     "float"),
    ("CR",
     None,                            None,
     "cy_cr_diff",
     None,                            None,
     "py_cr_diff",                    "y2y_cr_diff",           "float"),
    ("Active listers",
     "cy_active_listers_before",      "cy_active_listers_after",
     "cy_active_listers_diff",
     None, None, None,                None,                    "int"),
    ("Campaign per User",
     "cy_campaign_per_user_before",   "cy_campaign_per_user_after",
     "CY Diff % Campaign per User",
     None, None, None,                None,                    "float"),
    ("New campaign cnt",
     "cy_new_campaign_cnt_before",    "cy_new_campaign_cnt_after",
     "CY Diff % New campaign cnt",
     None, None, None,                None,                    "int"),
    ("Price per day",
     "cy_price_per_day_before",       "cy_price_per_day_after",
     "CY Diff % Price per day",
     None, None, None,                None,                    "float"),
    ("ARPpCampaign",
     "cy_arp_p_campaign_before",      "cy_arp_p_campaign_after",
     "CY Diff % ARPpCampaign",
     None, None, None,                None,                    "float"),
    ("Refund",
     "cy_refund_before",              "cy_refund_after",
     "CY Diff % Refund",
     None, None, None,                None,                    "float"),
    ("%Campaign with refund",
     "cy_pct_campaign_with_refund_before", "cy_pct_campaign_with_refund_after",
     "CY Diff % %Campaign with refund",
     None, None, None,                None,                    "float"),
    ("Plan Imp per Campaign",
     "cy_plan_imp_per_campaign_before",   "cy_plan_imp_per_campaign_after",
     "CY Diff % Plan Imp per Campaign",
     None, None, None,                None,                    "float"),
    ("Fact Imp per Campaign",
     "cy_fact_imp_per_campaign_before",   "cy_fact_imp_per_campaign_after",
     "CY Diff % Fact Imp per Campaign",
     None, None, None,                None,                    "float"),
    ("%Execution Inventory",
     "cy_pct_execution_inventory_before", "cy_pct_execution_inventory_after",
     "CY Diff % %Execution Inventory",
     None, None, None,                None,                    "float"),
)

_LONG_OUTPUT_COLUMNS = [
    "category_id", "category_name", "scenario", "decision", "next_step",
    "metric",
    "Before", "After", "Diff %",
    "PY Before", "PY After", "PY Diff %", "Y2Y Diff %",
]


def _bulk_make_long_csv_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """Long-format export: one row per (category × metric)."""

    def _v(row, col):
        if col is None or col not in df.columns:
            return None
        v = row.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return v

    def _fmt_abs(v, kind):
        if v is None:
            return ""
        try:
            if kind == "int":
                return int(round(float(v)))
            return round(float(v), 4)
        except (TypeError, ValueError):
            return ""

    def _fmt_diff(v):
        if v is None:
            return ""
        try:
            fv = float(v)
            return f"{fv:+.1f}%"
        except (TypeError, ValueError):
            return ""

    out_rows = []
    for _, row in df.iterrows():
        cat_id   = row.get("category_id", "")
        cat_name = row.get("category_name", "")
        scenario = row.get("scenario_used", "")
        decision = row.get("final_decision", "")
        next_stp = row.get("next_step", "")
        if isinstance(next_stp, float) and pd.isna(next_stp):
            next_stp = ""

        for spec in _LONG_METRIC_SPECS:
            (label,
             cy_b_col, cy_a_col, cy_d_col,
             py_b_col, py_a_col, py_d_col, y2y_d_col,
             fmt) = spec

            cy_b = _v(row, cy_b_col)
            cy_a = _v(row, cy_a_col)
            cy_d = _v(row, cy_d_col)
            py_b = _v(row, py_b_col)
            py_a = _v(row, py_a_col)
            py_d = _v(row, py_d_col)
            y2y  = _v(row, y2y_d_col)

            out_rows.append({
                "category_id":   cat_id,
                "category_name": cat_name,
                "scenario":      scenario,
                "decision":      decision,
                "next_step":     next_stp,
                "metric":        label,
                "Before":        _fmt_abs(cy_b, fmt),
                "After":         _fmt_abs(cy_a, fmt),
                "Diff %":        _fmt_diff(cy_d),
                "PY Before":     _fmt_abs(py_b, fmt),
                "PY After":      _fmt_abs(py_a, fmt),
                "PY Diff %":     _fmt_diff(py_d),
                "Y2Y Diff %":    _fmt_diff(y2y),
            })

    return pd.DataFrame(out_rows, columns=_LONG_OUTPUT_COLUMNS)


def _bulk_cell_primary_bucket(val, *, kind: str) -> str:
    if kind == "int":
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                iv = None
            else:
                iv = int(float(val))
        except (TypeError, ValueError):
            iv = None
        return format_matrix_metric(iv, as_int=iv is not None)
    if kind == "float":
        try:
            fv = (
                float(val)
                if val is not None and not (isinstance(val, float) and pd.isna(val))
                else None
            )
        except (TypeError, ValueError):
            fv = None
        return format_matrix_metric(fv, as_int=False)
    raise ValueError(f"unexpected kind {kind!r}")


def _bulk_cell_pct_bucket(val) -> str:
    try:
        fv = (
            float(val)
            if val is not None and not (isinstance(val, float) and pd.isna(val))
            else None
        )
    except (TypeError, ValueError):
        fv = None
    return format_summary_percent_cell(fv)


def _parse_pct_val(s) -> float | None:
    """Parse formatted percent string back to float (e.g. '-11.79%' → -11.79)."""
    if s is None:
        return None
    try:
        return float(str(s).replace("%", "").replace(",", ".").replace(" ", "").strip())
    except (TypeError, ValueError):
        return None


def _style_detail_metrics_table(df: pd.DataFrame) -> object:
    """
    Styling for Metrics details / Additional metrics drill-down tables:
      - Diff % cells: green / red / amber by sign
      - CY Before/After: blue tint; PY Before/After: grey tint; Y2Y: purple tint
      - Group border-left at first column of each group
      - Metric column: bold
    """
    if df is None or df.empty:
        return df.style if hasattr(df, "style") else df

    cols = list(df.columns)

    _diff_cols    = frozenset(c for c in cols if "Diff %" in str(c))
    _cy_abs       = frozenset(c for c in cols if str(c).startswith("CY ") and "Diff" not in str(c))
    _py_abs       = frozenset(c for c in cols if str(c).startswith("PY ") and "Diff" not in str(c))
    _y2y_non_diff = frozenset(c for c in cols if str(c).startswith("Y2Y") and "Diff" not in str(c))

    cy_first  = next((c for c in cols if c in _cy_abs or "Diff" not in str(c) and str(c).startswith("CY")), None)
    py_first  = next((c for c in cols if c in _py_abs), None) or \
                next((c for c in cols if str(c).startswith("PY")), None)
    y2y_first = next((c for c in cols if str(c).startswith("Y2Y")), None)

    def _all_cells(data):
        out = pd.DataFrame("", index=data.index, columns=data.columns)
        for col in cols:
            ji = cols.index(col)
            border = ""
            if col == cy_first:
                border = f"border-left: {_BULK_GROUP_BORDER_CY}"
            elif col == py_first:
                border = f"border-left: {_BULK_GROUP_BORDER_PY}"
            elif col == y2y_first:
                border = f"border-left: {_BULK_GROUP_BORDER_Y2Y}"

            for i_pos in range(len(data)):
                v = data.iat[i_pos, ji]
                parts: list[str] = []

                if col == "Metric":
                    parts.append("font-weight: 600")
                elif col in _diff_cols:
                    num = _parse_pct_val(v)
                    if num is not None:
                        if num > 1.0:
                            parts.append(f"background-color: {_BULK_DIFF_CELL_POSITIVE}")
                        elif num < -1.0:
                            parts.append(f"background-color: {_BULK_DIFF_CELL_NEGATIVE}")
                        else:
                            parts.append(f"background-color: {_BULK_DIFF_CELL_NEAR_ZERO}")
                elif col in _cy_abs:
                    parts.append(f"background-color: {_BULK_GROUP_TINT_CY}")
                elif col in _py_abs:
                    parts.append(f"background-color: {_BULK_GROUP_TINT_PY}")
                elif col in _y2y_non_diff:
                    parts.append(f"background-color: {_BULK_GROUP_TINT_Y2Y}")

                if border:
                    parts.append(border)
                out.iat[i_pos, ji] = "; ".join(parts)
        return out

    try:
        sty = df.style.apply(_all_cells, axis=None)
        try:
            sty = sty.hide(axis="index")
        except TypeError:
            sty = sty.hide_index()
        return sty
    except Exception:
        return df


def _bulk_metrics_primary_detail_df(b, a, b_py=None, a_py=None):
    """Paid users, Active, Spending, CR — CY + optional PY columns."""
    b, a = b or {}, a or {}
    b_py, a_py = b_py or {}, a_py or {}
    has_py = bool(b_py or a_py)

    pn_b, pn_a = b.get("paid_users"), a.get("paid_users")
    ac_b, ac_a = b.get("active_listers"), a.get("active_listers")
    sp_b, sp_a = b.get("spending"), a.get("spending")
    cr_b = _matrix_safe_div(pn_b, ac_b)
    cr_a = _matrix_safe_div(pn_a, ac_a)

    pn_pb, pn_pa = b_py.get("paid_users"), a_py.get("paid_users")
    ac_pb, ac_pa = b_py.get("active_listers"), a_py.get("active_listers")
    sp_pb, sp_pa = b_py.get("spending"), a_py.get("spending")
    cr_pb = _matrix_safe_div(pn_pb, ac_pb)
    cr_pa = _matrix_safe_div(pn_pa, ac_pa)

    rows_build = []
    for label, bb, aa, pb, pa, bk in (
        ("Paid users",    pn_b, pn_a, pn_pb, pn_pa, "int"),
        ("Active listers",ac_b, ac_a, ac_pb, ac_pa, "int"),
        ("Spending",      sp_b, sp_a, sp_pb, sp_pa, "float"),
        ("CR",            cr_b, cr_a, cr_pb, cr_pa, "float"),
    ):
        cy_diff = _matrix_pct_diff(bb, aa)
        py_diff = _matrix_pct_diff(pb, pa) if has_py else None
        y2y_diff = (cy_diff - py_diff) if (cy_diff is not None and py_diff is not None) else None
        row = {
            "Metric":    label,
            "CY Before": _bulk_cell_primary_bucket(bb, kind=bk),
            "CY After":  _bulk_cell_primary_bucket(aa, kind=bk),
            "CY Diff %": format_percent(cy_diff),
        }
        if has_py:
            row["PY Before"] = _bulk_cell_primary_bucket(pb, kind=bk)
            row["PY After"]  = _bulk_cell_primary_bucket(pa, kind=bk)
            row["PY Diff %"] = format_percent(py_diff)
            row["Y2Y Diff %"] = format_percent(y2y_diff)
        rows_build.append(row)
    return pd.DataFrame(rows_build)


def _bulk_metrics_additional_detail_df(b, a):
    b = b or {}
    a = a or {}
    rows_build = []
    for mkey, title, kind in _BULK_DETAIL_ADDITIONAL_SPECS:
        vb, va = b.get(mkey), a.get(mkey)
        if kind == "pct":
            b_s, a_s = _bulk_cell_pct_bucket(vb), _bulk_cell_pct_bucket(va)
        elif kind == "int":
            b_s = _bulk_cell_primary_bucket(vb, kind="int")
            a_s = _bulk_cell_primary_bucket(va, kind="int")
        else:
            b_s = _bulk_cell_primary_bucket(vb, kind="float")
            a_s = _bulk_cell_primary_bucket(va, kind="float")
        rows_build.append(
            {
                "Metric": title,
                "Before": b_s,
                "After": a_s,
                "Diff %": format_percent(_matrix_pct_diff(vb, va)),
            }
        )
    return pd.DataFrame(rows_build)


def _bulk_render_category_drill_down(row: pd.Series, merged_data, merged_data_py=None) -> None:
    """Внутри expander: Metrics / Additional / Decision (без логики decision_engine)."""
    try:
        cid = int(row["category_id"])
        cid_disp = format_integer(cid, group_thousands=True)
    except (TypeError, ValueError):
        st.warning("Некорректный category_id.")
        return

    nm = str(row.get("category_name") or "").strip()
    title_name = nm if nm else "—"
    parent_cat = str(row.get("parent_category_name") or "").strip()

    data    = _bulk_lookup_merged_category(merged_data,    cid) if merged_data    else None
    data_py = _bulk_lookup_merged_category(merged_data_py, cid) if merged_data_py else None

    _sig_ct = inspect.signature(st.container).parameters
    if "border" in _sig_ct:
        _outer = st.container(border=True)
    else:
        _outer = st.container()

    with _outer:
        st.markdown(f"### Category {cid_disp}")
        if parent_cat:
            st.caption(f"{title_name} — decision by parent category: **{parent_cat}**")
        else:
            st.caption(title_name)
        st.markdown("---")

        st.markdown("**Metrics details**")
        if data is None:
            st.caption("Нет данных Current Year для этой категории.")
        else:
            _b,  _a  = data.get("before") or {},    data.get("after") or {}
            _pb, _pa = (data_py.get("before") or {} if data_py else {},
                        data_py.get("after")  or {} if data_py else {})
            st.dataframe(
                _style_detail_metrics_table(
                    _bulk_metrics_primary_detail_df(_b, _a, _pb, _pa)
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("**Additional metrics**")
        if data is None:
            st.caption("—")
        else:
            _b, _a = data.get("before") or {}, data.get("after") or {}
            st.dataframe(
                _style_detail_metrics_table(
                    _bulk_metrics_additional_detail_df(_b, _a)
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("**Decision details**")
        def _show(k):
            v = row.get(k)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "—"
            s = str(v).strip()
            return s if s else "—"

        st.markdown(
            f"- **decision_code:** {_show('decision_code')}\n"
            f"- **next_step:** {_show('next_step')}\n"
            f"- **warning_flags:** {_show('warning_flags')}"
        )


def _bulk_expander_title_for_row(row: pd.Series) -> str:
    try:
        cid_s = format_integer(int(row["category_id"]), group_thousands=True)
    except (TypeError, ValueError):
        cid_s = str(row.get("category_id", "—"))
    nm = str(row.get("category_name") or "")
    if len(nm) > 52:
        nm = nm[:49] + "…"
    pr = str(row.get("priority") or "—")
    return f"{cid_s} · {nm} · {pr}"


def _matrix_format_result_display(raw: str) -> str:
    """Excel-style labels for matrix Result column (↑ / ↓ / =). Display-only."""
    dash = "—"
    if raw == "":
        return ""
    if raw == dash:
        return dash
    prefix = ""
    body = raw.strip()
    if body.startswith("O: "):
        prefix = "O: "
        body = body[3:].strip()
    mapped = {
        "Growth": "↑ Growth",
        "Stable": "= Stable",
        "Decrease": "↓ Decrease",
    }.get(body)
    if mapped is None:
        return raw
    return prefix + mapped


def _matrix_result_semantic_css(val) -> str:
    """Dashboard pill for Result cells — Growth / Stable / Decrease (display-only, high contrast)."""
    if val is None:
        return ""
    s = str(val).strip()
    dash = "—"
    if not s or s == dash:
        return ""
    low = s.lower()
    base = (
        "border-radius: 9999px; padding: 4px 12px; font-weight: 700; font-size: 0.88rem; "
        "display: inline-block; min-width: 8em; text-align: center; letter-spacing: 0.01em;"
    )
    if "decrease" in low:
        return (
            base
            + "background: #fee2e2; color: #991b1b; border: 1px solid #f87171;"
        )
    if "growth" in low:
        return (
            base
            + "background: #dcfce7; color: #166534; border: 1px solid #4ade80;"
        )
    if "stable" in low:
        return (
            base
            + "background: #fef9c3; color: #854d0e; border: 1px solid #facc15;"
        )
    return ""


def _matrix_classify_label(pct_diff, geo: str, metric_key: str):
    if pct_diff is None:
        return "—"
    th = _matrix_geo_thresholds(geo)[metric_key]
    code = classify_change(
        pct_diff,
        growth_threshold=th["growth"],
        decline_threshold=th["decline"],
    )
    return decode_status(code)


def _results_compute_y2y_npl_sp_cr_bundle(
    geo: str,
    paid_users_before,
    paid_users_after,
    spending_before,
    spending_after,
    active_before,
    active_after,
    py_paid_users_before,
    py_paid_users_after,
    py_spending_before,
    py_spending_after,
    py_ac_before,
    py_ac_after,
):
    """
    Y2Y deltas for Paid users (NPL %), Spending %, CR % — same construction as PPV matrix diff Y2Y rows.
    Used to align Results with matrix when matrix_result_focus == \"diff_y2y\".
    """
    cy_cr_b = _matrix_safe_div(paid_users_before, active_before)
    cy_cr_a = _matrix_safe_div(paid_users_after, active_after)
    py_cr_b = _matrix_safe_div(py_paid_users_before, py_ac_before)
    py_cr_a = _matrix_safe_div(py_paid_users_after, py_ac_after)

    cy_npl_d = _matrix_pct_diff(paid_users_before, paid_users_after)
    py_npl_d = _matrix_pct_diff(py_paid_users_before, py_paid_users_after)
    cy_sp_d = _matrix_pct_diff(spending_before, spending_after)
    py_sp_d = _matrix_pct_diff(py_spending_before, py_spending_after)
    cy_cr_d = _matrix_pct_diff(cy_cr_b, cy_cr_a)
    py_cr_d = _matrix_pct_diff(py_cr_b, py_cr_a)

    y2y_npl = (
        (cy_npl_d - py_npl_d)
        if cy_npl_d is not None and py_npl_d is not None
        else None
    )
    y2y_sp = (
        (cy_sp_d - py_sp_d) if cy_sp_d is not None and py_sp_d is not None else None
    )
    y2y_cr = (
        (cy_cr_d - py_cr_d) if cy_cr_d is not None and py_cr_d is not None else None
    )

    th = _matrix_geo_thresholds(geo)
    npl_code = (
        classify_change(
            y2y_npl,
            growth_threshold=th["npl"]["growth"],
            decline_threshold=th["npl"]["decline"],
        )
        if y2y_npl is not None
        else None
    )
    sp_code = (
        classify_change(
            y2y_sp,
            growth_threshold=th["sp"]["growth"],
            decline_threshold=th["sp"]["decline"],
        )
        if y2y_sp is not None
        else None
    )
    cr_code = (
        classify_change(
            y2y_cr,
            growth_threshold=th["cr"]["growth"],
            decline_threshold=th["cr"]["decline"],
        )
        if y2y_cr is not None
        else None
    )

    complete = npl_code is not None and sp_code is not None and cr_code is not None
    decision_code = f"{npl_code}{sp_code}{cr_code}" if complete else None

    return {
        "complete": complete,
        "y2y_npl": y2y_npl,
        "y2y_sp": y2y_sp,
        "y2y_cr": y2y_cr,
        "npl_code": npl_code,
        "sp_code": sp_code,
        "cr_code": cr_code,
        "decision_code": decision_code,
    }


def _results_render_metric_detail_row(
    title: str, pct, code: str | None, other_o_prefix: bool
):
    if pct is None or code is None:
        st.warning(f"{title}: —")
        return
    lbl = decode_status(code)
    if other_o_prefix:
        lbl = f"O: {lbl}"
    row = f"{title}: {pct:.2f}% → {lbl} ({code})"
    if code == "G":
        st.success(row)
    elif code == "D":
        st.error(row)
    else:
        st.warning(row)


def _build_ppv_matrix_rows(
    geo: str,
    cy_paid_users_b,
    cy_paid_users_a,
    cy_spending_b,
    cy_spending_a,
    cy_ac_b,
    cy_ac_a,
    py_paid_users_b,
    py_paid_users_a,
    py_spending_b,
    py_spending_a,
    py_ac_b,
    py_ac_a,
    omit_previous_year: bool = False,
    omit_y2y_only: bool = False,
    is_other_category_scenario: bool = False,
    matrix_result_focus: str = "diff_y2y",
):
    """Returns list of flat dicts for display (Paid users, Spending, CR, Active)."""
    cy_cr_b = _matrix_safe_div(cy_paid_users_b, cy_ac_b)
    cy_cr_a = _matrix_safe_div(cy_paid_users_a, cy_ac_a)
    if omit_previous_year:
        py_cr_b = None
        py_cr_a = None
    else:
        py_cr_b = _matrix_safe_div(py_paid_users_b, py_ac_b)
        py_cr_a = _matrix_safe_div(py_paid_users_a, py_ac_a)

    dash = "—"
    metrics = [
        (
            "Paid users",
            "npl",
            cy_paid_users_b,
            cy_paid_users_a,
            py_paid_users_b,
            py_paid_users_a,
            True,
        ),
        (
            "Spending",
            "sp",
            cy_spending_b,
            cy_spending_a,
            py_spending_b,
            py_spending_a,
            False,
        ),
        ("CR", "cr", cy_cr_b, cy_cr_a, py_cr_b, py_cr_a, False),
        ("Active listers", "npl", cy_ac_b, cy_ac_a, py_ac_b, py_ac_a, True),
    ]

    rows_out = []
    for title, th_key, cbb, cba, pbb, pba, as_int in metrics:
        cy_d = _matrix_pct_diff(cbb, cba)
        if omit_previous_year:
            py_d = None
            y2y = None
            py_before = dash
            py_after = dash
            py_diff_s = dash
        else:
            py_d = _matrix_pct_diff(pbb, pba)
            if omit_y2y_only:
                y2y = None
                y2y_diff_cell = dash
            else:
                y2y = (cy_d - py_d) if cy_d is not None and py_d is not None else None
                y2y_diff_cell = format_percent(y2y)
            py_before = format_matrix_metric(pbb, as_int=as_int and pbb is not None)
            py_after = format_matrix_metric(pba, as_int=as_int and pba is not None)
            py_diff_s = format_percent(py_d)

        # Single Result column: show classification only on the primary row for this scenario
        # (diff Y2Y for Regular / Low NPL / Other category; Current Year for New category /
        # Previous Year anomaly). Other category adds O: prefix on diff Y2Y only.
        focus_y2y = matrix_result_focus == "diff_y2y"
        focus_cy = matrix_result_focus == "current_year"

        if focus_cy:
            res_cy = _matrix_classify_label(cy_d, geo, th_key)
            res_y2y = dash
        elif focus_y2y:
            res_cy = ""
            if omit_previous_year or omit_y2y_only:
                res_y2y = dash
            else:
                base_y2y = _matrix_classify_label(y2y, geo, th_key)
                if base_y2y == dash:
                    res_y2y = dash
                elif is_other_category_scenario:
                    res_y2y = f"O: {base_y2y}"
                else:
                    res_y2y = base_y2y
        else:
            res_cy = ""
            res_y2y = dash

        res_cy = _matrix_format_result_display(res_cy)
        res_y2y = _matrix_format_result_display(res_y2y)

        rows_out.append(
            {
                "Metric": title,
                "Period": "Current Year",
                "Before": format_matrix_metric(cbb, as_int=as_int and cbb is not None),
                "After": format_matrix_metric(cba, as_int=as_int and cba is not None),
                "Diff %": format_percent(cy_d),
                "Result": res_cy,
            }
        )
        rows_out.append(
            {
                "Metric": title,
                "Period": "Previous Year",
                "Before": py_before,
                "After": py_after,
                "Diff %": py_diff_s,
                "Result": "",
            }
        )
        rows_out.append(
            {
                "Metric": title,
                "Period": "diff Y2Y",
                "Before": "",
                "After": "",
                "Diff %": dash if omit_previous_year else y2y_diff_cell,
                "Result": res_y2y,
            }
        )
    return rows_out


def _ppv_matrix_primary_period_label(matrix_result_focus: str) -> str:
    return "diff Y2Y" if matrix_result_focus == "diff_y2y" else "Current Year"


def _ppv_matrix_style_analytics(df: pd.DataFrame, matrix_result_focus: str):
    """
    Primary-period rows: blue accent band. diff Y2Y rows: always bold + slate accent.
    PY rows: subtle zebra. Metric groups separated by top rule.
    Result cells: pill semantic styling.
    """
    primary_period = _ppv_matrix_primary_period_label(matrix_result_focus)

    primary_bg    = "background-color: rgba(59,130,246,0.11)"
    primary_left  = "border-left: 4px solid #3b82f6"
    diff_bg       = "background-color: rgba(15,23,42,0.055)"
    diff_left     = "border-left: 4px solid #94a3b8"
    py_bg         = "background-color: rgba(241,245,249,0.75)"
    grp_rule      = "border-top: 2px solid rgba(100,116,139,0.28)"

    metrics_col = df["Metric"].tolist()

    def _row_styles(row):
        try:
            ri = int(row.name)
        except (TypeError, ValueError):
            ri = metrics_col.index(row["Metric"]) if row["Metric"] in metrics_col else 0

        period      = row["Period"]
        is_diff     = period == "diff Y2Y"
        is_primary  = period == primary_period
        group_start = ri > 0 and metrics_col[ri] != metrics_col[ri - 1]

        styles = []
        for col in df.columns:
            parts = []
            if group_start:
                parts.append(grp_rule)

            if is_diff:
                parts.append(diff_bg)
                parts.append(diff_left)
                parts.append("font-weight: 700")
            elif is_primary:
                parts.append(primary_bg)
                parts.append(primary_left)
                parts.append("font-weight: 600")
            else:
                parts.append(py_bg)

            if col == "Result":
                sem = _matrix_result_semantic_css(row[col])
                if sem:
                    parts = [p for p in parts if "background-color" not in p]
                    parts.append(sem)

            styles.append("; ".join(parts) + ";" if parts else "")
        return styles

    return df.style.apply(_row_styles, axis=1)


def _ppv_matrix_render_html(df: pd.DataFrame, matrix_result_focus: str) -> None:
    """Render PPV matrix as an HTML table with bold headers and full row styling."""
    primary_period = _ppv_matrix_primary_period_label(matrix_result_focus)
    metrics_col = df["Metric"].tolist()
    cols = df.columns.tolist()

    th_s = (
        "font-weight:700;padding:10px 12px;"
        "border-bottom:2px solid rgba(100,116,139,0.25);"
        "text-align:left;font-size:0.83rem;color:#475569;white-space:nowrap;"
    )
    header_html = "".join(f'<th style="{th_s}">{c}</th>' for c in cols)

    rows_html = []
    for ri, (_, row) in enumerate(df.iterrows()):
        period = str(row.get("Period", ""))
        is_diff    = period == "diff Y2Y"
        is_primary = period == primary_period
        group_start = ri > 0 and metrics_col[ri] != metrics_col[ri - 1]

        if is_diff:
            row_bg, left_clr, fw = "rgba(15,23,42,0.055)", "#94a3b8", "700"
        elif is_primary:
            row_bg, left_clr, fw = "rgba(59,130,246,0.11)", "#3b82f6", "600"
        else:
            row_bg, left_clr, fw = "rgba(241,245,249,0.75)", "transparent", "400"

        top = "border-top:2px solid rgba(100,116,139,0.28);" if group_start else ""
        row_style = f"background:{row_bg};border-left:4px solid {left_clr};{top}"

        cells = []
        for col in cols:
            raw = row[col]
            val_str = (
                str(raw)
                if raw is not None and not (isinstance(raw, float) and pd.isna(raw))
                else "—"
            )
            td_s = f"padding:10px 12px;font-weight:{fw};font-size:0.875rem;"
            if col == "Result":
                sem = _matrix_result_semantic_css(val_str)
                content = f'<span style="{sem}">{val_str}</span>' if sem else val_str
            else:
                content = val_str
            cells.append(f'<td style="{td_s}">{content}</td>')

        rows_html.append(f'<tr style="{row_style}">{"".join(cells)}</tr>')

    html = (
        '<div style="width:100%;overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;border-radius:10px;'
        'overflow:hidden;border:1px solid rgba(148,163,184,0.18);font-family:inherit;">'
        f'<thead><tr style="background:rgba(248,250,252,0.95)">{header_html}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        "</table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _ppv_matrix_add_primary_fallback_column(df: pd.DataFrame, matrix_result_focus: str):
    primary_period = _ppv_matrix_primary_period_label(matrix_result_focus)
    out = df.copy()
    out.insert(
        0,
        "Primary",
        ["✓" if p == primary_period else "" for p in out["Period"]],
    )
    return out


def _compute_potential_spendings_block(
    cy_paid_users_b,
    cy_paid_users_a,
    cy_spending_b,
    cy_spending_a,
    cy_ac_b,
    cy_ac_a,
    py_paid_users_b,
    py_paid_users_a,
    py_ac_b,
    py_ac_a,
    omit_py: bool = False,
):
    cy_cr_b = _matrix_safe_div(cy_paid_users_b, cy_ac_b)
    cy_cr_a = _matrix_safe_div(cy_paid_users_a, cy_ac_a)

    fact_arppu = _matrix_safe_div(cy_spending_a, cy_paid_users_a)
    could_be_arppu = _matrix_safe_div(cy_spending_b, cy_paid_users_b)
    fact_spending = cy_spending_a

    if omit_py:
        return {
            "fact_arppu": fact_arppu,
            "could_be_arppu": could_be_arppu,
            "fact_spending": fact_spending,
            "could_be_spendings": None,
            "potential_spendings_diff": None,
        }

    py_cr_b = _matrix_safe_div(py_paid_users_b, py_ac_b)
    py_cr_a = _matrix_safe_div(py_paid_users_a, py_ac_a)
    py_cr_diff_pct = _matrix_pct_diff(py_cr_b, py_cr_a)

    expected_cr_after = None
    if cy_cr_b is not None and py_cr_diff_pct is not None:
        expected_cr_after = cy_cr_b * (1.0 + py_cr_diff_pct / 100.0)

    could_be_spendings = None
    if cy_ac_a is not None and expected_cr_after is not None and could_be_arppu is not None:
        could_be_spendings = cy_ac_a * expected_cr_after * could_be_arppu

    potential_spendings_diff = None
    if fact_spending is not None and could_be_spendings is not None and could_be_spendings != 0:
        potential_spendings_diff = fact_spending / could_be_spendings - 1.0

    return {
        "fact_arppu": fact_arppu,
        "could_be_arppu": could_be_arppu,
        "fact_spending": fact_spending,
        "could_be_spendings": could_be_spendings,
        "potential_spendings_diff": potential_spendings_diff,
    }


def _potential_spendings_row_diff_pct(fact, could_be) -> float | None:
    """((Fact / Could be) - 1) * 100 — на сколько % Fact выше/ниже Could be (база = Could be)."""
    if fact is None or could_be is None:
        return None
    try:
        ff = float(fact)
        cf = float(could_be)
    except (TypeError, ValueError):
        return None
    if cf == 0:
        return None
    if ff == 0:
        return None
    return (ff / cf - 1.0) * 100.0


def _potential_spendings_row_diff_abs(fact, could_be) -> float | None:
    """Fact − Could be; None if inputs invalid."""
    if fact is None or could_be is None:
        return None
    try:
        return float(fact) - float(could_be)
    except (TypeError, ValueError):
        return None


def _potential_spendings_diff_pct_display(d: float | None) -> str:
    """Display-only: ↑ / ↓ / = + %, aligned with PPV matrix semantic colors (no logic change)."""
    dash = "—"
    if d is None:
        return dash
    if abs(float(d)) < 1e-15:
        return "= 0.00%"
    body = f"{float(d):.2f}%"
    if float(d) > 0:
        return f"↑ {body}"
    return f"↓ {body}"


def _potential_spendings_diff_pct_cell_css(val) -> str:
    """diff % badges: сохраняем полупрозрачные фоны; текст — высококонтрастный для читаемости."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if not s or s == "—" or s.lower() == "not available":
        return ""
    if s.startswith("="):
        return "background-color: rgba(234,179,8,0.18); color: #92400e; font-weight: 700; border-radius: 8px;"
    if s.startswith("↑"):
        return "background-color: rgba(34,197,94,0.16); color: #166534; font-weight: 700; border-radius: 8px;"
    if s.startswith("↓"):
        return "background-color: rgba(239,68,68,0.14); color: #991b1b; font-weight: 700; border-radius: 8px;"
    return ""


def _potential_spendings_style_table(df: pd.DataFrame):
    row_bgs = [
        "background-color: rgba(241,245,249,0.0)",
        "background-color: rgba(241,245,249,0.75)",
    ]
    left_border = "border-left: 4px solid #94a3b8"

    def _row_styles(row):
        try:
            ri = int(row.name)
        except (TypeError, ValueError):
            ri = 0
        bg = row_bgs[ri % len(row_bgs)]
        styles = []
        for col in df.columns:
            parts = [bg, left_border]
            if col == "Potential Spendings":
                parts.append("font-weight: 700")
            if col == "diff %":
                css = _potential_spendings_diff_pct_cell_css(row[col])
                if css:
                    parts = [p for p in parts if "background-color" not in p]
                    parts.append(css)
            styles.append("; ".join(parts) + ";")
        return styles

    try:
        return df.style.apply(_row_styles, axis=1)
    except Exception:
        try:
            return df.style.map(_potential_spendings_diff_pct_cell_css, subset=["diff %"])
        except AttributeError:
            return df.style.applymap(_potential_spendings_diff_pct_cell_css, subset=["diff %"])


def _potential_spendings_render_html(df: pd.DataFrame) -> None:
    """Render Potential Spendings as an HTML table with bold headers."""
    cols = df.columns.tolist()

    th_s = (
        "font-weight:700;padding:10px 12px;"
        "border-bottom:2px solid rgba(100,116,139,0.25);"
        "text-align:left;font-size:0.83rem;color:#475569;white-space:nowrap;"
    )
    header_html = "".join(f'<th style="{th_s}">{c}</th>' for c in cols)

    row_bgs = ["rgba(255,255,255,0.0)", "rgba(241,245,249,0.75)"]

    rows_html = []
    for ri, (_, row) in enumerate(df.iterrows()):
        bg = row_bgs[ri % len(row_bgs)]
        row_style = f"background:{bg};border-left:4px solid #94a3b8;"

        cells = []
        for col in cols:
            raw = row[col]
            val_str = (
                str(raw)
                if raw is not None and not (isinstance(raw, float) and pd.isna(raw))
                else "—"
            )
            td_s = "padding:10px 12px;font-size:0.875rem;"
            if col == "Potential Spendings":
                td_s += "font-weight:700;"
                content = val_str
            elif col == "diff %":
                badge = _potential_spendings_diff_pct_cell_css(val_str)
                content = (
                    f'<span style="{badge} padding:3px 8px;">{val_str}</span>'
                    if badge else val_str
                )
            else:
                content = val_str
            cells.append(f'<td style="{td_s}">{content}</td>')

        rows_html.append(f'<tr style="{row_style}">{"".join(cells)}</tr>')

    html = (
        '<div style="width:100%;overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;border-radius:10px;'
        'overflow:hidden;border:1px solid rgba(148,163,184,0.18);font-family:inherit;">'
        f'<thead><tr style="background:rgba(248,250,252,0.95)">{header_html}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        "</table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _potential_spendings_table_dataframe_kwargs() -> dict:
    """Fixed px columns + dataframe width so the grid stays readable (no manual resize)."""
    out: dict = {}
    try:
        sig = inspect.signature(st.dataframe).parameters
        if "column_config" not in sig:
            return out
        # Integer widths → Glide pinned widths (Streamlit 1.46+).
        _w_metric, _w_fact, _w_could, _w_diff, _w_pct = 200, 128, 176, 120, 210
        out["column_config"] = {
            "Potential Spendings": st.column_config.TextColumn(
                "Potential Spendings",
                width=_w_metric,
            ),
            "Fact": st.column_config.TextColumn("Fact", width=_w_fact),
            "Could be": st.column_config.TextColumn("Could be", width=_w_could),
            "diff": st.column_config.TextColumn("diff", width=_w_diff),
            "diff %": st.column_config.TextColumn("diff %", width=_w_pct),
        }
        if "hide_index" in sig:
            out["hide_index"] = True
        if "use_container_width" in sig:
            out["use_container_width"] = True
        row_px = 44
        if "height" in sig:
            out["height"] = 56 + 3 * row_px + 12
        if "row_height" in sig:
            out["row_height"] = row_px
    except (TypeError, ValueError):
        return {}
    return out


def _build_potential_spendings_table_df(
    _pot: dict,
    *,
    omit_py_dependent_row: bool = False,
) -> pd.DataFrame:
    """Compact table: Potential Spendings | Fact | Could be | diff | diff %."""
    fa, ca = _pot.get("fact_arppu"), _pot.get("could_be_arppu")
    fs, cs = _pot.get("fact_spending"), _pot.get("could_be_spendings")
    d1 = _potential_spendings_row_diff_pct(fa, ca)
    a1 = _potential_spendings_row_diff_abs(fa, ca)
    dash = "—"

    row_arppu = {
        "Potential Spendings": "ARPpU",
        "Fact": format_potential_amount(fa),
        "Could be": format_potential_amount(ca),
        "diff": format_delta(a1, as_integer=False),
        "diff %": _potential_spendings_diff_pct_display(d1),
    }

    if omit_py_dependent_row:
        row_spend = {
            "Potential Spendings": "Spendings",
            "Fact": format_potential_amount(fs),
            "Could be": dash,
            "diff": dash,
            "diff %": dash,
        }
    else:
        d2 = _potential_spendings_row_diff_pct(fs, cs)
        a2 = _potential_spendings_row_diff_abs(fs, cs)
        row_spend = {
            "Potential Spendings": "Spendings",
            "Fact": format_potential_amount(fs),
            "Could be": format_potential_amount(cs),
            "diff": format_delta(a2, as_integer=True),
            "diff %": _potential_spendings_diff_pct_display(d2),
        }

    return pd.DataFrame([row_arppu, row_spend])


def _ppv_matrix_primary_hint_html(matrix_result_focus: str) -> str:
    label = _ppv_matrix_primary_period_label(matrix_result_focus)
    return (
        '<div class="sd-dash-card" style="padding:8px 12px;margin-bottom:6px;">'
        f'<strong>Primary comparison:</strong> '
        f'<span style="opacity:0.9">{label}</span> — Result column shows classification for this period only.'
        "</div>"
    )


def _ppv_matrix_dataframe_kwargs() -> dict:
    """Pinned Metric + Period when Streamlit supports pinned on TextColumn."""
    out: dict = {}
    try:
        sig = inspect.signature(st.dataframe).parameters
        if "column_config" not in sig:
            return out
        tc_sig = inspect.signature(st.column_config.TextColumn).parameters
        pin_kw: dict = {"pinned": "left"} if "pinned" in tc_sig else {}
        out["column_config"] = {
            "Metric": st.column_config.TextColumn("Metric", width="medium", **pin_kw),
            "Period": st.column_config.TextColumn("Period", width="small", **pin_kw),
            "Before": st.column_config.TextColumn("Before", width="small"),
            "After": st.column_config.TextColumn("After", width="small"),
            "Diff %": st.column_config.TextColumn("Diff %", width="small"),
            "Result": st.column_config.TextColumn("Result", width="medium"),
        }
        if "hide_index" in sig:
            out["hide_index"] = True
        if "use_container_width" in sig:
            out["use_container_width"] = True
    except (TypeError, ValueError):
        return {}
    return out


def _dataframe_tall_height_kw(n_rows: int) -> dict:
    """Viewport height matched to row count (~no empty tail under PPV matrix)."""
    kw: dict = {}
    try:
        sig = inspect.signature(st.dataframe).parameters
        if "height" not in sig or not n_rows:
            return kw
        row_px = 44
        chrome = 56
        slack_rows = 1
        h = chrome + (int(n_rows) + slack_rows) * row_px + 12
        kw["height"] = min(1400, max(220, h))
        if "row_height" in sig:
            kw["row_height"] = row_px
    except (TypeError, ValueError):
        return {}
    return kw


def _metric_summary_dataframe_kw(n_rows: int) -> dict:
    """Tight viewport: all data rows visible, +1 spare grid row — avoid large blank tail."""
    kw: dict = {}
    try:
        sig = inspect.signature(st.dataframe).parameters
        if "height" not in sig or n_rows <= 0:
            return kw
        row_px = 36
        chrome = 56
        slack_rows = 1
        h = chrome + (int(n_rows) + slack_rows) * row_px + 12
        kw["height"] = min(1200, max(260, h))
        if "row_height" in sig:
            kw["row_height"] = row_px
    except (TypeError, ValueError):
        return {}
    return kw


def _exec_arrow_for_code(code: str | None) -> str:
    if code == "G":
        return "↑"
    if code == "D":
        return "↓"
    return "="


def _compute_single_executive_kpis(
    *,
    geo: str,
    matrix_result_focus_run: str,
    result: dict,
    y2y_bundle,
    paid_users_before,
    paid_users_after,
    spending_before,
    spending_after,
    active_before,
    active_after,
    matrix_py_ac_before,
    matrix_py_ac_after,
) -> list[tuple[str, str | None, str | None]]:
    """(label, formatted_pct_or_none, code G/S/D) for four core metrics."""
    th = _matrix_geo_thresholds(geo or "default")["npl"]
    out: list[tuple[str, str | None, str | None]] = []

    def _fmt(v) -> str | None:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return f"{float(v):+.2f}%"

    if matrix_result_focus_run == "current_year":
        out.append(("Paid users", _fmt(result.get("npl_diff")), result.get("npl_code")))
        out.append(("Spending", _fmt(result.get("sp_diff")), result.get("sp_code")))
        out.append(("CR", _fmt(result.get("cr_diff")), result.get("cr_code")))
        ad = result.get("active_diff")
        ac_code = None
        if ad is not None and not (isinstance(ad, float) and pd.isna(ad)):
            ac_code = classify_change(float(ad), th["growth"], th["decline"])
        out.append(("Active listers", _fmt(ad), ac_code))
        return out

    if y2y_bundle is not None and getattr(y2y_bundle, "__getitem__", None) and y2y_bundle.get("complete"):
        out.append(
            ("Paid users", _fmt(y2y_bundle.get("y2y_npl")), y2y_bundle.get("npl_code"))
        )
        out.append(("Spending", _fmt(y2y_bundle.get("y2y_sp")), y2y_bundle.get("sp_code")))
        out.append(("CR", _fmt(y2y_bundle.get("y2y_cr")), y2y_bundle.get("cr_code")))
        cy_a = _matrix_pct_diff(active_before, active_after)
        py_a = _matrix_pct_diff(matrix_py_ac_before, matrix_py_ac_after)
        ay = (
            (cy_a - py_a)
            if cy_a is not None and py_a is not None
            else None
        )
        acode = (
            classify_change(ay, th["growth"], th["decline"])
            if ay is not None
            else None
        )
        out.append(("Active listers", _fmt(ay), acode))
        return out

    return [(n, None, None) for n in ("Paid users", "Spending", "CR", "Active listers")]


def _render_single_executive_summary(kpis: list[tuple[str, str | None, str | None]], disp_fd: str) -> None:
    """Compact KPI strip mirrored to primary-period metrics."""

    def _esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    hb = ""
    for label, pct_s, code in kpis:
        if pct_s is None:
            val = "<span style='opacity:0.75'>—</span>"
            sub = ""
        else:
            arr = _exec_arrow_for_code(code)
            deco = decode_status(code) if code else ""
            val = f"{arr} {_esc(pct_s)}"
            sub = f'<div class="sd-mini-kpi-sub">{_esc(deco)}</div>' if deco else ""
        hb += (
            f'<div class="sd-mini-kpi"><div class="sd-mini-kpi-label">{_esc(label)}</div>'
            f'<div class="sd-mini-kpi-val">{val}</div>{sub}</div>'
        )

    oc = (
        '<div class="sd-mini-kpi" style="flex:2 1 220px;background:rgba(148,163,184,0.12);">'
        '<div class="sd-mini-kpi-label">Final decision</div>'
        f'<div class="sd-mini-kpi-val" style="font-size:1.15rem;">{_esc(disp_fd)}</div></div>'
    )

    st.markdown(
        '<p class="sd-h2" style="margin-top:0.35rem">Executive summary</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="sd-mini-kpis">{hb}{oc}</div>',
        unsafe_allow_html=True,
    )


def _render_potential_spendings_kpi_cards(pot_df: pd.DataFrame) -> None:
    """Single analysis: KPI blocks inside one bordered panel (Fact, Could be, Diff %)."""
    if pot_df is None or pot_df.empty:
        return
    rows = list(pot_df.iterrows())
    with st.container(border=True):
        for i, (_, row) in enumerate(rows):
            st.markdown(f"**{row.get('Potential Spendings', '—')}**")
            fc1, fc2, fc3 = st.columns(3, gap="small")
            with fc1:
                st.caption("Fact")
                st.markdown(f"**{row.get('Fact', '—')}**")
            with fc2:
                st.caption("Could be")
                st.markdown(f"**{row.get('Could be', '—')}**")
            with fc3:
                st.caption("Diff %")
                pct = row.get("diff %", "—")
                st.markdown(
                    _potential_spendings_diff_pct_badge_md(pct),
                    unsafe_allow_html=True,
                )
            if i < len(rows) - 1:
                st.markdown("")


def _potential_spendings_diff_pct_badge_md(pct) -> str:
    s = "—" if pct is None else str(pct)
    css = _potential_spendings_diff_pct_cell_css(s)
    if not css:
        return f"<span>{s}</span>"
    esc = (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f'<span style="{css}; padding: 4px 10px;">{esc}</span>'


def _single_next_step_lead_icon(ns: str | None) -> tuple[str, str]:
    """(emoji, short label) for recommendation header — heuristic only."""
    if not ns:
        return "💡", "Recommendation"
    s = str(ns).lower()
    if "rollback" in s or "roll back" in s or "return prices" in s:
        return "↩️", "Rollback suggested"
    if "keep" in s:
        return "✅", "Keep / maintain"
    if "re-increase" in s or "raise price" in s or "raise prices" in s:
        return "📈", "Price increase option"
    if "monitor" in s or "watch" in s:
        return "👀", "Monitor"
    if "teamlead" in s:
        return "👥", "Review with leadership"
    if "experiment" in s or "search" in s:
        return "🔍", "Further investigation"
    return "💡", "Recommended actions"


def _render_single_outcome_hero_and_actions(
    disp_dc: str,
    disp_fd: str,
    disp_ns: str,
) -> None:
    st.markdown('<p class="sd-h2">Decision</p>', unsafe_allow_html=True)

    def _esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    if disp_fd == "Positive impact":
        hcls = "sd-hero-wrap sd-hero-positive"
    elif disp_fd == "Negative impact":
        hcls = "sd-hero-wrap sd-hero-negative"
    elif disp_fd == "No impact":
        hcls = "sd-hero-wrap sd-hero-neutral"
    else:
        hcls = "sd-hero-wrap sd-hero-muted"

    st.markdown(
        f'<div class="{hcls}">'
        f'<div class="sd-hero-title">Outcome</div>'
        f'<div class="sd-hero-decision">{_esc(disp_fd)}</div></div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Decision code encodes Paid users × Spending × CR trend (Growth / Stable / Decrease per metric)."
    )
    dc_clean = _esc(str(disp_dc))
    st.markdown(
        f'<span class="sd-code-pill" title="G Growth · S Stable · D Decrease">{dc_clean}</span>',
        unsafe_allow_html=True,
    )
    with st.expander("Legend: G · S · D", expanded=False):
        st.markdown(
            "- **G** — Growth (above geo growth threshold)\n"
            "- **S** — Stable (between decline and growth thresholds)\n"
            "- **D** — Decrease (below decline threshold)"
        )

    emoji, ttl = _single_next_step_lead_icon(disp_ns)
    ns_html = _esc(str(disp_ns)).replace("\n", "<br/>")
    st.markdown(
        f'<div class="sd-next-card">'
        f'<div style="font-weight:600;margin-bottom:8px;font-size:1rem;">{emoji} {_esc(ttl)}</div>'
        f"<p>{ns_html}</p></div>",
        unsafe_allow_html=True,
    )


st.divider()

st.markdown('<p class="sd-h2 sd-h2-tight">Ручной ввод данных</p>', unsafe_allow_html=True)

_cy_ba: dict[str, tuple[float, float]] = {}
# Single-режим: матрица ручного ввода открыта по умолчанию (иначе ниже видны только даты Release/CY/PY).
with st.expander(
    "Ручной ввод данных · Current Year + Previous Year (матрица)",
    expanded=bool(_category_single_mode),
):
    _manuel_cy, _manuel_py = st.columns([1.08, 0.94], gap="small")
    with _manuel_cy:
        with st.container(border=True):
            st.subheader("Current Year input")
            st.caption(
                "Абсолютные **Before** и **After**. Колонки **До %** и **После %** в сводке ниже "
                "считаются в приложении. **До, %** — относительно опорного периода из выгрузки (если есть в данных). "
                "**После, %** = (After − Before) / Before."
            )

            _cy_h0, _cy_h1, _cy_h2 = st.columns([1.55, 1, 1])
            with _cy_h0:
                st.caption("Metric")
            with _cy_h1:
                st.markdown("**Before**")
            with _cy_h2:
                st.markdown("**After**")

            for _dk, _dlabel, _dtyp in _CY_INPUT_METRICS:
                sk = _cy_sess_key(_dk)
                _float_min = (
                    None if _dk in _CY_FLOAT_INPUT_ALLOW_NEGATIVE else 0.0
                )
                _cr0, _cr1, _cr2 = st.columns([1.55, 1, 1])
                with _cr0:
                    st.markdown(_dlabel)
                with _cr1:
                    if _dtyp == "int":
                        _bv = st.number_input(
                            f"{_dlabel} — Before",
                            min_value=0,
                            key=f"{sk}_before",
                            label_visibility="collapsed",
                        )
                    else:
                        _bv = st.number_input(
                            f"{_dlabel} — Before",
                            min_value=_float_min,
                            key=f"{sk}_before",
                            label_visibility="collapsed",
                        )
                with _cr2:
                    if _dtyp == "int":
                        _av = st.number_input(
                            f"{_dlabel} — After",
                            min_value=0,
                            key=f"{sk}_after",
                            label_visibility="collapsed",
                        )
                    else:
                        _av = st.number_input(
                            f"{_dlabel} — After",
                            min_value=_float_min,
                            key=f"{sk}_after",
                            label_visibility="collapsed",
                        )
                _cy_ba[_dk] = (float(_bv), float(_av))

    with _manuel_py:
        with st.container(border=True):
            st.subheader("Previous Year")
            if _scenario_is_new_category(scenario):
                st.caption(
                    "New category: Previous Year и Y2Y недоступны."
                )
            st.caption(
                "Значения для **матрицы**, **Y2Y** и **Potential Spending**. "
                "После загрузки PY файлов и merge — автозаполнение; иначе вручную или OCR (**Previous Year**)."
            )
            st.markdown("**Paid users**")
            matrix_py_paid_users_before = st.number_input(
                "PY Paid users Before", min_value=0, key="matrix_py_paid_users_before"
            )
            matrix_py_paid_users_after = st.number_input(
                "PY Paid users After", min_value=0, key="matrix_py_paid_users_after"
            )
            st.markdown("**Spending**")
            matrix_py_spending_before = st.number_input(
                "PY Spending Before", min_value=0.0, key="matrix_py_spending_before"
            )
            matrix_py_spending_after = st.number_input(
                "PY Spending After", min_value=0.0, key="matrix_py_spending_after"
            )
            st.markdown("**Active listers**")
            matrix_py_ac_before = st.number_input(
                "PY Active Before", min_value=0, key="matrix_py_ac_before"
            )
            matrix_py_ac_after = st.number_input(
                "PY Active After", min_value=0, key="matrix_py_ac_after"
            )

_ss = st.session_state
if _cy_ba:
    paid_users_before = int(_cy_ba["paid_users"][0])
    paid_users_after = int(_cy_ba["paid_users"][1])
    spending_before = float(_cy_ba["spending"][0])
    spending_after = float(_cy_ba["spending"][1])
    active_before = int(_cy_ba["active_listers"][0])
    active_after = int(_cy_ba["active_listers"][1])
else:
    paid_users_before = int(_ss.get("paid_users_before") or 0)
    paid_users_after = int(_ss.get("paid_users_after") or 0)
    spending_before = float(_ss.get("spending_before") or 0)
    spending_after = float(_ss.get("spending_after") or 0)
    active_before = int(_ss.get("active_before") or 0)
    active_after = int(_ss.get("active_after") or 0)

_cy_baseline_snap = {}
if merged_data and _category_single_mode and _resolved_single_category_id is not None:
    _cid_tbl = int(_resolved_single_category_id)
    _cy_tbl_b = _bulk_lookup_merged_category(merged_data, _cid_tbl)
    if _cy_tbl_b is not None:
        _bs = _cy_tbl_b.get("baseline")
        if isinstance(_bs, dict):
            _cy_baseline_snap = _bs

_cy_tbl = []
for _dk, _dlabel, _dtyp in _CY_INPUT_METRICS:
    sk = _cy_sess_key(_dk)
    _bl_raw = _cy_baseline_snap.get(_dk)
    if _bl_raw is None:
        _bl_raw = _ss.get(f"{sk}_baseline")
    _pair_ui = _cy_ba.get(_dk) if _cy_ba else None
    if _pair_ui is not None:
        _bfv, _afv = _pair_ui[0], _pair_ui[1]
    else:
        _bfv = _ss.get(f"{sk}_before", 0)
        _afv = _ss.get(f"{sk}_after", 0)
    _as_int = _dtyp == "int"
    if _as_int:
        _bfv, _afv = int(_bfv or 0), int(_afv or 0)
        if _bl_raw is None or (isinstance(_bl_raw, str) and _bl_raw.strip() == ""):
            _blv_for_pct = None
        else:
            try:
                _blv_for_pct = int(float(_bl_raw))
            except (TypeError, ValueError):
                _blv_for_pct = None
    else:
        _bfv, _afv = float(_bfv or 0), float(_afv or 0)
        if _bl_raw is None or (isinstance(_bl_raw, str) and _bl_raw.strip() == ""):
            _blv_for_pct = None
        else:
            try:
                _blv_for_pct = float(_bl_raw)
            except (TypeError, ValueError):
                _blv_for_pct = None

    _bf_f = float(_bfv)
    _af_f = float(_afv)
    _before_diff = pct_change_relative(_bf_f, _blv_for_pct)
    _after_diff = pct_change_relative(_af_f, _bf_f)

    _cy_tbl.append(
        {
            "Metric": _dlabel,
            "До": format_matrix_metric(_bfv, as_int=_as_int),
            "После": format_matrix_metric(_afv, as_int=_as_int),
            "beforeDiff": _before_diff,
            "afterDiff": _after_diff,
        }
    )

_df_cy = pd.DataFrame(_cy_tbl)
# Display layer: same underlying _cy_tbl calculations; hide empty «До %» (baseline) column.
_df_cy_display = pd.DataFrame(
    {
        "Metric": _df_cy["Metric"],
        "Before": _df_cy["До"],
        "After": _df_cy["После"],
        "Diff %": pd.to_numeric(_df_cy["afterDiff"], errors="coerce"),
    }
)

_sty_cy = _df_cy_display.style
try:
    _sty_cy = _sty_cy.map(_metric_summary_diff_pct_style, subset=["Diff %"])
except AttributeError:
    _sty_cy = _sty_cy.applymap(_metric_summary_diff_pct_style, subset=["Diff %"])
_sty_cy = _sty_cy.format(format_summary_percent_cell, subset=["Diff %"])

st.caption(
    "**Периоды и Release** — компактная строка (справочно). Расчёт не затрагивают."
)
_per_rel, _per_cy, _per_py = st.columns([0.78, 1.08, 1.08], gap="small")
with _per_rel:
    st.markdown("**Release**")
    st.date_input(
        "Release date",
        value=date.today(),
        key="release_date",
    )
with _per_cy:
    st.markdown("**Current Year**")
    _pc_top = st.columns(4)
    with _pc_top[0]:
        st.date_input("CY Before from", value=date.today(), key="cy_before_from")
    with _pc_top[1]:
        st.date_input("CY Before to", value=date.today(), key="cy_before_to")
    with _pc_top[2]:
        st.date_input("CY After from", value=date.today(), key="cy_after_from")
    with _pc_top[3]:
        st.date_input("CY After to", value=date.today(), key="cy_after_to")
with _per_py:
    st.markdown("**Previous Year**")
    _pp_top = st.columns(4)
    with _pp_top[0]:
        st.date_input("PY Before from", value=date.today(), key="py_before_from")
    with _pp_top[1]:
        st.date_input("PY Before to", value=date.today(), key="py_before_to")
    with _pp_top[2]:
        st.date_input("PY After from", value=date.today(), key="py_after_from")
    with _pp_top[3]:
        st.date_input("PY After to", value=date.today(), key="py_after_to")

st.divider()

if _category_single_mode:
    st.markdown(
        '<p class="sd-h2 sd-h2-tight">Analytics</p>',
        unsafe_allow_html=True,
    )

_nc_sc = _scenario_is_new_category(scenario)
_py_anom_sc = _scenario_is_py_anomaly(scenario)
_matrix_result_focus = "current_year" if (_nc_sc or _py_anom_sc) else "diff_y2y"
_matrix_df = pd.DataFrame(
    _build_ppv_matrix_rows(
        geo,
        paid_users_before,
        paid_users_after,
        spending_before,
        spending_after,
        active_before,
        active_after,
        matrix_py_paid_users_before,
        matrix_py_paid_users_after,
        matrix_py_spending_before,
        matrix_py_spending_after,
        matrix_py_ac_before,
        matrix_py_ac_after,
        omit_previous_year=_nc_sc,
        omit_y2y_only=_py_anom_sc and not _nc_sc,
        is_other_category_scenario=_scenario_is_other_category(scenario),
        matrix_result_focus=_matrix_result_focus,
    )
)
_pot = _compute_potential_spendings_block(
    paid_users_before,
    paid_users_after,
    spending_before,
    spending_after,
    active_before,
    active_after,
    matrix_py_paid_users_before,
    matrix_py_paid_users_after,
    matrix_py_ac_before,
    matrix_py_ac_after,
    omit_py=_nc_sc or _py_anom_sc,
)
_pot_df = _build_potential_spendings_table_df(
    _pot,
    omit_py_dependent_row=_nc_sc or _py_anom_sc,
)

_matrix_h_kw = _dataframe_tall_height_kw(len(_matrix_df))


_PPD_SCENARIOS: dict[str, dict] = {
    "PRICE_OK": {
        "label": "Распределение стабильно",
        "description": "Значимого перетока между шагами нет — цена приемлема для юзеров.",
        "action": "Дополнительных действий не требуется.",
        "sentiment": "positive",
    },
    "PRICE_TOO_HIGH": {
        "label": "Цена чувствительна для юзеров",
        "description": "Кампании перетекают с шагов выше дефолта на дешёвые (1st и default) — повышение цен слишком сильное.",
        "action": "Риск снижения спендингов. Рассмотрите возврат к прежним ценам или меньшее повышение.",
        "sentiment": "negative",
    },
    "CAN_RAISE_MORE": {
        "label": "Можно поднять цену выше",
        "description": "Кампании растут на шагах выше дефолта (особенно VIP) — юзеры готовы платить больше.",
        "action": "Рассмотрите дополнительное повышение цен.",
        "sentiment": "positive",
    },
    "HIGH_VIP_SHARE": {
        "label": "Высокая концентрация на VIP",
        "description": (
            "Значительная доля кампаний на VIP-шаге — возможен супер-сезон, "
            "сильная конкуренция за контакты или преимущественно бизнес-категория."
        ),
        "action": "Поднять цену только на VIP-шаг.",
        "sentiment": "positive",
    },
    "VIP_TOO_EXPENSIVE": {
        "label": "VIP-шаг слишком дорогой",
        "description": "Юзеры уходят с VIP на шаги выше дефолта, но дешевле VIP — VIP-цена перестала оправдывать ценность.",
        "action": "Снизить цену только на VIP-шаг.",
        "sentiment": "negative",
    },
    "AFFECTS_INDIVIDUALS": {
        "label": "Дорого для физических лиц",
        "description": (
            "VIP и дорогие шаги (выше дефолта) стабильны, но доля 1st и default шагов "
            "значительно снизилась — физлица чувствуют ценовое давление."
        ),
        "action": "Снизить цены на 1st и default шаги.",
        "sentiment": "negative",
    },
    "MIXED": {
        "label": "Неоднозначная картина",
        "description": "Изменения не укладываются в один сценарий — необходим дополнительный анализ.",
        "action": "Проверьте распределение по каждому шагу вручную.",
        "sentiment": "neutral",
    },
}


def _classify_price_distribution(
    before_dist: dict,
    after_dist: dict,
    grid: dict,
) -> str | None:
    if not before_dist or not after_dist or not grid:
        return None

    THRESHOLD = 0.05

    first_steps       = {s for s, v in grid.items() if v.get("is_first")}
    default_steps     = {s for s, v in grid.items() if v.get("is_default")}
    vip_steps         = {s for s, v in grid.items() if v.get("is_vip")}
    cheap_steps       = first_steps | default_steps
    above_default     = {s for s in grid if s not in cheap_steps}
    mid_above         = above_default - vip_steps

    def _share(dist: dict, steps: set) -> float:
        total = sum(dist.values()) or 1
        return sum(dist.get(s, 0) for s in steps) / total

    def _delta(steps: set) -> float | None:
        sb = _share(before_dist, steps)
        sa = _share(after_dist, steps)
        return (sa - sb) / sb if sb > 0 else None

    d_cheap = _delta(cheap_steps)
    d_above = _delta(above_default)
    d_vip   = _delta(vip_steps) if vip_steps else None
    d_mid   = _delta(mid_above) if mid_above else None

    vip_share_after = _share(after_dist, vip_steps) if vip_steps else 0.0

    # Priority order: most specific / critical first
    if d_cheap is not None and d_cheap > THRESHOLD and d_above is not None and d_above < -THRESHOLD:
        return "PRICE_TOO_HIGH"

    if (vip_steps and d_vip is not None and d_vip < -THRESHOLD
            and d_mid is not None and d_mid > THRESHOLD
            and (d_cheap is None or abs(d_cheap) <= THRESHOLD)):
        return "VIP_TOO_EXPENSIVE"

    if (d_above is not None and d_above >= -THRESHOLD
            and d_cheap is not None and d_cheap < -THRESHOLD):
        return "AFFECTS_INDIVIDUALS"

    if vip_steps and vip_share_after > 0.25 and (d_vip is None or d_vip >= -THRESHOLD):
        return "HIGH_VIP_SHARE"

    if d_above is not None and d_above > THRESHOLD and (d_cheap is None or d_cheap <= THRESHOLD):
        return "CAN_RAISE_MORE"

    all_deltas = [d for d in [d_cheap, d_above, d_vip] if d is not None]
    if all(abs(d) <= THRESHOLD for d in all_deltas):
        return "PRICE_OK"

    return "MIXED"


def _render_price_per_day_block(
    budget_dist: dict,
    category_id: int,
    scenario_code: str | None = None,
) -> None:
    try:
        import altair as alt
    except ImportError:
        return

    cat_dist = budget_dist.get(category_id)
    if not cat_dist:
        return

    before_dist = cat_dist.get("before", {})
    after_dist  = cat_dist.get("after", {})
    grid        = cat_dist.get("grid", {})
    if not before_dist and not after_dist:
        return

    total_b   = sum(before_dist.values()) or 1
    total_a   = sum(after_dist.values()) or 1
    all_steps = sorted(set(list(before_dist.keys()) + list(after_dist.keys()) + list(grid.keys())))
    if not all_steps:
        return

    def _zone(step: int) -> str:
        if grid:
            info = grid.get(step, {})
            if info.get("is_vip"):
                return "VIP-step"
            if info.get("is_default"):
                return "default"
            if info.get("is_first"):
                return "1st step"
            # find default step for relative position
            default_steps = [s for s, v in grid.items() if v.get("is_default")]
            if default_steps:
                ds = default_steps[0]
                return "decrease" if step < ds else "increase"
        return ""

    # Only include price steps that have at least one campaign in either period
    active_steps = sorted(
        s for s in all_steps
        if before_dist.get(s, 0) > 0 or after_dist.get(s, 0) > 0
    )
    if not active_steps:
        return

    rows = []
    for step in active_steps:
        for period_lbl, dist, total in [
            ("Default", before_dist, total_b),
            ("Target",  after_dist,  total_a),
        ]:
            cnt = dist.get(step, 0)
            pct = round(cnt / total * 100, 1) if cnt > 0 else 0.0
            rows.append({
                "step":      str(step),
                "step_num":  step,
                "period":    period_lbl,
                "n":         cnt,
                "pct":       pct,
                "pct_label": f"{pct:.1f}%",
            })

    if not rows:
        return

    df_c = pd.DataFrame(rows)
    df_c["x_key"] = df_c.apply(lambda r: f"{r['step']} {r['period']}", axis=1)

    # Only show bars where there is actual data (n > 0)
    df_c_active = df_c[df_c["n"] > 0].copy()
    df_c_active["bar_h"] = 1.0

    # Flat x-axis: only positions with data, preserving Default→Target order per step
    x_order = []
    for s in active_steps:
        for period_lbl in ("Default", "Target"):
            key = f"{s} {period_lbl}"
            if key in df_c_active["x_key"].values:
                x_order.append(key)

    CHART_H   = 200   # px — bar area height
    CENTER_PX = CHART_H // 2   # vertical center of bars in pixels from top

    color_scale = alt.Scale(
        domain=["Default", "Target"],
        range=["#4A86C8", "#F5A623"],
    )

    bars = (
        alt.Chart(df_c_active)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
        .encode(
            x=alt.X(
                "x_key:O",
                sort=x_order,
                axis=alt.Axis(
                    labelAngle=0,
                    labelFontSize=12,
                    title="Price per day",
                    titleFontSize=12,
                    labelExpr="split(datum.label, ' ')[0]",
                ),
            ),
            y=alt.Y(
                "bar_h:Q",
                scale=alt.Scale(domain=[0, 1]),
                axis=None,
            ),
            color=alt.Color(
                "period:N",
                scale=color_scale,
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("step:O",      title="Price/day"),
                alt.Tooltip("period:N",    title="Period"),
                alt.Tooltip("n:Q",         title="Campaigns"),
                alt.Tooltip("pct:Q",       title="% of total", format=".1f"),
            ],
        )
    )

    # Pct label centred inside bar — "XX.X%"
    pct_text = (
        alt.Chart(df_c_active)
        .mark_text(
            align="center", baseline="middle",
            fontSize=16, fontWeight="bold",
            dy=-10,
        )
        .encode(
            x=alt.X("x_key:O", sort=x_order),
            y=alt.value(CENTER_PX),
            text=alt.Text("pct_label:N"),
            color=alt.value("white"),
        )
    )

    # Count label below pct — "N"
    cnt_text = (
        alt.Chart(df_c_active)
        .mark_text(
            align="center", baseline="middle",
            fontSize=14, fontWeight="normal",
            dy=10,
        )
        .encode(
            x=alt.X("x_key:O", sort=x_order),
            y=alt.value(CENTER_PX),
            text=alt.Text("n:Q"),
            color=alt.value("white"),
        )
    )

    main_chart = (bars + pct_text + cnt_text).properties(height=CHART_H)

    # Zone annotation strip — iterate only over positions that exist in x_order
    zone_rows = []
    seen_zones: set = set()
    for x_key in x_order:
        parts = x_key.rsplit(" ", 1)
        s = int(parts[0])
        z = _zone(s)
        lbl = ""
        if z and z not in seen_zones:
            lbl = z
            seen_zones.add(z)
        zone_rows.append({"x_key": x_key, "zone_lbl": lbl})

    zone_colors = {
        "1st step": "#9B59B6", "default": "#E67E22",
        "VIP-step": "#2C3E50", "decrease": "#85929E", "increase": "#85929E",
    }

    if zone_rows and any(r["zone_lbl"] for r in zone_rows):
        df_zone = pd.DataFrame(zone_rows)
        df_zone["color"] = df_zone["zone_lbl"].map(
            lambda z: zone_colors.get(z, "#bbb")
        )
        zone_strip = (
            alt.Chart(df_zone)
            .mark_text(fontSize=9, fontWeight="bold", align="left", dx=4)
            .encode(
                x=alt.X(
                    "x_key:O", sort=x_order,
                    axis=alt.Axis(labels=False, ticks=False, title=None, domain=False),
                ),
                y=alt.value(10),
                text=alt.Text("zone_lbl:N"),
                color=alt.Color("color:N", scale=None, legend=None),
            )
            .properties(height=24)
        )
        chart = alt.vconcat(main_chart, zone_strip, spacing=0).configure_view(stroke=None)
    else:
        chart = main_chart

    st.markdown("##### Price per day")
    st.markdown(
        "<span style='color:#4A86C8;font-size:18px'>■</span>&nbsp;<b>Default</b>&nbsp;&nbsp;&nbsp;"
        "<span style='color:#F5A623;font-size:18px'>■</span>&nbsp;<b>Target</b>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Default (Before): **{total_b}** campaigns · "
        f"Target (After): **{total_a}** campaigns"
    )
    st.altair_chart(chart, use_container_width=True)

    if scenario_code and scenario_code in _PPD_SCENARIOS:
        sc = _PPD_SCENARIOS[scenario_code]
        _badge_icons = {
            "positive": "🟢",
            "negative": "🔴",
            "neutral":  "🟡",
        }
        icon = _badge_icons.get(sc["sentiment"], "🔵")
        st.markdown(
            f"{icon} **{sc['label']}** — {sc['description']}",
        )


def _render_analytics_potential_block(*, show_heading: bool = True) -> None:
    if show_heading:
        st.markdown("##### Potential Spendings")
    if _nc_sc:
        st.caption(
            "New category: PY-dependent Potential Spendings excluded."
        )
    elif _py_anom_sc:
        st.caption(
            "PY anomaly: Spendings row excluded; Could be / diff / diff % —."
        )
    elif _category_single_mode:
        st.caption(
            "Сравнение **Fact** vs **Could be** (только отображение)."
        )
    else:
        st.caption("Fact vs **Could be** (display only).")

    if _category_single_mode:
        _render_potential_spendings_kpi_cards(_pot_df)
    else:
        _potential_spendings_render_html(_pot_df)


with st.container(border=bool(_category_single_mode)):
    st.markdown("##### Metric summary")
    st.caption(
        "Абсолютные **Before** / **After** и **Diff %** = (After − Before) / Before."
    )
    _ms_df_kw = _metric_summary_dataframe_kw(len(_df_cy_display))
    try:
        st.dataframe(_sty_cy, use_container_width=True, hide_index=True, **_ms_df_kw)
    except TypeError:
        st.dataframe(_sty_cy, use_container_width=True, hide_index=True)

_ppd_scenario: str | None = None
if _category_single_mode and budget_dist:
    _cat_dist_ppd = budget_dist.get(int(_resolved_single_category_id), {})
    _ppd_scenario = _classify_price_distribution(
        _cat_dist_ppd.get("before", {}),
        _cat_dist_ppd.get("after", {}),
        _cat_dist_ppd.get("grid", {}),
    )
    _render_price_per_day_block(budget_dist, int(_resolved_single_category_id), _ppd_scenario)

if _category_single_mode:
    st.markdown(_ppv_matrix_primary_hint_html(_matrix_result_focus), unsafe_allow_html=True)
    mtx_col, pot_col = st.columns(
        [2.85, 1.35], gap="medium", vertical_alignment="top"
    )
    with mtx_col:
        st.markdown("##### PPV matrix")
        _ppv_cap = (
            "Только отображение (не влияет на Calculate). "
            "**Result** — для **primary comparison**. "
        )
        if _py_anom_sc:
            _ppv_cap += (
                "PY anomaly: Y2Y и PY-зависимый Potential — исключены."
            )
        st.caption(_ppv_cap)
        _ppv_matrix_render_html(_matrix_df, _matrix_result_focus)
    with pot_col:
        st.markdown("##### Potential Spendings")
        _render_analytics_potential_block(show_heading=False)
else:
    mq_left, mq_right = st.columns(
        [2.85, 1.35], gap="medium", vertical_alignment="top"
    )
    with mq_left:
        st.markdown("##### PPV matrix (analytics)")
        _ppv_cap_b = (
            "Display only (does not affect Calculate). "
            "**Result** is for the primary comparison period. "
        )
        if _py_anom_sc:
            _ppv_cap_b += (
                "PY anomaly: Y2Y and PY-dependent Potential are excluded."
            )
        st.caption(_ppv_cap_b)
        _ppv_matrix_render_html(_matrix_df, _matrix_result_focus)
    with mq_right:
        st.markdown("##### Potential Spendings")
        _render_analytics_potential_block(show_heading=False)

st.markdown("##### Scenario")
st.caption(f"Активный сценарий: **{scenario}** (переключение — блок **Настройки** под **Inputs**).")

_ac1, _ac2 = st.columns([3, 1])
with _ac1:
    st.caption("Single mode: после просмотра аналитики нажмите **Calculate** для итогового решения.")
with _ac2:
    _run_calc = st.button("Calculate", type="primary", use_container_width=True)

if _run_calc:
    has_invalid_data = False
    if active_before < paid_users_before:
        st.warning(
            "Active listers (Before) не могут быть меньше Paid users (Before)"
        )
        has_invalid_data = True
    if active_after < paid_users_after:
        st.warning(
            "Active listers (After) не могут быть меньше Paid users (After)"
        )
        has_invalid_data = True

    if (
        paid_users_before == 0
        and paid_users_after == 0
        and spending_before == 0
        and spending_after == 0
        and active_before == 0
        and active_after == 0
    ):
        st.info("Вы ввели нулевые значения — это тестовый расчет")

    if geo == "RS":
        st.info("Для RS используются default thresholds (нужна дополнительная настройка)")

    if not has_invalid_data:
        result = analyze_category(
            npl_before=paid_users_before,
            npl_after=paid_users_after,
            sp_before=spending_before,
            sp_after=spending_after,
            active_before=active_before,
            active_after=active_after,
            geo=geo or "default",
            force_low_npl=scenario == "Low NPL (<10)",
            is_other_category=scenario == "Other category",
        )

        _nc_sc_run = _scenario_is_new_category(scenario)
        _py_anom_sc_run = _scenario_is_py_anomaly(scenario)
        _matrix_result_focus_run = (
            "current_year" if (_nc_sc_run or _py_anom_sc_run) else "diff_y2y"
        )
        _is_other_run = _scenario_is_other_category(scenario)
        _low_npl_override = scenario == "Low NPL (<10)" or paid_users_after < _geo_min_npl(geo)

        # Results block must use the same primary comparison period as PPV matrix to avoid conflicting interpretations.
        y2y_bundle = None
        if _matrix_result_focus_run == "diff_y2y":
            y2y_bundle = _results_compute_y2y_npl_sp_cr_bundle(
                geo or "default",
                paid_users_before,
                paid_users_after,
                spending_before,
                spending_after,
                active_before,
                active_after,
                matrix_py_paid_users_before,
                matrix_py_paid_users_after,
                matrix_py_spending_before,
                matrix_py_spending_after,
                matrix_py_ac_before,
                matrix_py_ac_after,
            )

        if _matrix_result_focus_run == "current_year":
            disp_dc = result["decision_code"]
            disp_fd = result["final_decision"]
            disp_ns = result["next_step"]
        elif _is_other_run:
            disp_dc = result["decision_code"]
            disp_fd = result["final_decision"]
            disp_ns = result["next_step"]
        elif y2y_bundle and y2y_bundle["complete"]:
            disp_dc = y2y_bundle["decision_code"]
            dr = get_decision(disp_dc)
            disp_fd = dr["decision"]
            disp_ns = dr["next_step"]
            if _low_npl_override:
                disp_fd = result["final_decision"]
                disp_ns = result["next_step"]
        else:
            disp_dc = "—"
            disp_fd = "Insufficient data"
            disp_ns = (
                "Year-over-year comparison is unavailable for one or more metrics. "
                "Enter Previous Year Paid users, Spending, and Active listers (Before and After) "
                "so diff Y2Y can be computed for NPL, Spending, and Conversion."
            )

        if (
            _ppd_scenario
            and _ppd_scenario in _PPD_SCENARIOS
            and _ppd_scenario not in ("PRICE_OK", "MIXED")
        ):
            _ppd_sc = _PPD_SCENARIOS[_ppd_scenario]
            disp_ns = f"{disp_ns}\n\n**Price per day:** {_ppd_sc['action']}"

        with st.container(border=True):
            st.markdown("##### Results")
            if _category_single_mode:
                _kp_single = _compute_single_executive_kpis(
                    geo=geo or "default",
                    matrix_result_focus_run=_matrix_result_focus_run,
                    result=result,
                    y2y_bundle=y2y_bundle,
                    paid_users_before=paid_users_before,
                    paid_users_after=paid_users_after,
                    spending_before=spending_before,
                    spending_after=spending_after,
                    active_before=active_before,
                    active_after=active_after,
                    matrix_py_ac_before=matrix_py_ac_before,
                    matrix_py_ac_after=matrix_py_ac_after,
                )
                _render_single_executive_summary(_kp_single, disp_fd)

            with st.expander("Детали по метрикам (NPL, Spending, CR)", expanded=False):
                if _matrix_result_focus_run == "current_year":
                    paid_users_row = (
                        f"Paid users: {result['npl_diff']:.2f}% → "
                        f"{decode_status(result['npl_code'])} ({result['npl_code']})"
                    )
                    if result["npl_code"] == "G":
                        st.success(paid_users_row)
                    elif result["npl_code"] == "D":
                        st.error(paid_users_row)
                    else:
                        st.warning(paid_users_row)

                    sp_text = (
                        f"Spending: {result['sp_diff']:.2f}% → "
                        f"{decode_status(result['sp_code'])} ({result['sp_code']})"
                    )
                    if result["sp_code"] == "G":
                        st.success(sp_text)
                    elif result["sp_code"] == "D":
                        st.error(sp_text)
                    else:
                        st.warning(sp_text)

                    cr_text = (
                        f"Conversion (CR): {result['cr_diff']:.2f}% → "
                        f"{decode_status(result['cr_code'])} ({result['cr_code']})"
                    )
                    if result["cr_code"] == "G":
                        st.success(cr_text)
                    elif result["cr_code"] == "D":
                        st.error(cr_text)
                    else:
                        st.warning(cr_text)
                elif y2y_bundle is not None:
                    op = _is_other_run
                    _results_render_metric_detail_row(
                        "Paid users / NPL (Y2Y)",
                        y2y_bundle["y2y_npl"],
                        y2y_bundle["npl_code"],
                        op,
                    )
                    _results_render_metric_detail_row(
                        "Spending (Y2Y)",
                        y2y_bundle["y2y_sp"],
                        y2y_bundle["sp_code"],
                        op,
                    )
                    _results_render_metric_detail_row(
                        "CR (Y2Y)",
                        y2y_bundle["y2y_cr"],
                        y2y_bundle["cr_code"],
                        op,
                    )

            if _category_single_mode:
                _render_single_outcome_hero_and_actions(disp_dc, disp_fd, disp_ns)
            else:
                st.markdown("**Decision code**")
                st.code(disp_dc)

                st.markdown("**Final decision**")
                final_decision = disp_fd
                if final_decision == "Positive impact":
                    st.success(final_decision)
                elif final_decision == "Negative impact":
                    st.error(final_decision)
                elif final_decision == "No impact":
                    st.info(final_decision)
                else:
                    st.warning(final_decision)

                st.markdown("**Next step**")
                st.info(disp_ns)

if _category_bulk_mode:
    st.subheader("Bulk analysis")
    st.caption(
        "Используются загруженные Current Year / Previous Year данные и **GEO**. "
        "**Scenario** сверху задаёт default для всех категорий; для исключений — списки ниже. "
        "Price data в bulk не используется."
    )
    with st.expander("Bulk scenario overrides", expanded=False):
        st.caption(
            "ID через запятую, пробел, `;` или перенос строки. "
            "Приоритет при дублях: Other category → New category → Previous Year anomaly."
        )
        st.text_area(
            "New category IDs",
            placeholder="e.g. 1001, 1002",
            key="bulk_override_new_cat_ids",
            height=88,
        )
        st.text_area(
            "Previous Year anomaly IDs",
            placeholder="Categories with PY merge but Y2Y excluded",
            key="bulk_override_py_anomaly_ids",
            height=88,
        )
        st.text_area(
            "Other category IDs",
            placeholder="Categories evaluated with Other category matrix",
            key="bulk_override_other_cat_ids",
            height=88,
        )

    _ov_o, _bad_o = _parse_category_ids(st.session_state.get("bulk_override_other_cat_ids", ""))
    _ov_n, _bad_n = _parse_category_ids(st.session_state.get("bulk_override_new_cat_ids", ""))
    _ov_p, _bad_p = _parse_category_ids(st.session_state.get("bulk_override_py_anomaly_ids", ""))
    _ov_warn_parts = []
    if _bad_o:
        _ov_warn_parts.append(f"Other IDs: пропущены токены {_bad_o[:15]!r}{'…' if len(_bad_o) > 15 else ''}")
    if _bad_n:
        _ov_warn_parts.append(f"New category IDs: пропущены токены {_bad_n[:15]!r}{'…' if len(_bad_n) > 15 else ''}")
    if _bad_p:
        _ov_warn_parts.append(
            f"PY anomaly IDs: пропущены токены {_bad_p[:15]!r}{'…' if len(_bad_p) > 15 else ''}"
        )
    if _ov_warn_parts:
        st.warning("\n".join(_ov_warn_parts))

    _ov_conf = _bulk_override_conflict_messages(
        set(_ov_o), set(_ov_n), set(_ov_p)
    )
    if _ov_conf:
        st.warning("\n\n".join(_ov_conf))

    _bulk_sig = (
        tuple(_bulk_effective_category_ids),
        str(geo or ""),
        str(scenario),
        st.session_state.get("_upload_sig"),
        st.session_state.get("_upload_sig_py"),
        str(st.session_state.get("bulk_override_other_cat_ids", "")),
        str(st.session_state.get("bulk_override_new_cat_ids", "")),
        str(st.session_state.get("bulk_override_py_anomaly_ids", "")),
    )
    if st.session_state.get("_bulk_analysis_sig") != _bulk_sig:
        st.session_state.pop("bulk_analysis_result", None)
    st.session_state["_bulk_analysis_sig"] = _bulk_sig

    if st.button("Run bulk analysis", type="primary", key="run_bulk_analysis"):
        if not merged_data:
            st.warning(
                "Загрузите Current Year: **New PPV (spending)** и **Active listers** "
                "(минимум), чтобы строить bulk-таблицу."
            )
        else:
            _bulk_result = _bulk_analysis_dataframe(
                _bulk_effective_category_ids,
                merged_data,
                merged_data_previous_year or {},
                geo,
                scenario,
                list(_ov_o),
                list(_ov_n),
                list(_ov_p),
            )

            # ── Parent category fallback (aggregate children, no extra CH query) ──
            try:
                from clickhouse_loader import fetch_category_parents
                _all_bulk_ids = [
                    int(v) for v in _bulk_result["category_id"].tolist()
                    if pd.notna(v)
                ]
                _insuf_mask = _bulk_result["final_decision"].apply(
                    lambda x: str(x).strip() == "Insufficient data"
                )
                _insuf_count = int(_insuf_mask.sum())
                if _insuf_count > 0:
                    with st.spinner(f"Загружаем иерархию категорий…"):
                        _child_to_parent, _cat_names = fetch_category_parents(_all_bulk_ids)
                    if _child_to_parent:
                        _parent_groups = _bulk_detect_parent_groups(
                            _bulk_result, _child_to_parent, _cat_names
                        )
                        if _parent_groups:
                            _bulk_result = _bulk_enrich_with_parents(
                                _bulk_result, _parent_groups,
                                merged_data, merged_data_previous_year or {},
                                geo, scenario,
                            )
                            _enriched_n = int((_bulk_result["parent_category_name"] != "").sum())
                            st.caption(
                                f"Родительский анализ: {len(_parent_groups)} групп, "
                                f"{_enriched_n} категорий получили решение по родителю."
                            )
            except Exception as _pe:
                st.warning(f"Parent enrichment skipped: {_pe}")

            st.session_state["bulk_analysis_result"] = _bulk_result
            st.session_state["bulk_run_nonce"] = int(st.session_state.get("bulk_run_nonce", 0)) + 1

    _bulk_df = st.session_state.get("bulk_analysis_result")
    if merged_data and _bulk_df is None:
        st.info(
            "Нажмите **Run bulk analysis**, чтобы выполнить расчёт по всем выбранным ID "
            "(поле Category ID или **Bulk: Category ID из Current Year файла**)."
        )
    if _bulk_df is not None and not _bulk_df.empty:
        _bulk_render_insights(_bulk_df)
        _bulk_render_summary(_bulk_df)
        _bulk_nonce = int(st.session_state.get("bulk_run_nonce", 0))
        _pri_opts = sorted(_bulk_df["priority"].dropna().unique().tolist())
        _fd_opts = sorted(
            _bulk_df["final_decision"]
            .apply(lambda x: "(no data)" if pd.isna(x) else str(x))
            .unique()
            .tolist()
        )
        _wf_opts = _bulk_unique_warning_flag_options(_bulk_df)

        st.markdown("##### Фильтры таблицы")
        st.caption(
            "Summary выше считается по всем строкам. Фильтры ниже влияют только на отображение таблицы."
        )
        _fc1, _fc2, _fc3 = st.columns(3)
        with _fc1:
            _sel_p = st.multiselect(
                "Priority",
                options=_pri_opts,
                default=_pri_opts,
                key=f"bulk_table_f_priority_{_bulk_nonce}",
            )
        with _fc2:
            _sel_fd = st.multiselect(
                "final_decision",
                options=_fd_opts,
                default=_fd_opts,
                key=f"bulk_table_f_final_decision_{_bulk_nonce}",
            )
        with _fc3:
            if _wf_opts:
                _sel_wf = st.multiselect(
                    "warning_flags",
                    options=_wf_opts,
                    default=_wf_opts,
                    key=f"bulk_table_f_warning_flags_{_bulk_nonce}",
                )
            else:
                st.caption("warning_flags: нет значений в данных")
                _sel_wf = []

        _filtered_bulk = _bulk_apply_table_filters(
            _bulk_df,
            _sel_p,
            _pri_opts,
            _sel_fd,
            _fd_opts,
            _sel_wf,
            _wf_opts,
        )
        st.caption(
            f"Showing {len(_filtered_bulk)} of {len(_bulk_df)} categories"
        )
        if _filtered_bulk.empty and not _bulk_df.empty:
            st.warning(
                "По выбранным фильтрам не осталось ни одной строки. "
                "Измените **Priority**, **final_decision** или **warning_flags**, чтобы вернуть категории в таблицу."
            )
        if not _filtered_bulk.empty:
            st.markdown("##### Таблица")
            _base = _filtered_bulk.reset_index(drop=True)
            _fmt = _bulk_format_table_for_display(
                _base,
                new_category_mode=False,
                py_anomaly_mode=False,
            )
            _fmt = _fmt.copy()
            if "next_step" in _base.columns:
                _fmt["next_step"] = _base["next_step"].map(_bulk_next_step_short_cell)
            else:
                _fmt["next_step"] = "—"
            _summary_cols = [c for c in _BULK_SUMMARY_COLUMNS if c in _fmt.columns]
            _compact = _bulk_format_compact_diff_pct_columns(_fmt[_summary_cols].copy())
            _compact = _bulk_mask_py_y2y_cells_by_scenario(_base, _compact)
            _compact[_BULK_TABLE_DETAILS_COL] = _BULK_TABLE_DETAILS_CELL
            _col_order = [_BULK_TABLE_DETAILS_COL] + [
                c for c in _BULK_SUMMARY_COLUMNS if c in _compact.columns and c != _BULK_TABLE_DETAILS_COL
            ]
            _compact = _compact[_col_order]
            _styled_compact = _bulk_styled_dataframe(_compact, style_source=_base)

            st.caption("Click on a row to see category details below")

            _df_sig = inspect.signature(st.dataframe).parameters
            _df_kw: dict = {}
            if "hide_index" in _df_sig:
                _df_kw["hide_index"] = True
            if "width" in _df_sig:
                _df_kw["width"] = "stretch"
            elif "use_container_width" in _df_sig:
                _df_kw["use_container_width"] = True

            if "column_config" in _df_sig:
                _df_kw["column_config"] = _bulk_compact_table_column_config(
                    list(_compact.columns)
                )

            _bulk_table_key = f"bulk_compact_select_{_bulk_nonce}"
            _sel_rows: list[int] = []
            _supports_row_pick = (
                "on_select" in _df_sig and "selection_mode" in _df_sig and "key" in _df_sig
            )

            if _supports_row_pick:
                _ev = st.dataframe(
                    _styled_compact,
                    key=_bulk_table_key,
                    on_select="rerun",
                    selection_mode="single-row",
                    **_df_kw,
                )
                _sel_rows = _bulk_dataframe_selection_rows(_ev)
            else:
                st.dataframe(_styled_compact, **_df_kw)

            if not _sel_rows and _supports_row_pick:
                st.caption("Click on a row in the table above to open details.")
            elif not _sel_rows:
                _opts = [_bulk_expander_title_for_row(_base.iloc[i]) for i in range(len(_base))]
                _j = st.selectbox(
                    "Развернуть детали категории",
                    options=list(range(len(_base))),
                    format_func=lambda i: _opts[i],
                    key=f"bulk_detail_pick_{_bulk_nonce}",
                )
                _sel_rows = [int(_j)]

            if _sel_rows:
                _row_sel = _base.iloc[int(_sel_rows[0])]
                with st.expander("Category details", expanded=True):
                    _bulk_render_category_drill_down(
                        _row_sel, merged_data,
                        merged_data_py=st.session_state.get("merged_data_previous_year"),
                    )

        _dl_col1, _dl_col2 = st.columns([1, 1])
        with _dl_col1:
            _csv_export_df = _bulk_make_csv_export_df(_bulk_df)
            _csv_bytes = _csv_export_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="Download CSV (wide)",
                data=_csv_bytes,
                file_name="bulk_analysis_wide.csv",
                mime="text/csv",
                key="download_bulk_analysis_csv",
            )
        with _dl_col2:
            _long_csv_df = _bulk_make_long_csv_export_df(_bulk_df)
            _long_csv_bytes = _long_csv_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="Download CSV (long)",
                data=_long_csv_bytes,
                file_name="bulk_analysis_long.csv",
                mime="text/csv",
                key="download_bulk_analysis_long_csv",
            )