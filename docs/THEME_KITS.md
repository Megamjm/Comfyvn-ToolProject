# Theme Kits

## Overview
The theme kit catalog lives in `comfyvn/themes/templates.py` and can be queried via
`GET /api/themes/templates`, `POST /api/themes/preview`, and `POST /api/themes/apply`.
Each kit bundles LUT stacks, ambience assets, music cues, prompt flavors, camera
defaults, prop clusters, and style/tag remaps so modders can restyle a project without
hand-editing every scene.

- Feature flag: `enable_themes` (default **false**). Flip it on in `config/comfyvn.json`
  before wiring the Studio panels.
- API routes: see `docs/THEME_SWAP_WIZARD.md` for payloads, curl snippets, branch
  provenance rules, and hook contracts (`on_theme_preview`, `on_theme_apply`).
- Accessibility: every kit ships `base`, `high_contrast`, and `color_blind` variants.
  Variants append accessibility style tags (`accessibility_high_contrast`,
  `accessibility_color_blind`) and tweak LUT/camera/palette stacks without discarding
  the creative intent of the base theme.

## Kit Index
| Theme          | Summary                                                         | Default Subtype     | Prompt Flavor                                   |
|----------------|-----------------------------------------------------------------|---------------------|-------------------------------------------------|
| Modern School  | Bright classrooms and festival nights for slice-of-life arcs   | Homeroom Day        | Homeroom chatter and club plans                 |
| Urban Noir     | Rain-slick neon alleys and smoky basements for mystery beats   | Back-Alley Stakeout | Detectives tracking leads through back alleys   |
| Gothic         | Shadowed cathedrals and moonlit vows for dramatic rituals      | Cathedral Nave      | Oaths whispered beneath stained glass           |
| Cosmic         | Nebula-lit observatories and eldritch experiments              | Deep-Sky Observatory| Scientists decoding stellar anomalies           |
| Cyberpunk      | Neon arteries, holograms, and corporate intrigue               | Lower Streets       | Runners weaving through corporate choke points  |
| Space Frontier | Bridge briefings, holo tables, and starlit vistas              | Command Bridge      | Captains plotting jumps across uncharted sectors|
| Post-Apoc      | Sun-bleached ruins, scavenger camps, and survival fires        | Collapsed Overpass  | Survivors bargaining for clean water            |
| High Fantasy   | Verdant glades, citadel halls, and gleaming sigils             | Elven Glade         | Companions swear oaths beneath ancient trees    |
| Historical     | Tea house intrigue, court scribes, and dusk campaigns          | Tea House           | Quiet negotiations over tea                     |
| Steampunk      | Brass foundries, dirigible decks, and alchemical gauges        | Gear Foundry        | Captains haggle over aether routes              |
| Pirate         | Salt-sprayed decks, lantern-lit gambits, and raucous crews     | Harbor Sunset       | Crews chart mutinous courses at dusk            |
| Superhero      | City skylines, signal beacons, and kinetic hero poses          | Rooftop Signal      | Team briefings high above the streets           |
| Mecha          | Towering frames, maintenance crews, and briefing alarms        | Hangar Dawn         | Pilots suit up amid hydraulic hiss              |
| Cozy           | Fireplace glow, rainy cafe breaks, and intimate conversations  | Mountain Cabin      | Friends exchange gifts beneath string lights    |

## Theme Details
Below is a quick reference for each kit. Values match the canonical data inside
`comfyvn/themes/templates.py` so previews and authored docs stay in sync.

