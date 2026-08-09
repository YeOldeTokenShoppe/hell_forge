class_name Player
extends CharacterBody3D
## Free-roam gauntlet walker (Michelle 2026-08-07: full turning).
## Hold (right ~2/3 of screen) = walk in the facing direction; slide the held
## finger sideways = steer. Tap left third = jump / double-tap gait.
## Desktop: W/Up = walk, A/D or arrows = turn, Space = jump, Shift = gait.
## The route Path3D no longer drives movement — it is a measuring tape:
## progress = nearest route offset, powering checkpoints, respawn and finish.
## States: RUNNING = in player control, STOPPED = scripted interaction hold,
## DEAD = awaiting respawn.

signal died(cause: String)

enum State { RUNNING, STOPPED, DEAD }

@export var route: Path3D

var state: State = State.RUNNING
var progress: float = 0.0
var last_ground_y: float = 0.0
var fast_gait: bool = false
var move_speed: float = Balance.WALK_SPEED

var taps_registered: int = 0
var jumps_done: int = 0

var _heading: float = 0.0
var _anim: AnimationPlayer
var _jump_queued: bool = false
var _jump_buffer: float = 0.0
var _action_hold: float = 0.0  # while > 0, a cast/attack anim owns the body
var _last_tap: float = -10.0
var _walk_touch_index: int = -1
var _mouse_walk: bool = false
var _key_walk: bool = false
var _key_left: bool = false
var _key_right: bool = false

var staff_tip: Node3D  # spell origin; imported with the character (staff is
                       # bone-parented in character.blend, exporter carries it)

func _ready() -> void:
	var players: Array[Node] = find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty():
		_anim = players[0] as AnimationPlayer
		for anim_name: String in ["run", "walk", "idle"]:
			if _anim.has_animation(anim_name):
				_anim.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
		# "light" and combat/reaction clips stay one-shot
	staff_tip = find_child("Staff_tip", true, false)
	_play_anim("idle", 1.0)

func is_walking() -> bool:
	return state == State.RUNNING \
			and (_walk_touch_index >= 0 or _mouse_walk or _key_walk)

func is_standing() -> bool:
	return state == State.RUNNING and not is_walking()

func facing_dir() -> Vector3:
	return Vector3(-sin(_heading), 0.0, -cos(_heading))

func play_cast(anim_name: String = "attack_1", hold: float = 1.0) -> void:
	## Full-body cast gesture; movement anims resume after the hold window.
	if _anim and _anim.has_animation(anim_name):
		_anim.speed_scale = 1.6
		_anim.play(anim_name)
		_action_hold = hold

func commit_look(yaw_delta: float) -> void:
	## Camera orbit while standing becomes the new heading when walking starts.
	_heading += yaw_delta

func stop() -> void:
	## Scripted interaction hold (dialogue, offerings); input is ignored.
	if state == State.RUNNING:
		state = State.STOPPED
		_play_anim("idle", 1.0)

func resume() -> void:
	if state == State.STOPPED:
		state = State.RUNNING

func queue_jump() -> void:
	_jump_queued = true
	_jump_buffer = Balance.JUMP_BUFFER
	taps_registered += 1

func cancel_jump() -> void:
	_jump_queued = false
	_jump_buffer = 0.0

func toggle_gait() -> void:
	fast_gait = not fast_gait
	move_speed = Balance.RUN_SPEED if fast_gait else Balance.WALK_SPEED

func reset_at(new_progress: float) -> void:
	## Respawn helper: place on the route facing along it.
	progress = new_progress
	var curve: Curve3D = route.curve
	var spawn: Vector3 = curve.sample_baked(new_progress)
	var ahead: Vector3 = curve.sample_baked(minf(new_progress + 0.5, curve.get_baked_length()))
	var dir: Vector3 = ahead - spawn
	dir.y = 0.0
	if dir.length_squared() > 0.0001:
		_heading = atan2(-dir.x, -dir.z)
	global_position = spawn + Vector3(0.0, Balance.RESPAWN_HEIGHT, 0.0)
	rotation.y = _heading
	velocity = Vector3.ZERO
	last_ground_y = spawn.y
	_jump_queued = false
	_walk_touch_index = -1
	_mouse_walk = false
	state = State.RUNNING
	_play_anim("idle", 1.0)

func route_length() -> float:
	return route.curve.get_baked_length()

func distance_to_route_end() -> float:
	return global_position.distance_to(
			route.to_global(route.curve.sample_baked(route.curve.get_baked_length())))

func _play_anim(name: String, speed: float) -> void:
	if _anim and _anim.has_animation(name) and _anim.current_animation != name:
		_anim.speed_scale = speed
		_anim.play(name)
	elif _anim:
		_anim.speed_scale = speed

