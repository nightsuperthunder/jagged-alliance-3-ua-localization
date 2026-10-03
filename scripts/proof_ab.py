"""Суддя «до/після вичитки»: велика модель (Claude) вибирає кращий варіант для змістовних правок proofread.py.

  python scripts/proof_ab.py export [--size 150]   -> work/_proof_ab/packet_NN.json (+ _map.json, прихований від судді)
  (агенти пишуть work/_proof_ab/out_NN.json = {"ключ": 1 | 2 | "власний варіант"})
  python scripts/proof_ab.py local [--model M]      -> локальна модель судить усе -> work/_proof_ab/local.json (дозапуск)
  python scripts/proof_ab.py escalate [--size 150]  -> «обидва погані» / різні імена -> sonnet_NN.json для Claude
  python scripts/proof_ab.py apply [--dry]          -> відкат/власні варіанти через fix.py (статус manual)
                                                       (відповіді Claude важливіші за локальні; ескальовані без
                                                        відповіді Claude не чіпаються)

Варіанти 1/2 перемішані випадково, щоб суддя не віддавав перевагу «після». Типографічні правки
(різниця лише в розділових знаках/пробілах) не експортуються — їх лишаємо.
"""
import argparse
import json
import random
import re
import subprocess
import time
import urllib.request
import sys
from pathlib import Path

from common import TRANSLATIONS, WORK, load_json, load_strings, save_json

OUT = WORK / "_proof_ab"
CTX_FILES = {"conversations", "banters"}


def norm(s):
    return re.sub(r"[\W_]+", "", s.lower().replace("’", "'"))


def export(args):
    tr = load_json(TRANSLATIONS, {})
    strings = sorted(load_strings(), key=lambda x: (x["file"], x["order"]))
    by_file = {}
    for s in strings:
        by_file.setdefault(s["file"], []).append(s)
    rnd = random.Random(42)
    items, mapping = [], {}
    for f, rows in by_file.items():
        for i, s in enumerate(rows):
            t = tr.get(s["key"])
            if not t or t["status"] != "ok" or not t.get("uk_before_proof"):
                continue
            before, after = t["uk_before_proof"], t["uk"]
            if before == after or norm(before) == norm(after):
                continue
            flip = rnd.random() < 0.5
            mapping[s["key"]] = "after" if flip else "before"  # що стоїть під номером 1
            it = {"key": s["key"], "speaker": s.get("speaker", ""), "en": s["en"],
                  "1": after if flip else before, "2": before if flip else after}
            if s.get("comment"):
                it["comment"] = s["comment"][:100]
            if f in CTX_FILES:
                ctx = lambda r: (r.get("speaker") or "?") + ": " + r["en"][:120]
                it["prev"] = [ctx(r) for r in rows[max(0, i - 1):i]]
            items.append(it)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("packet_*.json"):
        old.unlink()
    n = 0
    for n, start in enumerate(range(0, len(items), args.size), 1):
        with open(OUT / f"packet_{n:02d}.json", "w", encoding="utf-8") as fh:
            fh.write("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False)
                                         for x in items[start:start + args.size]) + "\n]\n")
    save_json(OUT / "_map.json", mapping)
    print(f"Пакетів: {n}, рядків: {len(items)} -> {OUT}")


def load_items(pattern="packet_*.json"):
    items = []
    for p in sorted(OUT.glob(pattern)):
        items += [json.loads(l.rstrip().rstrip(",")) for l in open(p, encoding="utf-8") if l.startswith("{")]
    return items


def caps(s):
    """Слова з великої літери не на початку речення — грубий слід імен і назв."""
    return {w[:4] for w in re.findall(r"(?<![.!?…»]\s)(?<!^)\b[А-ЯҐЄІЇA-Z][а-яґєіїa-z’']{2,}", s)}


SCHEMA = {"type": "object", "properties": {"choice": {"type": "integer"}, "why": {"type": "string"}},
          "required": ["choice", "why"]}