### Modern School
- **LUT stack**: `neutral`, `daylight_soft`, `chalk_pastel`
- **Prompt flavor**: homeroom chatter and club plans
- **Palette**: `#F7F8FB` primary, `#1E6FFF` secondary, `#FDB515` accent, `#3B3F4C` neutral
- **Music**: acoustic set, uplifting mood, intensity 0.28
- **Props**: desk scatter foreground, blank banner midground, notebook scribbles UI
- **Tag remaps**: classroom assets, school posters, hallway crowd SFX
- **Style tags**: `slice_of_life`, `campus`, `youth`
- **Subtypes**:
  - *Homeroom Day* (default): window-lit classroom midday.
  - *School Festival*: lantern glow booth row, handheld camera drift, `festival`, `night` style tags.
- **Accessibility**:
  - High contrast adds `lights/festival_strings`, spotlight halo overlay, and contrast-safe camera guard.
  - Color blind shifts accent → `#118AB2`, secondary → `#8D99AE` without dropping the kit palette.

### Urban Noir
- **LUT stack**: `cool`, `noir_high_contrast`, `grain_emphasis`
- **Prompt flavor**: detectives tracking leads through back alleys
- **Palette**: `#1B1F29` primary, `#3D405B` secondary, `#FF3366` accent, `#0B132B` neutral
- **Music**: jazz set, brooding mood, intensity 0.52
- **Props**: cigarette glow foreground, streetlamp midground, film grain UI overlay
- **Tag remaps**: rain-soaked alley, venetian-blind lighting, steam vents
- **Style tags**: `noir`, `urban`, `crime`
- **Subtypes**:
  - *Back-Alley Stakeout* (default): tripod-locked cams and `stakeout` tag.
  - *Speakeasy Den*: smoky club overlays, melancholic jazz, `speakeasy`, `night` tags.
- **Accessibility**:
  - High contrast projects `ui/anchors/noir_highlight` for anchor halos.
  - Color blind shifts accent → `#F4D35E`, secondary → `#577590`.

### Gothic
- **LUT stack**: `warm`, `gothic_shadow`, `moonlit_blue`
- **Prompt flavor**: oaths whispered beneath stained glass
- **Palette**: `#2F1B41`, `#6A4C93`, `#C9ADA7`, `#160A1E`
- **Music**: orchestral, somber, intensity 0.48
- **Props**: candle clusters, stained glass midground, scrollwork UI frame
- **Tag remaps**: cathedral candles, gargoyles, clustered candle lighting
- **Style tags**: `gothic`, `melancholy`, `ritual`
- **Subtypes**:
  - *Cathedral Nave* (default): echoing halls.
  - *Graveyard Fog*: fog overlays, raven SFX, `graveyard`, `fog` tags.
- **Accessibility**: candle anchor glows; color blind accent → `#FFD166`, secondary → `#4A4E69`.

### Cosmic
- **LUT stack**: `cool`, `cosmic_violet`, `starfield_overlay`
- **Prompt flavor**: scientists decoding stellar anomalies
- **Palette**: `#0B132B`, `#1C2541`, `#5BC0BE`, `#3A506B`
- **Music**: synth set, mysterious mood, intensity 0.40
- **Props**: hologram armillary midground, constellation UI
- **Tag remaps**: observatory lab, ultraviolet lighting, star charts
- **Style tags**: `cosmic`, `eldritch`, `science`
- **Subtypes**:
  - *Deep-Sky Observatory* (default).
  - *Eldritch Storm*: anomaly SFX, rune overlays, `eldritch`, `storm` tags.
- **Accessibility**: constellation anchor halo; color blind accent → `#F4D35E`, secondary → `#4CC9F0`.

### Cyberpunk
- **LUT stack**: `vibrant`, `neon_split`, `chromatic_aberration`
- **Prompt flavor**: runners weaving through corporate choke points
- **Palette**: `#0A0E1A`, `#FF3366`, `#21FBDD`, `#111827`
- **Music**: synthwave set, driving mood, intensity 0.62
- **Props**: holo ads foreground, skyrail midground, HUD circuitry UI
- **Tag remaps**: mega-avenue backdrop, hologram lighting, hover sleds
- **Style tags**: `cyberpunk`, `neon`, `future`
- **Subtypes**:
  - *Lower Streets* (default).
  - *Corporate Atrium*: glass skybridges, `corporate`, `atrium` tags.
