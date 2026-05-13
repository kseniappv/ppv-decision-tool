# Сценарии (Scenario)

Сценарий задаётся в **настройках** Streamlit (**`Scenario`**). В **bulk** тот же сценарий — **глобальный default** для каждой категории, если не применены overrides или авто‑Low NPL.

Ниже — соответствие **коду** (`app.py`, `decision_engine.py`) и того, какой **primary comparison period** показывает **PPV matrix** и **Results** после Calculate / Run bulk analysis.

Общее правило **primary**:

| Primary | Условие |
|---------|---------|
| **Current Year** | Сценарий **New category** или **Previous Year anomaly** |
| **diff Y2Y** | Все прочие (Regular, Low NPL, Other), при наличии данных для полного Y2Y пакета |

---

## Regular

### Логика

- Вызывается **`analyze_category(..., is_other_category=False)`** на CY метриках.  
- Если primary = **diff Y2Y**, итоговый **`decision_code` / final_decision** для пользователя собираются из **`_results_compute_y2y_npl_sp_cr_bundle`** + **`get_decision`**, см. **`app.py`**.  
- Если **`scenario == "Low NPL (<10)"`** **или** `paid_users_after < 10`: итог **CY `analyze_category`** с insufficient перезаписывает результат Y2Y (как при single Calculate, так и в bulk строке при `_low_npl_override_run`).

### PPV matrix

- Предыдущий год и колонки Y2Y **показаны** при наличии PY данных.  
- Колонка **Result** только для строки от primary (здесь **diff Y2Y** с классификацией G/S/D через GEO).

### Potential Spendings

- PY‑зависимые строки активны при наличии PY (исключены только New / PY anomaly сценарии).

---

## Low NPL (&lt;10)

### Логика

- При **Calculate / bulk**: **`force_low_npl=True`** в **`analyze_category`** (single: `scenario == "Low NPL (<10)"`).  
- Внутри **`analyze_category`** (не Other): после базовой матрицы принудительно **`Insufficient data`** и фиксированный текст next step про малое NPL — **если** `force_low_npl or npl_after < 10`.  
- Если primary всё же **diff Y2Y**, UI может сначала посчитать Y2Y decision, затем подменить его CY insufficient при override (см. **`_low_npl_override`** single / **`_low_npl_override_run`** bulk).

### Визуальная связь матрицы

- Как Regular по primary (обычно **diff Y2Y**), если сценарий не переключает на current year.

---

## Low NPL auto (**только bulk**)

Не отдельный пункт sidebar, а **`scenario_used`**, когда:

1. Category ID не в override‑списках **Other / New / PY anomaly**  
2. **`paid_users_after < 10`** → **`_bulk_resolve_scenario_used`** возвращает **`"Low NPL auto"`** вместо глобального сценария  

Дальнейшая строка считается с **`force_low_npl`** как для Low NPL (поскольку `row_force_low` включает **Low NPL auto** и **Low NPL (&lt;10)** overrides).

---

## New category

### Логика

- **analyze_category**: `is_other_category=False`.  
- **Primary**: **`current_year`**. Отображение и финальный результат — из **CY **`analyze_category`**** (код решения три буквы NPL-SP-CR CY).  
- **Y2Y** в матрице **отключены** (**`omit_previous_year=True`** для построения строк матрицы). Single Results detail не переходит на Y2Y‑пучок.

### PPV matrix

- Строка Previous Year как **«—»**; Y2Y — **«—»**.  
- **Result** считают только CY diff по метрикам.

### Bulk

ID в списке **New category overrides** получают **`scenario_used == "New category"`** без авто‑low NPL.

---

## Previous Year anomaly

### Логика

- **Primary**: **`current_year`** (как у New category для отображения).  
- **`analyze_category`** на CY.  
- В матрице: **`omit_y2y_only=True`** когда не New одновременно — **PY Before/After** показываются, но **`y2y` и Result по Y2Y** — **`—`** (нет diff Y2Y как primary).  

### Potential Spendings

Исключены PY‑зависимые части там же, где New — см. блок **`omit_py`** в **`app.py`**.

### Bulk

Override **Previous Year anomaly** → строка считаётся с CY primary; **warning_flags** могут включать **`PY_ANOMALY`**; столбцы **PY/Y2Y** в компактной таблице могут быть **замены на «—»** по строке см. masking.

---

## Other category

### Логика

- **`analyze_category(..., is_other_category=True)`** → код **`O: …`** и **`OTHER_CATEGORY_DECISIONS`**.  
- При **Calculate / bulk**: **даже если** primary для матрицы «обычный» режим задаёт diff Y2Y, **`final_decision` после оркестрации** всё равно берётся из **`analyze_category`** (Other), а не из Y2Y трёхбуквенной матрицы — см. ветви **`_is_other_run`** в **`app.py`**.  
- Для строк **Other category** результат в bulk/single уже выбран в ветви **`analyze_category` (Other)** до расчёта Y2Y; переопределение insufficient по Low NPL из ветки Y2Y‑bundle **не применяется** к этим строкам.

### PPV matrix (diff Y2Y primary)

При отображении **Result** для Y2Y к классификации добавляется префикс **`O:`** (источник **`_build_ppv_matrix_rows`**, **`is_other_category_scenario`**).

---

## Bulk overrides (приоритет)

Реализовано в **`_bulk_normalize_override_id_sets`** / **`_bulk_resolve_scenario_used`**:

```text
Other category ID  >  New category ID  >  Previous Year anomaly ID  >  (авто Low NPL если NPL после < 10)  >  глобальный Scenario
```

Конфликты один ID в нескольких списках — предупреждения в UI (применяется более приоритетный сценарий).

---

## Сводная таблица

| Сценарий | `analyze_category` Other? | Primary в matrix / Results | PY row в матрице | Y2Y в матрице |
|----------|-------------------------|----------------------------|-----------------|---------------|
| Regular | Нет | diff Y2Y (если полные данные) | Да | Да |
| Low NPL (&lt;10) | Нет | diff Y2Y | Да | Да |
| New category | Нет | Current Year | — | — |
| PY anomaly | Нет | Current Year | Да | — (Y2Y скрыт) |
| Other category | Да | diff Y2Y labels с `O:` | Да | Да |

Детали строк bulk: [bulk_analysis.md](bulk_analysis.md).
