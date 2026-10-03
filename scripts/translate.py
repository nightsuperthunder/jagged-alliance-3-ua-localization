"""Переклад рядків локальною моделлю (Ollama).

  python scripts/translate.py --file dialogue --limit 40 --out work/test_a.json   # проба
  python scripts/translate.py                  # повний переклад (Ctrl+C і запуск знову — продовжить)
  python scripts/translate.py --redo-errors    # перекласти заново рядки з помилками

Партії ≤1800 символів / 25 рядків, 5 попередніх перекладених рядків + 2 наступні як контекст,
глосарій і автоглосарій інтерфейсу — лише терміни, що є в партії. Кожен рядок перевіряється
validate(); невдалі — ще до 2 спроб поштучно, з текстом помилки в промпті.
"""
import argparse
import json
import re
import time

from common import (autofix, needs_translit, ru_mask, ru_translit, ru_unmask, CFG, DEFAULT_MODEL, ORDER, TRANSLATIONS, glossary_terms, is_stub,
                    load_json, load_strings, save_json, src_hash, system_prompt, validate)
from ru_ref import grammar_errors, note as ru_note
from llm import (REQUEST_ERRORS, ensure_ollama, add_model_args, call_translate, file_hint, glossary_for,
                 item_head, make_batches, ui_terms)

EXTRA_NOTES = CFG.get("extra_notes", {})
NEXT_FILES = set(CFG.get("context_next_files", []))