func _physics_process(delta: float) -> void:
	if state == State.DEAD:
		return

	var walking: bool = is_walking()

	# steering: keys turn at a fixed rate (touch/mouse steer via input events)
	if _key_left:
		_heading += Balance.KEY_TURN_RATE * delta
	if _key_right:
		_heading -= Balance.KEY_TURN_RATE * delta

	var forward: Vector3 = Vector3(-sin(_heading), 0.0, -cos(_heading))
	if walking:
		velocity.x = forward.x * move_speed
		velocity.z = forward.z * move_speed
	else:
		velocity.x = 0.0
		velocity.z = 0.0

	# vertical: gravity + buffered jump (works standing or walking)
	velocity.y -= Balance.GRAVITY * delta
	if _jump_queued and is_on_floor() and state == State.RUNNING:
		velocity.y = Balance.JUMP_VELOCITY
		jumps_done += 1
		_jump_queued = false
		_jump_buffer = 0.0
	elif _jump_queued:
		_jump_buffer -= delta
		if _jump_buffer <= 0.0:
			_jump_queued = false

	move_and_slide()

	# step-assist only while walking and genuinely blocked
	var real_h: Vector3 = get_real_velocity()
	real_h.y = 0.0
	if walking and is_on_floor() and real_h.length() < move_speed * 0.1:
		_step_assist(forward)

	rotation.y = lerp_angle(rotation.y, _heading, 1.0 - exp(-10.0 * delta))

	# progress is measured, not driven: nearest offset along the route
	progress = route.curve.get_closest_offset(route.to_local(global_position))

	# animation follows movement: dedicated clips per gait — unless a
	# cast/attack gesture temporarily owns the body
	if _action_hold > 0.0:
		_action_hold -= delta
	elif state == State.RUNNING:
		if walking:
			_play_anim("run" if fast_gait else "walk", 1.0)
		else:
			_play_anim("idle", 1.0)

	if is_on_floor():
		last_ground_y = global_position.y
		for i: int in get_slide_collision_count():
			var col: KinematicCollision3D = get_slide_collision(i)
			if _is_named(col.get_collider(), "Lava"):
				_die("lava")
				return
			if Balance.HAZARDS_LETHAL and _is_named(col.get_collider(), "obstacle"):
				_die("obstacle")
				return

	if global_position.y < last_ground_y - Balance.FALL_KILL_DEPTH:
		_die("fall")

func _step_assist(forward: Vector3) -> void:
	var space := get_world_3d().direct_space_state
	var probe_top: Vector3 = global_position + forward * Balance.STEP_PROBE_AHEAD \
			+ Vector3(0.0, Balance.STEP_HEIGHT + 0.4, 0.0)
	var query := PhysicsRayQueryParameters3D.create(
			probe_top, probe_top + Vector3(0.0, -(Balance.STEP_HEIGHT + 0.4), 0.0))
	query.exclude = [get_rid()]
	var hit: Dictionary = space.intersect_ray(query)
	if hit.is_empty():
		return
	var rise: float = (hit["position"] as Vector3).y - global_position.y
	if rise > 0.08 and rise <= Balance.STEP_HEIGHT:
		global_position.y += rise + 0.05

func _is_named(node: Object, name_prefix: String) -> bool:
	var n: Node = node as Node
	while n != null:
		if n.name.begins_with(name_prefix):
			return true
		n = n.get_parent()
	return false

func _die(cause: String) -> void:
	if state == State.DEAD:
		return
	state = State.DEAD
	if _anim:
		_anim.pause()
	died.emit(cause)

func _register_tap() -> void:
	# tap = jump; second tap inside the window = gait toggle instead
	var now: float = Time.get_ticks_msec() / 1000.0
	if now - _last_tap < Balance.DOUBLE_TAP_WINDOW:
		cancel_jump()
		toggle_gait()
		_last_tap = -10.0
	else:
		queue_jump()
		_last_tap = now

func _in_jump_zone(pos_x: float) -> bool:
	return pos_x < get_viewport().get_visible_rect().size.x * 0.35

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		var touch: InputEventScreenTouch = event as InputEventScreenTouch
		if touch.pressed:
			if _in_jump_zone(touch.position.x):
				_register_tap()
			elif _walk_touch_index < 0:
				_walk_touch_index = touch.index
		elif touch.index == _walk_touch_index:
			_walk_touch_index = -1
	elif event is InputEventScreenDrag:
		var drag: InputEventScreenDrag = event as InputEventScreenDrag
		if drag.index == _walk_touch_index:
			_heading -= drag.relative.x * Balance.STEER_SENSITIVITY
	elif event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index == MOUSE_BUTTON_LEFT:
			if mouse.pressed:
				if _in_jump_zone(mouse.position.x):
					_register_tap()
				else:
					_mouse_walk = true
			else:
				_mouse_walk = false
	elif event is InputEventMouseMotion and _mouse_walk:
		_heading -= (event as InputEventMouseMotion).relative.x * Balance.STEER_SENSITIVITY
	elif event is InputEventKey:
		var key: InputEventKey = event as InputEventKey
		if key.keycode == KEY_W or key.keycode == KEY_UP:
			_key_walk = key.pressed
		elif key.keycode == KEY_A or key.keycode == KEY_LEFT:
			_key_left = key.pressed
		elif key.keycode == KEY_D or key.keycode == KEY_RIGHT:
			_key_right = key.pressed
		elif key.pressed and not key.echo and key.keycode == KEY_SPACE:
			_register_tap()
		elif key.pressed and not key.echo and key.keycode == KEY_SHIFT:
			toggle_gait()
