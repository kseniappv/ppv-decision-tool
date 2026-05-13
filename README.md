# PPV Decision Tool

Инструмент для оценки влияния ценовых экспериментов **PPV** по категориям: сравнение метрик до/после, классификация **Growth / Stable / Decrease**, итог **`final_decision`** и **`next_step`**.

## Запуск локально

Требования: **Python 3.9+** (рекомендуется та же версия, что используете для Streamlit проекта).

```bash
cd ppv-decision-tool
pip install -r requirements.txt
python3 -m streamlit run app.py
```

Зависимости см. файл **`requirements.txt`** (ключевые: **streamlit**, **pandas**, **numpy**, загрузка **openpyxl** для Excel).

## Структура проекта

| Путь | Назначение |
|------|------------|
| `app.py` | Streamlit приложение: single/bulk UI, матрица, фильтры, экспорт CSV |
| `decision_engine.py` | `analyze_category`, GEO thresholds, матрицы решений |
| `ppv_data_loader.py` | Загрузка и merge экспортов (CSV/XLSX) по `category_id` |
| `number_format.py` | Форматирование процентов и чисел для таблиц |
| `test_decision_engine.py` | Pytest-слой над правилами движка |
| `docs/` | **Документация проекта** (архитектура, сценарии, метрики) |

## Документация

| Документ | Содержание |
|----------|-------------|
| [docs/overview.md](docs/overview.md) | Цель приложения, режимы, архитектура |
| [docs/decision_logic.md](docs/decision_logic.md) | `decision_engine`, коды G/S/D, матрицы |
| [docs/scenarios.md](docs/scenarios.md) | Regular, Low NPL, New, PY anomaly, Other, bulk overrides |
| [docs/single_analysis.md](docs/single_analysis.md) | Поток single category analysis |
| [docs/bulk_analysis.md](docs/bulk_analysis.md) | Bulk таблица, фильтры, CSV, drill-down |
| [docs/metrics.md](docs/metrics.md) | Справочник метрик и формул |
| [docs/ui_ux_rules.md](docs/ui_ux_rules.md) | Правила отображения и UX |

## Режимы

- **Single analysis** — один `category_id`, матрица PPV, блок **Potential Spendings**, кнопка **Calculate**.  
- **Bulk analysis** — много категорий: **Run bulk analysis**, фильтры, компактная таблица и **Download CSV**.

В обоих режимах **Scenario** и **GEO** задаются в боковой панели; в bulk допускаются **списки ID** для переопределения сценария строки.

## Тесты

```bash
pytest test_decision_engine.py
```
