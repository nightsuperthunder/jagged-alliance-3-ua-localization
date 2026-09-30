"""Вичитка перекладу локальною моделлю (редактор).

Модель отримує оригінал + переклад і виправляє граматику, рід, кальки, відповідність глосарію.
Попередня версія зберігається в полі uk_before_proof; всі зміни пишуться в work/proofread_log.csv.
Ручні правки (manual) не чіпаються; кожен рядок вичитується один раз (proofed: true).

  python scripts/proofread.py
  python scripts/proofread.py --file dialogue --limit 30   # проба
  python scripts/proofread.py --revert                     # відкотити вичитку
"""
import argparse
import csv
import json
import time

from common import (DEFAULT_MODEL, ORDER, TRANSLATIONS, WORK, glossary_terms, load_json,
                    load_strings, save_json, system_prompt, validate)
from llm import (REQUEST_ERRORS, ensure_ollama, add_model_args, call_translate, file_hint, glossary_for,
                 item_head, make_batches, ui_terms)

EDITOR = """

ТВОЯ РОЛЬ ЗАРАЗ — РЕДАКТОР. Тобі дають англійський оригінал і готовий український переклад.
Виправ у перекладі:
- граматичні помилки, узгодження роду/числа/відмінка;
- кальки з англійської й неприродні звороти (див. СТИЛЬ);
- смислові помилки й пропуски порівняно з оригіналом;
- невідповідність глосарію та назвам інтерфейсу.
Якщо переклад уже добрий — поверни його БЕЗ ЗМІН. Не переписуй заради переписування,
не додавай нічого від себе. Усі ТЕХНІЧНІ ПРАВИЛА (теги, плейсхолдери, префікси, \\:) лишаються в силі.
"""


def build(batch, fk, terms, ui):
    text = " ".join(x["en"] for x in batch)
    parts = [file_hint(fk)]
    g = glossary_for(text, terms)
    if g:
        parts.append("ГЛОСАРІЙ:\n" + "\n".join(g))
    u = glossary_for(text, ui)
    if u:
        parts.append("НАПИСИ ІНТЕРФЕЙСУ (у лапках «…», не відмінювати):\n" + "\n".join(u))
    items = [f"{item_head(i, x)}\nEN: {json.dumps(x['en'], ensure_ascii=False)}\n"
             f"UK: {json.dumps(x['uk'], ensure_ascii=False)}" for i, x in enumerate(batch, 1)]
    parts.append(f"ВІДРЕДАГУЙ ці {len(batch)} перекладів. Відповідь — JSON {{\"t\": [{{\"n\": номер, "
                 f"\"uk\": \"виправлений або незмінний переклад\"}}]}} з рівно {len(batch)} елементами.\n\n"
                 + "\n\n".join(items))
    return "\n\n".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    add_model_args(ap, DEFAULT_MODEL, 0.2)
    ap.add_argument("--file", choices=ORDER, action="append")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--chars", type=int, default=1500)
    ap.add_argument("--items", type=int, default=15)
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    tr = load_json(args.tr, {})
    if args.revert:
        n = 0
        for v in tr.values():
            if "uk_before_proof" in v:
                v["uk"] = v.pop("uk_before_proof")
                v.pop("proofed", None)
                n += 1
        save_json(args.tr, tr)
        print(f"Відкочено {n}")
        return

    ensure_ollama(args.model)
    strings = load_strings()
    terms = glossary_terms()
    allowed = {t["en"] for t in terms}
    system = system_prompt() + EDITOR
    ui = ui_terms(strings, tr)
    log_path = WORK / "proofread_log.csv"
    new_log = not log_path.exists()
    log = open(log_path, "a", encoding="utf-8-sig", newline="")
    lw = csv.writer(log)
    if new_log:
        lw.writerow(["key", "en", "before", "after"])

    files = args.file or ORDER
    t0, done, changed = time.time(), 0, 0
    for fk in [f for f in ORDER if f in files]:
        rows = []
        for s in sorted((x for x in strings if x["file"] == fk), key=lambda x: x["order"]):
            t = tr.get(s["key"])
            if t and t["status"] == "ok" and not t.get("proofed") and t.get("model") != "dup":
                rows.append({**s, "uk": t["uk"]})
        if args.limit:
            rows = rows[:args.limit]
        print(f"\n=== {fk}: на вичитку {len(rows)}")
        for batch in make_batches(rows, args.chars, args.items):
            try:
                res = call_translate(args, system, build(batch, fk, terms, ui), args.temp)
            except REQUEST_ERRORS as e:
                print(f"  ! запит не вдався ({e}), пропускаю партію")
                continue
            bc = 0
            for i, r in enumerate(batch, 1):
                t = tr[r["key"]]
                new = res.get(i)
                t["proofed"] = True
                # правка редактора приймається, лише якщо проходить перевірку
                if new and new != r["uk"] and not validate(r["en"], new, allowed):
                    t["uk_before_proof"] = r["uk"]
                    t["uk"] = new
                    lw.writerow([r["key"], r["en"], r["uk"], new])
                    bc += 1
            save_json(args.tr, tr)
            log.flush()
            done += len(batch)
            changed += bc
            print(f"  [{fk}] +{len(batch)} (змінено {bc}) | всього {done}, змінено {changed} | "
                  f"{(time.time() - t0) / 60:.1f} хв", flush=True)
    log.close()
    print(f"\nВичитку завершено: переглянуто {done}, змінено {changed}. Лог: {log_path}")


if __name__ == "__main__":
    main()
