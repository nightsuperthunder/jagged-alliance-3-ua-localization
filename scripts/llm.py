"""Запити до локальної моделі (Ollama) і спільні шматки промптів."""
import json
import re
import sys
import urllib.error
import urllib.request

from common import CFG, FILES

OLLAMA = "http://localhost:11434/api/chat"
EMBED_URL = "http://localhost:11434/api/embed"
# помилки, після яких партію варто повторити або пропустити, а не падати
REQUEST_ERRORS = (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError, ConnectionError)

# відповідь перекладача: {"t": [{"n": 1, "uk": "..."}]}
SCHEMA = {
    "type": "object",
    "properties": {
        "t": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "uk": {"type": "string"}},
                "required": ["n", "uk"],
            },
        }
    },
    "required": ["t"],
}


def add_model_args(ap, model, temp, ctx=16384):
    ap.add_argument("--model", default=model)
    ap.add_argument("--ctx", type=int, default=ctx, help="num_ctx для Ollama")
    ap.add_argument("--temp", type=float, default=temp)
    ap.add_argument("--no-think", action="store_true", help="вимкнути режим міркувань (Gemma 4, Qwen)")


def ensure_ollama(*models):
    """Перевірка на старті: сервер доступний і моделі встановлені (інакше всі рядки стали б error)."""
    try:
        with urllib.request.urlopen(OLLAMA.replace("/api/chat", "/api/tags"), timeout=10) as r:
            have = {m["name"] for m in json.loads(r.read().decode("utf-8"))["models"]}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        sys.exit(f"Ollama не відповідає ({e}). Запустіть її (ollama serve або програма в треї) і повторіть.")
    missing = [m for m in models if m and m not in have and f"{m}:latest" not in have]
    if missing:
        sys.exit(f"В Ollama немає моделей: {missing}. Встановлені: {sorted(have)}")


def call_raw(args, system, user, temperature, schema):
    """Запит до Ollama зі структурованою відповіддю (JSON schema); повертає розібраний JSON."""
    body = {
        "model": args.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": schema,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "top_p": 0.9, "num_ctx": args.ctx, "num_predict": 8192},
    }
    if getattr(args, "no_think", False):
        body["think"] = False
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.loads(r.read().decode("utf-8"))
    return json.loads(data["message"]["content"])


def call_translate(args, system, user, temperature):
    """Переклад/редагування: повертає {номер рядка: текст}."""
    out = call_raw(args, system, user, temperature, SCHEMA)["t"]
    return {int(o["n"]): o["uk"] for o in out if isinstance(o, dict) and "n" in o}


def embed(model, texts):
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(EMBED_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))["embeddings"]


def make_batches(rows, max_chars, max_items):
    batch, size = [], 0
    for r in rows:
        if batch and (size + len(r["en"]) > max_chars or len(batch) >= max_items):
            yield batch
            batch, size = [], 0
        batch.append(r)
        size += len(r["en"])
    if batch:
        yield batch


def file_hint(fk):
    return FILES.get(fk, {}).get("hint", "")


def glossary_for(text, terms):
    """Рядки глосарію, чиї англійські терміни трапляються в тексті (цілим словом)."""
    low = text.lower()
    hits = []
    for t in terms:
        if re.search(r"(?<![a-z])" + re.escape(t["en"].lower()) + r"(?![a-z])", low):
            line = f"- {t['en']} → {t['uk']}"
            if t.get("note"):
                line += f"  ({t['note']})"
            hits.append(line)
    return hits


def ui_terms(strings, tr):
    """Короткі вже перекладені написи інтерфейсу (кнопки, вкладки) — автоглосарій для решти файлів."""
    ui_file = CFG.get("ui_file")
    out = []
    for s in strings:
        t = tr.get(s["key"])
        en = s["en"].strip()
        if (s["file"] != ui_file or not t or t["status"] not in ("ok", "manual")
                or len(en.split()) > 4 or not re.search(r"[A-Za-z]", en)
                or re.search(r"[{}<>]", en) or en.endswith((".", "!", "?"))):
            continue
        out.append({"en": en, "uk": t["uk"].strip()})
    return out


def item_head(i, row, extra=""):
    """Заголовок рядка в промпті: номер, мовець, коментар розробників."""
    notes = []
    if row.get("speaker"):
        notes.append(f"мовець: {row['speaker']}")
    if row.get("comment"):
        notes.append(f"коментар розробників: {row['comment']}")
    if extra:
        notes.append(f"примітка: {extra}")
    return f"[{i}]" + (f" ({'; '.join(notes)})" if notes else "")
