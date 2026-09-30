# Dressmaker (Unity 6, Mono, Unity Localization) — how it was done

Use only if the new game is similar. Files here expect the old project.json fields (`source.bundle`, `files.*.collection`, `mod.*`).

- Text: Unity Localization StringTables in `StreamingAssets/aa/<platform>/localization-string-tables-english(en)_assets_all.bundle`,
  read with UnityPy (`export_unity_localization.py`); id = `m_Id`; dev comments in `references.RefIds[].data.m_CommentText`.
- Delivery: BepInEx 5 plugin (`Plugin/`): custom `ITableProvider` builds a StringTable from the English one + `uk.json`
  (copies `IsSmart`), adds locale `uk` with `FallbackLocale(en)`. Game files untouched.
- Gotchas: add the locale before the game picks the startup locale (patch `IStartupLocaleSelector.GetStartupLocale`);
  asset tables → return `default` (returning the English one gave a blank logo); TMP fonts have no Cyrillic → dynamic
  fallback font (fonts/*.ttf or OS Georgia); TMP auto-size for our locale, min never above authored size (world-space
  texts blew up), skip linked-overflow text (newspaper columns); strings with code-side English fallback need a Harmony postfix;
  language name in menu comes from `CultureInfo.NativeName` → patch.
- Decompile: `ilspycmd -p -o <dir> -r <Managed> <Managed>/Assembly-CSharp.dll`.
- Build: csproj with `DebugType none`, `Deterministic`, `PathMap` (else the Windows user name ends up in the dll);
  `build_mod.py` scans the zip for personal data; `release.py` bumps version + builds with BepInEx + versioned zip.
- Test: close the game before install, launch, check `BepInEx/LogOutput.log`, screenshots via PowerShell `CopyFromScreen`.
