"""Пошук смислових помилок у перекладі: три етапи поспіль (години роботи — запускати у фоні).

1) backtranslate.py          — модель перекладу перекладає український текст назад англійською;
2) backtranslate.py --judge  — велика модель порівнює ОРИГІНАЛ і ЗВОРОТНИЙ переклад (англ. vs англ.);
3) context_review.py         — вона ж перевіряє підозрілі рядки з контекстом сусідніх реплік і пропонує fix.

  python scripts/find_issues.py                       # файли з project.json issue_files
  python scripts/find_issues.py --file dialogue --file content

Результат: work/context_review.csv — перегляньте, зайві рядки видаліть, решту застосуйте:
  python scripts/review.py import --csv work/context_review.csv

Сліпа зона: рід, узгодження, займенники — англійська їх стирає, зворотний переклад їх не бачить.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

from common import JUDGE_MODEL
from run_all import keep_awake

HERE = Path(__file__).resolve().parent


def run(script, *extra):
    print(f"\n######## {script} {' '.join(extra)}", flush=True)
    rc = subprocess.call([sys.executable, "-u", str(HERE / script), *extra])
    if rc != 0:
        print(f"!!! крок завершився з кодом {rc}", flush=True)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=None)
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--top", type=int, default=1500, help="скільки підозрілих рядків віддати рецензенту")
    args = ap.parse_args()
    files = []
    for f in (args.file or []):
        files += ["--file", f]

    keep_awake()
    t0 = time.time()
    run("backtranslate.py", *files)
    run("backtranslate.py", "--judge", "--judge-model", args.judge_model, "--no-think",
        "--top", str(args.top), *files)
    run("context_review.py", "--only-keys", str(HERE.parent / "work" / "suspects.txt"),
        "--model", args.judge_model, "--no-think", "--restart", *files)
    print(f"\n######## ГОТОВО за {(time.time() - t0) / 3600:.1f} год", flush=True)
    print("Перегляньте work/context_review.csv, потім:")
    print("  python scripts/review.py import --csv work/context_review.csv")


if __name__ == "__main__":
    main()
