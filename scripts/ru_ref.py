"""Підказки й перевірки з офіційної російської локалізації (work/ref_Russian.json) для перекладу і вичитки.

Російський текст моделі НЕ показуємо (щоб не тягнути кальки) — лише висновок із нього:
  - звертання до співрозмовника: «ти» чи «ви» (система ввічливості в RU і UA однакова);
  - перевірка відповіді: звертання не суперечить RU і не змішане, рід «я зробив/зробила» = статі мовця.
"""
from check_ru import RU_TY, RU_VY, UK_I, UK_TY, UK_VY, address, first_person_gender
from common import WORK, load_json

REF = load_json(WORK / "ref_Russian.json", {}) or {}


def address_hint(row):
    """'ти' / 'ви' / '' — як звертаються в цьому рядку в RU-версії."""
    ru = REF.get(row["key"], "")
    return address(ru, RU_TY, RU_VY) if ru else ""


def note(row):
    a = address_hint(row)
    return f"звертання до співрозмовника — на «{a}» (не змішуй «ти» і «ви» в одному рядку)" if a else ""


def grammar_errors(row, uk):
    errs = []
    a = address_hint(row)
    if a and uk:
        u = address(uk, UK_TY, UK_VY)
        if UK_TY.search(uk) and UK_VY.search(uk):
            errs.append(f"змішано «ти» і «ви» — тут звертання на «{a}»")
        elif u and u != a:
            errs.append(f"звертання має бути на «{a}», а не на «{u}»")
    spk = row.get("gender", "")
    g = first_person_gender(uk or "", UK_I, ("ла", "лася", "лась"), ("в", "вся"))
    if spk and len(g) == 1 and spk not in g:
        errs.append("мовець — " + ("жінка: «я зробила», «я готова»" if spk == "f" else "чоловік: «я зробив», «я готовий»"))
    return errs
