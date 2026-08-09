class_name Balance
## Every gameplay tuning number lives here — see DESIGN.md ("keep them in one
## balance.gd so tuning never means hunting through scenes").

const WALK_SPEED: float = 1.5           # m/s default gait
const RUN_SPEED: float = 4.5            # m/s fast gait (double-tap to toggle)
const DOUBLE_TAP_WINDOW: float = 0.3    # seconds between taps that counts as a double-tap
const JUMP_VELOCITY: float = 8.2        # m/s upward on tap (apex ~1.87 m clears the 1.7 m barriers)
const JUMP_BUFFER: float = 0.2          # seconds a tap stays queued before landing
const GRAVITY: float = 18.0             # m/s^2 (snappier than earth for game feel)
const CHECKPOINT_SPACING: float = 40.0  # meters of route between checkpoints
const FALL_KILL_DEPTH: float = 12.0     # meters below last ground contact = death
const RESPAWN_HEIGHT: float = 3.0       # spawn this far above the route point
const STEP_HEIGHT: float = 0.65         # ledges up to this tall are auto-climbed
const STEP_PROBE_AHEAD: float = 0.55    # how far ahead to look for a step
const STEER_SENSITIVITY: float = 0.006  # radians of turn per pixel of finger slide
const KEY_TURN_RATE: float = 2.6        # radians/second for A/D key turning
const HAZARDS_LETHAL: bool = false      # experiment 2026-08-07: pilgrimage mode —
										# obstacles are scenery; falls still respawn
const MINIMAP_WORLD_SIZE: float = 460.0 # world meters covered by assets/ui/minimap.png
										# (must match ORTHO in the map render script)
