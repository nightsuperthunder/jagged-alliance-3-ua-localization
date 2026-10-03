"""Пошук перекладів, що «з'їхали» на сусідній рядок: український рядок ближчий за змістом до англійського
сусіда, ніж до власного оригіналу (ембеддинги, локально).

  python scripts/find_shifts.py [--file banters …] [--margin 0] [--low 0.3] [--keys k1 k2 …]
  (калібрування 2026-10-02: правильні рядки gap -0.1…-0.27; з'їхавши — gap +0.03…+0.47 або own < 0.3)
  -> work/shift_candidates.json (список ключів, від найпідозріліших) + короткий друк
"""
import argparse
import json
import math

from common import TRANSLATIONS, WORK, load_json, load_strings, save_json
from llm import embed

MODEL = "embeddinggemma:300m"


def norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def embed_all(texts, batch=64):
    out = []
    for i in range(0, len(texts), batch):
        out += [norm(v) for v in embed(MODEL, texts[i:i + batch])]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append")
    ap.add_argument("--margin", type=float, default=0.0)
    ap.add_argument("--low", type=float, default=0.3, help="схожість з власним оригіналом нижче цього — теж підозра")
    ap.add_argument("--min-len", type=int, default=12, help="коротші EN не перевіряти (вигуки схожі між собою)")
    ap.add_argument("--keys", nargs="*", help="лише показати оцінки цих ключів (калібрування)")
    args = ap.parse_args()
    files = args.file or ["conversations", "banters", "story", "voice"]
    tr = load_json(TRANSLATIONS, {})
    strings = sorted((s for s in load_strings() if s["file"] in files and s["key"] in tr and tr[s["key"]].get("uk")),
                     key=lambda x: (x["file"], x["order"]))
    print(f"Рядків: {len(strings)}", flush=True)
    en = embed_all([s["en"] for s in strings])
    uk = embed_all([tr[s["key"]]["uk"] for s in strings])
    res = []
    for i, s in enumerate(strings):
        if len(s["en"]) < args.min_len:
            continue
        own = cos(uk[i], en[i])
        best, where = -1.0, ""
        for j in (i - 2, i - 1, i + 1, i + 2):
            if 0 <= j < len(strings) and strings[j]["file"] == s["file"] and len(strings[j]["en"]) >= args.min_len:
                c = cos(uk[i], en[j])
                if c > best:
                    best, where = c, strings[j]["key"]
        res.append({"key": s["key"], "own": round(own, 3), "nb": round(best, 3), "gap": round(best - own, 3),
                    "nb_key": where})
    if args.keys:
        for r in res:
            if r["key"] in args.keys:
                print(r)
        return
    flagged = sorted((r for r in res if r["gap"] > args.margin or r["own"] < args.low),
                     key=lambda r: -max(r["gap"], args.low - r["own"]))
    save_json(WORK / "shift_candidates.json", flagged)
    print(f"Підозрілих: {len(flagged)} -> work/shift_candidates.json")


if __name__ == "__main__":
    main()
