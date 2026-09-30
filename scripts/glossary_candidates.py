"""Кандидати в глосарій ДО перекладу: імена, місця, повторювані терміни.

  python scripts/glossary_candidates.py                 # -> work/glossary_candidates.csv (частоти + приклад)
  python scripts/glossary_candidates.py --llm           # + локальна модель пропонує переклад і примітку

Шукає: слова/фрази з великої літери не на початку речення (імена, назви), короткі написи
інтерфейсу, що повторюються в інших файлах. Уже наявні в glossary.json — пропускаються.
Далі людина (або Claude на невеликому списку) переносить потрібне в glossary.json.
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict

from common import CFG, DEFAULT_MODEL, WORK, glossary_terms, load_strings
from llm import REQUEST_ERRORS, ensure_ollama, add_model_args, call_raw

CAP_RE = re.compile(r"\b([A-Z][a-z']+(?:\s+(?:(?:of|the|de|von|van)\s+)?[A-Z][a-z']+)*)")
SENT_SPLIT = re.compile(r"(?<=[.!?…:])\s+|[\n\t]+")
STOP = {"I", "I'm", "I'll", "I've", "I'd", "Mr", "Mrs", "Miss", "Ms", "Lady", "Lord", "Sir", "Madam",
        "OK", "Oh", "Yes", "No", "The", "A", "An"}

SYSTEM = """Ти — перекладач-локалізатор відеоігор з англійської на українську.
Тобі дають терміни з гри (імена, назви місць, ігрові поняття) з прикладом вживання.
Для кожного запропонуй переклад для глосарію і коротку примітку: що це (персонаж і стать, місце, предмет,
механіка), як відмінювати чи лишати латиницею. Імена людей — транслітеруй за звучанням;
говорящі назви — адаптуй. Відповідь — JSON {"t": [{"n": номер, "uk": "переклад", "note": "примітка"}]}."""

SCHEMA = {"type": "object", "properties": {"t": {"type": "array", "items": {
    "type": "object", "properties": {"n": {"type": "integer"}, "uk": {"type": "string"},
                                     "note": {"type": "string"}}, "required": ["n", "uk", "note"]}}},
          "required": ["t"]}


def main():
    ap = argparse.ArgumentParser()
    add_model_args(ap, DEFAULT_MODEL, 0.2)
    ap.add_argument("--min", type=int, default=3, help="мінімальна частота")
    ap.add_argument("--llm", action="store_true", help="попросити локальну модель запропонувати переклади")
    args = ap.parse_args()

    strings = load_strings()
    known = {t["en"].lower() for t in glossary_terms()}
    freq, example, files = Counter(), {}, defaultdict(set)
    for s in strings:
        text = re.sub(r"<[^<>]+>|\{[^{}]*\}", " ", s["en"])
        for sent in SENT_SPLIT.split(text):
            sent = sent.lstrip(" \"“‘'(«—-")
            for m in CAP_RE.finditer(sent):
                w = m.group(1).strip()
                # перше слово речення — з великої літери за правилами, не обов'язково назва
                if m.start() == 0 or w in STOP or w.lower() in known or len(w) < 3:
                    continue
                freq[w] += 1
                files[w].add(s["file"])
                example.setdefault(w, text.strip()[:160])
    # короткі написи інтерфейсу, які згадуються деінде
    ui_file = CFG.get("ui_file")
    if ui_file:
        body = " ".join(s["en"] for s in strings if s["file"] != ui_file)
        for s in strings:
            en = s["en"].strip()
            if (s["file"] == ui_file and 1 <= len(en.split()) <= 3 and en.lower() not in known
                    and len(en) >= 4 and en not in STOP and re.fullmatch(r"[A-Za-z' ]+", en)):
                n = len(re.findall(r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])", body))
                if n >= args.min:
                    freq[en] = max(freq[en], n)
                    files[en].add("ui")
                    example.setdefault(en, "(напис інтерфейсу)")

    rows = [(w, n) for w, n in freq.most_common() if n >= args.min]
    out = [{"en": w, "count": n, "files": ",".join(sorted(files[w])), "example": example[w],
            "uk": "", "note": ""} for w, n in rows]
    print(f"Кандидатів: {len(out)}")

    if args.llm:
        ensure_ollama(args.model)
        for i in range(0, len(out), 20):
            batch = out[i:i + 20]
            user = "\n\n".join(f"[{n}] {json.dumps(r['en'], ensure_ascii=False)}\nприклад: {r['example']}"
                               for n, r in enumerate(batch, 1))
            try:
                res = call_raw(args, SYSTEM, user, args.temp, SCHEMA)["t"]
            except REQUEST_ERRORS as e:
                print(f"  ! запит не вдався ({e})")
                continue
            for x in res:
                if isinstance(x, dict) and 1 <= x.get("n", 0) <= len(batch):
                    batch[x["n"] - 1].update(uk=x.get("uk", ""), note=x.get("note", ""))
            print(f"  {min(i + 20, len(out))}/{len(out)}", flush=True)

    path = WORK / "glossary_candidates.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, ["en", "count", "files", "uk", "note", "example"])
        w.writeheader()
        w.writerows(out)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
