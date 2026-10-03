"""Фільтр підозр (напр. work/context_review.csv): локальна модель перевіряє, чи помилка ще є в ПОТОЧНОМУ перекладі.

  python scripts/judge_suspects.py local [--csv work/context_review.csv --csv work/shift_candidates.csv]   -> work/_suspects/local.json (дозапуск)
  python scripts/judge_suspects.py export [--size 150]                     -> work/_suspects/packet_NN.json для Claude
  (агенти пишуть work/_suspects/out_NN.json = {"ключ": "виправлений переклад"} лише для справжніх помилок)
  python scripts/judge_suspects.py apply [--dry]                           -> через fix.py (статус manual)
Дешевший шлях без Claude (рекомендований):
  python scripts/judge_suspects.py retranslate [--keys work/_suspects/keys.txt]  -> MamayLM по одному рядку -> new.json
  python scripts/judge_suspects.py ab                                            -> gpt-oss: старий чи новий -> ab.json
  python scripts/judge_suspects.py apply-ab [--dry]                              -> новий через fix.py; «обидва погані»
                                                                                    -> escalate.txt (для Claude)

Пропозиції першого судді не застосовуються — лише його пояснення ("errors") іде підказкою.
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

from common import TRANSLATIONS, WORK, glossary_terms, load_json, load_strings, save_json
from llm import glossary_for
from proof_ab import ask

OUT = WORK / "_suspects"
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["error", "ok"]},
                                           "why": {"type": "string"}}, "required": ["verdict", "why"]}
SYSTEM = """Ти перевіряєш український переклад гри Jagged Alliance 3 (найманці, вигадана африканська країна, чорний гумор).
Інший рецензент позначив рядок як помилковий і пояснив чому (note). Його пояснення може бути хибним.
Вирішуй щодо ПОТОЧНОГО перекладу (uk): чи є в ньому СПРАВЖНЯ помилка, помітна гравцю:
- зміст не відповідає оригіналу (en), щось важливе додано/загублено, переклад узагалі про інше
  (наприклад, це переклад сусідньої репліки — порівняй із контекстом ctx);
- ім'я/назва не відповідає глосарію або замінено на інше ім'я;
- рід мовця (speaker) чи адресата неправильний;
- мат — лише слова з коренями хуй, пизд, бля, їба/єба — заборонений.
НЕ помилка:
- нематюкова лайка будь-якої сили: довбаний, гівно, лайно, дупа, срака, покидьки, падлюки, сучий син, дідько,
  «до сраки», «під три чорти» — це правильна передача англійських fuck/shit/ass/goddamn;
