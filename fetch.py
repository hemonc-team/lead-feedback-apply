#!/usr/bin/env python3
"""Собрать applied/rejected из chat31598 через Bitrix REST.

Без SSH на VM: бот уже пишет в чат маркеры [AI-FB]#… НА УТВЕРЖДЕНИИ / УТВЕРЖДЕНО / ОТКЛОНЕНО.
Скрипт читает сообщения за окно (по умолчанию 3 дня) и кладёт JSONL в .run/latest/.

Env:
    BITRIX24_WEBHOOK_URL   входящий вебхук, со слэшем в конце
    LEAD_FEEDBACK_CHAT     по умолчанию chat31598
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("lead_feedback_fetch")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

MSK = ZoneInfo("Europe/Moscow")
PROD_CHAT = "chat31598"
MARK = re.compile(
    r"\[AI-FB\]#(\S+)\s+(НА УТВЕРЖДЕНИИ|СТАТУС: УТВЕРЖДЕНО|СТАТУС: ОТКЛОНЕНО|AWAIT_REASON|ЗАМЕНЁН)"
)
RE_ENTITY = re.compile(r"Сущность:\s*(.+)")
RE_RULE = re.compile(r"Правило:\s*(.+)")
RE_WAS = re.compile(r"БЫЛО:\s*[«\"](.+?)[»\"]", re.S)
RE_NOW = re.compile(r"СТАЛО:\s*[«\"](.+?)[»\"]", re.S)
RE_LEAD = re.compile(r"лиду\s+#(\d+)")
RE_APPROVED_BY = re.compile(r"утвердил\s+(\S+)")
RE_REJECT_REASON = re.compile(r"причина:\s*[«\"](.+?)[»\"]")


class BitrixError(RuntimeError):
    pass


_last_call = [0.0]


def _webhook() -> str:
    url = (os.environ.get("BITRIX24_WEBHOOK_URL") or "").strip()
    if not url:
        raise BitrixError("BITRIX24_WEBHOOK_URL не задан в окружении")
    return url.rstrip("/")


def _throttle() -> None:
    min_interval = 1.0 / max(float(os.environ.get("BITRIX_RATE_LIMIT", "2")), 0.1)
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_call[0] = time.monotonic()


def bitrix_call(method: str, params: dict | None = None, max_retries: int = 6) -> dict:
    url = _webhook() + "/" + method + ".json"
    params = params or {}
    backoff = 1.0
    for attempt in range(1, max_retries + 1):
        _throttle()
        try:
            resp = requests.post(url, json=params, timeout=120)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise BitrixError(f"сеть: {exc}") from exc
            log.warning("сеть (%s), повтор через %.0fс", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        if resp.status_code == 200:
            data = resp.json()
            if "error" in data:
                err = data.get("error")
                desc = data.get("error_description", "")
                if err in ("QUERY_LIMIT_EXCEEDED", "OPERATION_TIME_LIMIT") and attempt < max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue
                raise BitrixError(f"{err}: {desc}")
            return data
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        raise BitrixError(f"HTTP {resp.status_code}")
    raise BitrixError("исчерпаны повторы")


def _msg_text(m: dict) -> str:
    return (m.get("text") or m.get("TEXT") or "").strip()


def _msg_date(m: dict) -> str:
    return str(m.get("date") or m.get("DATE") or "")


def _msg_id(m: dict) -> int:
    try:
        return int(m.get("id") or m.get("ID") or 0)
    except (TypeError, ValueError):
        return 0


def fetch_chat_messages(dialog_id: str, since: datetime) -> list[dict]:
    """Сообщения чата новее since, новые в конце. Без текстов в stdout."""
    collected: list[dict] = []
    last_id = None
    since_naive = since.replace(tzinfo=None)
    for _ in range(40):
        params: dict = {"DIALOG_ID": dialog_id, "LIMIT": 50}
        if last_id:
            params["LAST_ID"] = last_id
        data = bitrix_call("im.dialog.messages.get", params)
        result = data.get("result") or {}
        if isinstance(result, list):
            batch = result
        else:
            batch = result.get("messages") or []
        if not batch:
            break
        stop = False
        for m in batch:
            dt_raw = _msg_date(m)
            try:
                dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                dt = since_naive
            if dt < since_naive:
                stop = True
                continue
            collected.append(m)
        ids = [_msg_id(m) for m in batch if _msg_id(m)]
        if not ids:
            break
        oldest = min(ids)
        if last_id == oldest:
            break
        last_id = oldest
        if stop:
            break
    collected.sort(key=_msg_id)
    return collected


def parse_feedback(messages: list[dict], chat_id: str) -> tuple[list[dict], list[dict]]:
    """Из сообщений чата собрать applied.jsonl и rejected.jsonl записи."""
    proposals: dict[str, dict] = {}
    last_await: dict | None = None
    applied: list[dict] = []
    rejected: list[dict] = []

    for m in messages:
        text = _msg_text(m)
        if not text or "[AI-FB]#" not in text:
            continue
        match = MARK.search(text)
        if not match:
            continue
        mark_id, kind = match.group(1), match.group(2)
        if kind == "AWAIT_REASON":
            lead_m = RE_LEAD.search(text)
            last_await = {
                "fb_id": mark_id,
                "lead_id": lead_m.group(1) if lead_m else "",
            }
            continue
        if kind == "НА УТВЕРЖДЕНИИ":
            entity_m = RE_ENTITY.search(text)
            rule_m = RE_RULE.search(text)
            was_m = RE_WAS.search(text)
            now_m = RE_NOW.search(text)
            fb_id = (last_await or {}).get("fb_id") or f"p-{mark_id}"
            lead_id = (last_await or {}).get("lead_id") or ""
            proposals[mark_id] = {
                "proposal_id": mark_id,
                "fb_id": fb_id,
                "lead_id": lead_id,
                "chat_id": chat_id,
                "entity": (entity_m.group(1).strip() if entity_m else ""),
                "rule": (rule_m.group(1).strip() if rule_m else "?"),
                "was": (was_m.group(1).strip() if was_m else "(нет правила)"),
                "now": (now_m.group(1).strip() if now_m else ""),
                "date": _msg_date(m),
            }
            continue
        if kind == "ЗАМЕНЁН":
            continue
        if kind == "СТАТУС: УТВЕРЖДЕНО":
            base = proposals.get(mark_id) or {
                "proposal_id": mark_id,
                "fb_id": f"p-{mark_id}",
                "lead_id": "",
                "chat_id": chat_id,
                "entity": "",
                "rule": "?",
                "was": "(нет правила)",
                "now": "",
                "date": _msg_date(m),
            }
            by_m = RE_APPROVED_BY.search(text)
            rec = dict(base)
            rec["approved_by"] = by_m.group(1) if by_m else ""
            rec["date"] = _msg_date(m) or rec.get("date")
            if rec.get("now"):
                applied.append(rec)
            continue
        if kind == "СТАТУС: ОТКЛОНЕНО":
            base = proposals.get(mark_id) or {
                "proposal_id": mark_id,
                "fb_id": f"p-{mark_id}",
                "lead_id": "",
                "chat_id": chat_id,
                "rule": "?",
                "was": "",
                "now": "",
                "date": _msg_date(m),
            }
            reason_m = RE_REJECT_REASON.search(text)
            rec = {
                "fb_id": base.get("fb_id"),
                "lead_id": base.get("lead_id"),
                "chat_id": chat_id,
                "proposal": "P" + str(mark_id),
                "rule": base.get("rule"),
                "was": base.get("was"),
                "proposed": base.get("now"),
                "reason": reason_m.group(1) if reason_m else "",
                "date": _msg_date(m),
            }
            rejected.append(rec)
    return applied, rejected


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=".run/latest")
    parser.add_argument("--days", type=int, default=3, help="окно сообщений, дни")
    parser.add_argument("--chat", default=os.environ.get("LEAD_FEEDBACK_CHAT", PROD_CHAT))
    args = parser.parse_args()

    since = datetime.now(MSK) - timedelta(days=args.days)
    chat = args.chat if str(args.chat).startswith("chat") else f"chat{args.chat}"
    log.info("fetch chat=%s since=%s", chat, since.date().isoformat())
    messages = fetch_chat_messages(chat, since)
    applied, rejected = parse_feedback(messages, chat)
    out = Path(args.out_dir)
    write_jsonl(out / "applied.log", applied)
    write_jsonl(out / "rejected.log", rejected)
    log.info(
        "fetch: messages=%s applied=%s rejected=%s",
        len(messages),
        len(applied),
        len(rejected),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BitrixError as exc:
        log.error("%s", exc)
        raise SystemExit(1) from exc
