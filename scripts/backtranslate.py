"""Крок 3г. Пошук смислових помилок зворотним перекладом.

Модель перекладає наш український текст назад англійською, а далі програма порівнює
цей зворотний переклад з оригіналом за змістом (embeddings). Що нижча схожість —
то ймовірніше, що зміст спотворено.

  python scripts/backtranslate.py                       # файли з project.json issue_files
  python scripts/backtranslate.py --file content --file tutorial
  python scripts/backtranslate.py --limit 200           # проба
  python scripts/backtranslate.py --report 300          # лише перебудувати CSV з наявних даних

Результат:
  work/backtranslate.json  — зворотні переклади і схожість (можна переривати й продовжувати)
  work/suspects.csv        — найпідозріліші рядки у форматі review.py
  work/suspects.txt        — їхні ключі (для context_review.py --only-keys)
"""
import argparse
import csv
import json
import math
import time

from common import (CFG, DEFAULT_MODEL, EMBED_MODEL, JUDGE_MODEL, ORDER, TRANSLATIONS, WORK,
                    load_json, load_strings, save_json)
from llm import REQUEST_ERRORS, ensure_ollama, call_raw, embed, make_batches

OUT = WORK / "backtranslate.json"

SYSTEM = """Ти — перекладач. Тобі дають український текст з відеогри.
Переклади його назад англійською МАКСИМАЛЬНО БУКВАЛЬНО: передавай саме те, що написано українською,
навіть якщо це звучить незграбно. Не покращуй, не здогадуйся, не повертай «оригінальне» формулювання.
Зберігай теги, плейсхолдери {0} і префікси. Відповідь — JSON {"t": [{"n": номер, "en": "переклад"}]}."""

SCHEMA = {
    "type": "object",
    "properties": {
        "t": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "en": {"type": "string"}},
                "required": ["n", "en"],
            },
        }
    },
    "required": ["t"],
}


