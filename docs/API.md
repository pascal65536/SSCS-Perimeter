# Программные интерфейсы

## SettingsManager

```python
from settings_manager import SettingsManager

manager = SettingsManager("settings.json")
settings = manager.load()
manager.add_root("requests", "2.32.3")
manager.replace_perimeter(packages, generated_at="2026-10-25T00:00:00Z")
```

Все методы сохранения вызывают валидацию и атомарную замену файла.

## PerimeterBuilder

```python
from perimeter import PerimeterBuilder

result = PerimeterBuilder(max_workers=8).build(
    [{"name": "requests", "version": "2.32.3"}],
    project_name="my-project",
)
print(result.packages, result.warnings)
```

Клиенты `DepsDevClient` и `PyPIClient` можно заменить совместимыми fake-объектами в тестах. Метод `rebuild(settings_path)` читает roots и записывает результат через Manager.

## DiskSpool и Gateway

```python
from spool import DiskSpool
from siem import OpenSearchGateway

spool = DiskSpool(".sscs/spool", max_bytes=64 * 1024 * 1024)
spool.enqueue(event)
spool.deliver(OpenSearchGateway("https://localhost:9200"), batch_size=500)
```

`peek()` не удаляет элементы; `ack(n)` удаляет первые n. `deliver()` не выполняет ack при ошибках SIEM.

## GUI DataBackend

Обязательный интерфейс:

- `projects()` — список проектов;
- `packages(project)` — узлы проекта;
- `children(package)` — ленивая выборка зависимостей;
- `node(package)` / `details(package)` — метаданные и риск;
- `findings(package)` — готовые находки;
- `mark_finding(id, label, comment)` — только live;
- `export_snapshot(path)` — явный экспорт.

`DemoBackend(path)` не создаёт сетевых клиентов. `LiveBackend(settings)` создаёт OpenSearch client; для тестов можно передать `client=`.

## Событие sscs-event/1.0

Обязательный минимум для Spool:

```json
{
  "@timestamp": "2026-10-25T10:00:00Z",
  "event": {
    "id": "pypi:requests:2.32.3:2024-05-29T12:00:00Z",
    "kind": "event",
    "category": "package",
    "type": "creation",
    "action": "package.release"
  },
  "source": {"service": "pypi-api", "component": "pypi-json"},
  "package": {"name": "requests", "version": "2.32.3", "registry": "pypi"},
  "sscs": {
    "schema_version": "1.0",
    "watchlist": "monitored",
    "perimeter_root": ["my-project"],
    "point_in_time": true
  }
}
```

Метка времени канонизируется как UTC `YYYY-MM-DDTHH:MM:SSZ`. Watchlist: `monitored`, `reference`, `ground_truth`.
