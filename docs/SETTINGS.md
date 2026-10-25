# Настройки

Файл `settings.json` имеет `schema_version: 1.2` и не содержит секретов.

## Секции

| Секция | Назначение |
|---|---|
| `project` | Имя проекта и корневые пакеты `{name, version}`; `version=null` означает последнюю версию PyPI |
| `perimeter` | Время пересчёта и узлы графа |
| `reference` | Эталонные имена для typosquatting enrichment |
| `polling` | Интервалы, timeout и число параллельных задач |
| `detectors` | Веса и калиброванные параметры, переносимые в SIEM |
| `spool` | Каталог временной очереди и лимит байтов |
| `siem` | URL, имена индексов и TLS-проверка |
| `logging` | DEBUG/INFO/WARNING/ERROR |

## Узел периметра

```json
{
  "name": "urllib3",
  "version": "2.2.2",
  "level": "DIRECT",
  "dependencies": [],
  "perimeter_root": ["my-project"],
  "summary": "HTTP library...",
  "repo": "urllib3/urllib3",
  "pypi_url": "https://pypi.org/project/urllib3/",
  "releases": [{"version": "2.2.2", "released_at": "2024-06-17T00:00:00Z"}]
}
```

`level` принимает `SELF`, `DIRECT`, `INDIRECT`. Каждая зависимость должна присутствовать в списке узлов. Имена нормализуются по PEP 503 (`_`, `.`, `-` приводятся к единому виду).

## Гарантии записи

- временный файл в том же каталоге, `fsync`, затем `os.replace`;
- детерминированная сортировка ключей и UTF-8;
- повторное добавление того же root не меняет файл;
- схема проверяется до записи;
- ключи `token`, `password`, `secret`, `api_key`, `authorization` и производные отклоняются на любом уровне;
- GUI не получает прямого доступа к файловой записи.

## Переменные окружения

| Переменная | Использование |
|---|---|
| `GITHUB_TOKEN` | GitHub REST API |
| `GITHUB_WEBHOOK_SECRET` | Резерв для проверки подписи Webhook-адаптера |
| `SSCS_OPENSEARCH_TOKEN` | Bearer-аутентификация OpenSearch |
| `SSCS_OPENSEARCH_USERNAME` / `SSCS_OPENSEARCH_PASSWORD` | Basic-аутентификация, если Bearer не задан |

Роль GUI в OpenSearch должна иметь read-only доступ к событиям/findings/scores и отдельное разрешение записи только в feedback index.
