"""Підготовка релізу: версія в project.json -> збірка мода (з install.bat) -> перевірка приватності -> zip з версією.
Коміт, push і `gh release` робить агент ПІСЛЯ підтвердження користувача (команди друкуються в кінці).

  python scripts/release.py 0.9.0 [--install]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

from common import CFG, ROOT

PROJECT = ROOT / "project.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="X.Y.Z")
    ap.add_argument("--install", action="store_true", help="ще й встановити в %%AppData%% (гру закрити)")
    args = ap.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        sys.exit("Версія має бути X.Y.Z")

    cfg = json.loads(PROJECT.read_text(encoding="utf-8"))
    major, minor, _ = args.version.split(".")
    cfg["mod"]["version"] = f"{major}.{minor}"  # metadata.lua: version_major/minor; revision = кількість рядків
    PROJECT.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"project.json: mod.version = {major}.{minor}")

    cmd = [sys.executable, str(ROOT / "scripts" / "build_mod.py")] + (["--install"] if args.install else [])
    subprocess.check_call(cmd)  # build_mod сам перевіряє архів на особисті дані

    zip_path = ROOT / "mod" / CFG["mod"]["zip_name"]
    versioned = zip_path.with_name(f"{zip_path.stem}-v{args.version}.zip")
    shutil.copy2(zip_path, versioned)
    print(f"\nГотово: {versioned}")
    print("Далі (лише після «так» від користувача):")
    print("  git add project.json work/translations.json glossary.json style_guide.md && git commit && git push")
    print(f"  gh release create v{args.version} \"{versioned}\" --target main "
          f"--title \"Українська локалізація v{args.version}\" --notes-file <нотатки>")
    print(f"  потім видалити {versioned.name}")


if __name__ == "__main__":
    main()
