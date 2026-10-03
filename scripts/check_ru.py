"""Перевірка роду й звертання (ти/ви) проти офіційної російської локалізації — без моделі, за хвилини.

Англійська стирає рід і ти/ви, тож зворотний переклад цих помилок не бачить. Російська таблиця гри
(work/ref_Russian.json, python scripts/export_strings.py --ref Russian) граматично близька до нашої:
  1) рід мовця: «я зробив/зробила» — проти статі мовця з даних гри і проти російського рядка;
  2) ти/ви: у російському рядку лише «ты…», а в нашому лише «ви…» (або навпаки).
Розбіжність — сигнал переглянути рядок, не автоматична правка (російська теж буває неправа).

  python scripts/check_ru.py            # -> work/ru_check.csv (формат review.py + колонка ru)
  python scripts/review.py import --csv work/ru_check.csv   # після ручних правок у колонці uk
"""
import argparse
import csv
import re
from collections import Counter

from common import TRANSLATIONS, WORK, load_json, load_strings

REF = WORK / "ref_Russian.json"
OUT = WORK / "ru_check.csv"
COLS = ["key", "file", "status", "en", "uk", "ru", "comment", "errors"]

W = r"[А-Яа-яІіЇїЄєҐґЁё’']"
# «я … дієслово минулого часу» у межах одного речення
RU_I = re.compile(rf"(?<!{W})я(?!{W})[^.!?\n]{{0,25}}?(?<!{W})({W}+?)(ла|лась|л|лся)(?!{W})", re.I)
UK_I = re.compile(rf"(?<!{W})я(?!{W})[^.!?\n]{{0,25}}?(?<!{W})({W}+?)(ла|лася|лась|в|вся)(?!{W})", re.I)
RU_TY = re.compile(r"(?<![а-яё])(ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|твоего|твоей|твоих|твоим)(?![а-яё])", re.I)
RU_VY = re.compile(r"(?<![а-яё])(вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|ваших|вашим)(?![а-яё])", re.I)
UK_TY = re.compile(r"(?<![а-яіїєґ’'])(ти|тебе|тобі|тобою|твій|твоя|твоє|твої|твого|твоєї|твоїх|твоїм)(?![а-яіїєґ’'])", re.I)
UK_VY = re.compile(r"(?<![а-яіїєґ’'])(ви|вас|вам|вами|ваш|ваша|ваше|ваші|вашого|вашої|ваших|вашим)(?![а-яіїєґ’'])", re.I)
# слова, що закінчуються на -в/-л, але не є дієсловами минулого часу
NOT_VERB = {"нів", "ков", "лов", "ров", "мов", "слов", "бов", "лив", "дів", "рів", "зів", "пів", "в", "ла", "л"}


def first_person_gender(text, rx, fem, masc):
    g = set()
    for stem, end in rx.findall(TAG.sub(" ", text)):
        if len(stem) < 2 or (stem + end).lower() in NOT_VERB:
            continue
        g.add("f" if end.lower() in fem else "m" if end.lower() in masc else "")
    g.discard("")
    return g


TAG = re.compile(r"<[^<>]+>")


def address(text, ty, vy):
    t, v = bool(ty.search(text)), bool(vy.search(text))
    return "ти" if t and not v else "ви" if v and not t else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--csv", default=str(OUT))
    args = ap.parse_args()

    ref = load_json(REF)
    if not ref:
        raise SystemExit("Спершу: python scripts/export_strings.py --ref Russian")
    tr = load_json(args.tr, {})
    rows, stats = [], Counter()
    for s in load_strings():
        t = tr.get(s["key"])
        ru = ref.get(s["key"], "")
        if not t or t["status"] not in ("ok", "manual") or not t.get("uk"):
            continue
        uk = t["uk"]
        errs = []
        uk_g = first_person_gender(uk, UK_I, ("ла", "лася", "лась"), ("в", "вся"))
        ru_g = first_person_gender(ru, RU_I, ("ла", "лась"), ("л", "лся")) if ru else set()
        spk = s.get("gender", "")
        if len(uk_g) == 1:
            g = next(iter(uk_g))
            if spk and g != spk:
                errs.append(f"рід мовця: у перекладі «я …» {'жіночий' if g == 'f' else 'чоловічий'}, "
                            f"а мовець — {'жінка' if spk == 'f' else 'чоловік'}")
                stats["рід мовця"] += 1
            elif len(ru_g) == 1 and g not in ru_g:
                errs.append("рід «я …» не збігається з російською версією")
                stats["рід (RU)"] += 1
        if ru:
            a_uk, a_ru = address(uk, UK_TY, UK_VY), address(ru, RU_TY, RU_VY)
            if a_uk and a_ru and a_uk != a_ru:
                errs.append(f"звертання: у нас «{a_uk}», у російській «{'ти' if a_ru == 'ти' else 'ви'}»")
                stats["ти/ви"] += 1
        if errs:
            rows.append({"key": s["key"], "file": s["file"], "status": t["status"], "en": s["en"], "uk": uk,
                         "ru": ru, "comment": (s.get("speaker") or "") + " | " + s.get("comment", ""),
                         "errors": "; ".join(errs)})
    with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"Підозрілих рядків: {len(rows)} {dict(stats)} -> {args.csv}")


if __name__ == "__main__":
    main()
