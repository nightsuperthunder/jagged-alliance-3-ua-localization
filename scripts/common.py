"""Спільні функції: конфіг проєкту, шляхи, JSON, перевірка перекладу."""
import hashlib
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
STRINGS = WORK / "strings.json"
TRANSLATIONS = WORK / "translations.json"
GLOSSARY = ROOT / "glossary.json"
STYLE = ROOT / "style_guide.md"
PROJECT = ROOT / "project.json"


def load_json(path, default=None):
    if not Path(path).exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


def _strip_readme(d):
    if isinstance(d, dict):
        return {k: _strip_readme(v) for k, v in d.items() if k != "_readme"}
    return d


CFG = _strip_readme(load_json(PROJECT, {}))
FILES = CFG.get("files", {})           # ключ -> {hint, collection?}; порядок = порядок перекладу
ORDER = list(FILES)
COLLECTIONS = {k: v.get("collection", k) for k, v in FILES.items()}  # назва таблиці/файлу в грі, якщо інша
MODELS = CFG.get("models", {})
DEFAULT_MODEL = MODELS.get("translate", "")
JUDGE_MODEL = MODELS.get("judge", "")
EMBED_MODEL = MODELS.get("embed", "embeddinggemma:300m")
GAME_DIR = CFG.get("game_dir", "")
_V = CFG.get("validator", {})


def src_hash(en):
    """Відбиток англійського оригіналу: у репозиторії зберігаємо його замість самого тексту гри."""
    return hashlib.sha1(en.encode("utf-8")).hexdigest()[:12]


def load_strings():
    strings = load_json(STRINGS)
    if not strings:
        sys.exit("Спершу витягніть тексти з гри: python scripts/export_strings.py")
    return strings


def glossary_terms():
    return load_json(GLOSSARY, {"terms": []})["terms"]


def system_prompt():
    text = STYLE.read_text(encoding="utf-8")
    if "[ЗАПОВНИТИ" in text:
        sys.exit("style_guide.md ще містить [ЗАПОВНИТИ …] — допишіть опис гри перед перекладом")
    return text


# ---------- перевірка перекладу ----------

TAG_RE = re.compile(r"<[^<>]+>")
PH_RE = re.compile(r"\{[^{}]*\}")
EXTRA_PH = [re.compile(p) for p in _V.get("extra_placeholder_regex", [])]
PREFIX_RE = re.compile(_V["prefix_regex"]) if _V.get("prefix_regex") else None
STUB_RE = re.compile(_V["stub_regex"]) if _V.get("stub_regex") else None
SKIP_COMMENT_RE = re.compile(_V["skip_comment_regex"]) if _V.get("skip_comment_regex") else None
FORBIDDEN = _V.get("forbidden", {})
CYR_RE = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
LAT_WORD_RE = re.compile(r"\b[A-Za-z]{4,}\b")


def strip_prefix(s):
    return PREFIX_RE.sub("", s) if PREFIX_RE else s


def is_stub(en, comment=""):
    """Рядок, який лишаємо як у грі: заглушка за stub_regex або поле за skip_comment_regex (логіни, e-mail)."""
    return bool((STUB_RE and STUB_RE.fullmatch(en.strip()))
                or (SKIP_COMMENT_RE and comment and SKIP_COMMENT_RE.search(comment)))


def has_placeholders(en):
    return bool(PH_RE.search(en) or any(r.search(en) for r in EXTRA_PH))


_RU_LAT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                   ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r",
                    "s", "t", "u", "f", "h", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))
RU_WORD_RE = re.compile(r"[А-Яа-яЁё]+")
KEEP_CYR_SPEAKERS = set(CFG.get("keep_cyrillic_speakers", []))


def ru_translit(text):
    """Російські вставки (Іван: «Молодец!») -> латиниця, як в офіційній RU-локалізації (Molodets!).
    Теги не чіпає. Рішення користувача: російське в українському тексті — лише транслітом."""
    def word(m):
        w = m.group(0)
        out = "".join(_RU_LAT.get(c.lower(), c) for c in w)
        if w.isupper() and len(w) > 1:
            return out.upper()
        return out[:1].upper() + out[1:] if w[0].isupper() else out
    parts = re.split(r"(<[^<>]+>)", text)
    return "".join(p if i % 2 else RU_WORD_RE.sub(word, p) for i, p in enumerate(parts))


RU_SPAN_RE = re.compile(r"[А-Яа-яЁё]+(?:[\s,\-–—]+[А-Яа-яЁё]+)*")


def ru_mask(text):
    """Російські фрази -> теги <r1>, <r2>… (модель зберігає теги, але перекладає латиницю).
    Повертає (текст із тегами, {тег: транслітерація})."""
    spans = {}

    def sub(m):
        tag = f"<r{len(spans) + 1}>"
        spans[tag] = ru_translit(m.group(0))
        return tag
    parts = re.split(r"(<[^<>]+>)", text)
    return "".join(p if i % 2 else RU_SPAN_RE.sub(sub, p) for i, p in enumerate(parts)), spans


def ru_unmask(text, spans):
    for tag, val in spans.items():
        text = text.replace(tag, val)
    return text


def needs_translit(row):
    return bool(RU_WORD_RE.search(TAG_RE.sub("", row["en"]))) and row.get("speaker") not in KEEP_CYR_SPEAKERS