def ask(args, system, user, schema=None):
    body = {"model": args.model, "stream": False, "think": args.think, "format": schema or SCHEMA,
            "options": {"temperature": 0.2, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for att in range(3):
        if att:
            body.pop("format", None)  # gpt-oss іноді повертає порожньо зі схемою
        req = urllib.request.Request("http://localhost:11434/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            c = json.loads(urllib.request.urlopen(req, timeout=600).read())["message"]["content"]
            return json.loads(c[c.find("{"):c.rfind("}") + 1])
        except Exception:
            time.sleep(2)
    return None


def local(args):
    tr = load_json(TRANSLATIONS, {})
    path = OUT / "local.json"
    res = load_json(path, {})
    system = (OUT / "INSTRUCTIONS.md").read_text(encoding="utf-8").split("## Відповідь")[0] + (
        '\n## Відповідь\nJSON: {"choice": 1 | 2 | 0, "why": "коротко"} — 0, якщо обидва варіанти явно погані '
        "(не той зміст, зламане ім’я, неправильний рід мовця).")
    todo = [x for x in load_items() if x["key"] not in res and tr.get(x["key"], {}).get("status") == "ok"]
    print(f"Залишилось: {len(todo)}", flush=True)
    t0 = time.time()
    for n, x in enumerate(todo, 1):
        a = ask(args, system, json.dumps({k: v for k, v in x.items() if k != "key"}, ensure_ascii=False))
        res[x["key"]] = {"choice": a.get("choice", -1) if a else -1, "why": (a or {}).get("why", "")[:300]}
        if n % 20 == 0 or n == len(todo):
            save_json(path, res)
            print(f"{n}/{len(todo)}  {(time.time() - t0) / n:.1f} с/рядок", flush=True)


def escalate(args):
    res = load_json(OUT / "local.json", {})
    tr = load_json(TRANSLATIONS, {})
    esc = []
    for x in load_items():
        r = res.get(x["key"])
        if not r or tr.get(x["key"], {}).get("status") != "ok":
            continue
        if r["choice"] not in (1, 2) or caps(x["1"]) != caps(x["2"]):
            esc.append(x)
    for old in OUT.glob("sonnet_*.json"):
        old.unlink()
    n = 0
    for n, start in enumerate(range(0, len(esc), args.size), 1):
        with open(OUT / f"sonnet_{n:02d}.json", "w", encoding="utf-8") as fh:
            fh.write("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False)
                                         for x in esc[start:start + args.size]) + "\n]\n")
    (OUT / "_escalated.txt").write_text("\n".join(x["key"] for x in esc), encoding="utf-8")
    print(f"До Claude: {len(esc)} рядків, пакетів {n} (sonnet_NN.json -> відповіді out_sNN.json)")


def apply(args):
    tr = load_json(TRANSLATIONS, {})
    mapping = load_json(OUT / "_map.json", {})
    fixes, stats = {}, {"before": 0, "after": 0, "own": 0, "missing": 0}
    answers = {}
    esc_path = OUT / "_escalated.txt"
    escalated = set(esc_path.read_text(encoding="utf-8").split()) if esc_path.exists() else set()
    for k, r in load_json(OUT / "local.json", {}).items():
        if k not in escalated and r["choice"] in (1, 2):
            answers[k] = r["choice"]
    for p in sorted(OUT.glob("out_*.json")):
        answers.update(load_json(p, {}))
    for k, first in mapping.items():
        a = answers.get(k)
        t = tr.get(k)
        if a is None or not t or t["status"] != "ok" or not t.get("uk_before_proof"):
            stats["missing"] += 1
            continue
        if isinstance(a, str) and a.strip() in ("1", "2"):
            a = int(a)
        if isinstance(a, int):
            pick = first if a == 1 else ("after" if first == "before" else "before")
            stats[pick] += 1
            if pick == "before":
                fixes[k] = t["uk_before_proof"]
        else:
            stats["own"] += 1
            fixes[k] = a
    print(stats)
    if args.dry or not fixes:
        return
    path = OUT / "_apply.json"
    save_json(path, fixes)
    subprocess.run([sys.executable, str(Path(__file__).with_name("fix.py")), "--json", str(path)], check=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--size", type=int, default=150)
    lo = sub.add_parser("local")
    lo.add_argument("--model", default="gpt-oss:latest")
    lo.add_argument("--think", default="medium")
    es = sub.add_parser("escalate")
    es.add_argument("--size", type=int, default=150)
    a = sub.add_parser("apply")
    a.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    {"export": export, "local": local, "escalate": escalate, "apply": apply}[args.cmd](args)


if __name__ == "__main__":
    main()
