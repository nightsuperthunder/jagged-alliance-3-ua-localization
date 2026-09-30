using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using Newtonsoft.Json;
using TMPro;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.Localization;
using UnityEngine.Localization.Metadata;
using UnityEngine.Localization.Settings;
using UnityEngine.Localization.Tables;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;

namespace GameUA
{
    /// <summary>
    /// Українська локалізація для Unity-гри на Unity Localization (Mono, BepInEx 5).
    /// Додає мову "uk" у список мов гри, віддає для неї таблиці рядків з translations/uk.json
    /// (відсутні рядки — англійською), підключає шрифт з кирилицею як запасний і вмикає
    /// автозменшення тексту, що не вміщається. Файли гри не змінюються.
    ///
    /// ШАБЛОН: загальні частини перевірено на Dressmaker. Місця, які залежать від гри, позначено TODO
    /// (див. docs/PLAYBOOK.md, фаза «Мод»).
    /// </summary>
    [BepInPlugin(Guid, "Ukrainian localization", Version)]
    public class Plugin : BaseUnityPlugin
    {
        // TODO: унікальний GUID для гри, напр. "ua.<game>.localization"
        public const string Guid = "ua.game.localization";
        public const string Version = "0.1.0";

        internal static ManualLogSource Log;

        internal static ConfigEntry<string> LocaleCode;
        internal static ConfigEntry<string> DisplayName;
        internal static ConfigEntry<string> OsFontFallback;
        internal static ConfigEntry<bool> AutoSizeText;
        internal static ConfigEntry<float> AutoSizeMinRatio;

        // колекція ("UI", "Dialogue"...) -> id рядка -> переклад
        internal static Dictionary<string, Dictionary<long, string>> Translations =
            new Dictionary<string, Dictionary<long, string>>();

        internal static string PluginDir;

        private void Awake()
        {
            Log = Logger;
            PluginDir = Path.GetDirectoryName(Info.Location);

            LocaleCode = Config.Bind("General", "LocaleCode", "uk", "Код мови, під яким переклад додається в гру.");
            DisplayName = Config.Bind("General", "DisplayName", "Українська", "Назва мови в меню вибору мови.");
            OsFontFallback = Config.Bind("Fonts", "OsFontFallback", "Georgia",
                "Системний шрифт з кирилицею, якщо в папці fonts немає власних шрифтів.");
            AutoSizeText = Config.Bind("Fonts", "AutoSizeText", true,
                "Автоматично зменшувати текст, який не вміщається в кнопку чи напис "
                + "(українські слова довші за англійські).");
            AutoSizeMinRatio = Config.Bind("Fonts", "AutoSizeMinRatio", 0.6f,
                "Наскільки максимально дозволено зменшити текст: 0.6 = до 60% від авторського розміру.");

            LoadTranslations();

            LocalizationSettings.StringDatabase.TableProvider = new UkTableProvider();

            var harmony = new Harmony(Guid);
            harmony.PatchAll(typeof(Patches));
            PatchStartupSelectors(harmony);
            SceneManager.sceneLoaded += OnSceneLoaded;

            // якщо ініціалізація вже пройшла — додати мову зараз, інакше після неї
            var init = LocalizationSettings.InitializationOperation;
            if (init.IsDone) EnsureLocale(LocalizationSettings.AvailableLocales);
            else init.Completed += _ => EnsureLocale(LocalizationSettings.AvailableLocales);

            Log.LogInfo($"Завантажено перекладів: {Translations.Sum(t => t.Value.Count)} рядків у {Translations.Count} таблицях");
        }

        private void LoadTranslations()
        {
            string path = Path.Combine(PluginDir, "translations", LocaleCode.Value + ".json");
            if (!File.Exists(path))
            {
                Log.LogError("Не знайдено файл перекладу: " + path);
                return;
            }
            try
            {
                var raw = JsonConvert.DeserializeObject<Dictionary<string, Dictionary<string, string>>>(
                    File.ReadAllText(path, System.Text.Encoding.UTF8));
                foreach (var table in raw)
                {
                    var dict = new Dictionary<long, string>();
                    foreach (var kv in table.Value)
                        if (long.TryParse(kv.Key, out long id)) dict[id] = kv.Value;
                    Translations[table.Key] = dict;
                }
            }
            catch (Exception e)
            {
                Log.LogError("Помилка читання " + path + ": " + e);
            }
        }

