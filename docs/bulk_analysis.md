# Bulk analysis (`app.py`)

Самый объёмный режим: одна таблица по **множеству `category_id`**, с возможностью перекатегоризации сценариев по строке.

## Активация bulk mode

В **`app.py`** флаги **`_bulk_from_text`** (в поле Category ID разобрано **&gt; 1** валидный ID) или **`_bulk_from_pick`** (множественный выбор категорий). Тогда **`_category_bulk_mode`** и отображается подзаголовок **Bulk Category IDs** и блок **Bulk analysis**.

**Merge по файлам (важно):** чтобы в **`merged_data`** и **`merged_data_previous_year`** появились категории из выгрузок, для **Current Year** нужны **оба** файла — **New PPV (spending)** и **Active listers** (пересечение по **`category_id`**). Один файл без второго ⇒ merge не запускается, в блоке статусов bulk все ID будут «вне данных». То же для **Previous Year**: оба слота (**Previous Year New PPV** и **Previous Year Active listers**).

## Парсинг category ID

**`_parse_category_ids`**: разделители **пробел, запятая, `;`, перенос строки**; только целые числа; дубликаты схлопываются в порядке появления для текста; «пик» из UI — отдельный sorted список.

## Расчёт таблицы: `bulk_analysis_result`

Кнопка **Run bulk analysis** вызывает **`_bulk_analysis_dataframe`** с:

| Аргумент | Смысл |
|----------|--------|
| `_bulk_effective_category_ids` | Список ID из текста или multiselect |
| `merged_data` | CY merge |
| `merged_data_previous_year` | PY merge (может быть `{}`) |
| `geo` | Из сайдбара |
| `scenario` | Глобальный Scenario |
| Списки override | Три text_area → parse → sets |

Строк без данных CY в merged: **`status`** = **`Missing current year data`**, метрики `None`, priority bucket missing.

Сортировка результата: по **`priority`** порядковому ключу, затем **`category_id`** (поле **`_pri_sort`** внутреннее, затем удаляется).

## `scenario_used` (построчно)

Функция **`_bulk_resolve_scenario_used`**:

1. Если ID в **`Other`** override → **`Other category`**  
2. Иначе **`New category`** override  
3. Иначе **`Previous Year anomaly`** override  
4. Иначе если **`paid_users_after < 10`** → **`Low NPL auto`**  
5. Иначе строка **`scenario`** из sidebar (**Regular**, **Low NPL (&lt;10)**, и т.д.)

Конфликты между списками (один ID в двух текстовых полях) — **`_bulk_override_conflict_messages`** и предупреждения в Streamlit.

## Согласованность с single: primary period решения

В каждой строке:

- **`_matrix_focus_run`**: **`current_year`** если New или PY anomaly, иначе **`diff_y2y`**.  
- Если **`current_year`** или **Other**: итог — из **`analyze_category`** по CY.  
- Иначе при наличии PY merge для категории: **`_results_compute_y2y_npl_sp_cr_bundle`** как в single → **`get_decision`**.  
- Если пакет неполный или нет PY: **`Insufficient data`**, текст **`_BULK_Y2Y_DECISION_UNAVAILABLE_NEXT_STEP`**.  
- Если **`scenario_used`** в (**`Low NPL (<10)`** **или** **`Low NPL auto`**) или **`npl_after < 10`** **и** сработала ветка с полным **Y2Y**‑расчётом: итог Y2Y **перебивается** на результат CY **`analyze_category`** (Insufficient, если применимо) — см. **`_low_npl_override_run`**. Строки **Other category** решение берётся из ветви CY Other **до** входа в Y2Y‑пакет и эта подмена на них не влияет.

### `warning_flags` (CSV / не в compact столбце)

Строковое поле, токены через запятую, формируется **`_bulk_row_warning_flags`**:

| Токен | Когда |
|-------|-------|
| `MISSING_CY` | Нет CY данных категории в merge |
| `LOW_NPL` | См. код: insufficient + low sample |
| `Y2Y_DECISION_UNAVAILABLE` | Неполный Y2Y расчёт |
| `NEW_CATEGORY` | scenario_used |
| `PY_ANOMALY` | scenario_used PY anomaly |
| `MISSING_PY` | Контекст Regular/Low без PY bucket (не для New/PY anom/Other) |
| `OTHER_CATEGORY` | scenario_used Other |

## Полный DataFrame строки колонки (ориентир)

После добавления активных пользователей в diff блоки порядок в коде включает (см. `cols` в **`_bulk_analysis_dataframe`**):

