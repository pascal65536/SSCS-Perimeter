# Карта приёмочных проверок

| Требование | Реализация / проверка |
|---|---|
| Периметр по корням и lock-файлу | `perimeter/`; `tests/test_perimeter.py` |
| SELF/DIRECT/INDIRECT и union roots | BFS deps.dev graph, объединение `_Node.roots` |
| Отсутствие deps.dev / repo | Предупреждение и пропуск; `repo=null` |
| Атомарный Settings Manager | `tests/test_settings.py` |
| Конверт и детерминированный id | Существующий `collector/` + регрессии `collector/tests/` |
| Retry-After и PyPI >=0,3 с | `collector/live.py`, `collector/ratelimit.py` |
| Spool, ротация, DLQ, ack | `tests/test_spool.py` |
| Идемпотентная доставка | `_id=event.id`; `tests/test_integration.py` |
| Detector Content SSCS-001…006, CHAIN, DORM | `siem/content/catalog.json` и связанные файлы |
| Critical = score>=0,9 и >=3 правил | `tests/test_analytics.py` |
| Исследовательские детекторы | `analytics/`, включая CHAIN/DORM; `verify.py` |
| GUI tree/details/alerts/notes | `tests/test_gui_widgets.py` |
| Demo без сети | `gui/demo_snapshot.json`; DemoBackend не имеет HTTP-клиента |
| Добавление через GUI | `SettingsClient.add_package` + фоновый Builder; `tests/test_integration.py` |
| TP/FP только в SIEM | LiveBackend feedback index; demo вызывает BackendError |
| Live→demo деградация | `gui.app.create_backend` |
| Воспроизводимый хеш контента | `siem.provision.content_hash` |

## Проверки, требующие внешнего стенда

Следующие критерии нельзя подтвердить автономными unit-тестами:

- фактическое время построения 10 корней и цикла 100 пакетов;
- backfill 100 000 событий за 30 минут;
- FP<=5% на топ-1000 и целевые 3,4% SSCS-002;
- обнаружение ground truth реальными ML Commons jobs;
- импорт correlation rules и Dashboards в конкретной версии OpenSearch;
- запись TP/FP с реальной ролью и еженедельная адаптивная калибровка;
- ≥80% покрытия — измеряется командой `coverage`, а не декларируется заранее.

Эти пункты требуют инфраструктуры, исторического корпуса и отчёта эксперимента. Код не выдаёт их за уже достигнутые результаты.
