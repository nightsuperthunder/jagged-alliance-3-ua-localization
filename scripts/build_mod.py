"""Збирає мод для вбудованого менеджера модів JA3: mod/dist/<тека>/{metadata.lua, items.lua, <csv>} + zip.

  python scripts/build_mod.py              # зібрати
  python scripts/build_mod.py --install    # і скопіювати в %AppData%/Jagged Alliance 3/Mods (гру перезапустити)
  python scripts/build_mod.py --all        # включити й рядки зі статусом error (лише для перевірки в грі)

CSV має колонки гри (ID, Text, Translation…); гра читає 1-шу (ID), 2-гу (Text) і 3-тю (Translation).
Text лишаємо порожнім — англійський оригінал у мод не потрапляє. Рядків без перекладу в CSV немає:
для них гра бере текст зі своєї таблиці. Також додаються заміни шрифтів (див. font_overrides()).
"""
import argparse
import csv
import getpass
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

from common import CFG, GAME_DIR, ROOT, TRANSLATIONS, load_json, load_strings, src_hash
from export_strings import CONTEXT, ID, TEXT, read_table

MOD = ROOT / "mod"
DIST = MOD / "dist"
M = CFG["mod"]
HEADER = ["ID", "Text", "Translation", "Old Text", "Old Translation", "Status", "Gender"]


def font_overrides(game):
    """Рядки TextStyle — це назви шрифтів. У Source Code Pro Italic немає кирилиці, тож беремо ті самі
    заміни, що й офіційна локалізація з кирилицею (Italic -> Regular)."""
    lang = M.get("font_overrides_from")
    if not lang:
        return {}
    en = {r[ID]: r for r in read_table(game)}
    out = {}
    for r in read_table(game, lang):
        e = en.get(r[ID])
        if e and e[CONTEXT].startswith("TextStyle") and r[2].strip() and r[2] != e[TEXT]:
            out[r[ID]] = r[2]
    return out


def write_csv(path, game, include_errors, translations=TRANSLATIONS):
    tr = load_json(translations, {})
    rows, stale = {}, 0
    ok = ("ok", "manual", "error") if include_errors else ("ok", "manual")
    for s in load_strings():
        t = tr.get(s["key"])
        if t and t["status"] in ok and t.get("uk"):
            rows[s["id"]] = t["uk"]
            stale += t.get("src") != src_hash(s["en"])
    if stale:
        print(f"Увага: {stale} перекладів зроблено для старої версії оригіналу (review.py export --errors)")
    fonts = font_overrides(game)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)  # перший рядок гра пропускає
        for i, uk in {**rows, **fonts}.items():
            w.writerow([i, "", uk, "", "", "", ""])
    return len(rows), len(fonts)


def render(name, dest, n):
    major, minor = (M.get("version", "0.1").split(".") + ["0"])[:2]
    text = (MOD / name).read_text(encoding="utf-8")
    desc = M.get("description", "Фанатський український переклад тексту гри. Мова гри має бути English.")
    for k, v in {"TITLE": M["title"], "DESCRIPTION": desc.replace('"', '\\"').replace("\n", "\\n"),
                 "ID": M["id"], "CSV": M["csv_name"], "LANGUAGE": M["language"],
                 "VERSION_MAJOR": major, "VERSION_MINOR": minor, "REVISION": str(n),
                 "SAVED": str(int(time.time()))}.items():
        text = text.replace(f"@{k}@", v)
    (dest / name).write_text(text, encoding="utf-8", newline="\n")


def privacy_check(zip_path):
    """Шукає в архіві ім'я користувача Windows, пошту, локальні шляхи."""
    needles = {getpass.getuser().lower(), os.environ.get("USERNAME", "").lower(),
               *(p.lower() for p in CFG.get("privacy_patterns", []))}
    needles = {n for n in needles if len(n) >= 4}
    found = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            data = z.read(info).lower()
            for n in needles:
                if n.encode("utf-8") in data or n in info.filename.lower():
                    found.append(f"{info.filename}: «{n}»")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=GAME_DIR)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--translations", default=str(TRANSLATIONS), help="інший файл перекладів (проба)")
    ap.add_argument("--all", action="store_true", help="включити рядки з помилками валідації")
    args = ap.parse_args()

    if DIST.exists():
        shutil.rmtree(DIST)
    dest = DIST / M["folder"]
    dest.mkdir(parents=True)
    n, nf = write_csv(dest / M["csv_name"], args.game, args.all, args.translations)
    render("metadata.lua", dest, n)
    render("items.lua", dest, n)
    shutil.copytree(MOD / "Code", dest / "Code")
    print(f"Перекладених рядків у моді: {n} (+ замін шрифтів: {nf})")

    zip_path = MOD / M["zip_name"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dest.rglob("*")):
            z.write(f, f.relative_to(DIST))
        if (MOD / "README_UA.txt").exists():
            z.write(MOD / "README_UA.txt", "README_UA.txt")
    print(f"Архів: {zip_path}")
    leaks = privacy_check(zip_path)
    if leaks:
        print("!!! В АРХІВІ ОСОБИСТІ ДАНІ — не публікуйте:\n  " + "\n  ".join(leaks))
        sys.exit(2)
    print("Перевірка на особисті дані: чисто")

    if args.install:
        mods = Path(os.environ["APPDATA"]) / "Jagged Alliance 3" / "Mods"
        target = mods / M["folder"]
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(dest, target)
        print(f"Встановлено в {target}. Увімкніть мод у Mod Manager, мова гри — English.")


if __name__ == "__main__":
    main()
