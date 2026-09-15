import apply_feedback as A
import hashlib


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


CANON = (
    "## ПРАВИЛА\n\n"
    "### R03 — Проверка\n"
    "**Правило:** старый текст R03.\n\n"
    "### F03 — Статус\n"
    "**Правило:** старый F03.\n"
)


def test_p6_test_chat_never_touches_canon():
    entries = [{"fb_id": "1-88442", "chat_id": "chat36910", "rule": "S02", "was": "(нет правила)", "now": "тест", "lead_id": "88442"}]
    new, ch, newly = A.apply_to_canon(entries, CANON)
    assert h(new) == h(CANON), "тест-чат НЕ должен менять мастер-свод"
    assert ch[0]["status"] == "SKIP_TEST_CHAT"
    print("PASS P6: chat36910 -> мастер-свод БЕЗ изменений")


def test_p6_prod_chat_applies():
    entries = [{"fb_id": "9-1", "chat_id": "chat31598", "rule": "R03", "was": "старый текст R03.", "now": "НОВЫЙ текст R03.", "lead_id": "1"}]
    new, ch, newly = A.apply_to_canon(entries, CANON)
    assert h(new) != h(CANON) and "НОВЫЙ текст R03." in new and "старый текст R03." not in new
    assert ch[0]["status"] == "APPLIED"
    print("PASS P6: chat31598 -> правило применено к своду")


def test_new_rule_appended():
    entries = [{"fb_id": "9-2", "chat_id": "31598", "rule": "НУЖНО НОВОЕ ПРАВИЛО (S)", "was": "(нет правила)", "now": "новое про госпитализацию", "lead_id": "85456"}]
    new, ch, newly = A.apply_to_canon(entries, CANON)
    assert "новое про госпитализацию" in new and ch[0]["status"] == "APPENDED"
    print("PASS: новое правило дописано в свод")


def test_p7_antipatterns_skip_test_chat():
    rej = [
        {"rule": "F03", "lead_id": "88656", "proposed": "ставить Отказ пациента", "reason": "нельзя без явного отказа", "chat_id": "chat31598"},
        {"rule": "S", "lead_id": "88400", "proposed": "тест", "reason": "так надо", "chat_id": "chat36910"},
    ]
    ap = A.antipatterns_from_rejected(rej)
    assert "НЕ предлагать" in ap and "88656" in ap
    assert "88400" not in ap
    print("PASS P7: анти-паттерн только из боевого чата")


def test_mixed_only_prod_applied():
    entries = [
        {"fb_id": "t", "chat_id": "chat36910", "rule": "R03", "was": "старый текст R03.", "now": "X", "lead_id": "1"},
        {"fb_id": "p", "chat_id": "chat31598", "rule": "F03", "was": "старый F03.", "now": "НОВЫЙ F03.", "lead_id": "2"},
    ]
    new, ch, newly = A.apply_to_canon(entries, CANON)
    assert "старый текст R03." in new, "тест-запись НЕ применена"
    assert "НОВЫЙ F03." in new, "боевая запись применена"
    print("PASS: в миксе применена только боевая запись")


def test_idempotency_skip_already_applied():
    e = {"fb_id": "9-9", "chat_id": "chat31598", "rule": "НУЖНО НОВОЕ ПРАВИЛО (S)", "was": "(нет правила)", "now": "новое правило X", "lead_id": "5"}
    new1, ch1, newly1 = A.apply_to_canon([e], CANON)
    assert "новое правило X" in new1 and newly1 == ["9-9"]
    new2, ch2, newly2 = A.apply_to_canon([e], new1, processed=["9-9"])
    assert h(new2) == h(new1)
    assert ch2[0]["status"] == "SKIP_ALREADY_APPLIED" and newly2 == []
    assert new2.count("новое правило X") == 1
    print("PASS идемпотентность: processed fb_id пропускается")


def test_dedup_same_run_keeps_last():
    entries = [
        {"fb_id": "68-1", "chat_id": "chat31598", "rule": "R03", "was": "старый текст R03.", "now": "версия 1", "lead_id": "1"},
        {"fb_id": "68-1", "chat_id": "chat31598", "rule": "R03", "was": "старый текст R03.", "now": "версия 2", "lead_id": "1"},
    ]
    new, ch, newly = A.apply_to_canon(entries, CANON)
    assert newly == ["68-1"]
    assert "версия 2" in new and "версия 1" not in new
    assert sum(1 for c in ch if c["status"] == "APPLIED") == 1
    print("PASS: дубль fb_id в одном логе — одна правка, последняя версия")


if __name__ == "__main__":
    import traceback

    ts = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for t in ts:
        try:
            t()
            ok += 1
        except Exception as e:
            print("FAIL", t.__name__, e)
            traceback.print_exc()
    print(f"\n{ok}/{len(ts)} passed")
    raise SystemExit(0 if ok == len(ts) else 1)
