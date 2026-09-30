"""Витягує англійські рядки гри в work/strings.json (локально, у Git не потрапляє).

  python scripts/export_strings.py                     # адаптер з project.json -> engine
  python scripts/export_strings.py --game "D:\\...\\Game"

Кожен адаптер повертає список рядків у СТАНДАРТНОМУ форматі (на ньому працюють усі інші скрипти):
  {"key": "<file>:<id>", "file": <ключ з project.json files>, "id": <id в таблиці гри>,
   "order": <порядок у файлі>, "en": <текст>, "comment": <коментар розробників або "">,
   "speaker": <хто говорить, якщо гра це зберігає; поле необов'язкове>}
id — те, за чим мод потім знайде рядок у грі. key має бути стабільним між версіями гри.

Нова гра на іншому рушії / системі локалізації — допишіть функцію adapter_<engine>(cfg, game_dir)
і зареєструйте її в ADAPTERS (див. docs/ENGINES.md).
"""
import argparse
import sys
from pathlib import Path

from common import CFG, COLLECTIONS, GAME_DIR, STRINGS, save_json


# ---------- Unity Localization (StringTable у бандлі Addressables) ----------

def rows_from_string_table(file_key, mb):
    """mb — StringTable (typetree з UnityPy або YAML-експорт — структура однакова)."""
    comments = {}
    for ref in (mb.get("references") or {}).get("RefIds") or []:
        text = (ref.get("data") or {}).get("m_CommentText")
        if text:
            comments[ref["rid"]] = text
    out = []
    for i, row in enumerate(mb["m_TableData"]):
        en = row.get("m_Localized")
        en = "" if en is None else str(en)
        rids = [it["rid"] for it in (row.get("m_Metadata") or {}).get("m_Items") or []]
        out.append({
            "key": f"{file_key}:{row['m_Id']}",
            "file": file_key,
            "id": row["m_Id"],
            "order": i,
            "en": en,
            "comment": " | ".join(comments[r] for r in rids if r in comments),
        })
    return out


def adapter_unity_localization(cfg, game_dir):
    try:
        import UnityPy
    except ImportError:
        sys.exit("Потрібен UnityPy: pip install UnityPy")
    src = cfg["source"]
    bundle = Path(game_dir) / src["bundle"]
    if not bundle.exists():
        sys.exit(f"Не знайдено {bundle}\nВкажіть папку гри: --game \"...\"")
    env = UnityPy.load(str(bundle))
    tables = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        t = obj.read_typetree()
        if "m_TableData" in t:
            tables[t["m_Name"]] = t
    print("Таблиці в бандлі:", ", ".join(sorted(tables)))
    out = []
    for key, coll in COLLECTIONS.items():
        name = f"{coll}_{src.get('locale', 'en')}"
        if name not in tables:
            sys.exit(f"У бандлі немає таблиці {name} — виправте files у project.json")
        rows = rows_from_string_table(key, tables[name])
        print(f"{name}: {len(rows)} рядків")
        out += rows
    return out


ADAPTERS = {
    "unity-localization": adapter_unity_localization,
    # "i2-localization": adapter_i2,        # див. docs/ENGINES.md
    # "unreal-locres": adapter_locres,
    # "csv": adapter_csv,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=GAME_DIR, help="папка гри")
    args = ap.parse_args()
    engine = CFG.get("engine")
    if engine not in ADAPTERS:
        sys.exit(f"Немає адаптера для engine={engine!r}. Є: {', '.join(ADAPTERS)}")
    out = ADAPTERS[engine](CFG, args.game)
    keys = [r["key"] for r in out]
    if len(keys) != len(set(keys)):
        sys.exit("Ключі рядків не унікальні — виправте адаптер")
    save_json(STRINGS, out)
    print(f"Разом {len(out)} -> {STRINGS}")


if __name__ == "__main__":
    main()
