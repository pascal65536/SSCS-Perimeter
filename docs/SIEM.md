# Интеграция с OpenSearch

## Контент

| Файл | Назначение |
|---|---|
| `siem/content/index-template.json` | Data stream `sscs-events`, ECS/sscs mappings |
| `siem/content/ism-policy.json` | Ротация, warm/cold, удаление после 540 дней |
| `siem/content/rules/*.yml` | Sigma-правила Security Analytics |
| `siem/content/ml-sscs-*.json` | ML Commons anomaly detectors с category_field |
| `siem/content/correlation-content.json` | Окна, группировки и последовательности корреляций |
| `siem/content/scoring-query.json` | Score = 1 − Π(1 − base_i), Critical только при ≥3 правилах |
| `siem/content/catalog.json` | Единый версионируемый манифест весов и порогов |
| `siem/content/logstash.conf` | Пример файловой доставки с document_id из event.id |

## Установка

1. Создать data stream и ISM:

   ```bash
   python -m siem.provision --url https://localhost:9200
   ```

2. Проверить и импортировать Sigma через Security Analytics. Поля `sscs.pr.author_is_new`, `sscs.pr.self_merge`, `sscs.release.dormant_days`, `sscs.release.history_count` должны присутствовать в соответствующих выборках. Первые два формируются нормализатором; производные DORM рассчитываются SIEM transform/агрегацией.
3. Создать ML jobs командой с `--apply-ml` или через Dashboards. До прогрева снизить чувствительность; SSCS-005 требует не менее 10 исторических коммитов автора.
4. Перенести корреляции из JSON-спецификации в Correlation rules используемой версии Security Analytics. Формат API корреляций отличается между линейками 2.x/3.x, поэтому спецификация намеренно отделена от установочного скрипта.
5. Настроить findings/scores indices под запросы LiveBackend: `sscs-findings-*`, `sscs-scores-*`.
6. Настроить еженедельную SIEM-задачу Feedback Loop. Индивидуальные веса включаются после 90 дней истории; агент в эту задачу не входит.

## Контракт риска для GUI

Документ в `sscs-scores-*`:

```json
{
  "@timestamp": "2026-10-24T18:00:00Z",
  "package": {"name": "urllib3"},
  "risk": {
    "severity": "high",
    "score": 0.82,
    "rules": ["SSCS-002", "SSCS-003"],
    "updated_at": "2026-10-24T18:00:00Z",
    "detector_config_hash": "…"
  }
}
```

Находка в `sscs-findings-*` содержит `@timestamp`, `package.name`, `rule_id`, `severity`, `status` и `evidence`. Идентификатор документа OpenSearch используется как finding id.

Feedback в `sscs-feedback`:

```json
{
  "finding_id": "…",
  "label": "true_positive",
  "comment": "",
  "labeled_at": "2026-10-25T10:00:00Z",
  "source": "sscs-gui"
}
```

## Проверка перед стендом

```bash
python -m siem.provision --dry-run
```

Команда печатает SHA-256 всего контента. Его следует сохранять в каждой находке как `detector_config_hash`. Установка index template/ISM/ML реализована, но без реального кластера не считается приёмочно проверенной. Корреляции и Dashboards требуют импорта/проверки на целевой минорной версии.
