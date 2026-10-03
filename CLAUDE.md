# Ukrainian fan localization of Jagged Alliance 3 — agent guide

Pipeline template distilled from a finished project (Dressmaker, 5886 strings), adapted to JA3 (30.5k strings,
~300k words). Investigation is done — see "Game facts" and "Current state" at the bottom.

Answer the user in **Ukrainian**. This file and commit messages in English.

## Rules
- **Claude tokens are expensive for the user.** Bulk work (translating, proofreading, reviewing hundreds of lines) goes to
  the **local LLM (Ollama) via scripts**. You: investigation, scripts, glossary, prompts, mod code, small samples (≤ ~50 lines).
  Don't dump big files into context; use `scripts/lookup.py`, `review.py stats`, short one-liners.
- **If the local model can't handle a task or produces garbage — stop and tell the user** (what fails, a few examples,
  options: better prompt/glossary, another local model, smaller batches). **Do the work yourself only with the user's
  explicit permission**, and only for the agreed scope. Never silently fall back to doing bulk work with Claude.
- Long jobs run in background; don't poll.
- **Ask before downloading anything** (tools, models, fonts, mod loaders).
- **Never commit the game's original text** (copyright): no extracted strings, dumps, English back-translations.
  The repo holds only the Ukrainian translation + a hash of each source line. Check `git status` before `git add -A`.
- Commits, pushes, releases, public posts — only when the user says so. Author only `nightsuperthunder`
  (`git config user.name nightsuperthunder`, `user.email 42420139+nightsuperthunder@users.noreply.github.com`),
  **no `Co-Authored-By` or any Claude attribution**. New repos start private.

## Strategy
1. **Investigate** the game: engine, where the text lives, how to read it, how to get a translation back into the game
   without breaking it (mod/plugin > patched data files > replaced files), fonts (Cyrillic?), what must stay untouched
   (tags, placeholders, escapes). Write findings into "Game facts" below.
2. **Extract** all source strings into the standard `work/strings.json` (local only). Keep every piece of context the game
   has: dev comments, speaker, file/scene order.
3. **Prepare before any bulk run** — this is the biggest quality lever:
   glossary (names + gender, places, terms, UI labels), characters (gender, ти/ви), player address policy (player gender
   defined? «ви»?), words the game substitutes into placeholders and how sentences are built around them,
   `style_guide.md` (setting, tone, voices), validator rules for this game's markup.
4. **Pilot** 40–100 lines per file, show the user a small sample, fix prompt/glossary/validator — not individual lines.
5. **Full run** with the local model: translate (batched, with context and glossary) → retry failures → proofread pass.
6. **Find meaning errors** automatically (back-translation + big judge model + context review) → user skims a CSV.
7. **Deliver**: build the mod/patch, install, test in the game (screenshots), fix overflow/fonts/missing strings.
8. **Release** (zip, README with screenshots, GitHub release) and handle **community fix batches**.

## Metadata (keep these formats — all scripts rely on them)
`work/strings.json` (git-ignored) — list of source strings:
```json
{"key": "<file>:<id>", "file": "<file key>", "id": "<id the game/mod uses>", "order": 0,
 "en": "source text", "comment": "dev/translator comment or ''", "speaker": "optional"}
```
`key` must be stable across game updates. `file` groups strings (ui, dialogue, items…); `order` = position for context.

`work/translations.json` (committed) — `key → record`:
```json
{"src": "<first 12 hex of sha1(en)>", "uk": "переклад", "status": "ok|manual|skip|error",
 "model": "…", "errors": ["…"], "proofed": true, "uk_before_proof": "…"}
```
`ok` = model, validated · `manual` = human/Claude edit, **scripts never overwrite it** · `skip` = leave as in game
(stubs, no letters) · `error` = failed validation, not shipped. `src` mismatch = source changed → retranslate/flag.

`glossary.json` — `{"terms": [{"en", "uk", "note"}]}`; only terms present in a batch go into the prompt.
`style_guide.md` — the system prompt; must be filled (scripts refuse to run while it contains `[ЗАПОВНИТИ`).
`project.json` — everything game-specific: file keys + per-file hint for the model (order = translation order, UI first:
translated short UI labels become an auto-glossary for the rest), validator rules, models.

