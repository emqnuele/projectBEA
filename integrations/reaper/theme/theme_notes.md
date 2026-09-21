# AETHERWOUND Theme — Installation and Customization Notes

---

## Theme Approach

The AETHERWOUND theme is NOT a binary `.ReaperThemeZip` file created in isolation. Instead, it uses a hybrid approach:

1. **Theme customization script** (`AETHERWOUND_Theme_Apply.lua`) — applies basic customization programmatically and provides reference documentation.
2. **Manual theme customization instructions** (this file) — describes how to manually apply the AETHERWOUND palette in REAPER's theme editor and save it as a permanent theme file.
3. **Future binary theme file** (`AETHERWOUND_Theme.ReaperThemeZip`) — can be created by saving a manually customized theme; this file is portable and installable on any REAPER installation.

---

## Installation Process

### Step 1: Load the Customization Script
In REAPER:
- Actions > Show action list > ReaScript: Load
- Select `~/projectSHURA/integrations/reaper/theme/AETHERWOUND_Theme_Apply.lua`
- Run the script (optional — informational only)

### Step 2: Apply Theme Settings Manually (Recommended)
REAPER's theme customization is primarily handled through the theme editor interface. To apply AETHERWOUND colors:

1. **Base Theme**: Start with `Default 7.0` theme (already installed).
2. **Theme Editor**: Access through REAPER's theme customization options (or via the theme adjuster script: `Default_7.0_theme_adjuster.lua` in `Scripts/Cockos/`)
3. **Apply Colors**: Use the color values documented in `docs/COLOR_SEMANTICS.md` and `AETHERWOUND_Theme_Apply.lua`.
4. **Save Theme**: Once customized, save the theme as `AETHERWOUND_Theme` (or `AETHERWOUND_7.0`) via REAPER's theme management.

### Step 3: Install Theme File (Future / Optional)
Once a customized `.ReaperThemeZip` file is saved:
- Place it in `~/Library/Application Support/REAPER/ColorThemes/`
- Load it via REAPER's theme manager (`View > Theme > Load theme`)
- The file can be committed to `theme/` in the repository for portability

---

## Color Reference Table

Quick reference for manual customization (from `docs/COLOR_SEMANTICS.md`):

| Role | Hex | RGB | Dark Variant Hex | Light Variant Hex |
|---|---|---|---|---|
| Base Background | `#0A0A12` | 10, 10, 18 | — | — |
| Surface | `#12121A` | 18, 18, 26 | — | — |
| Panel | `#16161E` | 22, 22, 30 | — | — |
| Reference | `#6A6A7A` | 106, 106, 122 | `#3A3A48` | `#A0A0B8` |
| Generated Source | `#C8A8E8` | 200, 168, 232 | `#6A4A8A` | `#E0C8F8` |
| Drums | `#F0A0D0` | 240, 160, 208 | `#8A3A60` | `#FFC0E8` |
| Bass | `#6AB8F0` | 106, 184, 240 | `#2A5080` | `#A0D8FF` |
| Melodic | `#A070E0` | 160, 112, 224 | `#4A2A70` | `#D0B0F0` |
| FX / Vocal FX | `#30D0D0` | 48, 208, 208 | `#1A6A6A` | `#A0F0F0` |
| Lead Vocal | `#F8F0F8` | 248, 240, 248 | `#705060` | `#FFF0F8` |
| Vocal Doubles | `#F0A0C0` | 240, 160, 192 | `#802A50` | `#FFC8D8` |
| Harmonies | `#D8B0E8` | 216, 176, 232 | `#704A80` | `#F0D8FF` |
| Adlibs | `#E87090` | 232, 112, 144 | `#803A50` | `#FFC0C8` |
| Bus / Architecture | `#B0A070` | 176, 160, 112 | `#504030` | `#D8C8A0` |
| Master / Final | `#F0F0F0` | 240, 240, 240 | `#333338` | `#FFFFFF` |

---

## Theme Design Principles (Reiterated)

From `docs/COLOR_SEMANTICS.md`:

- Near-black base (`#0A0A12`) — deep enough for 2 AM sessions
- Deep charcoal surfaces (`#12121A`) — readable without glare
- Pastel neon accents — visible under fatigue, not aggressive
- Semantic consistency — same role = same color family, always
- Feminine / eerie / cyber-fairy — soft glow, not gaming RGB
- No pure white on dark surfaces (except master, which is intentionally bright)
- Contrast minimum 4.5:1 for text; 3:1 for decorative elements

---

## Theme File Status

As of 2026-09-15:
- `AETHERWOUND_Theme_Apply.lua` — created (programmatic customization script)
- `AETHERWOUND_Theme.ReaperThemeZip` — NOT YET CREATED (requires manual customization and save, or programmatic theme file generation; deferred to Phase 1 completion or Phase 5)
- Theme customization notes — complete (this file + `COLOR_SEMANTICS.md`)

---

## References

- Script: `theme/AETHERWOUND_Theme_Apply.lua`
- Color documentation: `docs/COLOR_SEMANTICS.md`
- Architecture: `docs/ARCHITECTURE.md`
- REAPER theme customization reference: `~/Library/Application Support/REAPER/Scripts/Cockos/Default_7.0_theme_adjuster.lua`
