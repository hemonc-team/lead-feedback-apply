from fetch import parse_feedback


def test_parse_approved_links_await_reason():
    messages = [
        {"id": 1, "text": "❓ по лиду #89072 — напишите\n· [AI-FB]#68-89072 AWAIT_REASON", "date": "2026-07-20T09:00:00"},
        {
            "id": 2,
            "text": (
                "[AI-FB]#500 НА УТВЕРЖДЕНИИ\nproposal: P500\n"
                "Сущность: коммуникация\nПравило: R02\n"
                "БЫЛО: «старое»\nСТАЛО: «новое правило»"
            ),
            "date": "2026-07-20T09:01:00",
        },
        {"id": 3, "text": "[AI-FB]#500 СТАТУС: УТВЕРЖДЕНО (правило R02, 2026-07-20) — утвердил 8", "date": "2026-07-20T09:02:00"},
    ]
    applied, rejected = parse_feedback(messages, "chat31598")
    assert rejected == []
    assert len(applied) == 1
    rec = applied[0]
    assert rec["fb_id"] == "68-89072"
    assert rec["lead_id"] == "89072"
    assert rec["was"] == "старое"
    assert rec["now"] == "новое правило"
    assert rec["rule"] == "R02"
    assert rec["chat_id"] == "chat31598"
    print("PASS parse: УТВЕРЖДЕНО связано с AWAIT_REASON")


def test_parse_rejected():
    messages = [
        {
            "id": 1,
            "text": "[AI-FB]#9 НА УТВЕРЖДЕНИИ\nСущность: UF-поле\nПравило: F03\nБЫЛО: «a»\nСТАЛО: «ставить Отказ»",
            "date": "2026-07-17T10:00:00",
        },
        {"id": 2, "text": "[AI-FB]#9 СТАТУС: ОТКЛОНЕНО (причина: «нельзя без явного отказа», 2026-07-17)", "date": "2026-07-17T10:05:00"},
    ]
    applied, rejected = parse_feedback(messages, "chat31598")
    assert applied == []
    assert len(rejected) == 1
    assert rejected[0]["proposed"] == "ставить Отказ"
    assert "явного отказа" in rejected[0]["reason"]
    print("PASS parse: ОТКЛОНЕНО")


def test_ignore_replaced_proposal():
    messages = [
        {
            "id": 1,
            "text": "[AI-FB]#1 НА УТВЕРЖДЕНИИ\nСущность: x\nПравило: R\nБЫЛО: «a»\nСТАЛО: «черновик»",
            "date": "2026-07-20T09:00:00",
        },
        {"id": 2, "text": "[AI-FB]#1 ЗАМЕНЁН → P2", "date": "2026-07-20T09:01:00"},
        {
            "id": 3,
            "text": "[AI-FB]#2 НА УТВЕРЖДЕНИИ\nСущность: x\nПравило: R\nБЫЛО: «a»\nСТАЛО: «финал»",
            "date": "2026-07-20T09:02:00",
        },
        {"id": 4, "text": "[AI-FB]#2 СТАТУС: УТВЕРЖДЕНО (правило R, 2026-07-20) — утвердил 8", "date": "2026-07-20T09:03:00"},
    ]
    applied, rejected = parse_feedback(messages, "chat31598")
    assert len(applied) == 1
    assert applied[0]["now"] == "финал"
    print("PASS parse: ЗАМЕНЁН не попадает в applied")


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
