"""Повний нічний прогін: переклад -> повтор помилок -> вичитка -> статистика -> CSV для перевірки.
Поки працює, не дає Windows заснути (SetThreadExecutionState, налаштування не змінює).

  python scripts/run_all.py
"""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / "work"
STEPS = [
    ["translate.py"],
    ["translate.py", "--redo-errors"],
    ["proofread.py"],
    ["review.py", "stats"],
    ["review.py", "export", "--errors", "--csv", str(WORK / "review_errors.csv")],
    ["review.py", "export"],
]


def keep_awake():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # CONTINUOUS | SYSTEM_REQUIRED
    except Exception:
        print("(не вдалося заборонити сон)")


def main():
    keep_awake()
    t0 = time.time()
    for step in STEPS:
        print(f"\n######## {' '.join(step)}  [{(time.time() - t0) / 60:.0f} хв]", flush=True)
        rc = subprocess.call([sys.executable, "-u", str(HERE / step[0]), *step[1:]])
        if rc != 0:
            print(f"!!! крок завершився з кодом {rc}", flush=True)
            if step == ["translate.py"]:
                # одна повторна спроба (напр. Ollama впала) — скрипт продовжить з місця
                time.sleep(30)
                subprocess.call([sys.executable, "-u", str(HERE / step[0]), *step[1:]])
    print(f"\n######## ВСЕ ГОТОВО за {(time.time() - t0) / 3600:.1f} год", flush=True)


if __name__ == "__main__":
    main()