- Идентификация и сценарий: `category_id`, `category_name`, `scenario_used`, `priority`  
- CY decision diffs + **`cy_*_extra`** столбцы (`_BULK_CY_EXTRA_DIFF_COLUMN_NAMES`)  
- PY / Y2Y diff столбцы (включая **active_listers**)  
- `decision_code`, `final_decision`, `next_step`, `warning_flags`, `status`  

**Download CSV** — **`_bulk_df.to_csv`** полного набора столбцов.

## Компактная таблица (видимые колонки)

Константа **`_BULK_SUMMARY_COLUMNS`** определяет подмножество для **`st.dataframe`**:

Порядок (внутренние имена):

1. Колонка **Details** (**`🔍`**) добавляется в UI первой  
2. `category_id`, `category_name`, `scenario_used`  
3. **CY**: `cy_paid_users_diff`, `cy_spending_diff`, `cy_cr_diff`, `cy_active_listers_diff`  
4. **PY**: аналогично `py_*`  
5. **Y2Y**: `y2y_*` четыре метрики  
6. **`final_decision`**, **`next_step`** (**краткий label** через **`_bulk_format_next_step_short`**, полный текст в drill-down)

**Не показываются** в компактном виде: `priority`, `status`, дополнительные CY spending метрики из `_BULK_CY_EXTRA_DIFF_*`.

### Отображение %

Цепочка: **`_bulk_format_table_for_display`** → subset **`_bulk_format_compact_diff_pct_columns`** → **`format_percent`** для колонок, чьи имена заканчиваются на **`_diff`**.

## Маскировка PY / Y2Y построчно

**`_bulk_mask_py_y2y_cells_by_scenario`**: если **`scenario_used == "New category"`** → в compact для этой строки **все PY и Y2Y** ячейки **`—`**; если **`Previous Year anomaly`** → только **Y2Y** часть **`—`**.

Логику раскраски строк см. **`_bulk_row_background`** (**`final_decision`**, затем статус missing CY).

## Фильтрация таблицы

Мультиселекты **Priority**, **final_decision**, **warning_flags** — **`_bulk_apply_table_filters`**.

- Если выбраны **все** опции по измерению — фильтр по этому измерению **не режет**.  
- **warning_flags**: строка проходит если пересечение токенов строки и выбранных флагов непусто (**OR по токенам** среди выбранных значений фильтра).  
- Пустые multiselect трактуются как «без ограничений» для этой оси там, где так задокументировано в коде.

## Сортировка

Только на уровне **`_bulk_analysis_dataframe`**: после расчёта. Фильтры **пересортировку не добавляют** — порядок строк сохраняет порядок в отфильтрованном срезе.

## Summary insights + Overview KPI

**`_bulk_render_insights`** — сводный markdown по счётчикам (**summary insights** текстом).

**`_bulk_render_summary`** — метрики priority (6 блоков), breakdown в expanders.

**`_bulk_render_compact_dashboard`** — блок **Overview** перед таблицей: счётчики решений (**priority** тех же семейств что Summary), строка **`scenario_used`**, опционально **среднее** **`cy_spending_diff`** и **`y2y_cr_diff`** численно (**не** переопределение решений).

## Category details в bulk

При выборе строки (**`st.dataframe`**, `selection_mode='single-row'`) или **`selectbox`** fallback — **`Category details`** expander **`_bulk_render_category_drill_down`**: метрики primary + **Additional metrics** из merge ведра **before/after** (включая все доп. поля loaded).

## Column config и лейблы

**`_bulk_compact_table_column_config`** + **`_bulk_compact_column_ui_labels`**: человекочитаемые заголовки для compact; при наличии параметра **`pinned`** у `TextColumn` — закрепление первых колонок (Details, category, scenario).

## Next step в компактной таблице

Колонка показывает **короткий** текст по эвристикам **`_bulk_format_next_step_short`**; полный **`next_step`** остаётся в раскрытии Category details.

---

## Метрики: decision vs informational

| Участвуют в `analyze_category` / Y2Y decision bundle | Только в drill-down / CSV extra cols |
|-----------------------------------------------------|--------------------------------------|
| Paid users, Spending, CR (через NPL & Active), Active listers diff (Other + для отображения Y2Y/CY) | `_BULK_CY_EXTRA_DIFF_*` (Campaign per User, Refund, Plan/Fact Imp, …) |

Имена extra колонок см. **`_BULK_CY_EXTRA_DIFF_PCT_SPECS`** в **`app.py`**.

См. также: [metrics.md](metrics.md), [ui_ux_rules.md](ui_ux_rules.md), [scenarios.md](scenarios.md).
