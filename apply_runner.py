#!/usr/bin/env python3
"""Точка входа прогона: JSONL из .run/latest → свод rules.md + processed.log.

dry-run по умолчанию (LEAD_FEEDBACK_MODE=dry-run). live пишет файлы.
Отчёт в chat31598 — только если есть APPLIED/APPENDED и режим live.
В чат — человеческий язык, без техтерминов.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import apply_feedback as A

ROOT = Path(__file__).resolve().parent
CANON = ROOT / "references" / "rules.md"
ANTI = ROOT / "references" / "rejected_patterns.md"
PROC = ROOT / "pec" / "processed.log"
RUN = ROOT / ".run" / "latest"
PROD_CHAT = "chat31598"


def _mode() -> str:
    return (os.environ.get("LEAD_FEEDBACK_MODE") or "dry-run").strip().lower()


def human_summary(result: dict) -> str | None:
    applied = [c for c in result["changes"] if c["status"] in ("APPLIED", "APPENDED")]
    if not applied:
        return None
    lines = [
        "Обратная связь по оценке AI: в свод правил внесено "
        + str(len(applied))
        + (" изменение." if len(applied) == 1 else " изменений.")
    ]
    for c in applied:
        how = "обновлено существующее" if c["status"] == "APPLIED" else "добавлено новое"
        lines.append(f"· {how} правило {c.get('rule', '?')}")
    skip_test = sum(1 for c in result["changes"] if c["status"] == "SKIP_TEST_CHAT")
    skip_done = sum(1 for c in result["changes"] if c["status"] == "SKIP_ALREADY_APPLIED")
    extra = []
    if skip_done:
        extra.append(f"уже учтено ранее: {skip_done}")
    if skip_test:
        extra.append(f"тестовый контур пропущен: {skip_test}")
    if extra:
        lines.append("(" + "; ".join(extra) + ")")
    return "\n".join(lines)


def post_chat(text: str) -> None:
    import requests

    url = (os.environ.get("BITRIX24_WEBHOOK_URL") or "").strip().rstrip("/")
    if not url:
        print(json.dumps({"warn": "нет BITRIX24_WEBHOOK_URL — отчёт в чат не отправлен"}, ensure_ascii=False))
        return
    payload = {"DIALOG_ID": PROD_CHAT, "MESSAGE": text}
    r = requests.post(url + "/im.message.add.json", json=payload, timeout=60)
    data = r.json() if r.content else {}
    if "error" in data:
        print(json.dumps({"warn": "im.message.add failed", "error": data.get("error")}, ensure_ascii=False))
    else:
        print(json.dumps({"posted": True, "message_id": data.get("result")}, ensure_ascii=False))


def main() -> int:
    dry = _mode() != "live"
    applied = RUN / "applied.log"
    rejected = RUN / "rejected.log"
    if not applied.exists():
        print(json.dumps({"error": "нет .run/latest/applied.log — сначала python3 fetch.py"}, ensure_ascii=False))
        return 1
    result = A.apply_to_files(
        str(applied),
        str(CANON),
        rejected_path=str(rejected) if rejected.exists() else None,
        antipatterns_path=str(ANTI),
        processed_path=str(PROC),
        dry_run=dry,
    )
    applied_n = sum(1 for c in result["changes"] if c["status"] in ("APPLIED", "APPENDED"))
    summary = {
        "mode": "dry-run" if dry else "live",
        "canon_changed": result["canon_changed"],
        "applied": applied_n,
        "skipped_test": sum(1 for c in result["changes"] if c["status"] == "SKIP_TEST_CHAT"),
        "skipped_already": sum(1 for c in result["changes"] if c["status"] == "SKIP_ALREADY_APPLIED"),
        "newly_processed": result.get("newly_processed", []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    text = human_summary(result)
    if text and not dry:
        post_chat(text)
    elif not text:
        print(json.dumps({"note": "новых правил нет — в чат не пишем"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