- **Accessibility**: neon anchor traces; color blind accent → `#FEE440`, secondary → `#2EC4B6`.

### Space Frontier
- **LUT stack**: `cool`, `sterile_white`, `starlight_reflect`
- **Prompt flavor**: captains plotting jumps across uncharted sectors
- **Palette**: `#0D1B2A`, `#1B263B`, `#70F0FF`, `#415A77`
- **Music**: ambient set, expansive mood, intensity 0.35
- **Props**: hologrid lines, command chair midground, HUD reticle UI
- **Tag remaps**: bridge command, hologrid lighting, holo tables
- **Style tags**: `space`, `bridge`, `scifi`
- **Subtypes**:
  - *Command Bridge* (default).
  - *Colony Concourse*: promenade overlays, `colony`, `civilians` tags.
- **Accessibility**: holo ping anchor ring; color blind accent → `#FFD23F`, secondary → `#4EA8DE`.

### Post-Apoc
- **LUT stack**: `warm_desaturate`, `dust_filter`, `sunset_smoke`
- **Prompt flavor**: survivors bargaining for clean water
- **Palette**: `#3D2C29`, `#735751`, `#E07A5F`, `#403D39`
- **Music**: percussion set, tense mood, intensity 0.58
- **Props**: barrel fire, warning sign, tape overlay UI
- **Tag remaps**: overpass ruins, fire barrel lighting, rusted vans
- **Style tags**: `post_apocalyptic`, `survival`, `dust`
- **Subtypes**:
  - *Collapsed Overpass* (default).
  - *Makeshift Refuge*: canvas tents, `camp`, `refuge` tags.
- **Accessibility**: flare marker anchor highlight; color blind accent → `#F6AE2D`, secondary → `#5E6F64`.

### High Fantasy
- **LUT stack**: `warm`, `storybook`, `verdant_glow`
- **Prompt flavor**: companions swear oaths beneath ancient trees
- **Palette**: `#2A9D8F`, `#264653`, `#E9C46A`, `#2F3E46`
- **Music**: orchestral set, adventurous mood, intensity 0.55
- **Props**: stone circle, banner sigils, rune UI frame
- **Tag remaps**: elven glade, sun shafts, banner sigils
- **Style tags**: `high_fantasy`, `magic`, `quest`
- **Subtypes**:
  - *Elven Glade* (default).
  - *Citadel Hall*: marble halls, `court`, `citadel` tags.
- **Accessibility**: glimmer trail on anchors; color blind accent → `#FFD166`, secondary → `#4E9F3D`.

### Historical
- **LUT stack**: `warm`, `tea_brown`, `film_grain_soft`
- **Prompt flavor**: quiet negotiations over tea
- **Palette**: `#F1E4C3`, `#8B5E3C`, `#C06014`, `#3D2B1F`
- **Music**: chamber set, reflective mood, intensity 0.33
- **Props**: tea service, paper screens, ink brush UI
- **Tag remaps**: tea houses, paper lantern lighting, calligraphy props
- **Style tags**: `historical`, `period_drama`, `tradition`
- **Subtypes**:
  - *Tea House* (default).
  - *Battlefield Dusk*: ember overlays, `campaign`, `battlefield` tags.
- **Accessibility**: paper glow anchors; color blind accent → `#B5838D`, secondary → `#6D6875`.

### Steampunk
- **LUT stack**: `warm_copper`, `smog_filter`, `brass_glow`
- **Prompt flavor**: captains haggle over aether routes
- **Palette**: `#3A2618`, `#B08968`, `#E09F3E`, `#5E503F`
- **Music**: clockwork set, driving mood, intensity 0.60
- **Props**: gauge console, gear wall, gear overlay UI
- **Tag remaps**: foundry floor, arc lighting, brass pipe props
- **Style tags**: `steampunk`, `industrial`, `brass`
- **Subtypes**:
  - *Gear Foundry* (default).
  - *Airship Deck*: cloud scud overlays, `airship`, `sky` tags.
