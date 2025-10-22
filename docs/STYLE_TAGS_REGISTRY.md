# Style Tags Registry

Theme kits, props, and battle overlays converge on a shared set of style tags. The
registry below gives modders a single source of truth when building dashboards,
filters, or automation that pivots on tone.

Tags appear in:
- Theme kits (`comfyvn/themes/templates.py`, see `docs/THEME_KITS.md`).
- Theme wizard responses (`metadata.style_tags`, `mutations.style_tags`).
- Props manager and battle systems via `docs/VISUAL_STYLE_MAPPER.md`.

| Tag                 | Description                                               | Primary Theme Kits                      |
|---------------------|-----------------------------------------------------------|-----------------------------------------|
| `action`            | High-energy heroics, kinetic cuts, comic punch            | Superhero                               |
| `airship`           | Dirigible decks, rope lattices, sky vistas                | Steampunk (Airship Deck)                |
| `atrium`            | Corporate glass atriums and elevated promenades           | Cyberpunk (Corporate)                  |
| `battle`            | On-deck clashes or storm duels                            | Pirate (Tempest Deck)                  |
| `battlefield`       | Campaign staging grounds, banners, distant drums          | Historical (Battlefield)               |
| `brass`             | Polished brass, riveted machinery, alchemical gauges      | Steampunk                               |
| `bridge`            | Command bridges, holo tables, flagship command            | Space Frontier                           |
| `cafe`              | Rainy windows, latte art, neighborhood spots              | Cozy (Cafe)                              |
| `camp`              | Makeshift shelters, recycled tech, ration logistics       | Post-Apoc (Refuge)                      |
| `campaign`          | Pre-battle councils, war table strategy                    | Historical (Battlefield)               |
| `campus`            | School corridors, clubs, classroom banter                  | Modern School                            |
| `citadel`           | Banner-lined halls, marble light, courtly debates         | High Fantasy (Citadel)                  |
| `city`              | Metropolis skylines, rooftop silhouettes                  | Superhero                               |
| `civilians`         | Public promenades, colony concourses                      | Space Frontier (Colony)                 |
| `colony`            | Terraform domes, concourse stalls                         | Space Frontier (Colony)                 |
| `command`           | Mission control rooms, live briefing stages               | Superhero (HQ)                          |
| `corporate`         | Executive-grade spaces, mirrored glass, security drones   | Cyberpunk (Corporate)                  |
| `cosmic`            | Stellar anomalies, nebula hues, research labs             | Cosmic                                   |
| `court`             | Diplomatic courts, banner halls, heraldry                 | High Fantasy (Citadel)                  |
| `cozy`              | Hearthside calm, blankets, gentle lighting                | Cozy                                     |
| `crime`             | Noir investigations, smoky dealings                       | Urban Noir                              |
| `cyberpunk`         | Neon blades, augmented city cores                         | Cyberpunk                               |
| `dust`              | Sandblasted streets, rusted infrastructure                | Post-Apoc                               |
| `eldritch`          | Anomalous sigils, unsettling resonance                    | Cosmic (Eldritch)                       |
| `festival`          | Lantern strings, booths, handheld camera drift            | Modern School (Festival)                |
| `field`             | Open training grounds, dust kicked by mechs               | Mecha (Training Field)                  |
| `fog`               | Low-lying mist, graveyard gloom                           | Gothic (Graveyard)                      |
| `future`            | Hypermodern city cores, holographic signage               | Cyberpunk                               |
| `gothic`            | Candlelit cathedrals, gothic romance                      | Gothic                                   |
| `graveyard`         | Tombstones, willow silhouettes, nocturnal vows            | Gothic (Graveyard)                      |
| `hangar`            | Maintenance bays, cranes, diagnostic HUDs                 | Mecha                                   |
| `high_fantasy`      | Heroic quests, elven glades, legendary relics             | High Fantasy                            |
| `high_seas`         | Open water, rigging, nautical vistas                      | Pirate                                   |
| `historical`        | Tea houses, scrolls, period etiquette                     | Historical                              |
| `home`              | Domestic warmth, keepsakes, soft lighting                 | Cozy                                     |
| `hq`                | Mission control centers, multi-monitor pits               | Superhero (HQ)                          |
| `industrial`        | Steel beams, steam power, machine rhythm                  | Steampunk                               |
| `magic`             | Arcane rituals, enchanted flora, runic motifs             | High Fantasy                            |
| `mecha`             | Piloted frames, hydraulics, mechanical scale              | Mecha                                   |
| `melancholy`        | Somber vows, introspective ritual beats                   | Gothic                                   |
| `military`          | Briefing alarms, regimented cadence                       | Mecha                                   |
| `neon`              | Saturated neon strips, holograms, chromatic shifts        | Cyberpunk                               |
| `night`             | After-dark energy, lantern glow, moody lighting           | Modern School (Festival), Urban Noir    |
| `noir`              | Rain-slick alleys, venetian blinds, smoky speakeasies     | Urban Noir                              |
| `period_drama`      | Court intrigue, delicate etiquette                        | Historical                              |
| `pirate`            | Jolly roger bravado, deck duels, sea lore                 | Pirate                                   |
| `post_apocalyptic`  | Scavenger grit, improvised settlements                    | Post-Apoc                               |
| `quest`             | Fellowship journeys, bannered halls                       | High Fantasy                            |
| `rain`              | Window streaks, umbrella strolls, ambient showers         | Cozy (Cafe)                              |
| `refuge`            | Communal shelters, lantern clusters, ration storage       | Post-Apoc (Refuge)                      |
| `ritual`            | Ceremonial vows, ancestral rites, reliquaries             | Gothic                                   |
| `science`           | Research labs, consoles, data analysis                    | Cosmic                                   |
| `scifi`             | Clean specular panels, holo projectors                    | Space Frontier                           |
| `sky`               | Cloud banks, open air decks, aerial vistas                | Steampunk (Airship)                     |
| `slice_of_life`     | Everyday campus life, lighthearted club energy            | Modern School                            |
| `space`             | Bridge command, starlit navigation                         | Space Frontier                           |
| `speakeasy`         | Jazz lounges, smoky haze, whispered deals                 | Urban Noir (Speakeasy)                  |
| `stakeout`          | Surveillance rigs, patient observation                    | Urban Noir (Stakeout)                   |
| `steampunk`         | Gearwork, clockwork gadgets, aether tech                  | Steampunk                               |
| `storm`             | Tempestuous decks, lightning flashes, heavy seas          | Pirate (Tempest), Gothic (Graveyard)    |
| `superhero`         | Hero silhouettes, skyline beacons                         | Superhero                               |
| `survival`          | Scarcity mindset, repurposed infrastructure               | Post-Apoc                               |
| `swashbuckler`      | Daring escapades, swinging lines, bold color              | Pirate                                   |
| `tradition`         | Heritage rituals, calligraphy, tatami textures            | Historical                              |
| `training`          | Field drills, instructor critiques, telemetry overlays    | Mecha (Training Field)                  |
| `urban`             | Dense city fabric, sodium vapor pools, concrete grit      | Urban Noir                              |
| `warmth`            | Ember glow, knit textures, quiet comfort                  | Cozy                                     |
| `youth`             | Energetic student life, bright color pops                 | Modern School                            |

### Accessibility Tags
Accessibility variants append dedicated tags so renderers and dashboards can react
without parsing LUT names.

| Tag                           | Description                                  |
|-------------------------------|----------------------------------------------|
| `accessibility_high_contrast` | High-contrast palette, highlight-safe camera |
| `accessibility_color_blind`   | Daltonized palette tweaks, safe accent pairs |

## Usage Notes
- The Theme Wizard exposes `metadata.style_tags` and `mutations.style_tags`; both are
  sorted and deduplicated so diff viewers remain stable.
- Props and battle payloads consume the same vocabulary. When you invent a new tag,
  update this document and the visual style mapper so negotiations stay cohesive.
- Accessibility tags are additive—do not strip the base creative tags when rendering
  alternate variants.
