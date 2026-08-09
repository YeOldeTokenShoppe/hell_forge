# DESIGN.md — The Gauntlet of Perpetual Profit

Game design spec, v1. Technical constraints live in `CLAUDE.md` — that file wins any
conflict. All numbers below are tuning defaults, expected to change in playtesting;
keep them in one `balance.gd` (or `balance.json`) so tuning never means hunting through
scenes.

## Concept

A player-paced gauntlet walk (~60–90 seconds at a committed pace) through a
hell-forge underworld, run from the website of **Our Lady of Perpetual Profit**.
Movement is hold-to-walk along a fixed route — standing still is the default
state, and interactions happen while stopped. (Pivoted from auto-runner on
2026-08-07 after playtesting.) The player collects hell-forged coins,
spends those same coins to survive (spells) and to worship (candle offerings), and is
judged at the finish on both **wealth** and **piety**. The reward is a serialized,
dated digital trophy displayed in a public reliquary.

**Tone:** liturgical-financial satire, played straight. Death messages read like
brokerage notices ("Your assets have been liquidated"). Loading tips read like
scripture ("Blessed are the liquid, for they shall inherit the yield"). The trophy
ceremony is a canonization.

## Core loop

1. Run starts; the player freely walks/runs the gauntlet (hold to move, slide to
   steer) and releases to stop — pauses are where interactions live. The route
   is measured for checkpoints and the finish, not enforced.
2. Tap to jump; double-tap toggles walk/run; two spell buttons: FIRE and BOLT
   (see Controls in CLAUDE.md).
3. Coins line the path and reward risky lines. Hazards and villains block the way.
4. Votive candles sit on pedestals along the route; casting FIRE near one lights it
   (auto-targeted) — this is an **offering** and costs coins like any cast.
5. Checkpoints every ~20 s of route. Death = instant respawn at last checkpoint;
   deaths are counted and tax the final trophy.
6. Finish → trophy forging ceremony → result card.

Target: first clear within ~5 attempts for an average player; a clean, pious, wealthy
run should stay hard for weeks.

## Economy (tuning defaults)

- Coins available on route: **~400** (300 on the safe line, ~100 on risky lines).
- FIRE cast: **25** coins.
- BOLT cast: **40** coins (bigger punch, instant, short range).
- Candle offering: the FIRE cast that lights it (25) + **15** surcharge consumed by the
  candle = **40 per candle**.
- Candles on route: **9**. Full piety therefore costs ~360 — nearly everything you can
  carry. That is the point.
- Indulgence (skip current section OR revive without death-count): **100** coins,
  offered on the death screen. "Forgiveness is available at competitive rates."
- Casting with insufficient coins: allowed at a penalty — the shortfall is borrowed
  against your final score ("margin"), displayed in red. Debt at the finish caps the
  trophy at the lowest tier.

## Powers

- **FIRE** — lobbed projectile, medium range, area burst on impact. Kills standard
  villains, destroys wooden barriers, lights candles (priority target when in range).
- **BOLT** — instant strike at a fixed point ahead, brief stun radius. The panic
  button and the elite-villain answer. Cannot light candles (it shatters them —
  a lit candle struck by BOLT is lost; do not protect the player from this).

## Judgment: the trophy matrix

At the finish, two axes: **Wealth** = coins banked (after debts), **Piety** = candles
lit. Defaults: Wealthy ≥ 150 banked; Pious ≥ 6 of 9 candles.

| | Impious (<6) | Pious (≥6) |
|---|---|---|
| **Wealthy** | Faithless Magnate | Blessed Portfolio |
| **Poor** | Debased Coinage | Penniless Saint |

- A **deathless** run adds the prefix **Immaculate** (e.g., *Immaculate Blessed
  Portfolio*). Any margin debt at finish forces *Debased Coinage* regardless of axes.
- Every trophy is **serialized and dated**: "Trophy № 1,847 · struck 7 August 2026",
  with a player-chosen inscription (profanity-filtered), displayed in the public
  **Reliquary** page.
- Trophy is cosmetic (3D render + shareable image) AND account-bound (stored
  server-side). Stretch: downloadable GLTF of your trophy.

## The Daily Gauntlet

- One seeded layout per calendar day (UTC), identical for all players: seed drives
  hazard order, villain placement, coin/candle positions along a fixed set of route
  chunks.
- Unlimited attempts; your **best** daily result counts.
- **Share card** (image + copyable text):
  `OUR LADY OF PERPETUAL PROFIT — Daily Gauntlet #142`
  `⏱ 1:14 · 🪙 340 · 🕯 7/9 · ☠ 2 · BLESSED PORTFOLIO`
- Free-play mode uses random seeds and still forges trophies, but daily results are
  what the leaderboard ranks (fastest time among top-tier trophies).

## Backend (minimal)

- Endpoints: `POST /run/start` (issues signed session token + daily seed),
  `POST /run/finish` (token + result → validate → grant trophy), `GET /reliquary`,
  `GET /daily`.
- Anti-cheat is heuristic, not bulletproof (client game): reject finishes faster than
  the theoretical minimum run time, coins > max obtainable, candle count > 9, token
  reuse. Good enough for a fun-first site trophy; revisit only if stakes rise.
- Accounts: lightest possible — email magic link or existing site auth. Trophy grants
  keyed to account; anonymous players can play but must claim before forging.

## Website placement

- Homepage centerpiece: looping teaser video (a few hundred KB) + "**Enter the
  Forge**" CTA. The game itself loads only on the dedicated `/gauntlet` page,
  full-screen, with a themed loading litany. Never inline the engine on the homepage.

## Milestones

- **M0 — Pipeline proof.** .blend platform + character exported to web, 60 fps on a
  real iPhone in Safari. Nothing else matters until this passes.
- **M1 — Runner core.** Auto-run, jump, checkpoints, death/respawn, one hazard type.
- **M2 — Spells & candles.** SpellManager port (pools + prewarm), FIRE/BOLT, candle
  lighting, coin pickup.
- **M3 — Economy & judgment.** Costs, margin debt, trophy matrix, forging ceremony.
- **M4 — Daily & sharing.** Seeded dailies, result card, leaderboard.
- **M5 — Backend & reliquary.** Accounts, trophy persistence, public reliquary page.
- **M6 — Polish.** Tone pass on all copy, teaser video, glow tuning, soak test on
  low-end devices.

## Explicitly deferred (v2 candidates)

Other-player death memorials on the route, candle-extinguishing hazards, capped daily
trophy mints ("the forge cools after 100"), seasonal market-crash modifiers, trophy
GLTF download.
