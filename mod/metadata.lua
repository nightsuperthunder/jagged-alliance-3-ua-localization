return PlaceObj('ModDef', {
	'title', "@TITLE@",
	'description', "@DESCRIPTION@",
	'id', "@ID@",
	'author', "nightsuperthunder",
	'version_major', @VERSION_MAJOR@,
	'version_minor', @VERSION_MINOR@,
	'version', @REVISION@,
	'lua_revision', 233360,
	'saved_with_revision', 366685,
	'code', {
		"Code/UkrLoc.lua",
	},
	'loctables', {
		{
			filename = "@CSV@",  -- ModsLoadLocTables prepends Mod/<id>/ itself
			language = "@LANGUAGE@",
		},
	},
	'default_options', {},
	'saved', @SAVED@,
})
