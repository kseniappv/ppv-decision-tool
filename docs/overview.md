# PPV Decision Tool — обзор

## Цель

Веб-приложение (**Streamlit**) для оценки влияния изменений **PPV (pay-per-view / spending)** по категориям маркетплейса: сравниваются показатели **до и после** ценового эксперимента, выводится **классификация изменений** (Growth / Stable / Decrease и аналоги для Other category), и возвращается **итоговое решение** (`final_decision`) с рекомендованными **next steps**.

Центральная логика изолирована в **`decision_engine.py`** и вызывается из **`app.py`** и UI.

## Что анализируется

На уровне **одной категории** расчёт строится на трёх «основных» метриках:

| Метрика | Роль |
|--------|------|
| **Paid users** (New Paid Listers / NPL) | Число платящих |
| **Spending** | Траты |
| **CR (Conversion)** | Отношение Paid users к Active listers |

**Active listers** входят напрямую в CR и во **флаг Other category** (отдельный классификатор по активным).

Дополнительные поля из выгрузок (campaign per user, refund и т.д.) **не входят в `analyze_category`**, но доступны для просмотра и в экспорте (см. [metrics.md](metrics.md)).

## Какие данные нужны

- **Текущий год (CY)**: загрузка **`ppv_data_loader`** — минимально **New PPV / spending** и **active listers** с возможностью сопоставить по **`category_id`** и периоду Before/After.
- **Previous Year (PY)** (опционально для режимов с Y2Y): отдельные файлы того же семейства; используются для строки PY и diff Y2Y.
- Уровень GEO и сценарий задаются в **настройках** приложения (`app.py`, sidebar).

## Режимы работы приложения

| Режим | Активация | Назначение |
|-------|-----------|------------|
| **Single analysis** | Один **`category_id`** (ввод текста или выбор из файла CY) | Пошаговый ввод матрицы, аналитика, кнопка **Calculate**. |
| **Bulk analysis** | Несколько ID (поле категории или режим массовых ID из CY) | Табличная сводка по многим категориям, фильтры, CSV. |

Подробнее: [single_analysis.md](single_analysis.md), [bulk_analysis.md](bulk_analysis.md).

## Основные сценарии (Scenario)

Строкой в UI задаётся **глобальный** сценарий для массовых расчётов и для одиночной категории; в bulk возможны **overrides по ID**:

- Regular  
- Low NPL (&lt;10)  
- New category  
- Previous Year anomaly  
- Other category  
- Автоматическое **Low NPL auto**, если Paid users после &lt; 10 (см. [scenarios.md](scenarios.md))

## Высокоуровневая архитектура

```text
┌─────────────────┐      ┌──────────────────┐
│   ppv_data_     │      │    app.py         │
│   loader.py     │──────│  • Streamlit UI   │
│  merge / OCR    │      │  • single / bulk  │
└─────────────────┘      │  • matrix / CSV   │
         │               └────────┬───────────┘
         │                        │
         │               ┌────────▼───────────┐
         │               │ decision_engine.py  │
         │               │ analyze_category    │
         │               │ GEO_THRESHOLDS      │
         │               │ matrices            │
         └──────────────►│                     │
                         └─────────────────────┘
```

Дополнительно:

- **`number_format.py`** — форматирование чисел и процентов для таблиц.
- **`test_decision_engine.py`** — тесты решений (минимально).

Ссылки на документацию:

- [decision_logic.md](decision_logic.md) — правила решений и коды  
- [scenarios.md](scenarios.md) — сценарии и primary period  
- [metrics.md](metrics.md) — справочник метрик  
