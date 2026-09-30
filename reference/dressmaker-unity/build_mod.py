"""Збирає мод: dll + translations/<locale>.json -> mod/dist, архів mod/<zip_name>,
перевіряє архів на особисті дані і (за бажанням) встановлює в гру.

  python scripts/build_mod.py                   # зібрати
  python scripts/build_mod.py --install         # зібрати і скопіювати в гру (гру закрити! BepInEx має бути встановлений)
  python scripts/build_mod.py --with-bepinex <розпакований BepInEx_win_x64>   # архів для спільноти

Формат translations/<locale>.json: {"<Collection>": {"<id>": "переклад"}} — відсутні рядки гра покаже англійською.
"""
import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from common import CFG, COLLECTIONS, GAME_DIR, ROOT, TRANSLATIONS, load_json, load_strings, src_hash

MOD = ROOT / "mod"
PROJ = MOD / "Plugin"
DIST = MOD / "dist"
M = CFG.get("mod", {})
NAME = M.get("name", "GameUA")
LOCALE = M.get("locale_code", "uk")


def export_json(path):
    tr = load_json(TRANSLATIONS, {})
    out = {c: {} for c in COLLECTIONS.values()}
    n = stale = 0
    for s in load_strings():
        t = tr.get(s["key"])
        if t and t["status"] in ("ok", "manual"):
            out[COLLECTIONS[s["file"]]][str(s["id"])] = t["uk"]
            n += 1
            stale += t.get("src") != src_hash(s["en"])
    if stale:
        print(f"Увага: {stale} перекладів зроблено для старої версії оригіналу (review.py export --errors)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return n


def privacy_check(zip_path):
    """Шукає в архіві ім'я користувача Windows, пошту тощо (шляхи потрапляють у dll/pdb)."""
    needles = {getpass.getuser().lower(), os.environ.get("USERNAME", "").lower(),
               *(p.lower() for p in CFG.get("privacy_patterns", []))}
    needles = {n for n in needles if len(n) >= 4}  # коротке ім'я дасть випадкові збіги в бінарниках
    found = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            data = z.read(info).lower()
            for n in needles:
                if n.encode("utf-8") in data or n.encode("utf-16-le") in data or n in info.filename.lower():
                    found.append(f"{info.filename}: «{n}»")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=GAME_DIR)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--with-bepinex", help="шлях до розпакованого BepInEx_win_x64 (для архіву спільноти)")
    args = ap.parse_args()

    subprocess.check_call(["dotnet", "build", "-c", "Release", f"-p:GameDir={args.game}",
                           f"-p:GameData={CFG.get('game_data', '')}", f"-p:ModName={NAME}",
                           "-v", "q", "-nologo"], cwd=PROJ)
    if DIST.exists():
        shutil.rmtree(DIST)
    plug = DIST / "BepInEx" / "plugins" / NAME
    plug.mkdir(parents=True)
    shutil.copy2(PROJ / "bin" / "Release" / f"{NAME}.dll", plug)
    n = export_json(plug / "translations" / f"{LOCALE}.json")
    (plug / "fonts").mkdir()
    if (MOD / "fonts").exists():
        for f in (MOD / "fonts").iterdir():
            shutil.copy2(f, plug / "fonts")
    if args.with_bepinex:
        shutil.copytree(args.with_bepinex, DIST, dirs_exist_ok=True)
    if (MOD / "README_UA.txt").exists():
        shutil.copy2(MOD / "README_UA.txt", DIST)
    print(f"Перекладених рядків у моді: {n}")

    zip_path = MOD / M.get("zip_name", f"{NAME}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in DIST.rglob("*"):
            z.write(f, f.relative_to(DIST))
    print(f"Архів: {zip_path}")
    leaks = privacy_check(zip_path)
    if leaks:
        print("!!! В АРХІВІ ОСОБИСТІ ДАНІ — не публікуйте:\n  " + "\n  ".join(leaks))
        sys.exit(2)
    print("Перевірка на особисті дані: чисто")

    if args.install:
        game = Path(args.game)
        if not (game / "BepInEx" / "core").exists():
            sys.exit("У грі не встановлено BepInEx")
        shutil.copytree(DIST / "BepInEx", game / "BepInEx", dirs_exist_ok=True)
        print(f"Встановлено в {game}")


if __name__ == "__main__":
    main()
