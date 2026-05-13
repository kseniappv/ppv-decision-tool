# Справочник метрик

Все формулы ниже отражают **текущий код** (`decision_engine.py`, `app.py`, `ppv_data_loader.py`).

## Базовые определения

| Метрика (business) | Ключ в merge bucket | Тип в UI |
|--------------------|---------------------|----------|
| New Paid Listers / Paid users | `paid_users` | int |
| Spending | `spending` | float |
| Active listers | `active_listers` | int |
| CR (Conversion) | не хранится отдельно | `paid_users / active_listers` |

## Функция `diff` (decision engine)

Процент изменения **Before → After**:

```text
diff(b, a) = (a - b) / b * 100     если b ≠ 0
           = 0                     если b = 0
```

Используется для NPL, Spending, Active, и для **CR** (как diff между долями до/после).

## Классификация G / S / D

Для значения **x** (процент diff) и порогов **growth**, **decline** из **`GEO_THRESHOLDS[geo][metric]`**:

| Код | Условие |
|-----|---------|
| G | x > growth |
| D | x < decline |
| S | иначе |

## CY diff (Current Year)

Источник для решения: **`analyze_category`** возвращает **`npl_diff`**, **`sp_diff`**, **`cr_diff`**, **`active_diff`** — все через **`diff`** на соответствующих Before/After.

## PY diff (Previous Year)

В bulk / матрице для Previous Year периода:

```text
py_metric_diff = _engine_style_diff(before_py, after_py)
```

где **`_engine_style_diff`** в **`app.py`** совпадает по формуле с **`decision_engine.diff`**.

**CR PY**: сначала **`cr_b = npl_py / active_py`** (при active=0 в bulk helper — 0), затем diff CR.

## Y2Y diff (год к году динамики)

Для **NPL, Spending, CR** в **`_results_compute_y2y_npl_sp_cr_bundle`**:

1. `cy_d = _matrix_pct_diff(cy_before, cy_after)` — то же что relative change %  
2. `py_d = _matrix_pct_diff(py_before, py_after)`  
3. `y2y = cy_d - py_d` при обоих не `None`  

Затем **G/S/D** классифицируют **y2y** с GEO порогами.

В **bulk** для отображаемых колонок **`y2y_*`** используется **разность** CY diff % и PY diff % для той же метрики (см. **`_y2y`** во **`_bulk_analysis_dataframe`**): согласовано с идеей «дельта динамик», при этом **решение** по diff Y2Y bundle использует тот же конструктор, что single.

**Y2Y Active listers** в таблице bulk: `cy_active_listers_diff - py_active_listers_diff` (при отсутствии PY — `None`).

## Дополнительные CY метрики (informational)

Из **`_BULK_CY_EXTRA_DIFF_PCT_SPECS`** (имена колонок — второй элемент tuple):

| Имя колонки в CSV / `bulk_df` | Источник поля merge |
|------------------------------|---------------------|
| `CY Diff % Campaign per User` | campaign_per_user |
| `CY Diff % New campaign cnt` | new_campaign_cnt |
| `CY Diff % Price per day` | price_per_day |
| `CY Diff % ARPpCampaign` | arp_p_campaign |
| `CY Diff % Refund` | refund |
| `CY Diff % %Campaign with refund` | pct_campaign_with_refund |
| `CY Diff % Plan Imp per Campaign` | plan_imp_per_campaign |
| `CY Diff % Fact Imp per Campaign` | fact_imp_per_campaign |
| `CY Diff % %Execution Inventory` | pct_execution_inventory |

Формула: **`_matrix_pct_diff(before, after)`** = \((after-before)/before·100\) или `None` если нет данных / before=0 (см. **`_matrix_pct_diff`** в **`app.py`**).

**Не участвуют** в **`analyze_category`** и в **Y2Y decision bundle**.

## Участие в decision (кратко)

| Метрика / производная | В decision? |
|----------------------|-------------|
| NPL % diff CY | Да |
| Spending % diff CY | Да |
| CR % diff CY | Да |
| Active % diff CY | Да в **Other**; иначе косвенно через CR; отображается в bulk compact |
| PY / Y2Y как выше | Да, когда primary = diff Y2Y и bundle complete |
| Extra CY diff cols | Нет (только аналитика / CSV / drill-down additional) |

## Матрица и «Result» колонка

Для строки **Active listers** в **`_build_ppv_matrix_rows`** внутренний ключ порога — **`npl`** (как у Paid users) — **как в текущем коде**; семантически строка показывает относительное изменение числа активных.

---

Ссылки: [decision_logic.md](decision_logic.md), [bulk_analysis.md](bulk_analysis.md).
