#!/usr/bin/env python3
"""Применение утверждённых правил к мастер-своду.

P6: в канон пишутся только записи боевого chat31598.
P7: rejected.log → анти-паттерны (тоже только боевой чат).
Идемпотентность: fb_id из processed.log не применяется повторно.
Дубли fb_id в одном логе: остаётся последняя запись.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

PROD_CHATS = {"chat31598", "31598"}


def _norm_chat(c: Any) -> str:
    return str(c or "").replace("chat", "")


def _is_prod(entry: dict) -> bool:
    return _norm_chat(entry.get("chat_id")) in {"31598"}


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def dedup_by_fb_id(entries: list[dict]) -> list[dict]:
    """Оставить последнюю запись на каждый fb_id (повторное согласование)."""
    last: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        fbid = str(e.get("fb_id") or "")
        if not fbid:
            continue
        if fbid not in last:
            order.append(fbid)
        last[fbid] = e
    return [last[k] for k in order]


def apply_to_canon(
    applied_entries: list[dict],
    canon_text: str,
    processed: list[str] | None = None,
) -> tuple[str, list[dict], list[str]]:
    """Возвращает (new_canon, changes[], newly_processed[])."""
    done = set(processed or [])
    changes: list[dict] = []
    canon = canon_text
    newly: list[str] = []
    for e in dedup_by_fb_id(applied_entries):
        fbid = e.get("fb_id")
        if not _is_prod(e):
            changes.append({"status": "SKIP_TEST_CHAT", "fb_id": fbid, "chat_id": e.get("chat_id")})
            continue
        if fbid in done:
            changes.append({"status": "SKIP_ALREADY_APPLIED", "fb_id": fbid})
            continue
        was = (e.get("was") or "").strip()
        now = (e.get("now") or "").strip()
        rule = e.get("rule", "?")
        if was and was != "(нет правила)" and was in canon:
            canon = canon.replace(was, now, 1)
            changes.append({"status": "APPLIED", "rule": rule, "fb_id": fbid})
        else:
            canon = (
                canon.rstrip()
                + f'\n\n### {rule} — (из обратной связи {str(e.get("date", ""))[:10]}, лид {e.get("lead_id")})\n'
                + f"**Правило:** {now}\n"
            )
            changes.append({"status": "APPENDED", "rule": rule, "fb_id": fbid})
        newly.append(fbid)
        done.add(fbid)
    return canon, changes, newly


def antipatterns_from_rejected(rejected_entries: list[dict]) -> str:
    lines = [
        "# Отклонённые формулировки (анти-паттерны) — НЕ предлагать повторно",
        "> Автогенерация из rejected.log боевого chat31598. Бот учитывает это при формулировке.",
        "",
    ]
    n = 0
    for e in rejected_entries:
        if not _is_prod(e):
            continue
        n += 1
        proposed = (e.get("proposed") or "")[:120]
        reason = (e.get("reason") or "")[:80]
        lines.append(
            f'- Правило {e.get("rule", "?")} / лид {e.get("lead_id")}: '
            f"НЕ предлагать «{proposed}» — отклонено ({reason})."
        )
    if n == 0:
        lines.append("_Боевых отклонений пока нет._")
    return "\n".join(lines) + "\n"


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def apply_to_files(
    applied_path: str,
    canon_path: str,
    rejected_path: str | None = None,
    antipatterns_path: str | None = None,
    processed_path: str | None = None,
    dry_run: bool = True,
) -> dict:
    applied = _load_jsonl(applied_path)
    with open(canon_path, encoding="utf-8") as f:
        canon = f.read()
    processed: list[str] = []
    if processed_path and os.path.exists(processed_path):
        with open(processed_path, encoding="utf-8") as f:
            processed = [l.strip() for l in f if l.strip()]
    new_canon, changes, newly = apply_to_canon(applied, canon, processed=processed)
    result: dict[str, Any] = {
        "changes": changes,
        "canon_hash_before": _hash(canon),
        "canon_hash_after": _hash(new_canon),
        "canon_changed": _hash(canon) != _hash(new_canon),
        "dry_run": dry_run,
        "newly_processed": newly,
    }
    if rejected_path and os.path.exists(rejected_path):
        rej = _load_jsonl(rejected_path)
        ap = antipatterns_from_rejected(rej)
        result["antipatterns"] = ap
        if not dry_run and antipatterns_path:
            with open(antipatterns_path, "w", encoding="utf-8") as f:
                f.write(ap)
    if not dry_run:
        if result["canon_changed"]:
            with open(canon_path, "w", encoding="utf-8") as f:
                f.write(new_canon)
        if processed_path and newly:
            with open(processed_path, "a", encoding="utf-8") as f:
                for fb in newly:
                    f.write(fb + "\n")
    return result