- ідіоми й лайка, передані українськими відповідниками замість дослівного перекладу;
- синоніми, стиль, порядок слів, вільніший переклад того самого змісту, активний/пасивний стан;
- транслітеровані імена з глосарію, французькі слова латиницею (merde, mon Dieu), теги <…>.
Найважливіше — переклад, що взагалі про інше (часто це переклад сусідньої репліки з ctx), і втрачений або
перекручений зміст. Якщо сумніваєшся — "ok".
Відповідь — JSON: {"verdict": "error" | "ok", "why": "коротко"}."""


def items(args):
    notes = {}
    for path in args.csv or [str(WORK / "context_review.csv")]:
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            notes.setdefault(r["key"], r["errors"].removeprefix("[?] ").strip())
    tr = load_json(TRANSLATIONS, {})
    terms = glossary_terms()
    strings = sorted(load_strings(), key=lambda x: (x["file"], x["order"]))
    by_file = {}
    for s in strings:
        by_file.setdefault(s["file"], []).append(s)
    out = []
    for f, fr in by_file.items():
        for i, s in enumerate(fr):
            if s["key"] not in notes or s["key"] not in tr:
                continue
            ctx = lambda r: f"{r.get('speaker') or '?'}: {r['en'][:150]} => {tr.get(r['key'], {}).get('uk', '')[:150]}"
            it = {"key": s["key"], "speaker": s.get("speaker", ""), "en": s["en"], "uk": tr[s["key"]]["uk"],
                  "note": notes[s["key"]][:400], "comment": s.get("comment", "")[:150],
                  "ctx": [ctx(r) for r in fr[max(0, i - 2):i]] + ["(цей рядок)"] + [ctx(r) for r in fr[i + 1:i + 2]]}
            g = glossary_for(s["en"], terms)
            if g:
                it["glossary"] = g
            out.append(it)
    return out


def local(args):
    path = OUT / "local.json"
    res = load_json(path, {})
    todo = [x for x in items(args) if x["key"] not in res]
    print(f"Залишилось: {len(todo)}", flush=True)
    for n, x in enumerate(todo, 1):
        a = ask(args, SYSTEM, json.dumps({k: v for k, v in x.items() if k != "key"}, ensure_ascii=False), SCHEMA)
        res[x["key"]] = {"verdict": (a or {}).get("verdict", "?"), "why": (a or {}).get("why", "")[:300]}
        if n % 20 == 0 or n == len(todo):
            save_json(path, res)
            print(f"{n}/{len(todo)}", flush=True)


def export(args):
    res = load_json(OUT / "local.json", {})
    esc = [x for x in items(args) if res.get(x["key"], {}).get("verdict") != "ok"]
    for old in OUT.glob("packet_*.json"):
        old.unlink()
    n = 0
    for n, start in enumerate(range(0, len(esc), args.size), 1):
        with open(OUT / f"packet_{n:02d}.json", "w", encoding="utf-8") as fh:
            fh.write("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False)
                                         for x in esc[start:start + args.size]) + "\n]\n")
    print(f"До Claude: {len(esc)} рядків, пакетів {n}")


def apply(args):
    fixes = {}
    for p in sorted(OUT.glob("out_*.json")):
        fixes.update(load_json(p, {}))
    print(f"Виправлень: {len(fixes)}")
    if not fixes:
        return
    path = OUT / "_apply.json"
    save_json(path, fixes)
    cmd = [sys.executable, str(Path(__file__).with_name("fix.py")), "--json", str(path)] + (["--dry"] if args.dry else [])
    subprocess.run(cmd, check=True)


def by_file_index():
    strings = sorted(load_strings(), key=lambda x: (x["file"], x["order"]))
    byf = {}
    for s in strings:
        byf.setdefault(s["file"], []).append(s)
    return byf, {s["key"]: (f, i) for f, rows in byf.items() for i, s in enumerate(rows)}


def retranslate(args):
    """Локальний переклад заново — по ОДНОМУ рядку (у партіях переклади з'їжджали на сусідні рядки)."""
    from llm import call_translate, ui_terms
    from translate import build_prompt
    from common import system_prompt, validate
    tr = load_json(TRANSLATIONS, {})
    keys = [k for k in Path(args.keys).read_text(encoding="utf-8").split() if tr.get(k, {}).get("status") == "ok"]
    path = OUT / "new.json"
    new = load_json(path, {})
    terms = glossary_terms()
    allowed = {t["en"] for t in terms}
    byf, idx = by_file_index()
    ui = ui_terms([s for rows in byf.values() for s in rows], tr)
    system = system_prompt()
    todo = [k for k in keys if k not in new and k in idx]
    print(f"Залишилось: {len(todo)}", flush=True)
    for n, k in enumerate(todo, 1):
        f, i = idx[k]
        rows = byf[f]
        prev = [dict(x, uk=tr.get(x["key"], {}).get("uk", "")) for x in rows[max(0, i - 3):i]]
        user = build_prompt([rows[i]], prev, rows[i + 1:i + 2], f, terms, ui)
        for att in range(4):
            try:
                uk = call_translate(args, system, user, 0.3 + 0.2 * att).get(1)
            except Exception:
                uk = None
            if uk and not validate(rows[i]["en"], uk, allowed):
                new[k] = uk
                break
        if n % 20 == 0 or n == len(todo):
            save_json(path, new)
            print(f"{n}/{len(todo)}", flush=True)


def ab(args):
    """Суддя (gpt-oss): старий переклад чи новий; 0 — обидва погані."""
    import random
    tr = load_json(TRANSLATIONS, {})
    new = load_json(OUT / "new.json", {})
    path = OUT / "ab.json"
    res = load_json(path, {})
    terms = glossary_terms()
    byf, idx = by_file_index()
    system = (WORK / "_proof_ab" / "INSTRUCTIONS.md").read_text(encoding="utf-8").split("## Відповідь")[0] + (
        '\n## Відповідь\nJSON: {"choice": 1 | 2 | 0, "why": "коротко"} — 0, якщо обидва варіанти явно погані '
        "(не той зміст, зламане ім’я, неправильний рід мовця).")
    rnd = random.Random(7)
    todo = [k for k, v in new.items() if k not in res and tr.get(k, {}).get("status") == "ok" and v != tr[k]["uk"]]
    print(f"Залишилось: {len(todo)}", flush=True)
    for n, k in enumerate(todo, 1):
        f, i = idx[k]
        s = byf[f][i]
        first = "new" if rnd.random() < 0.5 else "old"
        a, b = (new[k], tr[k]["uk"]) if first == "new" else (tr[k]["uk"], new[k])
        it = {"speaker": s.get("speaker", ""), "en": s["en"], "1": a, "2": b, "comment": s.get("comment", "")[:150],
              "prev": [f"{r.get('speaker') or '?'}: {r['en'][:150]}" for r in byf[f][max(0, i - 2):i]]}
        g = glossary_for(s["en"], terms)
        if g:
            it["glossary"] = g
        r = ask(args, system, json.dumps(it, ensure_ascii=False))
        res[k] = {"choice": (r or {}).get("choice", -1), "first": first, "why": (r or {}).get("why", "")[:300]}
        if n % 20 == 0 or n == len(todo):
            save_json(path, res)
            print(f"{n}/{len(todo)}", flush=True)


def apply_ab(args):
    tr = load_json(TRANSLATIONS, {})
    new = load_json(OUT / "new.json", {})
    res = load_json(OUT / "ab.json", {})
    fixes, esc, kept = {}, [], 0
    for k, r in res.items():
        if tr.get(k, {}).get("status") != "ok":
            continue
        if r["choice"] in (1, 2):
            pick = r["first"] if r["choice"] == 1 else ("old" if r["first"] == "new" else "new")
            if pick == "new":
                fixes[k] = new[k]
            else:
                kept += 1
        else:
            esc.append(k)
    (OUT / "escalate.txt").write_text("\n".join(esc), encoding="utf-8")
    print(f"новий: {len(fixes)}, старий лишається: {kept}, обидва погані (-> escalate.txt): {len(esc)}")
    if fixes and not args.dry:
        p = OUT / "_apply_ab.json"
        save_json(p, fixes)
        subprocess.run([sys.executable, str(Path(__file__).with_name("fix.py")), "--json", str(p)], check=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rt = sub.add_parser("retranslate")
    rt.add_argument("--keys", default=str(OUT / "keys.txt"))
    rt.add_argument("--model", default="hf.co/INSAIT-Institute/MamayLM-Gemma-3-12B-IT-v2.0-GGUF:Q8_0")
    rt.add_argument("--ctx", type=int, default=8192)
    rt.set_defaults(no_think=True)
    abp = sub.add_parser("ab")
    abp.add_argument("--model", default="gpt-oss:latest")
    abp.add_argument("--think", default="medium")
    aa = sub.add_parser("apply-ab")
    aa.add_argument("--dry", action="store_true")
    lo = sub.add_parser("local")
    lo.add_argument("--model", default="gpt-oss:latest")
    lo.add_argument("--think", default="medium")
    ex = sub.add_parser("export")
    ex.add_argument("--size", type=int, default=150)
    a = sub.add_parser("apply")
    a.add_argument("--dry", action="store_true")
    for p in (lo, ex):
        p.add_argument("--csv", action="append", help="CSV з колонками key, errors (можна кілька)")
    args = ap.parse_args()
    {"local": local, "export": export, "apply": apply, "retranslate": retranslate, "ab": ab,
     "apply-ab": apply_ab}[args.cmd](args)


if __name__ == "__main__":
    main()
