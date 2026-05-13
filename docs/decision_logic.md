# Decision logic (`decision_engine.py`)

Этот документ описывает **фактическую** реализацию в **`decision_engine.py`**. Общий код **не изменяется** из UI.

## Основная функция: `analyze_category`

Сигнатура (упрощённо):

```python
analyze_category(
    npl_before, npl_after,
    sp_before, sp_after,
    active_before, active_after,
    geo="default",
    force_low_npl=False,
    is_other_category=False,
)
```

### Шаг 1 — относительные изменения (%)

Используется **`diff(before, after)`**:

```python
((after - before) / before * 100)   if before != 0 else 0
```

Вычисляются:

- `npl_diff` — изменение Paid users (NPL)  
- `sp_diff` — изменение Spending  
- `active_diff` — изменение Active listers  
- `cr_before = npl_before / active_before` (деление на 0 → 0)  
- `cr_after = npl_after / active_after`  
- `cr_diff` — **процентное** изменение CR как от `cr_before` к `cr_after` через ту же функцию **`diff`**  

То есть **CR** считается как доля и затем сравнивается в %-изменении, а не только как разница пунктов CR.

### Шаг 2 — классификация тренда по порогам: G / S / D

Функция **`classify_change(value, growth_threshold, decline_threshold)`**:

| Выходной код | Условие |
|--------------|---------|
| **G** (Growth) | `value > growth_threshold` |
| **D** (Decrease) | `value < decline_threshold` |
| **S** (Stable) | между порогами (включая границы, если ни одно условие не сработало) |

В UI и текстах помощники используют **`decode_status`**:

| Код | Подпись |
|-----|---------|
| G | Growth |
| S | Stable |
| D | Decrease |

Индивидуальные коды считаются **для каждой метрики** с порогами из **`GEO_THRESHOLDS`** (см. ниже):

- `npl_code`, `sp_code`, `cr_code`

### GEO thresholds (`GEO_THRESHOLDS`)

Структура по ключам GEO (**строковый ключ в верхнем регистре** в коде после `geo_key = str(geo).upper()`), с полями для **npl / sp / cr**: `growth` и `decline`.

| GEO | Особенности в коде |
|-----|--------------------|
| `default` | NPL/SP/CR growth 5%, decline -10%; CR те же базовые |
| `KG` | CR growth **11%**, остальное как база |
| `AZ` | Смягчённые NPL/SP (3 / -8), CR (3.5 / -10) |
| Прочее / ошибка имени | Падение на **`default`** |
| **`RS`** | Явное примечание в **`app.py`**: для RS пользователи видят сообщение что используются **default thresholds** до уточнения бизнес-правила |

Отдельно: `conversion_reference = thresholds["cr"]["growth"] / 100` используется для **предупреждения о низкой конверсии** (`low_conversion_warning`), а не как подмена логики матрицы.

### Формат `decision_code` и выбор решения

**Обычные сценарии** (`is_other_category=False`):

```text
decision_code = f"{npl_code}{sp_code}{cr_code}"   →  три буквы, напр. "GSD"
final_decision, next_step = get_decision(decision_code)
```

Матрица **`get_decision`** — статический словарь трёхбуквенных кодов (см. исходник `decision_engine.py`; при отсутствии ключа — `"Need review"`).

**Особый режим LOW NPL (после выбора из матрицы):**

Если **`force_low_npl`** **или** **`npl_after < 10`**, результат **перезаписывается** — **только в ветке обычной матрицы** (`is_other_category=False`), после `get_decision`:

- `final_decision = "Insufficient data"`  
- `next_step` — фиксированный текст про малую выборку NPL  

Для **`is_other_category=True`** этот блок **не выполняется** — применяется только матрица Other category.

**Other category** (`is_other_category=True`):

1. Spending → **`classify_other_spending(sp_diff)`** → `DO` / `GO` / `SO`  
2. Active → **`classify_other_active(active_diff)`** → `DO` / `GO` / `SO`  
3. CR → **`classify_other_conversion(cr_diff)`** → `D` / `G` / `S` (одна буква, не префикс `O`)

```text
decision_code = f"O: {other_sp}: {other_active}: {other_cr}"
final_decision, next_step = get_other_category_decision(decision_code)
```

Пороги Other (константы в `decision_engine.py`):

| Ось | Decrease если | Growth если |
|-----|---------------|-------------|
| Spending | &lt; -10% | &gt; 5% |
| Active | &lt; -10% | &gt; 5% |
| CR | &lt; -10% | &gt; 5% |

Иное → «стабильная» середина (**SO** / **S**).

## Пример (обычная матрица)

Пусть GEO `default`: growth 5, decline -10.

- NPL: +6% → **G**  
- Spending: -2% → **S**  
- CR: -11% → **D**  

`decision_code = "GSD"` → см. строку **`get_decision("GSD")`** в коде для фактических `final_decision` и `next_step`.

## Связь с single / bulk результатом

- **CY** блок `analyze_category` всегда строится на **текущих** Before/After.  
- **Final decision**, показанная пользователю в режимах **Regular / Low NPL** без Other, может быть переопределена **Y2Y** пакетом в **`app.py`** (то же самое в bulk строке категории) — см. [single_analysis.md](single_analysis.md) и [bulk_analysis.md](bulk_analysis.md). Это оркестрация **вне** `decision_engine`, но с использованием **`classify_change`**, **`get_decision`** и тех же GEO-порогов.
