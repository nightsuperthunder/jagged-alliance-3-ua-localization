"""Застосувати ручні правки (статус manual — модель їх більше не перезапише).

  python scripts/fix.py dialogue:1234 "Новий переклад"
  python scripts/fix.py --json work/_fixes.json        # {"dialogue:1234": "текст", ...}
  python scripts/fix.py --skip ui:77                   # лишити рядок як в оригіналі
  python scripts/fix.py --replace "Кравчино" "Кравчине" [--dry]   # масова заміна підрядка в uk

Кожна правка проходить validate(); з помилками не зберігається (хіба що --force).
"""
import argparse
import sys

from common import (TRANSLATIONS, glossary_terms, load_json, load_strings, save_json,
                    src_hash, validate)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key", nargs="?")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--json", help="файл {ключ: переклад}")
    ap.add_argument("--skip", action="append", default=[], help="ключ, який лишити англійською")
    ap.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="замінити підрядок у всіх перекладах")
    ap.add_argument("--dry", action="store_true", help="лише показати, що зміниться")
    ap.add_argument("--force", action="store_true", help="зберегти навіть з помилками перевірки")
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    args = ap.parse_args()

    en_by_key = {s["key"]: s["en"] for s in load_strings()}
    tr = load_json(args.tr, {})
    allowed = {t["en"] for t in glossary_terms()}

    fixes = {}
    if args.key and args.text is not None:
        fixes[args.key] = args.text
    if args.json:
        fixes.update(load_json(args.json))
    if args.replace:
        old, new = args.replace
        for k, t in tr.items():
            if t.get("uk") and old in t["uk"]:
                fixes[k] = t["uk"].replace(old, new)

    ok = bad = 0
    for k, uk in fixes.items():
        if k not in en_by_key:
            print(f"✗ {k}: немає такого ключа")
            bad += 1
            continue
        en = en_by_key[k]
        errs = validate(en, uk, allowed)
        old = tr.get(k, {}).get("uk")
        print(f"{'✗' if errs else '✓'} {k}\n   було:  {old!r}\n   стало: {uk!r}")
        if errs:
            print(f"   помилки: {errs}")
            bad += 1
            if not args.force:
                continue
        if not args.dry:
            tr[k] = {"src": src_hash(en), "uk": uk, "status": "manual"}
        ok += 1
    for k in args.skip:
        if k in en_by_key and not args.dry:
            tr[k] = {"src": src_hash(en_by_key[k]), "status": "skip"}
            ok += 1
            print(f"✓ {k}: лишається англійською")

    if not args.dry:
        save_json(args.tr, tr)
    print(f"\n{'(dry) ' if args.dry else ''}застосовано {ok}, відхилено {bad}")
    sys.exit(1 if bad and not args.force else 0)


if __name__ == "__main__":
    main()
