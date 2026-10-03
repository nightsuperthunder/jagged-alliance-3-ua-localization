"""Витягує тексти Jagged Alliance 3 з Local/English.hpk у work/strings.json (лише локально, не комітити).

  python scripts/export_strings.py [--game <тека гри>]

Таблиця гри — CurrentLanguage/Game.csv (20 колонок, рядки відсортовані за Location = файл(рядок) у
вихідному коді, тож порядок у таблиці = порядок реплік у розмові). Повторний запуск дає той самий файл.
"""
import argparse
import csv
import io
import re
from collections import Counter
from pathlib import Path

from common import GAME_DIR, STRINGS, save_json
from hpk import Hpk

TABLE = "CurrentLanguage/Game.csv"
# колонки Game.csv
ID, TEXT, LOCATION, CONTEXT, SECTION, KEYWORD, ACTOR = 0, 1, 10, 11, 12, 13, 14

# перше слово Context (клас пресету) -> наш файл; решта ділиться за Location
BY_CLASS = {
    "VoiceResponse": "voice",
    "Conversation": "conversations",
    "BanterDef": "banters",
    "QuestsDef": "story", "Email": "story", "PopupNotification": "story", "HistoryOccurence": "story",
    "GuardpostObjective": "story", "ConflictDescription": "story", "TutorialHint": "story",
    "LoadingScreenHint": "story", "ImpQuestionDef": "story",
    "UnitDataCompositeDef": "units", "EliteEnemyName": "units", "SquadName": "units", "EnemySquads": "units",
    "EmploymentHistoryLine": "units",
    "InventoryItemCompositeDef": "items", "WeaponComponent": "items", "WeaponComponentEffect": "items",
    "WeaponComponentSharedClass": "items", "WeaponPropertyDef": "items", "WeaponType": "items",
    "BobbyRayShopSubCategory": "items", "BobbyRayShopCategory": "items",
}
EDITOR_LOC = ("CommonLua/Ged", "CommonLua/Editor", "CommonLua/MapGen", "Zulu/Lua/Editor", "Zulu/Lua/Ged")


def read_table(game, lang="English"):
    data = Hpk(Path(game) / "Local" / f"{lang}.hpk").read(TABLE)
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))[1:]


def speaker_genders(game):
    """Actor -> 'f'/'m': з UnitDataCompositeDef (Packs/Data.hpk), інакше за назвою (NPC_VillagerFemale_01)."""
    pack = Hpk(Path(game) / "Packs" / "Data.hpk")
    out = {}
    for name in pack.files:
        if name.startswith("UnitDataCompositeDef/"):
            m = re.search(r"'gender', \"(\w+)\"", pack.read(name).decode("utf-8", "replace"))
            if m:
                out[name.split("/")[1][:-4]] = "f" if m.group(1) == "Female" else "m"
    return out


def gender_of(actor, units):
    if actor in units:
        return units[actor]
    if re.search(r"(?i)female|woman|girl|lady", actor):
        return "f"
    if re.search(r"(?i)male|man\b|boy|guy", actor):
        return "m"
    return ""


def classify(row):
    cls = row[CONTEXT].split(" ", 1)[0]
    loc = row[LOCATION].replace("Trunk\\", "").replace("\\", "/")
    if cls == "TextStyle":
        return None  # назви шрифтів («Source Code Pro Bold, 16»); потрібні заміни робить build_mod.py
    if cls in BY_CLASS:
        return BY_CLASS[cls]
    if loc.startswith(EDITOR_LOC):
        return "editor"
    if loc.startswith(("Zulu/Data/", "ZuluAssets/")) or cls.endswith(("CompositeDef", "Def", "Preset")):
        return "terms"
    return "ui"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=GAME_DIR)
    ap.add_argument("--ref", metavar="LANG", help="також зберегти офіційний переклад (напр. Russian, Polish) "
                    "у work/ref_<LANG>.json {key: текст} — лише локально, для перевірок статі та ти/ви")
    args = ap.parse_args()

    out, n = [], Counter()
    units = speaker_genders(args.game)
    for order, row in enumerate(read_table(args.game)):
        fk = classify(row)
        if fk is None or not row[TEXT].strip():
            continue
        comment = re.sub(r"\s+", " ", row[CONTEXT]).strip()
        if row[KEYWORD]:
            comment += f" | відповідь на репліку гравця: «{row[KEYWORD]}»"
        elif row[SECTION] and fk == "banters":
            comment += f" | сценка: {row[SECTION]}"
        out.append({"key": f"{fk}:{row[ID]}", "file": fk, "id": row[ID], "order": order,
                    "en": row[TEXT], "comment": comment, "speaker": row[ACTOR],
                    "gender": gender_of(row[ACTOR], units) if row[ACTOR] else ""})
        n[fk] += 1
    save_json(STRINGS, out)
    if args.ref:
        ref = {r[ID]: r[2] for r in read_table(args.game, args.ref)}
        path = STRINGS.with_name(f"ref_{args.ref}.json")
        save_json(path, {x["key"]: ref[x["id"]] for x in out if ref.get(x["id"], "").strip()})
        print(f"еталон {args.ref} -> {path}")
    print(f"{len(out)} рядків -> {STRINGS}")
    for fk, c in n.most_common():
        print(f"  {fk:14} {c}")


if __name__ == "__main__":
    main()
