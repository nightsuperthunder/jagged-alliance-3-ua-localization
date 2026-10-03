"""Повернути рядки з помилками до версії зі знімка (work/snapshots/*.json), якщо там вони були `ok`.

  python scripts/restore_snapshot.py work/snapshots/03_after_proofread.json --keys work/_ru_redo_keys.txt

Відновлюються лише рядки, які зараз `error`, а в знімку `ok` (англійська в грі гірша за трохи неточний переклад).
Відновлені позначаються model="restored:<знімок>" і лишаються `ok`; ручні правки не чіпає.
"""
import argparse
from pathlib import Path

from common import TRANSLATIONS, load_json, load_strings, save_json, src_hash, validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--keys", help="лише ці ключі (файл, по одному в рядку)")
    args = ap.parse_args()

    snap = load_json(args.snapshot)
    only = set(Path(args.keys).read_text(encoding="utf-8").split()) if args.keys else None
    tr = load_json(TRANSLATIONS)
    en = {s["key"]: s["en"] for s in load_strings()}
    n = 0
    for k, t in tr.items():
        old = snap.get(k)
        if (only is not None and k not in only) or t["status"] != "error" or not old or old.get("status") != "ok":
            continue
        if validate(en[k], old["uk"]):
            continue  # стара версія не проходить поточні правила (теги тощо)
        tr[k] = {"src": src_hash(en[k]), "uk": old["uk"], "status": "ok",
                 "model": "restored:" + Path(args.snapshot).stem, "errors_after_redo": t.get("errors", [])}
        n += 1
    save_json(TRANSLATIONS, tr)
    print(f"Відновлено {n} рядків зі знімка {args.snapshot}")


if __name__ == "__main__":
    main()
