"""Підготовка релізу: версія в Plugin.cs -> збірка з BepInEx -> перевірка приватності -> versioned zip.
Коміт, push і `gh release` робить агент ПІСЛЯ підтвердження користувача (команди друкуються в кінці).

  python scripts/release.py 1.2.0 --bepinex <розпакований BepInEx_win_x64> [--install]
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from common import CFG, ROOT

PLUGIN = ROOT / "mod" / "Plugin" / "Plugin.cs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="X.Y.Z")
    ap.add_argument("--bepinex", required=True, help="розпакований BepInEx_win_x64 (5.4.x для Mono)")
    ap.add_argument("--install", action="store_true", help="ще й встановити в гру (гру закрити)")
    args = ap.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        sys.exit("Версія має бути X.Y.Z")
    if not (Path(args.bepinex) / "BepInEx" / "core").exists():
        sys.exit(f"{args.bepinex} не схоже на розпакований BepInEx (немає BepInEx/core)")

    src = PLUGIN.read_text(encoding="utf-8")
    new, n = re.subn(r'(public const string Version = ")[^"]*(")', rf"\g<1>{args.version}\g<2>", src)
    if n != 1:
        sys.exit("Не знайшов рядок Version у Plugin.cs")
    PLUGIN.write_text(new, encoding="utf-8")
    print(f"Plugin.cs: Version = {args.version}")

    cmd = [sys.executable, str(ROOT / "scripts" / "build_mod.py"), "--with-bepinex", args.bepinex]
    if args.install:
        cmd.append("--install")
    subprocess.check_call(cmd)  # build_mod сам перевіряє архів на особисті дані

    m = CFG.get("mod", {})
    zip_path = ROOT / "mod" / m.get("zip_name", f"{m.get('name', 'GameUA')}.zip")
    versioned = zip_path.with_name(f"{zip_path.stem}-v{args.version}.zip")
    shutil.copy2(zip_path, versioned)
    print(f"\nГотово: {versioned}")
    print("Далі (лише після «так» від користувача):")
    print(f"  git add mod/Plugin/Plugin.cs work/translations.json glossary.json style_guide.md && git commit")
    print(f"  git push")
    print(f"  gh release create v{args.version} \"{versioned}\" --target main "
          f"--title \"Українська локалізація v{args.version}\" --notes-file -")
    print(f"  потім видалити {versioned.name}")


if __name__ == "__main__":
    main()
