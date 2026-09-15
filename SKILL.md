---
name: lead-feedback-apply
description: 'Утренний прогон: утверждённые «не согласен» из chat31598 → свод правил анализа лидов. fetch.py → apply_runner.py. День = вчера/сегодня МСК, до lead-analysis.'
---

# Дообучение свода по обратной связи

## Контур

| Переменная | Назначение |
|---|---|
| `BITRIX24_WEBHOOK_URL` | входящий REST prod, слэш в конце |
| `LEAD_FEEDBACK_MODE` | `dry-run` / `live` |

Scope: `im` (чтение chat31598 + пост отчёта). Остальное не нужно.

Кодировка REST: **Python + requests + UTF-8**. PowerShell запрещён.

---

## Пайплайн (строго по порядку)

```bash
pip install -r requirements.txt
python3 fetch.py --days 3 --out-dir .run/latest
python3 apply_runner.py
```

1. `fetch.py` читает маркеры `[AI-FB]` в `chat31598` за 3 дня. SSH на VM не нужен.
2. `apply_runner.py` вносит в `references/rules.md` **только** боевой чат, идемпотентно по `pec/processed.log`.
3. Тест-чат `chat36910` никогда не меняет свод.
4. `LEAD_FEEDBACK_MODE=dry-run` — только JSON в лог прогона, файлы не писать.
5. `live` — записать свод и processed.log; в chat31598 пост **только если** появились новые правила. Если новых нет — молчать.
6. Язык отчёта — для менеджеров, без UF/REST/fb_id.
7. `.run/` не коммитить. Коммитить можно `references/rules.md`, `references/rejected_patterns.md`, `pec/processed.log`.
8. Вебхук только из env.

Итог в Run History: mode, applied, skipped_already, skipped_test, canon_changed. Без текстов переписки.
