# SSCS-Perimeter v1.2

Программная реализация динамического периметра зависимостей: сбор нормализованной телеметрии PyPI/GitHub, временная буферизация и доставка в OpenSearch, каталог детекторов, исследовательский контур и настольный PyQt6‑клиент с live/demo‑режимами.

## Быстрый запуск демонстрации

Требуется Python 3.11+.

```bash
cd SSCS-Perimeter
python -m pip install -r requirements.txt
python -m gui.app --mode demo --settings settings.json
```

Демонстрационный снапшот встроен в `gui/demo_snapshot.json`. Он содержит 12 пакетов, дерево зависимостей, риски, версии и 7 находок. Для просмотра дерева, деталей, алертов и локальных заметок сеть и OpenSearch не нужны. В demo‑режиме кнопки TP/FP отключены: приложение не имитирует запись в SIEM.

## Основные сценарии

### 1. Конфигурация и периметр

```bash
python -m settings_manager.cli --settings settings.json init --project my-project
python -m settings_manager.cli --settings settings.json add-root requests --version 2.32.3
python -m perimeter.cli --settings settings.json
```

Пересчёт из lock‑файла:

```bash
python -m perimeter.cli --settings new-settings.json --project my-project --lockfile requirements.txt
```

Поддержаны pinned `requirements.txt`, `poetry.lock`, `uv.lock`, `pdm.lock` и `Pipfile.lock`. Граф разрешается через deps.dev API v3; метаданные и GitHub‑ссылки извлекаются из PyPI. Недоступные узлы пропускаются с предупреждением. Запись `settings.json` атомарна и выполняется только через Settings Manager.

### 2. Сбор периметра и Spool

```bash
export GITHUB_TOKEN="…"                 # необязательно, повышает квоту GitHub
python -m collector.service --settings settings.json --once
python -m spool.cli --directory .sscs/spool status
```

Коллектор не вычисляет риски и не хранит историю. Cursor содержит идентификаторы уже увиденных событий. События с отсутствующей/будущей меткой времени попадают в `dead-letter.jsonl`; при переполнении Spool удаляет самые старые записи.

Доставка в OpenSearch:

```bash
export SSCS_OPENSEARCH_TOKEN="…"        # либо USERNAME/PASSWORD из окружения
python -m spool.cli --directory .sscs/spool deliver \
  --url https://opensearch.example:9200 --index sscs-events
```

Bulk-доставка использует `_id=event.id`; HTTP 409 считается идемпотентным повтором. Выполняется не менее трёх попыток с экспоненциальной задержкой.

GitHub Webhook с обязательной проверкой HMAC SHA-256:

```bash
export GITHUB_WEBHOOK_SECRET="…"
python -m collector.webhook --settings settings.json --host 127.0.0.1 --port 8080
```

Endpoint принимает `POST /github` для push, pull_request, release, member и workflow_run. При его недоступности используется `collector.service` polling.

Проверка доступности глобального PyPI Changelog:

```bash
python -m collector.global_pypi --check
```

При недоступности XML-RPC используется polling периметра; глобальная статистика BigQuery оставлена внешним адаптером, а не скрытым обязательным компонентом.

### 3. OpenSearch

```bash
python -m siem.provision --url https://localhost:9200 --dry-run
python -m siem.provision --url https://localhost:9200 --apply-ml
```

Каталог `siem/content/` включает index template, ISM retention 540 дней, Sigma‑правила, ML Commons jobs, correlation‑спецификации, композитный scoring и Logstash‑пример. Порядок импорта и ограничения описаны в `docs/SIEM.md`. Перед промышленным развёртыванием контент необходимо проверить на конкретной минорной версии OpenSearch.

### 4. Live GUI

```bash
export SSCS_OPENSEARCH_TOKEN="…"
python -m gui.app --mode live --settings settings.json
```

GUI только читает риски/находки из OpenSearch. Запись возможна лишь в `settings.json` и индекс обратной связи `sscs-feedback`. При недоступности SIEM выполняется переход во встроенный demo‑снапшот с уведомлением. Токены не сохраняются в приложении или конфигурации.

## Проверки

```bash
python make_demo_fixtures.py
python make_fixtures.py
pytest -q
python verify.py
```

Покрытие ключевых модулей:

```bash
coverage run -m pytest -q
coverage report -m
```

Интеграционные тесты не обращаются к внешним API. Live API и импорт в OpenSearch требуют отдельной проверки на стенде; отсутствие такого стенда не подменяется утверждением о промышленной готовности.

## Структура

- `perimeter/` — deps.dev/PyPI, lock‑файлы, объединение графов.
- `settings_manager/` — схема, валидация, атомарная идемпотентная запись.
- `collector/` — нормализация `sscs-event/1.0`, backfill/incremental и live polling.
- `spool/` — ограниченная очередь, ack, ротация и DLQ.
- `siem/` — OpenSearch Gateway и версионируемый Detector Content.
- `gui/` — PyQt6 tree/details/actions, LiveBackend/DemoBackend, snapshots, notes.
- `analytics/`, `storage/` — только исследовательский контур и PIT backtesting.
- `docs/` — архитектура, конфигурация, SIEM и программные интерфейсы.

## Документация

- `docs/ARCHITECTURE.md`
- `docs/SETTINGS.md`
- `docs/SIEM.md`
- `docs/API.md`
- `docs/ACCEPTANCE.md`
- `docs/TEST_REPORT.md`
