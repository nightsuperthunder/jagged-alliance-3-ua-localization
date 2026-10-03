"""Пакети рядків для перекладу/виправлення великою моделлю (Claude) — з усім контекстом, що бачить локальна.

  python scripts/export_packets.py --keys work/_hard_keys.txt --size 60
  -> work/_packets/packet_NN.json  (список рядків; поле "uk" — поточний переклад, якщо є)

Відповідь агента: work/_packets/out_NN.json = {"ключ": "переклад"}; застосувати:
  python scripts/fix.py --json work/_packets/out_NN.json      (перевірка validate(), статус manual)
"""
import argparse
import json
from pathlib import Path

from common import TRANSLATIONS, WORK, glossary_terms, load_json, load_strings
from llm import glossary_for
from ru_ref import note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True)
    ap.add_argument("--size", type=int, default=60)
    ap.add_argument("--before", type=int, default=3)
    ap.add_argument("--after", type=int, default=2)
    args = ap.parse_args()

    only = set(Path(args.keys).read_text(encoding="utf-8").split())
    tr = load_json(TRANSLATIONS, {})
    terms = glossary_terms()
    strings = sorted(load_strings(), key=lambda x: (x["file"], x["order"]))
    by_file = {}
    for s in strings:
        by_file.setdefault(s["file"], []).append(s)
    items = []
    for f, rows in by_file.items():
        for i, s in enumerate(rows):
            if s["key"] not in only or tr.get(s["key"], {}).get("status") == "manual":
                continue
            ctx = lambda r: {"speaker": r.get("speaker", ""), "en": r["en"],
                             "uk": tr.get(r["key"], {}).get("uk", "") if r["key"] not in only else ""}
            items.append({
                "key": s["key"], "file": f, "speaker": s.get("speaker", ""), "gender": s.get("gender", ""),
                "comment": s.get("comment", ""), "address": note(s), "en": s["en"],
                "uk_current": tr.get(s["key"], {}).get("uk", ""),
                "errors": tr.get(s["key"], {}).get("errors", []),
                "glossary": glossary_for(s["en"], terms),
                "before": [ctx(r) for r in rows[max(0, i - args.before):i]],
                "after": [{"speaker": r.get("speaker", ""), "en": r["en"]} for r in rows[i + 1:i + 1 + args.after]],
            })
    out = WORK / "_packets"
    out.mkdir(exist_ok=True)
    for old in out.glob("packet_*.json"):
        old.unlink()
    n = 0
    for n, start in enumerate(range(0, len(items), args.size), 1):
        (out / f"packet_{n:02d}.json").write_text(
            json.dumps(items[start:start + args.size], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} рядків -> {n} пакетів у {out}")


if __name__ == "__main__":
    main()
