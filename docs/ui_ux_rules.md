# UX / UI правила (текущая реализация)

Документ фиксирует **наблюдаемое поведение** Streamlit UI в **`app.py`**, без нормативов «как должно быть в будущем».

## Компактная vs детальная информация

| Контекст | Компактно | Детально |
|----------|-----------|----------|
| Bulk | Одна строка категории: ключевые diff + short next step | **Category details** expander после выбора строки |
| Single | Matrix + блок Results после Calculate | Expander метрик Results, текстовые пояснения |

## Компактная bulk table

- **Скрыты** от прямого показа: **`priority`**, **`status`**, доп. CY spending столбцы.  
- **`priority`** используется для **сортировки** полного DF и фильтров.  
- **`status`** остаётся в данных и CSV; раскраска строк может опираться на **`style_source`** с полными полями.  
- **`final_decision`** и **`next_step`** (укороченный) — **в конце** видимых колонок после метрик.

## Row coloring

**`_bulk_styled_dataframe`**:

1. Если доступен **`Styler.apply(..., axis=None)`**: для каждой ячейки комбинируются **фон строки** (по **`_bulk_row_background`**) и **групповой tint/border** (CY/PY/Y2Y).  
2. Иначе fallback — только фон строки.

**`_bulk_row_background`** приоритет:

1. Если в meta **`status`** = Missing current year data → серый  
2. Иначе по **`final_decision`**: Negative / Insufficient / Positive / No impact — свои HEX константы

## Выделение решения (single Calculate)

После успешного расчёта **`Final decision`** окрашивается через **`st.success` / `st.error` / `st.info` / `st.warning`** в зависимости от строки.

## Закрепление колонок (sticky)

При наличии у **`streamlit.column_config.TextColumn`** параметра **`pinned`**, конфиг задаёт **`pinned='left'`** для **Details, category_id, category_name, scenario_used**. Если API Streamlit недоступен — колонки **не** замораживаются (ограничение версии).

## KPI и summary cards

**Overview** блок (`_bulk_render_compact_dashboard`): плотные **`st.metric`** по приоритетам и **`scenario_used`**, опционально средние по числовым CY/Y2Y полям bulk_df.

Более развёрнутая **Summary** секция (**`_bulk_render_summary`**) с expanders сохранена отдельно.

## Potential Spendings (аналитика)

Рендер: **`_render_analytics_potential_block`** (`app.py`).

| Режим | Вид |
|-------|-----|
| **Single** (`_category_single_mode`) | Компактные карточки **`_render_potential_spendings_kpi_cards`** (таблица не используется). |
| **Не single** (матрица + правая колонка) | **`st.dataframe`** с **`_potential_spendings_style_table`**: строки **ARPpU** и **Spendings**, колонки Fact / Could be / diff / diff %. |

**Таблица (не single):**

- **`_potential_spendings_table_dataframe_kwargs`**: у **`TextColumn`** заданы **целочисленные ширины в px** (фиксированная сетка Glide, без ручного поджатия столбцов); **`use_container_width=False`**; у **`st.dataframe`** передаётся **`width`** ≈ сумма ширин колонок + небольшой запас под рамку.
- Глобальный стиль **`[data-testid="stDataFrame"]`**: **`overflow-x: auto`**, чтобы при узкой колонке аналитики таблицу можно было **прокрутить по горизонтали**, а не обрезать молча.

**Колонка `diff %` (и согласованные бейджи в KPI):**

- Семантика ↑ / ↓ / = без изменений; фон ячеек — полупрозрачный tint (зелёный / красный / жёлтый).
- Текст и бейджи — **повышенный контраст** и **`font-weight: 700`** (**`_potential_spendings_diff_pct_cell_css`**, **`_potential_spendings_diff_pct_badge_md`**), чтобы проценты читались на тёмной теме.

## Форматирование Result / процентов

Используется **`number_format.py`**: **`format_percent`**, **`format_matrix_metric`**, **`format_integer`** (например group thousands для **`category_id`** в табличном отображении).

## Когда метрики скрыты или заменены на «—»

| Условие | Поведение |
|---------|-----------|
| New category (bulk row) | PY и Y2Y ячейки **—** |
| Previous Year anomaly (bulk row) | Y2Y **—** |
| Single / matrix New category | PY и Y2Y в матрице **—** |
| Single Previous Year anomaly | Y2Y в матрице **—**, PY строка может быть видна |

## Зачем убраны informational метрики из compact bulk

Дополнительные CY %-метрики (campaign per user, refund и т.д.) **не входят в `analyze_category`** и перегружали строку при сотнях категорий. Они остаются:

- В **полном CSV** и `bulk_df`  
- В **Category details → Additional metrics**

## Компактный `next_step`

Эвристика **`_bulk_format_next_step_short`**: ключевые фразы (teamlead / keep / rollback / increase / other methods), иначе **Need review**; полная строка в drill-down.

## Тёмная тема

Подобранные **rgba** для групповых tint и border — с низкой непрозрачностью; при конфликте с фоном строки приоритет у **цвета строки решения**.

## OCR / merge подсказки

В нескольких местах UI есть защита от случайной перезаписи session state после смены категории / re-upload — см. комментарии в **`app.py`** (не дублируются здесь дословно).

**Current Year OCR — позиционный fallback по Period Group:** если OCR отдаёт блок **Period Group** с числами **без имён метрик в строках**, и разбор по якорям/pipe ещё **не заполнил ни одну** метрику Before/After целиком, срабатывает **`_cy_maybe_ordered_numeric_fallback`**: строки блока (после **`_cy_primary_period_group_metric_lines`**, которая останавливается на **втором** заголовке «period group» и пропускает строки без цифр вроде **Default Target**) сопоставляются **по порядку** только с **первыми 11** ключами **`_CY_INPUT_METRICS`** (от **Paid users** до **%Execution Inventory**). **Active listers** этим путём не заполняются. Числовая пара в строке: **`_pp_order_row_numeric_pair`** (устойчивость к «битым» фрагментам OCR).

**CY — Active listers, если подписи потеряны:** в **`_parse_cy_metrics_from_ocr_text`** после основного разбора последовательно пробуются: **12‑я** числовая пара из панели (**`_cy_collect_pp_numeric_rows`**), затем **`_py_period_group_default_target_pair`** (**`_cy_period_group_pick_active_listers_pair`**) — **последний** подходящий числовой блок Period Group с фильтром по масштабу (**`_cy_active_mag_plausible_pair`**), с опциональным **`skip_if_matches`** от пары **Paid users**, чтобы не принять мусорную пару за Active. При подозрительном совпадении **%Execution Inventory** и Active срабатывает **`_cy_repair_pct_execution_if_dup_active`**.

**Previous Year (матрица) OCR:** при пустых полях после именованного разбора **`_py_fill_from_row_order_if_empty`** может подставить **1‑ю / 6‑ю / 12‑ю** числовые пары левой панели и при необходимости Active из **полного** текста OCR (если кроп обрезает блок Period Group).