- **Accessibility**: cog halo anchor; color blind accent → `#FFD166`, secondary → `#6A994E`.

### Pirate
- **LUT stack**: `warm`, `sunset_glow`, `spray_highlight`
- **Prompt flavor**: crews chart mutinous courses at dusk
- **Palette**: `#1C2A3A`, `#2A4D69`, `#F4A261`, `#3E3D32`
- **Music**: sea shanty set, rollicking mood, intensity 0.50
- **Props**: treasure chest, mast midground, map UI frame
- **Tag remaps**: storm decks, lantern light, jolly roger flags
- **Style tags**: `pirate`, `high_seas`, `swashbuckler`
- **Subtypes**:
  - *Harbor Sunset* (default).
  - *Tempest Deck*: heavy rain overlays, `storm`, `battle` tags.
- **Accessibility**: lantern glow anchors; color blind accent → `#FFD166`, secondary → `#577590`.

### Superhero
- **LUT stack**: `vibrant`, `comic_pop`, `deep_blue`
- **Prompt flavor**: team briefings high above the streets
- **Palette**: `#0D1F2D`, `#34495E`, `#F94144`, `#2C3E50`
- **Music**: orchestral hybrid set, heroic mood, intensity 0.70
- **Props**: hero banner, signal midground, comic panel UI
- **Tag remaps**: rooftop skyline, signal lighting, holo briefing boards
- **Style tags**: `superhero`, `city`, `action`
- **Subtypes**:
  - *Rooftop Signal* (default).
  - *Hero HQ*: hologrid panels, `hq`, `command` tags.
- **Accessibility**: signal glow anchors; color blind accent → `#FFD23F`, secondary → `#4ECDC4`.

### Mecha
- **LUT stack**: `cool`, `steel_blue`, `sparks`
- **Prompt flavor**: pilots suit up amid hydraulic hiss
- **Palette**: `#1A2A33`, `#2E4756`, `#FF9F1C`, `#14213D`
- **Music**: industrial set, tense mood, intensity 0.60
- **Props**: tool crates, frame silhouettes, HUD scanlines UI
- **Tag remaps**: dawn hangars, indicator lighting, weapon racks
- **Style tags**: `mecha`, `military`, `hangar`
- **Subtypes**:
  - *Hangar Dawn* (default).
  - *Training Field*: heat haze overlays, `training`, `field` tags.
- **Accessibility**: HUD trace anchor; color blind accent → `#FFB703`, secondary → `#4361EE`.

### Cozy
- **LUT stack**: `warm`, `ember_glow`, `soft_focus`
- **Prompt flavor**: friends exchange gifts beneath string lights
- **Palette**: `#F2E9E4`, `#C9ADA7`, `#9A8C98`, `#4A4E69`
- **Music**: acoustic set, relaxed mood, intensity 0.24
- **Props**: knit blankets, book stacks, recipe card UI
- **Tag remaps**: cabin fireplace, string light lighting, mug stacks
- **Style tags**: `cozy`, `home`, `warmth`
- **Subtypes**:
  - *Mountain Cabin* (default).
  - *Neighborhood Cafe*: rainy windows, `cafe`, `rain` tags.
- **Accessibility**: soft glow anchor; color blind accent → `#F4D35E`, secondary → `#8ECAE6`.

## Related Docs
- `docs/THEME_SWAP_WIZARD.md` — request/response payloads, branch provenance, hook payloads.
- `docs/STYLE_TAGS_REGISTRY.md` — canonical definitions for style tags referenced above.
- `docs/VISUAL_STYLE_MAPPER.md` — how style tags map into props, battle outcomes, and overlays.