def build_prompt(batch, prev, nxt, fk, terms, ui=()):
    text = " ".join(x["en"] for x in batch)
    parts = [file_hint(fk)]
    g = glossary_for(text + " " + " ".join(p["en"] for p in prev[-3:]), terms)
    if g:
        parts.append("ГЛОСАРІЙ (використовуй саме ці переклади, відмінюй за правилами):\n" + "\n".join(g))
    u = glossary_for(text, ui)
    if u:
        parts.append("НАПИСИ ІНТЕРФЕЙСУ ГРИ (якщо текст посилається на кнопку, вкладку чи розділ — "
                     "пиши назву точно як тут, у лапках «…», не відмінюючи):\n" + "\n".join(u))
    if prev:
        parts.append("ПОПЕРЕДНІ РЯДКИ (вже перекладені, лише для контексту, НЕ перекладай):\n"
                     + "\n".join(f"EN: {p['en']}\nUK: {p['uk']}" for p in prev))
    if nxt:
        parts.append("НАСТУПНІ РЯДКИ (лише для контексту, НЕ перекладай):\n"
                     + "\n".join(f"EN: {x['en']}" for x in nxt))
    items = [f"{item_head(i, x, '; '.join(n for n in (EXTRA_NOTES.get(x['en'].strip(), ''), ru_note(x)) if n))}\n"
             f"EN: {json.dumps(x['en'], ensure_ascii=False)}" for i, x in enumerate(batch, 1)]
    parts.append(
        f"ПЕРЕКЛАДИ ці {len(batch)} рядків. Відповідь — JSON {{\"t\": [{{\"n\": номер, \"uk\": \"переклад\"}}]}} "
        f"з рівно {len(batch)} елементами, по одному на кожен номер.\n\n" + "\n\n".join(items))
    return "\n\n".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    add_model_args(ap, DEFAULT_MODEL, 0.3)
    ap.add_argument("--file", choices=ORDER, action="append", help="лише ці файли (можна кілька разів)")
    ap.add_argument("--limit", type=int, help="максимум рядків на файл (для проби)")
    ap.add_argument("--start", type=int, default=0, help="пропустити перші N рядків файлу (для проби)")
    ap.add_argument("--keys", help="файл зі списком ключів (по одному в рядку) — перекладати лише їх")
    ap.add_argument("--out", default=str(TRANSLATIONS), help="куди писати переклади")
    ap.add_argument("--redo-errors", action="store_true", help="перекласти заново рядки з помилками")
    ap.add_argument("--redo-all", action="store_true", help="перекласти заново все (крім ручних правок)")
    ap.add_argument("--chars", type=int, default=1800, help="макс. символів англ. тексту в партії")
    ap.add_argument("--items", type=int, default=25, help="макс. рядків у партії")
    args = ap.parse_args()

    ensure_ollama(args.model)
    strings = load_strings()
    terms = glossary_terms()
    allowed_latin = {t["en"] for t in terms}
    system = system_prompt()
    tr = load_json(args.out, {})
    files = args.file or ORDER
    only = set(open(args.keys, encoding="utf-8").read().split()) if args.keys else None
    total_done, t0 = 0, time.time()

    for fk in [f for f in ORDER if f in files]:
        rows = sorted((x for x in strings if x["file"] == fk), key=lambda x: x["order"])[args.start:]
        # з --keys перекладаємо лише ці рядки, але сусідні лишаються в rows як контекст розмови
        if args.limit:
            rows = rows[:args.limit]
        index = {r["key"]: i for i, r in enumerate(rows)}

        # заглушки, дублікати, вже готове
        todo = []
        done_by_en = {r["en"]: tr[r["key"]]["uk"] for r in rows
                      if r["key"] in tr and tr[r["key"]]["status"] in ("ok", "manual")
                      and tr[r["key"]].get("src") == src_hash(r["en"])}
        for r in rows:
            if only is not None and r["key"] not in only:
                continue
            cur = tr.get(r["key"])
            src = src_hash(r["en"])
            if cur and cur["status"] == "manual":
                continue  # ручну правку не чіпаємо; якщо оригінал змінився, review.py це покаже
            if cur and cur.get("src") != src:
                cur = None  # оригінал у грі змінився
            if cur and cur["status"] in ("ok", "skip") and not args.redo_all:
                continue
            if cur and cur["status"] == "error" and not (args.redo_errors or args.redo_all):
                continue
            if is_stub(r["en"], r.get("comment", "")) or not re.search(r"[A-Za-zА-Яа-яЁё]", r["en"]):
                tr[r["key"]] = {"src": src, "status": "skip"}
                continue
            if needs_translit(r) and not re.search(r"[A-Za-z]", r["en"]):
                tr[r["key"]] = {"src": src, "uk": ru_translit(r["en"]), "status": "ok", "model": "translit"}
                continue
            if r["en"] in done_by_en and not args.redo_all:
                tr[r["key"]] = {"src": src, "uk": done_by_en[r["en"]], "status": "ok", "model": "dup"}
                continue
            if needs_translit(r):
                masked, spans = ru_mask(r["en"])
                note = "; ".join(f"{t} — російська вставка, гра покаже її як «{v}»" for t, v in spans.items())
                r = dict(r, en=masked, en_orig=r["en"], spans=spans,
                         comment=(r.get("comment", "") + " | " + note).strip(" |"))
            todo.append(r)
        save_json(args.out, tr)
        ui = ui_terms(strings, tr) if fk != CFG.get("ui_file") else []  # написи UI, назви дій/станів/предметів
        if CFG.get("ui_file") and fk != CFG["ui_file"] and not ui:
            print("  (увага: інтерфейс ще не перекладено — назви кнопок не будуть узгоджені)")
        print(f"\n=== {fk}: треба перекласти {len(todo)} із {len(rows)}"
              + (f", написів UI в глосарії: {len(ui)}" if ui else ""))

        for batch in make_batches(todo, args.chars, args.items):
            first = index[batch[0]["key"]]
            prev = [{"en": r["en"], "uk": tr[r["key"]]["uk"]} for r in rows[max(0, first - 5):first]
                    if r["key"] in tr and tr[r["key"]]["status"] in ("ok", "manual")]
            last = index[batch[-1]["key"]]
            nxt = rows[last + 1:last + 3] if fk in NEXT_FILES else []

            pending = list(batch)
            for attempt in range(3):
                if not pending:
                    break
                groups = [pending] if attempt == 0 else [[p] for p in pending]  # повтор — поштучно
                pending = []
                for g in groups:
                    user = build_prompt(g, prev, nxt, fk, terms, ui)
                    if attempt > 0 and tr.get(g[0]["key"], {}).get("errors"):
                        user += "\n\nМИНУЛОГО РАЗУ БУЛИ ПОМИЛКИ, виправ їх: " + "; ".join(tr[g[0]["key"]]["errors"])
                    try:
                        res = call_translate(args, system, user, args.temp + 0.2 * attempt)
                    except REQUEST_ERRORS as e:
                        print(f"  ! запит не вдався ({e}), повтор…")
                        res = {}
                    for i, r in enumerate(g, 1):
                        en = r.get("en_orig", r["en"])
                        uk = autofix(r["en"], res.get(i, ""))
                        errs = validate(r["en"], uk, allowed_latin)  # для рядків з <rN> — до підстановки
                        if "spans" in r:
                            uk = ru_unmask(uk, r["spans"])
                        errs += grammar_errors(r, uk)
                        rec = {"src": src_hash(en), "uk": uk, "status": "error" if errs else "ok",
                               "model": args.model}
                        if errs:
                            rec["errors"] = errs
                            pending.append(r)
                        tr[r["key"]] = rec
            save_json(args.out, tr)
            total_done += len(batch)
            ok = sum(1 for r in batch if tr[r["key"]]["status"] == "ok")
            el = time.time() - t0
            print(f"  [{fk}] +{len(batch)} (ok {ok}/{len(batch)}) | всього {total_done} | "
                  f"{el / 60:.1f} хв, {el / max(total_done, 1):.1f} с/рядок", flush=True)
            for r in batch:
                if tr[r["key"]]["status"] == "error":
                    print(f"    ✗ {r['key']}: {tr[r['key']]['errors']}")

    stats = {}
    for v in tr.values():
        stats[v["status"]] = stats.get(v["status"], 0) + 1
    print(f"\nГотово. Статуси: {stats}. Файл: {args.out}")


if __name__ == "__main__":
    main()
