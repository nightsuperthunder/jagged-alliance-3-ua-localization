"""Показати рядок(и) з контекстом — для розбору правок від спільноти.

  python scripts/lookup.py dialogue:1234              # рядок + по 2 сусідні з кожного боку
  python scripts/lookup.py dialogue:1234 --ctx 5
  python scripts/lookup.py 1234                        # m_Id без файлу — шукає в усіх файлах
  python scripts/lookup.py --search "Кравчин"          # пошук підрядка в en/uk (до 20 збігів)
  python scripts/lookup.py --search "hemstitch" --ctx 0

Виводить компактно: ключ, статус, EN, UK, коментар розробників; сусідів — позначкою ·.
"""
import argparse

from common import TRANSLATIONS, load_json, load_strings


def show(s, t, mark):
    uk = (t or {}).get("uk", "(як в оригіналі)" if t and t["status"] == "skip" else "—")
    st = (t or {}).get("status", "немає")
    print(f"{mark} {s['key']} [{st}]" + (f"  мовець: {s['speaker']}" if s.get("speaker") else ""))
    print(f"   EN: {s['en']!r}")
    print(f"   UK: {uk!r}")
    if mark == "▶" and s.get("comment"):
        print(f"   коментар: {s['comment']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", help="ключі file:id або просто id")
    ap.add_argument("--search", help="підрядок в en або uk (без урахування регістру)")
    ap.add_argument("--ctx", type=int, default=2, help="скільки сусідніх рядків показати")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    args = ap.parse_args()

    strings = load_strings()
    tr = load_json(args.tr, {})
    by_file = {}
    for s in strings:
        by_file.setdefault(s["file"], []).append(s)
    for rows in by_file.values():
        rows.sort(key=lambda x: x["order"])

    hits = []
    for k in args.keys:
        hits += [s for s in strings if s["key"] == k or str(s["id"]) == k]
    if args.search:
        q = args.search.lower()
        hits += [s for s in strings
                 if q in s["en"].lower() or q in (tr.get(s["key"], {}).get("uk") or "").lower()]
    if not hits:
        print("Нічого не знайдено")
    for s in hits[:args.max]:
        rows = by_file[s["file"]]
        i = s["order"] if s["order"] < len(rows) and rows[s["order"]] is s else rows.index(s)
        for j in range(max(0, i - args.ctx), min(len(rows), i + args.ctx + 1)):
            r = rows[j]
            show(r, tr.get(r["key"]), "▶" if j == i else "·")
        print("-" * 60)
    if len(hits) > args.max:
        print(f"… ще {len(hits) - args.max} збігів (--max)")


if __name__ == "__main__":
    main()