## Structure
```
CLAUDE.md  README.md  project.json  glossary.json  style_guide.md  .gitignore
scripts/                   # generic pipeline, works on strings.json
  common.py llm.py         # config, validate(), Ollama calls, batching
  glossary_candidates.py   # names/terms before translating (+ --llm suggestions)
  translate.py proofread.py review.py run_all.py
  backtranslate.py context_review.py find_issues.py
  lookup.py fix.py         # community fix batches
  hpk.py                   # JA3: reader for Haemimont .hpk archives (stdlib only, Python 3.14+ for zstd)
  export_strings.py        # JA3: Local/English.hpk -> work/strings.json (deterministic)
  build_mod.py             # JA3: translations.json -> mod/dist/<folder> + zip, --install to %AppData%
mod/                       # metadata.lua / items.lua templates (@PLACEHOLDERS@ filled by build_mod.py), README_UA.txt,
                           # installer/install.bat + uninstall.bat (CRLF, UTF-8 + chcp 65001; copied to zip root)
```

## Commands
| | |
|---|---|
| Extract strings | `python scripts/export_strings.py` → `work/strings.json` (re-run after a game update) |
| Build / install mod | `python scripts/build_mod.py [--install] [--all]` → `mod/JA3_Ukrainian_Localization.zip` |
| Release | `python scripts/release.py X.Y.Z` → versioned zip; then commit, push, `gh release create` (user's OK) |
| Inspect an archive | `python scripts/hpk.py <file.hpk> [<inner path> <out file>]` |
| Glossary candidates | `python scripts/glossary_candidates.py [--llm]` → `work/glossary_candidates.csv` |
| Pilot | `python scripts/translate.py --file <f> --limit 40 --out work/test_a.json [--model M --no-think]` |
| Full run (background) | `python scripts/run_all.py` (translate → redo errors → proofread → stats → CSVs) |
| Review in Excel | `python scripts/review.py export [--errors]` → edit `uk` → `review.py import [--csv F]` |
| Meaning errors | `python scripts/find_issues.py` → skim `work/context_review.csv` → `review.py import --csv …` |
| Gender & ти/ви vs RU | `python scripts/export_strings.py --ref Russian` once → `python scripts/check_ru.py` → `work/ru_check.csv`; retranslate flagged: `python scripts/redo_ru_check.py [--only address\|gender]` |
| Look up / fix | `python scripts/lookup.py <key or id> [--ctx N]` / `--search "…"`; `python scripts/fix.py <key> "текст"`, `--json F`, `--skip K`, `--replace OLD NEW --dry` |

**Community fix batch:** user sends lines + what's wrong → `lookup.py` for context → judge the English (players are
sometimes wrong) → verdict in Ukrainian → `fix.py` (validates, sets `manual`). A recurring mistake → fix the pattern
(glossary / validator `forbidden` / style guide + `fix.py --replace --dry`), not just the line. Rebuild, test, release on request.

## Lessons that apply to any game
- Local model failure modes (validator already catches them): wrapping the whole line in «…» (thousands of lines!,
  also hidden by a trailing space/period), dropping tags, stray `.` after `!?…`, nested «“…”», trailing spaces,
  translating placeholder-only lines, wrong vocative forms. New systematic error → new validator rule.
- Glossary before translating: without it `Discord` became «Розбрат», `Patterns` «Візерунки» (should be «викрійки»),
  a kingdom name was translated as a common noun.
- Grammatical gender/agreement errors are **invisible** to automated back-translation checks (English erases gender).
  Only glossary notes, speaker info and the prompt prevent them; players catch the rest.
- Placeholders: the game inserts English-grammar words; build Ukrainian sentences so the slot stays nominative
  («основна тканина — {1}») and translate the inserted words in one fixed form.
- Ukrainian text is ~15–30 % longer: plan for UI overflow (auto-shrink, shorter labels).
- Fonts without Cyrillic are the usual delivery blocker — find the game's font/fallback mechanism early.
- Meaning-error funnel that worked: back-translate with the translation model → big model judges ORIGINAL vs BACK
  (English only) → big model reviews suspects with neighbouring lines. Similarity scores alone and small-model review didn't work.
- Models (Ollama): translate `hf.co/INSAIT-Institute/MamayLM-Gemma-3-12B-IT-v2.0-GGUF:Q8_0` (~1–2.5 s/line on a 16 GB GPU),
  judge `gemma4:26b-a4b-it-q4_K_M --no-think`, embeddings `embeddinggemma:300m`.

---
## Game facts
- **Game:** Jagged Alliance 3 (Haemimont Games), `E:\Games\SteamLibrary\steamapps\common\Jagged Alliance 3`.
  No separate DLC text packs.
- **Engine:** Haemimont's own engine (Lua). Lua sources of the game ship in `ModTools/Src` (read them instead of guessing),
  docs in `ModTools/Docs` (`ModItemLocTable.md.html`, `ModItemFont.md.html`).