        // ---------- мова ----------

        internal static bool IsOurLocale(Locale locale) =>
            locale != null && locale.Identifier.Code == LocaleCode.Value;

        internal static void EnsureLocale(ILocalesProvider provider)
        {
            if (provider == null || provider.GetLocale(new LocaleIdentifier(LocaleCode.Value)) != null) return;
            var locale = Locale.CreateLocale(new LocaleIdentifier(LocaleCode.Value));
            locale.LocaleName = DisplayName.Value;
            locale.name = DisplayName.Value;
            // усе, чого немає в перекладі (картинки з текстом тощо), береться з англійської
            var en = provider.GetLocale(new LocaleIdentifier("en"));
            if (en != null) locale.Metadata.AddMetadata(new FallbackLocale(en));
            LocalizationSettings.AssetDatabase.UseFallback = true;
            UnityEngine.Object.DontDestroyOnLoad(locale);
            provider.AddLocale(locale);
            Log.LogInfo("Мову додано: " + LocaleCode.Value);
        }

        /// <summary>
        /// Мову треба додати ДО того, як гра вибере стартову (збережене налаштування, мова системи).
        /// Замість патча конкретного класу гри патчимо всі реалізації IStartupLocaleSelector.
        /// </summary>
        private static void PatchStartupSelectors(Harmony harmony)
        {
            var prefix = new HarmonyMethod(typeof(Plugin), nameof(BeforeStartupLocale));
            foreach (var type in AccessTools.AllTypes())
            {
                if (type.IsInterface || type.IsAbstract || !typeof(IStartupLocaleSelector).IsAssignableFrom(type)) continue;
                var m = AccessTools.Method(type, nameof(IStartupLocaleSelector.GetStartupLocale), new[] { typeof(ILocalesProvider) });
                if (m == null || m.IsAbstract) continue;
                try { harmony.Patch(m, prefix: prefix); }
                catch (Exception e) { Log.LogWarning("Не вдалося пропатчити " + type.FullName + ": " + e.Message); }
            }
        }

        private static void BeforeStartupLocale(object[] __args)
        {
            if (__args.Length > 0) EnsureLocale(__args[0] as ILocalesProvider);
        }

        // ---------- таблиці ----------

        internal static StringTable BuildTable(StringTable en, string collection)
        {
            var table = ScriptableObject.CreateInstance<StringTable>();
            table.name = collection + "_" + LocaleCode.Value;
            table.LocaleIdentifier = new LocaleIdentifier(LocaleCode.Value);
            table.SharedData = en.SharedData;
            Translations.TryGetValue(collection, out var tr);
            int translated = 0;
            foreach (var entry in en.Values)
            {
                string text = entry.Value;
                if (tr != null && tr.TryGetValue(entry.KeyId, out var uk)) { text = uk; translated++; }
                var e = table.AddEntry(entry.KeyId, text);
                e.IsSmart = entry.IsSmart; // інакше {0:list:…} і \: зламаються
            }
            UnityEngine.Object.DontDestroyOnLoad(table);
            Log.LogInfo($"Таблиця {collection}: перекладено {translated} з {en.Count}");
            return table;
        }

        // ---------- сцени: шрифти й автомасштаб ----------

        private static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            EnsureGlobalFontFallback();
            var texts = Resources.FindObjectsOfTypeAll<TMP_Text>();
            foreach (var text in texts)
                if (text != null && text.linkedTextComponent != null)
                    ExcludeLinkedChain(text);
            foreach (var text in texts)
                ApplyAutoSize(text);
        }

        // id напису → авторський розмір шрифту (-1: напис з ланцюжка колонок, не чіпаємо)
        private static readonly Dictionary<int, float> AutoSized = new Dictionary<int, float>();

