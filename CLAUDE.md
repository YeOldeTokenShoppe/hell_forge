# CLAUDE.md — The Gauntlet (Our Lady of Perpetual Profit)

Technical guardrails for this project. These decisions are settled — do not revisit them
without the owner (Michelle) explicitly asking. Game design lives in `DESIGN.md`; read it
before writing gameplay code.

## What this project is

A short (60–90 s) auto-runner gauntlet built in Godot, embedded on the Our Lady of
Perpetual Profit website, playable in **mobile browsers first** (iOS Safari is the
reference platform). Player runs a hell-forge underworld gauntlet, collects coins, spends
coins to cast fire/lightning and to light votive candles, and earns a serialized digital
trophy at the finish.

## Engine and renderer — settled

- **Godot 4.7.x stable, standard build (GDScript).** No .NET/C#. No beta/dev builds.
- **Compatibility renderer (WebGL2).** Never Forward+ or Mobile. Do not rely on
  WebGPU-only features.
- Language: GDScript with static typing (`var x: int`, typed function signatures).

## Web export — settled

These settings exist because previous attempts failed on mobile browsers. Keep all of them:

- **Thread support: OFF** (single-threaded export). This is what keeps iOS Safari stable
  and removes the COOP/COEP header requirement.
- **Audio: sample playback mode** for web. Pre-register SFX with
  `AudioServer.register_stream_as_sample()` during the loading screen. No audio bus
  effects (unsupported with sample playback).
- **Brotli/gzip compression on**; host must serve pre-compressed files with correct
  MIME types (`.wasm` → `application/wasm`).
- Size budget: **≤ 15 MB total first load** (engine + pck, compressed). Strip unused
  asset-pack content before export — ship only what levels use.
- PWA/offline support: off for v1.

## Performance budgets (mobile Compatibility renderer)

- On-screen triangles: **≤ 200 K** (asset packs are ~800 tris/model; props are cheap).
- Draw calls: **≤ 50 per gauntlet section.** Merge static level geometry into chunks;
  use `MultiMeshInstance3D` for repeated props (rocks, coins, torches, candles).
- Materials: consolidate both asset packs onto **1–2 shared atlased materials.**
- Dynamic lights: **≤ 3 active at once**, all owned by the FX light pool (below).
  Everything else is emissive materials + baked/faked lighting. **No real-time shadows.**
- Skinned characters: ≤ 30 bones each, 1–3 K tris, **≤ 8 animating concurrently.**
  (Exception: the hero unicorn keeps its finger bones — 34 total — so the hands
  articulate; the 30-bone budget applies to NPCs/villains.)
  Freeze/despawn characters behind the player; background flavor characters use simple
  transform animation on static meshes, not skeletal rigs.
- Textures: 1024 px on mobile (2048 max for the main atlas). Keep total GPU texture
  memory well under ~100 MB — iOS Safari kills the tab on memory pressure, silently.
- Particles: **`CPUParticles3D` or pooled meshes only** — no GPUParticles3D (web/mobile
  compatibility). Watch additive-blend overdraw: many SMALL particles, never large
  stacked transparent quads. Cap simultaneous explosions at 2.
- **No `Decal` nodes** (unsupported in Compatibility). Ground marks (scorch, shockwave
  rings) are flat `QuadMesh`/circle meshes with dissolve shaders, offset slightly above
  the surface.

## FX architecture (SpellManager pattern)

Port of a proven Three.js design — keep these invariants:

1. **Fixed light pool.** Allocate all `OmniLight3D` nodes at startup (pool of 3); FX
   acquire/release them by setting energy. **Never add/remove lights from the tree at
   runtime** (forces shader rebuilds → hitches).
2. **Prewarm at load.** During the loading screen, cast every spell / spawn every FX once
   far below the map so all shaders and pipelines compile before gameplay. First cast
   must never hitch.
3. **Pool everything short-lived:** scorch decals, shockwave rings, particles, bolt
   segments. No allocation during gameplay.
4. Spell shaders: `shading_mode unshaded`, `blend_add`, `depth_draw_never` for fire/
   lightning/glow; noise-based vertex displacement for flame silhouettes; lightning is a
   pooled chain of jittered cylinder segments rebuilt every ~50 ms.
5. HDR emissive + WorldEnvironment glow is desirable but **must degrade gracefully**: test
   glow cost on device; fallback is brighter additive billboards with glow off.

## Asset pipeline

- Source art is a **.blend file imported directly** (Editor Settings → FileSystem →
  Import → Blender path). Saving in Blender re-imports automatically.
- Blender conventions: apply all transforms before save; real-world scale; mesh name
  suffix **`-col`** = auto collision, **`-colonly`** = invisible collision only (use for
  edge walls).
- When merging the underworld + inferno packs: re-atlas onto shared textures, preserve
  UVs, verify scale agreement against the player character.

## Controls

- **Free-roam, player-paced** (evolved 2026-08-07: auto-runner → hold-to-walk →
  full steering — Michelle wants interaction-driven pacing and real agency).
  The route Path3D is a measuring tape only (progress/checkpoints/finish), it
  never drives movement.
- Touch: **hold right ~2/3 of screen = walk** in the facing direction;
  **slide the held finger sideways = steer**. Release = stop (standing is the
  default state). **Tap left third = jump**, double-tap = walk/run gait.
  Drag while standing = orbit camera; walking starts toward where you look.
  Spell buttons **FIRE**/**BOLT** (M2) live in the left zone above jump.
- Desktop: **W/↑** walk, **A/D** turn, **Space** jump, **Shift** gait, Z/X spells.
- No virtual joystick. Ever.

## Testing discipline

- **Milestone 0 is a pipeline proof:** platform + character exported to web and running
  on a real iPhone in Safari before any gameplay is built.
- Test on-device at every milestone, not at the end. Watch for silent tab reloads
  (= memory pressure) and first-cast hitches (= prewarm gap).
- Keep a debug overlay behind a query param (`?debug=1`): FPS, draw calls, active
  particles/lights.

## Out of scope for v1

Meta-progression/upgrade shops, candle-extinguishing hazards, capped daily trophy mints,
other-player death markers (v2 candidate), GPUParticles, .NET, multiplayer.
