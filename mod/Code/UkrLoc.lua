-- Ukrainian localization: (re)apply the mod's translation table.
-- The engine rebuilds TranslationTable from the base game (LoadTranslationTables) on language changes and
-- during startup; mod tables loaded earlier are lost then, so load ours again right after each rebuild.

local csv = CurrentModPath .. "English.csv"
local probe = 328054656910 -- "OPTIONS" in the main menu, used only for the log line

local function log(...)
	print("[UkrLoc]", ...)
end

local function ApplyUkr(reason)
	if GetLanguage() ~= "English" then
		log(reason, "skipped, language is", GetLanguage())
		return false
	end
	-- io.* is not available to mod code; LoadTranslationTableFile returns false if the file is missing/empty
	local ok, loaded = pcall(LoadTranslationTableFile, csv)
	log(reason, ok and (loaded and "applied" or "file not loaded: " .. csv) or ("error: " .. tostring(loaded)),
		"probe =", tostring(TranslationTable[probe]))
	return ok and loaded
end

-- wrap once per definition of LoadTranslationTables (a Lua reload redefines it, and reruns this file)
if SharedModEnv.UkrLocWrapper ~= LoadTranslationTables then
	local base_LoadTranslationTables = LoadTranslationTables
	local function wrapper(...)
		base_LoadTranslationTables(...)
		if ApplyUkr("after LoadTranslationTables") then
			Msg("TranslationChanged")
		end
	end
	local ok, err = pcall(function() LoadTranslationTables = wrapper end)
	if ok then
		SharedModEnv.UkrLocWrapper = wrapper
	end
	log("wrap LoadTranslationTables:", ok and "ok" or tostring(err))
end

ApplyUkr("code load")

-- safety net: whatever happens during startup, re-apply once the main menu is up
CreateRealTimeThread(function()
	Sleep(3000)
	log("before delayed apply, probe =", tostring(TranslationTable[probe]))
	if ApplyUkr("delayed") then
		Msg("TranslationChanged")
	end
end)