        /// <summary>
        /// Вмикає автомасштабування напису: якщо переклад не вміщається, TMP зменшить шрифт,
        /// замість того щоб рвати слово посередині. Авторський розмір лишається максимумом.
        /// </summary>
        internal static void ApplyAutoSize(TMP_Text text)
        {
            if (text == null || !AutoSizeText.Value || text.enableAutoSizing) return;
            if (!IsOurLocale(LocalizationSettings.SelectedLocale)) return;
            // колонки (газета тощо): текст перетікає в наступний напис — автомасштаб стиснув би першу колонку
            if (text.overflowMode == TextOverflowModes.Linked || text.linkedTextComponent != null) return;
            int id = text.GetInstanceID();
            if (AutoSized.ContainsKey(id)) return;
            float authored = text.fontSize;
            if (authored <= 0f) return;
            AutoSized[id] = authored;
            text.fontSizeMax = authored;
            // мінімум ніколи не більший за авторський: написи в 3D-сцені мають розмір < 6,
            // і «мінімум 6» роздуває їх на пів екрана
            text.fontSizeMin = Mathf.Min(authored,
                Mathf.Max(6f, authored * Mathf.Clamp(AutoSizeMinRatio.Value, 0.2f, 1f)));
            text.enableAutoSizing = true;
        }

        /// <summary>Наступні колонки ланцюжка могли отримати автомасштаб в OnEnable раніше — повертаємо їм розмір.</summary>
        private static void ExcludeLinkedChain(TMP_Text head)
        {
            var t = head.linkedTextComponent;
            for (int i = 0; t != null && t != head && i < 32; i++, t = t.linkedTextComponent)
            {
                int id = t.GetInstanceID();
                if (AutoSized.TryGetValue(id, out float authored) && authored > 0f)
                {
                    t.enableAutoSizing = false;
                    t.fontSize = authored;
                }
                AutoSized[id] = -1f;
            }
        }

        // ---------- шрифти ----------

        private static readonly Dictionary<string, TMP_FontAsset> FontCache = new Dictionary<string, TMP_FontAsset>();
        private static bool _fontsScanned, _globalFallbackAdded;
        private static readonly Dictionary<string, string> FontFiles = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// Загальний запасний шрифт TMP: його TextMeshPro використовує для будь-якого символу,
        /// якого немає в шрифті гри та в його власних fallback. Працює для будь-якої TMP-гри.
        /// Якщо гра має власну систему шрифтів для мов (як LocaleFontFallbacks у Dressmaker) —
        /// краще ще й підчепитися до неї (TODO в Patches), щоб підібрати шрифт під кожен шрифт гри.
        /// </summary>
        private static void EnsureGlobalFontFallback()
        {
            if (_globalFallbackAdded) return;
            _globalFallbackAdded = true;
            var font = GetCyrillicFont(null);
            if (font == null) return;
            var list = TMP_Settings.fallbackFontAssets;
            if (list != null && !list.Contains(font)) list.Add(font);
            Log.LogInfo("Запасний шрифт з кирилицею додано в TMP_Settings");
        }

        /// <summary>
        /// Шрифт з кирилицею: fonts/&lt;назва шрифту гри&gt;.ttf — для конкретного шрифту,
        /// fonts/default.ttf — для решти; інакше системний шрифт з налаштувань.
        /// </summary>
        internal static TMP_FontAsset GetCyrillicFont(TMP_FontAsset latin)
        {
            ScanFonts();
            string key = latin != null && FontFiles.ContainsKey(latin.name) ? latin.name : "default";
            if (FontCache.TryGetValue(key, out var cached)) return cached;

            TMP_FontAsset font = null;
            try
            {
                if (FontFiles.TryGetValue(key, out var file))
                    font = TMP_FontAsset.CreateFontAsset(file, 0, 90, 9, GlyphRenderMode.SDFAA, 1024, 1024);
                if (font == null && key != "default")
                    font = GetCyrillicFont(null);
                if (font == null && !string.IsNullOrEmpty(OsFontFallback.Value))
                    font = TMP_FontAsset.CreateFontAsset(OsFontFallback.Value, "Regular");
            }
            catch (Exception e)
            {
                Log.LogError("Не вдалося створити шрифт для " + key + ": " + e);
            }
            if (font != null)
            {
                font.name = "UA fallback (" + key + ")";
                font.isMultiAtlasTexturesEnabled = true;
                UnityEngine.Object.DontDestroyOnLoad(font);
                Log.LogInfo("Шрифт з кирилицею для " + key + " готовий");
            }
            FontCache[key] = font;
            return font;
        }

