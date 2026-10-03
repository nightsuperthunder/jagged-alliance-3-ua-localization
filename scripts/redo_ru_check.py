"""Повторно перекласти рядки, які check_ru.py позначив (ти/ви, рід мовця), з підказкою звертання з RU.

  python scripts/redo_ru_check.py               # усі позначені рядки з work/ru_check.csv
  python scripts/redo_ru_check.py --only address|gender

Ручні правки (status manual) не чіпає. Після перекладу знову запускає check_ru.py — що лишилось, видно в
work/ru_check.csv (там і справжні винятки, де RU сама неправа: їх можна лишити як є).
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

from common import TRANSLATIONS, WORK, load_json

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(WORK / "ru_check.csv"))
    ap.add_argument("--only", choices=["address", "gender"])
    args = ap.parse_args()

    tr = load_json(TRANSLATIONS, {})
    keys = []
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            kind = "address" if "звертання" in row["errors"] else "gender"
            if args.only and kind != args.only:
                continue
            if tr.get(row["key"], {}).get("status") == "manual":
                continue
            keys.append(row["key"])
    path = WORK / "_ru_redo_keys.txt"
    path.write_text("\n".join(keys), encoding="utf-8")
    print(f"Повторний переклад: {len(keys)} рядків", flush=True)
    py = [sys.executable, "-u"]
    subprocess.check_call(py + [str(HERE / "translate.py"), "--keys", str(path), "--redo-all"])
    subprocess.check_call(py + [str(HERE / "check_ru.py")])


if __name__ == "__main__":
    main()
