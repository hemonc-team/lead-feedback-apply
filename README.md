# lead-feedback-apply

Утреннее дообучение свода правил анализа лидов: утверждённые «❌ Не согласен»
из `chat31598` попадают в `references/rules.md` **до** прогона `lead-analysis-skill`.

Раньше это была Cowork-задача на Windows (scp логов с VM). Теперь — тот же смысл,
только Bitrix REST, без SSH.

## Что внутри

| Файл | Зачем |
|------|--------|
| `fetch.py` | Читает маркеры `[AI-FB]` в chat31598 за 3 дня |
| `apply_feedback.py` | Детерминированное ядро: боевой чат, идемпотентность, анти-паттерны |
| `apply_runner.py` | Прогон: dry-run / live, отчёт в чат только если есть новые правила |
| `references/rules.md` | Мастер-свод (канон) |
| `pec/processed.log` | Уже применённые `fb_id` |
| `docs/CURSOR_AUTOMATION.md` | Настройка облачного прогона |

## Архитектура

```
chat31598 [AI-FB] УТВЕРЖДЕНО  →  fetch.py  →  .run/latest/applied.log
                                           →  apply_runner.py
                                           →  references/rules.md
реалтайм-бот «Оценка AI» живёт на VM и сюда не входит.
```

Тест-чат `chat36910` в свод не пишется. Повтор того же `fb_id` пропускается.

## Запуск

```bash
pip install -r requirements.txt
export BITRIX24_WEBHOOK_URL='https://laskov-partners.bitrix24.ru/rest/<id>/<code>/'
export LEAD_FEEDBACK_MODE=dry-run

python3 fetch.py --days 3
python3 apply_runner.py
```

Тесты без сети:

```bash
python3 test_apply.py
python3 test_fetch.py
```

## Права вебхука

Минимум `im`. Секрет — только в env / Cursor Secrets / vault. Не коммитить.

## Связанные репозитории

- [lead-analysis-skill](https://github.com/hemonc-team/lead-analysis-skill) — ежедневный разбор лидов (после этого прогона)
- [claude-b24](https://github.com/hemonc-team/claude-b24) — бот «Оценка AI» на VM

## Org

[hemonc-team](https://github.com/hemonc-team) · портал prod: `laskov-partners`
