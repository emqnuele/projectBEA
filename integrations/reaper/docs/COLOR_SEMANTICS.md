# AETHERWOUND COLOR SEMANTICS — REAPER PRODUCTION PALETTE

Version: 1.0 | Date: 2026-09-15 | Author: SHURA
Status: ACTIVE — applied to new AETHERWOUND templates; does not override existing AW01 project colors

---

## Design Principles

- Near-black base (#0A0A12) — deep enough to feel like a terminal / dark-web environment
- Deep charcoal surfaces (#12121A) — readable without glare at 2 AM
- Pastel neon accents — readable under fatigue, not aggressive
- Semantic consistency — same role = same color family, always
- Feminine / eerie / cyber-fairy aesthetic — soft glow, not gaming RGB
- No pure white (#FFFFFF) on dark surfaces — reduces eye strain
- Contrast minimum: 4.5:1 for text; 3:1 for decorative elements

---

## Semantic Color Mapping

Each track type receives a base color, a dark variant (folders/buses), a light variant (items/items selected), and a glow/accent note.

### REFERENCE / NEUTRAL
Role: Playback reference tracks, comparison sources, working mix references
Base: `#6A6A7A` (muted silver-gray)
Dark (folder): `#3A3A48`
Light (selected item): `#A0A0B8`
Accent: `#C0C0D0`
Usage: Reference tracks, monitor mix tracks, comparison sources
Notes: Must not compete visually with production tracks. Subtle, almost invisible until needed.

### GENERATED SOURCE / EXPERIMENTS
Role: Raw AI-generated stems, generation folder contents, unprocessed sources
Base: `#C8A8E8` (lavender)
Dark (folder): `#6A4A8A` (deep purple)
Light (selected item): `#E0C8F8` (soft lavender)
Accent: `#DCC0FF` (lavender glow)
Usage: `01_GENERATION` folder and all children
Notes: Lavender = the "machine-born" sound. Distinct from human-vocal or hand-played tracks. Should feel cold and synthetic, but beautiful.

### DRUMS
Role: Drum stems, percussion, rhythmic layers
Base: `#F0A0D0` (pastel pink)
Dark (folder): `#8A3A60` (rose-dark)
Light (selected item): `#FFC0E8` (soft pink)
Accent: `#FFC8F0` (pink glow)
Usage: `02_STEMS/DRUMS`, individual drum tracks, percussion folders
Notes: Pink is the drum voice. Soft enough not to dominate the mixer, warm enough to feel alive.

### BASS
Role: Bass instruments, sub-bass, bass stems
Base: `#6AB8F0` (electric blue)
Dark (folder): `#2A5080` (deep navy-blue)
Light (selected item): `#A0D8FF` (ice blue)
Accent: `#A0E0FF` (cyan-blue glow)
Usage: `02_STEMS/BASS`, bass tracks
Notes: Blue = depth, weight, low-frequency authority. Should feel cool and grounded.

### MELODIC / HARMONIC
Role: Synths, pads, melodic instruments, harmonic layers (non-vocal)
Base: `#A070E0` (purple)
Dark (folder): `#4A2A70` (deep violet)
Light (selected item): `#D0B0F0` (lavender-violet)
Accent: `#D0B0FF` (violet glow)
Usage: `02_STEMS/MELODIC`, harmonic instrument tracks
Notes: Purple sits between the synthetic (lavender) and the emotional (pink/blue). It is the "magic" layer.

### FX / PROCESSING / SOUND DESIGN
Role: FX stems, atmospheric effects, processing chains, experimental audio
Base: `#30D0D0` (cyan / neon cyan)
Dark (folder): `#1A6A6A` (deep teal)
Light (selected item): `#A0F0F0` (pale cyan)
Accent: `#C0FFFF` (cyan glow)
Usage: `02_STEMS/FX`, `04_PROCESSING`, FX bus tracks
Notes: Cyan = electricity, glitch, transformation. The most "cybernetic" color in the palette.

### LEAD VOCAL
Role: Main vocal, lead performance
Base: `#F8F0F8` (near-white / pale pink-white)
Dark (folder): `#705060`
Light (selected item): `#FFF0F8` (soft white-pink)
Accent: `#FFC0D0` (pink-white glow)
Usage: `03_VOCALS/LEAD`, lead vocal track
Notes: Lead vocal must be the brightest object in the mix. Near-white with a pink undertone — pure, present, vulnerable.

### VOCAL DOUBLES
Role: Double-tracked vocals, unison doubles, thickening layers
Base: `#F0A0C0` (soft rose-pink)
Dark (folder): `#802A50` (rose-dark)
Light (selected item): `#FFC8D8` (soft rose-white)
Accent: `#FFC8E0` (rose glow)
Usage: `03_VOCALS/DOUBLES`
Notes: Doubles are slightly darker and warmer than the lead. They should feel like an echo of the same voice, not a separate color family.

### HARMONIES / BACKING VOCALS
Role: Harmony layers, backing vocals, choral elements
Base: `#D8B0E8` (lavender-pink mix)
Dark (folder): `#704A80`
Light (selected item): `#F0D8FF` (lavender-white)
Accent: `#E8CCF8` (lavender glow)
Usage: `03_VOCALS/HARMONIES`
Notes: A blend of the synthetic (lavender) and emotional (pink). The harmonic layer bridges machine and voice.

### ADLIBS / VOCAL FX / EXPERIMENTAL VOCAL
Role: Adlibs, spoken word, vocal FX, experimental vocal processing
Base: `#E87090` (rose / coral-rose)
Dark (folder): `#803A50` (dark coral)
Light (selected item): `#FFC0C8` (soft coral)
Accent: `#FFC8D0` (coral glow)
Usage: `03_VOCALS/ADLIBS`, vocal FX bus, experimental vocal tracks
Notes: Rose is more assertive than pink. Adlibs and vocal FX have more attitude — they should stand out without becoming the lead.

### BUS TRACKS (STEM / MIX / MASTER)
Role: Stem buses, mix bus, sub-mixes, master bus
Base: `#B0A070` (dark gold / muted amber)
Dark (folder): `#504030` (brown-dark)
Light (selected item): `#D8C8A0` (pale gold)
Accent: `#E8D8B0` (gold glow)
Usage: `05_BUSES`, all bus folders
Notes: Gold = value, integration, authority. Buses are the architecture that holds everything together.

### MASTER / PREMASTER
Role: Master output, pre-master bus, loudness/reference chain
Base: `#F0F0F0` (high-contrast neutral)
Dark (folder): `#333338`
Light (selected item): `#FFFFFF`
Accent: `#C8D8FF` (icy white-blue glow)
Usage: `MASTER` track, pre-master bus, reference output
Notes: The master is the brightest and most neutral point. High contrast, no color family — it is the final authority.

---

## Base Theme Values (REAPER Theme Format — Approximated)

These are target RGB approximations for a `.ReaperThemeZip` customization. REAPER's theme engine uses 32-bit color integers and named parameter keys; these values translate to:

```
Theme base dark:     10  10  18  (#0A0A12)
Theme surface:        18  18  26  (#12121A)
Theme panel:          22  22  30  (#16161E)
Theme text primary:   240 240 245  (#F0F0F5)
Theme text muted:     160 160 168  (#A0A0A8)
Theme text dark:      100 100 110  (#64646E)

Accent cyan:          48 208 208  (#30D0D0)
Accent blue:          106 184 240 (#6AB8F0)
Accent pink:          240 160 208 (#F0A0D0)
Accent purple:        160 112 224 (#A070E0)
Accent lavender:      200 168 232 (#C8A8E8)
Accent white:         248 240 248 (#F8F0F8)
Accent gold:          176 160 112 (#B0A070)
Accent rose:          232 112 144 (#E87090)
```

### Mixer Strip Customization Goals
- Background: near-black (#0A0A12)
- Selected/armed track background: very subtle dark tint of the track's semantic color (e.g., lavender tint ~#1A1028 for generated source)
- Mute/solo buttons: cyan accent for visibility
- Meter colors: pastel gradient matching the track type (e.g., pink gradient for drums, blue gradient for bass)
- Master meter: white/ice-blue gradient, clearly distinct
- Folder header: darker version of semantic color, with glow border (if theme engine allows)

---

## Application Rules

### Rule 1: Consistency Over Creativity Per Project
Within a single AETHERWOUND project, a given role always gets the same color. Do not change colors arbitrarily for "visual interest." The visual system serves automation and readability, not decoration.

### Rule 2: Selected Items Only Slightly Brighter
The selected-state color for any role should be no more than 20-30% brighter than the base. Avoid creating a separate bright palette that competes with unselected elements. Selection should be calm and clear, not loud.

### Rule 3: Folder Colors Darker Than Children
Folder/header colors should be the darker variant of the role. Children (tracks inside the folder) use the base or selected variants. This creates visual hierarchy: the folder is the architecture; the children are the content.

### Rule 4: No Random Color Assignment
Do not use REAPER's "random color" feature for AETHERWOUND projects. Every track should have a deterministic semantic assignment. Scripts that create tracks should explicitly call `reaper.GetTrackColor()` / `reaper.SetTrackColor()` with the correct palette value, or rely on track templates that already have colors assigned.

### Rule 5: Master and Buses Visually Dominant
The master bus and major stem buses should have slightly stronger borders, brighter meters, or stronger text contrast. The mix architecture must be visible at a glance.

---

## Implementation Notes for Scripts

For Lua scripts using the REAPER API:

```lua
-- Example: set track color to lavender (generated source)
local color_r = 0.784   -- 200/255
local color_g = 0.659   -- 168/255
local color_b = 0.910   -- 232/255
reaper.SetTrackColor(track, color_r * 255 + 65536 * (color_g * 255) + 16711680 * (color_b * 255))
-- Note: REAPER uses 32-bit color integers; adjust calculation as needed
```

For Python ReaScript (`reaper_python.py`):

```python
# Example reference (not executed)
# RPR_SetTrackColor uses similar integer encoding
```

The exact encoding method will be verified during Phase 2 script development.

---

## References

- AETHERWOUND visual identity: `~/projectSHURA/docs/ARCHITECTURE_AUDIT.md` (project identity)
- SHURA identity layer: `~/projectSHURA/data/prompts/soul.md`
- REAPER theme customization reference: REAPER user guide (theme editor / `.ReaperThemeZip` format)
- Existing theme files: `~/Library/Application Support/REAPER/ColorThemes/Default_6.0.ReaperThemeZip`