def autofix(en, uk):
    """Механічні виправлення до перевірки (без моделі): апостроф ' -> ’ між українськими літерами,
    прямі лапки "…" -> «…» поза тегами, якщо їх парна кількість; зайве тире «— » на початку."""
    if not uk:
        return uk
    if re.match(r"\s*[—–-]\s", uk) and not re.match(r"\s*[—–-]", en):
        uk = re.sub(r"^\s*[—–-]\s*", "", uk)  # модель додає тире діалогу, якого немає в оригіналі
    parts = re.split(r"(<[^<>]+>)", uk)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<=[А-Яа-яІіЇїЄєҐґ])'(?=[А-Яа-яІіЇїЄєҐґ])", "’", parts[i])
    text = "".join(parts[::2])
    if text.count('"') and text.count('"') % 2 == 0:
        opened = False
        for i in range(0, len(parts), 2):
            out = []
            for ch in parts[i]:
                if ch == '"':
                    out.append("»" if opened else "«")
                    opened = not opened
                else:
                    out.append(ch)
            parts[i] = "".join(out)
    return "".join(parts)


def validate(en, uk, allowed_latin=()):
    """Повертає список проблем (порожній = все добре). Тексти помилок ідуть і моделі, тому українською."""
    errs = []
    if not uk or not uk.strip():
        return ["порожній переклад"]
    core = TAG_RE.sub("", en)
    while PH_RE.search(core):
        core = PH_RE.sub("", core)
    for r in EXTRA_PH:
        core = r.sub("", core)
    core = core.strip()
    if ((not re.search(r"[A-Za-zА-Яа-яЁё]{2,}", core) and re.search(r"[А-Яа-яІіЇїЄєҐґ]{3,}", uk))
            or (re.fullmatch(r"[IVXLC]+", core) and uk != en)):
        # рядок лише з плейсхолдерів/розділових знаків або римська цифра — має лишитися як є
        errs.append("цей рядок не треба перекладати — залиш точно як в оригіналі")
    if sorted(TAG_RE.findall(en)) != sorted(TAG_RE.findall(uk)):
        errs.append(f"теги не збігаються: {TAG_RE.findall(en)} -> {TAG_RE.findall(uk)}")
    for r in [PH_RE, *EXTRA_PH]:
        if sorted(r.findall(en)) != sorted(r.findall(uk)):
            errs.append(f"плейсхолдери не збігаються: {r.findall(en)} -> {r.findall(uk)}")
    m = PREFIX_RE.match(en) if PREFIX_RE else None
    if m and not uk.startswith(m.group(0)):
        errs.append(f"рядок має починатися з {m.group(0)!r}")
    if en.count("\n") != uk.count("\n"):
        errs.append("кількість переносів рядка \\n не збігається")
    if "\\:" in en:
        # Smart string (SmartFormat): кожна двокрапка поза {} має бути екранована
        if re.search(r"(?<!\\):", strip_prefix(PH_RE.sub("", uk))):
            errs.append("у цьому рядку двокрапку треба писати як \\:")
    if re.search(r"[A-Za-z]", en) and not CYR_RE.search(uk):
        # дозволяємо, якщо рядок — це лише імена з глосарію / теги
        if re.search(r"[A-Za-z]{2,}", core) and len(core) > 3 and core not in allowed_latin:
            errs.append("немає кирилиці — схоже, не перекладено")
    translit = set(LAT_WORD_RE.findall(ru_translit(en))) if RU_WORD_RE.search(en) else set()  # Molodets тощо
    leftover = [w for w in LAT_WORD_RE.findall(TAG_RE.sub("", strip_prefix(uk)))
                if w not in allowed_latin and w not in translit]
    if len(leftover) >= 3:
        errs.append(f"залишилися англійські слова: {leftover[:6]}")
    # модель любить обгортати весь рядок у «…»; пробіл чи крапка після » не мають це ховати
    en_body = strip_prefix(en).lstrip()
    uk_body = re.sub(r"(?<=[»\"”])[.!?…]+$", "", strip_prefix(uk).strip())
    wrapped = (uk_body.startswith("«") and uk_body.endswith("»")) or \
              (uk_body.startswith('"') and uk_body.endswith('"')) or \
              (uk_body.startswith("“") and uk_body.endswith("”"))
    if wrapped and not en_body.startswith(('"', "“", "‘", "'", "«")):
        errs.append("зайві лапки навколо всього рядка — в оригіналі їх немає")
    if uk != uk.rstrip() and en == en.rstrip():
        errs.append("зайвий пробіл у кінці рядка")
    if uk.count("«") != uk.count("»") and en.count("“") == en.count("”"):
        errs.append("непарні лапки «»")
    if re.search(r"«[“\"]|[”\"]»", uk):
        errs.append("подвійні лапки «“…”» — лишіть тільки «…»")
    if re.search(r"[!?…]\.$", uk.strip()) and not re.search(r"[!?…]\.$", en.strip()):
        errs.append("зайва крапка після !, ? або …")
    uk_text = TAG_RE.sub("", uk)
    if re.search(r"[А-Яа-яІіЇїЄєҐґ]'[А-Яа-яІіЇїЄєҐґ]", uk_text):
        errs.append("апостроф у словах пиши як ’ (м’ята), а не '")
    if '"' in uk_text:
        errs.append('лапки пиши як «…», а не "…"')
    if (re.search(r"[A-Za-z0-9)>]$", en.rstrip()) and uk.rstrip().endswith(".")
            and not uk.rstrip().endswith("..")):
        errs.append("зайва крапка в кінці — в оригіналі її немає")
    lead = re.match(r"\s*(<[^<>/]+>)", en)
    if lead and not re.match(r"\s*" + re.escape(lead.group(1)), uk):
        tag = lead.group(1)
        name = re.match(r"<(\w+)", tag)
        paired = name and f"</{name.group(1)}>" in en
        if not paired:
            errs.append(f"тег {tag} стоїть на початку рядка — залиш його на початку")
    for bad, msg in FORBIDDEN.items():
        if bad in uk:
            errs.append(msg)
    if len(uk) > 3 * len(en) + 40:
        errs.append("переклад підозріло довгий")
    return errs
