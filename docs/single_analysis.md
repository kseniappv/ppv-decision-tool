# Single category analysis (`app.py`, single режим)

Single режим активен, когда в текущих данных режим **`_category_single_mode`** (один **`category_id`**, без bulk списка). Ниже — типовой поток **по текущей реализации**.

## Загрузка файлов и merge

- Выгрузки **Current Year**: spending / active и др. переменные сливаются через **`load_and_merge_spending_active`** (**`ppv_data_loader.py`**), пересечение по **`category_id`** теми файлами, которые реально поданы.  
- **Previous Year** — отдельный merge того же семейства.  
- Соответствие колонок экспорта — алиасы в **`SPENDING_MEASURE_ALIASES`** и нормализация имён.

## Auto-fill матрицы

После успешного merge для выбранного `category_id` сессионные ключи **`st.session_state`** заполняются **Before / After / baseline** для метрик (**`paid_users`**, **`spending`**, **`active_listers`**, и др. по конфигурации OCR/матрицы). Логику см. вокруг ключей **`_cy_sess_key`**, блоки merge dirty и восстановление **`_cy_ocr_override`**.

## Ввод текущего года и Previous Year в UI

- **Current Year**: number_input / OCR вкладки — значения читаются в переменные **`paid_users_before/after`**, **`spending_*`**, **`active_before/after`**. Разбор OCR: именованные строки и якоря; при «голых» числовых строках Period Group без подписей метрик — позиционный fallback (см. [ui_ux_rules.md](ui_ux_rules.md), OCR).
- **Previous Year** — expander **`Previous Year (...)`**: **`matrix_py_*`** поля чисел; для сценария **New category** подсказано, что PY не используется.

## PPV matrix (analytics)

Подзаголовок **«PPV matrix (analytics)»** (**`border=True`** контейнер):

- Строится через **`_build_ppv_matrix_rows`** → DataFrame со строками **Paid users**, **Spending**, **CR**, **Active listers**.  
- Капшн в UI: расчёт **только для отображения**, кнопка **Calculate решающая**.  
- **Primary comparison**: **`matrix_result_focus`**: **`current_year`** для New/PY anomaly, иначе **`diff_y2y`**.  
  - В этом режиме **Result** в колонке matrix показывается **только** для строки первичного метода (**CY diff** или **Y2Y diff** классификация).  

Стилизация условная: **`_ppv_matrix_style_analytics`** или fallback dataframe.

## Potential Spendings

Данные считаются в **`_compute_potential_spendings_block`**; отображение — **`_render_analytics_potential_block`** (заголовок **Potential Spendings**, капшн по сценарию).

- **New category** или **Previous Year anomaly**: PY‑зависимая часть опускается (`omit_py` / `omit_py_dependent_row` — строка Spendings или поля Could be / diff / diff % могут быть **—**).
- **Single** (`_category_single_mode`): вместо таблицы — **KPI‑карточки** (**`_render_potential_spendings_kpi_cards`**).
- **Рядом с PPV matrix** (не single): компактная **таблица** `st.dataframe` с **фиксированными ширинами столбцов в пикселях** и фиксированной шириной виджета (**`_potential_spendings_table_dataframe_kwargs`**), стилизация **`diff %`** через **`_potential_spendings_style_table`**. Подробности — [ui_ux_rules.md](ui_ux_rules.md) (раздел Potential Spendings).

## Кнопка Calculate

1. Проверки согласованности: **Active ≥ Paid** для Before и After.  
2. Вызов **`analyze_category`** с **`force_low_npl=(scenario == "Low NPL (<10)")`** и **`is_other_category=(scenario == "Other category")`**.  
3. Определение **`_matrix_result_focus_run`** (аналог matrix).  
4. Если **`diff_y2y`**: **`_results_compute_y2y_npl_sp_cr_bundle`** с CY + PY числами.  
5. Выбор того, что показать как **`disp_dc`, `disp_fd`, `disp_ns`**:  
   - **current_year** → из `analyze_category`  
   - **Other** → из Other ветви `analyze_category`  
   - иначе при полном Y2Y пакете → **`get_decision(y2y_bundle["decision_code"])`**, с **подменой на CY insufficient** при **`_low_npl_override`**  
   - иначе **Insufficient data** + текст про недоступность Y2Y  

## Блок Results

- Expander **«Детали по метрикам»**: либо CY три метрики с цветом, либо три строки Y2Y с префиксом **`O:`** для Other.  
- **`Decision code`** — `st.code`.  
- **`Final decision`** — success / error / info / warning по строке.  
- **`Next step`** — `st.info`.

## Category details (single)

В single режиме отдельный expander **Category details** для bulk **не используется** — детализация идёт через матрицу, сводки метрик, expander Results. (В bulk — **`_bulk_render_category_drill_down`**.)

## Ограничения важные для аналитиков

- **GEO == RS**: информационное сообщение о **default** порогах.  
- **Нулевой ввод** всех полей — допускается как «тестовый расчёт» с подсказкой.  

См. также: [decision_logic.md](decision_logic.md), [scenarios.md](scenarios.md), [metrics.md](metrics.md).
