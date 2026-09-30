# Українська локалізація Jagged Alliance 3

Фанатський переклад тексту гри (озвучення лишається англійським). Стан: **підготовка, перекладу ще немає**.

Мод для вбудованого менеджера модів JA3: таблиця перекладу підміняє англійський текст, файли гри не змінюються.

## Встановлення (коли вийде реліз)
1. Розпакувати теку `JA3 Ukrainian Localization` в `%AppData%\Jagged Alliance 3\Mods\`.
2. У грі: Mod Manager → увімкнути «Українська локалізація».
3. Мова гри — English (Options → Gameplay → Language).

## Збирання з вихідників
Потрібні Python 3.14+ і встановлена гра (оригінальні тексти в репозиторії не зберігаються — лише переклад і хеші).

```
python scripts/export_strings.py     # тексти гри -> work/strings.json (локально)
python scripts/build_mod.py          # work/translations.json -> mod/JA3_Ukrainian_Localization.zip
```

Деталі процесу — в `CLAUDE.md`.