        private static void ScanFonts()
        {
            if (_fontsScanned) return;
            _fontsScanned = true;
            string dir = Path.Combine(PluginDir, "fonts");
            if (!Directory.Exists(dir)) return;
            foreach (var f in Directory.GetFiles(dir))
            {
                string ext = Path.GetExtension(f).ToLowerInvariant();
                if (ext == ".ttf" || ext == ".otf")
                    FontFiles[Path.GetFileNameWithoutExtension(f)] = f;
            }
        }
    }

    /// <summary>Віддає таблиці для нашої мови, збудовані з англійських + переклад.</summary>
    internal class UkTableProvider : ITableProvider
    {
        public AsyncOperationHandle<TTable> ProvideTableAsync<TTable>(string tableCollectionName, Locale locale)
            where TTable : LocalizationTable
        {
            if (!Plugin.IsOurLocale(locale)) return default; // звичайне завантаження

            var rm = Addressables.ResourceManager;
            if (typeof(TTable) == typeof(StringTable))
            {
                // TODO: якщо таблиці гри мають інший адрес у Addressables — поправити тут
                var enHandle = Addressables.LoadAssetAsync<StringTable>(tableCollectionName + "_en");
                return rm.CreateChainOperation<TTable, StringTable>(enHandle, h =>
                {
                    if (h.Status != AsyncOperationStatus.Succeeded || h.Result == null)
                        return rm.CreateCompletedOperation<TTable>(null, "Не знайдено англійську таблицю " + tableCollectionName);
                    return rm.CreateCompletedOperation((TTable)(LocalizationTable)Plugin.BuildTable(h.Result, tableCollectionName), null);
                });
            }
            // таблиці ресурсів (картинки): НЕ віддавати англійську таблицю (у Dressmaker це дало порожній логотип) —
            // default + FallbackLocale(en) і гра сама візьме англійські ресурси
            return default;
        }
    }

    internal static class Patches
    {
        // написи, створені під час гри (кнопки в спливних вікнах тощо)
        [HarmonyPatch(typeof(TextMeshProUGUI), "OnEnable")]
        [HarmonyPostfix]
        private static void TextEnabled(TextMeshProUGUI __instance) => Plugin.ApplyAutoSize(__instance);

        // ---- TODO: патчі під конкретну гру (знайти в декомпіляції, див. docs/PLAYBOOK.md) ----
        //
        // 1) Назва мови в меню. Якщо меню бере CultureInfo.NativeName — буде «українська» з малої.
        //    Dressmaker:
        //    [HarmonyPatch(typeof(LanguageSelectorPopup), "NativeName")] [HarmonyPostfix]
        //    static void NativeName(Locale locale, ref string __result)
        //    { if (Plugin.IsOurLocale(locale)) __result = Plugin.DisplayName.Value; }
        //
        // 2) Власна система шрифтів для мов (щоб кожному шрифту гри — свій кириличний).
        //    Dressmaker:
        //    [HarmonyPatch(typeof(LocaleFontFallbacks), nameof(LocaleFontFallbacks.Get))] [HarmonyPostfix]
        //    static void FontFallback(TMP_FontAsset latin, Locale locale, ref TMP_FontAsset __result)
        //    { if (__result == null && latin != null && Plugin.IsOurLocale(locale)) __result = Plugin.GetCyrillicFont(latin); }
        //
        // 3) Рядки, які гра бере не з таблиць, а з коду/ассетів з англійським fallback
        //    (у Dressmaker — назви деталей з номером "Panel/BodiceButtonPlacket1": ключа немає → англійська).
        //    Патч на метод-обгортку гри: якщо результат == fallback — знайти переклад іншим способом.
    }
}
