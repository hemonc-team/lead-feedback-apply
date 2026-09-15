# Cursor Cloud Automation — lead-feedback-apply

Утренний прогон: утверждённые несогласия из `chat31598` попадают в свод правил
**до** ежедневного анализа лидов. SSH / VM / WSL не нужны — только Bitrix REST.

## 1. Секреты

[cursor.com/dashboard](https://cursor.com/dashboard) → **Cloud Agents** → **Secrets**:

| Имя | Тип | Значение |
|-----|-----|----------|
| `BITRIX24_WEBHOOK_URL` | Runtime Secret | входящий вебхук prod `laskov-partners`, со слэшем в конце |
| `LEAD_FEEDBACK_MODE` | Environment Variable | `dry-run` для проверки, потом `live` |

Права: `im` (чтение чата + `im.message.add`). Тот же вебхук, что у `lead-analysis-skill`, подходит.

```bash
curl -s "${BITRIX24_WEBHOOK_URL}scope.json" | python3 -m json.tool
```

## 2. Сеть

- `Default + allowlist`
- `laskov-partners.bitrix24.ru`

## 3. Environment

| Поле | Значение |
|------|----------|
| Install Script | `python3 -m pip install -r requirements.txt` |
| Start Script | *(пусто)* |
| Secrets | `BITRIX24_WEBHOOK_URL`, `LEAD_FEEDBACK_MODE=dry-run` |
| SSH-ключ | **не нужен** |

## 4. Automation

| Поле | Значение |
|------|----------|
| Repository | `hemonc-team/lead-feedback-apply`, ветка `main` |
| Schedule | 09:26 МСК (`26 6 * * *` UTC) — раньше `lead-analysis-skill` (09:50) |
| Model | Composer / fast |

### Agent instructions

```text
Дообучение свода правил анализа лидов по утверждённой обратной связи. Портал laskov-partners.

1) Код, не LLM:
   pip install -r requirements.txt
   python3 fetch.py --days 3 --out-dir .run/latest
   python3 apply_runner.py
   При ошибке fetch — стоп, свод не трогать, в чат не писать.

2) Прочитать SKILL.md (короткий пайплайн). JSON из apply_runner — источник итога.

3) LEAD_FEEDBACK_MODE:
   dry-run — файлы не менять;
   live — записать references/rules.md и pec/processed.log; в chat31598 пост только если applied>0.

4) В чат — человеческий язык (уже в apply_runner). Не дублировать JSON в chat31598.
   Самопроверка — в лог прогона.

5) Вебхук только из env. .run/ не коммитить.
   Если live и canon_changed — закоммитить rules.md, rejected_patterns.md, processed.log в эту ветку.

Итог в Run History: mode, applied, skipped_already, skipped_test, canon_changed.
```

## 5. Тестовый прогон

1. `LEAD_FEEDBACK_MODE=dry-run`
2. **Run now**
3. В логе: `fetch: messages=… applied=… rejected=…` и JSON `mode=dry-run`
4. `chat31598` без нового служебного поста
5. `live` → проверить свод и (если applied>0) чат → включить расписание

## 6. Типичные проблемы

| Симптом | Причина |
|---------|---------|
| `нет .run/latest/applied.log` | fetch не отработал |
| applied=0 каждый день | в окне 3 дней нет новых «УТВЕРЖДЕНО» — норма |
| правило дважды в своде | сломан `pec/processed.log` — не чистить без сверки |
| VM-бот формулирует по старому своду | этот репо не пушит на GCP; зеркало `~/.lead-feedback/references/rules.md` обновлять отдельно |