JUDGE_SYSTEM = """You compare two English sentences from a video game.
ORIGINAL is the game's English text. BACK is a literal back-translation of the Ukrainian localisation.

Report a line ONLY if BACK states something factually different from ORIGINAL, for example:
- the meaning of a word or phrase is different ("shan't be missed" vs "won't be mourning");
- who does what to whom changed; a negation, number, tense or person changed;
- a proper noun became a common word or vice versa;
- information was added or dropped.

IGNORE: different wording with the same meaning, style, word order, articles, idioms rendered
plainly, punctuation, slightly clumsy English. BACK is deliberately literal — that is NOT an error.
Empty list is a normal and frequent answer.

Answer JSON: {"issues": [{"n": number, "why": "what changed, in Ukrainian, one short sentence"}]}"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "why": {"type": "string"}},
                "required": ["n", "why"],
            },
        }
    },
    "required": ["issues"],
}


def judge(args, strings, tr, data):
    """Друга фаза: сильніша модель порівнює оригінал із зворотним перекладом."""
    rows = [s for s in strings if s["key"] in data and "judged" not in data[s["key"]]
            and (not args.file or s["file"] in args.file)]
    if args.limit:
        rows = rows[:args.limit]
    print(f"Порівняння: {len(rows)} рядків, модель {args.judge_model}")
    t0, done, found = time.time(), 0, 0
    args_judge = argparse.Namespace(**{**vars(args), "model": args.judge_model})
    for i in range(0, len(rows), args.judge_items):
        batch = rows[i:i + args.judge_items]
        user = "\n\n".join(
            f"[{n}]\nORIGINAL: {json.dumps(r['en'], ensure_ascii=False)}\n"
            f"BACK: {json.dumps(data[r['key']]['bt'], ensure_ascii=False)}"
            for n, r in enumerate(batch, 1))
        try:
            res = call_raw(args_judge, JUDGE_SYSTEM, user, args.temp, JUDGE_SCHEMA)["issues"]
        except REQUEST_ERRORS as e:
            print(f"  ! запит не вдався ({e})")
            continue
        flagged = {int(x["n"]): x.get("why", "") for x in res if isinstance(x, dict) and "n" in x}
        for n, r in enumerate(batch, 1):
            data[r["key"]]["judged"] = True
            if n in flagged:
                data[r["key"]]["issue"] = flagged[n]
                found += 1
        save_json(OUT, data)
        done += len(batch)
        el = time.time() - t0
        print(f"  порівняно {done}/{len(rows)}, зауважень {found} | {el / 60:.1f} хв", flush=True)
    return found


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def report(strings, tr, data, top, csv_path, txt_path):
    """У звіт ідуть рядки із зауваженням від судді; якщо їх немає — найнижча схожість."""
    rows = []
    for s in strings:
        d = data.get(s["key"])
        t = tr.get(s["key"])
        if not d or not t:
            continue
        rows.append((0 if d.get("issue") else 1, d.get("sim", 1), s, t, d))
    rows.sort(key=lambda r: (r[0], r[1]))
    rows = [r for r in rows if r[0] == 0] or rows[:top]
    rows = [(sim, s, t, d) for _, sim, s, t, d in rows][:top]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, ["key", "file", "status", "en", "uk", "comment", "errors"])
        w.writeheader()
        for sim, s, t, d in rows:
            w.writerow({"key": s["key"], "file": s["file"], "status": t["status"], "en": s["en"],
                        "uk": t["uk"], "comment": s["comment"],
                        "errors": (d.get("issue", "") + f" | схожість {sim:.2f}"
                                   f" | зворотний переклад: {d['bt']}").strip(" |")})
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(s["key"] for _, s, _, _ in rows))
    print(f"{len(rows)} найпідозріліших -> {csv_path} і {txt_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--embed-model", default=EMBED_MODEL)
    ap.add_argument("--file", choices=ORDER, action="append")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int, default=0, help="пропустити перші N рядків (для проби)")
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--chars", type=int, default=1500)
    ap.add_argument("--items", type=int, default=12)
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--temp", type=float, default=0.1)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--top", type=int, default=300, help="скільки найпідозріліших рядків у звіт")
    ap.add_argument("--report", type=int, help="лише зібрати звіт з уже наявних даних (число рядків)")
    ap.add_argument("--judge", action="store_true",
                    help="друга фаза: сильніша модель порівнює оригінал із зворотним перекладом")
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--judge-items", type=int, default=10)
    args = ap.parse_args()

    strings = load_strings()
    tr = load_json(args.tr, {})
    data = load_json(OUT, {})
    csv_path, txt_path = WORK / "suspects.csv", WORK / "suspects.txt"

    if args.report:
        report(strings, tr, data, args.report, csv_path, txt_path)
        return

    if args.judge:
        ensure_ollama(args.judge_model)
        judge(args, strings, tr, data)
        report(strings, tr, data, args.top, csv_path, txt_path)
        return

    ensure_ollama(args.model, args.embed_model)
    files = args.file or CFG.get("issue_files") or ORDER
    rows = []
    for s in sorted((x for x in strings if x["file"] in files), key=lambda x: (x["file"], x["order"])):
        t = tr.get(s["key"])
        if t and t.get("uk") and t["status"] in ("ok", "manual") and s["key"] not in data:
            rows.append({**s, "uk": t["uk"]})
    rows = rows[args.start:]
    if args.limit:
        rows = rows[:args.limit]
    print(f"Зворотний переклад: {len(rows)} рядків")

    t0, done = time.time(), 0
    for batch in make_batches(rows, args.chars, args.items):
        user = "ПЕРЕКЛАДИ НАЗАД АНГЛІЙСЬКОЮ:\n\n" + "\n\n".join(
            f"[{i}]\nUK: {json.dumps(r['uk'], ensure_ascii=False)}" for i, r in enumerate(batch, 1))
        try:
            res = call_raw(args, SYSTEM, user, args.temp, SCHEMA)["t"]
            back = {int(o["n"]): o["en"] for o in res if isinstance(o, dict) and "n" in o}
        except REQUEST_ERRORS as e:
            print(f"  ! запит не вдався ({e}), пропускаю партію")
            continue
        pairs = [(r, back.get(i, "")) for i, r in enumerate(batch, 1)]
        pairs = [(r, b) for r, b in pairs if b.strip()]
        if not pairs:
            continue
        try:
            vecs = embed(args.embed_model, [r["en"] for r, _ in pairs] + [b for _, b in pairs])
        except REQUEST_ERRORS as e:
            print(f"  ! embeddings не вдалися ({e})")
            continue
        half = len(pairs)
        for idx, (r, b) in enumerate(pairs):
            data[r["key"]] = {"bt": b, "sim": round(cosine(vecs[idx], vecs[half + idx]), 4)}
        save_json(OUT, data)
        done += len(batch)
        el = time.time() - t0
        print(f"  оброблено {done}/{len(rows)} | {el / 60:.1f} хв, {el / max(done, 1):.1f} с/рядок",
              flush=True)

    report(strings, tr, data, args.top, csv_path, txt_path)


if __name__ == "__main__":
    main()