- **Text:** one table per language, `Local/<Language>.hpk` → `CurrentLanguage/Game.csv` (UTF-8 BOM, 20 columns:
  ID, Text, Translation, Old Text, Old Translation, Status, Gender, 3× Warnings, Location, Context, Section, Keyword,
  Actor, Voice Actor, Voice ID, Revision, Old Revision, Edit Distance). 31221 rows, identical IDs in all 10 languages.
  `ModTools/Game.csv` is the same table cut to 5 columns (no Location) — we read the hpk.
  Loader (`CommonLua/Core/localization.lua`): reads columns 1 (id), 2 (text), 3 (translated_new), 5 (translated), 7 (gender),
  skips the first row; in English the priority is col 3 → col 2 → col 5. A row with all three empty wipes the string —
  never emit rows without a translation.
- **Delivery (verified in game 2026-10-01):** a regular mod, game language stays English. Mod folder
  `%AppData%\Jagged Alliance 3\Mods\JA3UkrLoc\{metadata.lua, items.lua, English.csv, Code/UkrLoc.lua}`
  (templates in `mod/`, filled by `build_mod.py`). Ukrainian is not in the engine's `AllLanguages`, so a separate
  language is impossible. Gotchas found the hard way:
  - `metadata.lua` `loctables[].filename` is relative (`English.csv`) — `ModsLoadLocTables` prepends `Mod/<id>/`;
    the dev sample's `Mod/<id>/x.csv` there resolves to a doubled path and is silently skipped.
    `items.lua` `ModItemLocTable.filename` is the full `Mod/<id>/English.csv`.
  - The Steam guide (https://steamcommunity.com/sharedfiles/filedetails/?id=3667341845) recommends JA3_CommonLib;
    we don't need it: `Code/UkrLoc.lua` wraps `LoadTranslationTables` and re-applies our CSV after every rebuild of
    the table + once 3 s after start, and logs `[UkrLoc] … probe = <translated OPTIONS>` to the game log.
  - Mod code runs in a sandboxed env: no `io.*`, no `AsyncFileToString` (see `ModEnvBlacklist` in Mod.lua).
  - Game log: `%AppData%\Jagged Alliance 3\logs\JA3.exe-*.log` (readable with Read/Grep; `[mod]` lines list loaded mods).
  - Workshop upload goes through the in-game Mod Editor (re-saves metadata.lua — re-check loctables/code after).
- **Markup:** everything is `<…>` tags (1086 distinct): formatting (`<em>` ×4872, `<newline>`, `<bullet_point>`,
  `<color R G B>`, `<style X>`, `<right>`, `<flavor>`, `<error>`), substitutions (`<Nick>`, `<name>`, `<amount>`,
  `<money(500)>`, `<SectorName('H2')>`, `<GameTerm('Overwatch')>`, `<u(name)>`), skill-check markers at line start
  (`<wisdom-s>`, `<mechanical-f>`…). Keep byte-exact (order may change) — `common.validate()` compares the multiset.
  `{}` is not used (4 editor strings), `%d` once. 652 strings contain real newlines, 632 end with a space.
  No TAB in translations (breaks the row in the game's CSV parser); quotes/commas are handled by the csv writer.
- **Files** (`export_strings.py: classify()` — first word of Context, then Location; translation order as in
  `project.json`): ui 3851 · terms 3066 · items 1165 · units 1290 · story 1540 · conversations 6954 · banters 4755 ·
  voice 7772 · editor 148 (mod/map editor UI, lowest priority). 675 `TextStyle` rows (font names) are not exported.
  `comment` = the game's Context column (preset class, id, property; VoiceResponse rows describe the situation;
  conversation rows also get the player's line they answer — the Keyword column). `speaker` = Actor (279 actors,
  18.3k rows). `order` = row index in the table = source file/line order, so lines of one conversation are adjacent.
  **Do not change `classify()` after translation starts — the file is part of the key.**
- **Substitutions:** tags insert names/numbers in one fixed (nominative) form. The engine supports gender variants
  (`id+1` = F, `id+2` = N, `Gender` column, `<ByGender()>`), but no shipped language uses them.
- **Player:** unseen commander, gender undefined → neutral «ви». Mercs have fixed genders (Actor → glossary notes).
- **Fonts:** `Packs/Fonts.hpk`. HMGothic (Regular/Rough A/B), Source Code Pro (all weights), LibelSuit have full Ukrainian
  Cyrillic incl. ґ є і ї, «», —, …, ’. Missing: `ʼ` (U+02BC) everywhere → use ’ (validator `forbidden`);
  **Source Code Pro Italic has no Cyrillic** (8 text styles) → `build_mod.py` copies the official Russian table's
  TextStyle overrides (Italic → Regular). No extra fonts needed.
- **Installing for tests:** files the agent writes under `%AppData%` land in the agent's sandbox overlay and are
  invisible to the game/user (confirmed 2026-09-30: the game and `dir` show only mods the user created). So
  `build_mod.py --install` is useless from the agent; the user copies `mod/dist/JA3UkrLoc` into
  `%AppData%\Jagged Alliance 3\Mods` by hand. The repo folder (D:) is shared normally.
- **Voices:** English only (`Local/Voices/English.hpk`); text is the subtitle, so voice lines should not grow much.

## Current state (2026-10-03)
- **Full translation done**: `work/translations.json` — ok 28 560, manual 1 771 (Sonnet/review fixes), skip 210, error 0 (as of 2026-10-03).
  Pipeline that ran: translate (MamayLM, 9.4 h) → redo errors → proofread → find_issues (6 h) → redo ти/ви+gender
  from RU → gemma4 on errors → Sonnet subagents on 288 hard lines (errors + ~90 lines whose translation landed on a
  neighbouring line — detected by comparing back-translation with neighbours' EN). Not committed yet.
- Snapshots of every stage: `work/snapshots/02_after_translate … 07_after_sonnet.json` (git-ignored);
  `scripts/restore_snapshot.py` restores error lines from a snapshot.
- Open work, in order:
  1. ~~Proofread decision~~ DONE 2026-10-02 (`scripts/proof_ab.py`): typography kept; 1 788 content edits judged
     before/after — gpt-oss:20b locally on all (~4.6 s/line), Sonnet on its "both bad" + lines whose names differ
     (241) + pilot packet (150). Result: 840 reverted, 793 kept, 57 own fixes (status manual). Snapshots 08/09.
     Then (2026-10-02/03): Red Rabies → «Червоний сказ» everywhere (case-aware regex), Kronenberg (woman,
     indeclinable) / Ґрузельгайм / Фоше / Чімуренга unified + glossary; achievements → «ви» (how_to «Убийте…»,
     description «Убили…»). Snapshots 10–12.
  2. ~~context_review.csv~~ DONE 2026-10-03 (`scripts/judge_suspects.py` + `scripts/find_shifts.py`): gpt-oss
     confirmed 443/567; embeddings shift detector (+18 strong). MamayLM retranslated 424 lines ONE BY ONE →
     gpt-oss A/B old/new → 238 new applied, 71 old kept; 88 "both bad"/unvalidated → Sonnet (85 fixed).
     Shift-detector + gpt-oss on voice barks is mostly false positives; only gap > 0.1 is worth checking.
  3. `work/ru_check.csv` — 52 leftovers (gender 36, ти/ви 18), low priority.
  4. Build mod (`python scripts/build_mod.py`), user copies `mod/dist/JA3UkrLoc` to `%AppData%\Jagged Alliance 3\Mods`,
     tests in game (start of campaign, A.I.M., first conversation, combat, Sat View), fix overflow/strings.
  5. Commit (user's permission!) translations.json + new scripts (check_ru, ru_ref, redo_ru_check, restore_snapshot,
     export_packets, proof_ab, judge_suspects, find_shifts, mod/Code) — check `git status`, no game text (work/strings.json, ref_*.json, csv are ignored).
- Decisions (user): names/nicknames transliterated (glossary: 48 mercs with gender, places Гран-Ш’єн, Порт-Какао,
  Пантагрюель, острів Ерні, Легіон, Майор, Алмазний Ред); Multiplayer → «Мережева гра»; French inserts Latin; Russian
  inserts → Latin translit in code (`common.ru_mask/ru_translit`, Kalyna excepted); profanity Ukrainian only, no мат.
  The user trusts the agent's game-term choices (AP → ОД, HP → ОЗ, Overwatch → Пильність, Sat View → Супутникова мапа…).
  Claude/Sonnet may translate hard lines (user OK'd ~300k tokens per batch; use `scripts/export_packets.py`
  packets → subagents write `work/_packets/out_NN.json` → `fix.py --json`).
- Lessons from this run: batches of 25 sometimes put a translation on the neighbouring line (validator can't see it);
  the proofreader and judge "fix" deliberate jokes; strict post-checks (ti/vy) turn ok lines into errors — always
  snapshot before a pass and restore leftovers; a background Bash task is killed after its time limit (resumable).
  Sonnet subagents cost ~600–800 tokens per judged line (re-reading context each turn), so for bulk A/B judging use
  the local gpt-oss first and escalate only doubtful lines; gpt-oss catches shifted lines/gender but is weak on
  spelling and register (it also returns empty output with a JSON schema — retry without `format`).
