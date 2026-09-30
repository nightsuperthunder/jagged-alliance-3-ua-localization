"""Перевірка і ручні правки через таблицю (Excel / Google Sheets / LibreOffice).

  python scripts/review.py export              -> work/review.csv (усі рядки)
  python scripts/review.py export --errors     -> лише проблемні
  python scripts/review.py import [--csv F]    <- забирає зміни з колонки uk (статус manual)
  python scripts/review.py stats               -> статистика і перевірка всього

Можна вказати інший файл перекладів: --tr work/test_a.json
"""
import argparse
import csv

from common import (TRANSLATIONS, WORK, glossary_terms, has_placeholders, load_json,
                    load_strings, save_json, src_hash, validate)

COLS = ["key", "file", "status", "en", "uk", "comment", "errors"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "import", "stats"])
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--csv", default=str(WORK / "review.csv"))
    ap.add_argument("--errors", action="store_true")
    args = ap.parse_args()

    strings = load_strings()
    tr = load_json(args.tr, {})
    allowed = {t["en"] for t in glossary_terms()}

    if args.cmd == "export":
        n = 0
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, COLS)
            w.writeheader()
            for s in strings:
                t = tr.get(s["key"])
                if not t:
                    continue
                uk = t.get("uk", s["en"])  # skip-рядки лишаються як в оригіналі
                errs = validate(s["en"], uk, allowed) if t["status"] != "skip" else []
                if t.get("src") != src_hash(s["en"]):
                    errs.append("оригінал у грі змінився — перевір переклад")
                if has_placeholders(s["en"]):
                    errs.append("ПЕРЕВІР: чи узгоджується підставлене слово {n} (див. style_guide.md)")
                if args.errors and not errs:
                    continue
                w.writerow({"key": s["key"], "file": s["file"], "status": t["status"], "en": s["en"],
                            "uk": uk, "comment": s.get("comment", ""), "errors": "; ".join(errs)})
                n += 1
        print(f"{n} рядків -> {args.csv}")

    elif args.cmd == "import":
        changed = bad = 0
        with open(args.csv, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                t = tr.get(row["key"])
                if not t or row["uk"] == t.get("uk", row["en"]):
                    continue
                t.update(uk=row["uk"], src=src_hash(row["en"]), status="manual")
                t.pop("errors", None)
                changed += 1
                errs = validate(row["en"], row["uk"], allowed)
                if errs:
                    bad += 1
                    print(f"  ! {row['key']}: {errs}")
        save_json(args.tr, tr)
        print(f"Оновлено {changed} рядків (позначено як manual). З попередженнями: {bad}")

    else:
        stats, bad = {}, 0
        for s in strings:
            t = tr.get(s["key"])
            st = t["status"] if t else "немає"
            stats[st] = stats.get(st, 0) + 1
            if t and t["status"] != "skip" and validate(s["en"], t.get("uk", ""), allowed):
                bad += 1
        print(f"Статуси: {stats}\nРядків, що не проходять перевірку: {bad}")


if __name__ == "__main__":
    main()
