extends Node3D
## M1 game controller: checkpoints, death/respawn, chase camera, debug overlay.

@onready var _player: Player = $Player
@onready var _camera: Camera3D = $Camera3D
@onready var _level: Node3D = $GauntletLevel
@onready var _overlay: CanvasLayer = $DebugOverlay
@onready var _debug_label: Label = $DebugOverlay/DebugLabel
@onready var _msg_label: Label = $DebugOverlay/MsgLabel
@onready var _minimap: TextureRect = $DebugOverlay/Minimap
@onready var _map_blip: Polygon2D = $DebugOverlay/Minimap/ArrowBlip
@onready var _spells: Spells = $Spells
@onready var _fire_button: Button = $DebugOverlay/FireButton
@onready var _bolt_button: Button = $DebugOverlay/BoltButton
@onready var _flash_rect: ColorRect = $DebugOverlay/FlashRect

var _fire_cooldown: float = 0.0
var _bolt_cooldown: float = 0.0
var _shake_amp: float = 0.0

# aiming reticle: desktop follows the mouse; touch aims by holding a spell
# button and dragging (up/down = distance, sideways = lateral), release casts
var _reticle: MeshInstance3D
var _aiming: String = ""
var _aim_vec: Vector2 = Vector2.ZERO
var _aim_target: Vector3 = Vector3.INF

const MAX_IMPORTED_LIGHTS: int = 2  # +1 directional HellSun = 3 total (budget)

var deaths: int = 0
var last_checkpoint: float = 0.0
var _respawn_age: float = 1e9
var _orbit_yaw: float = 0.0
var _was_walking: bool = false
var _spawn_node: Node3D = null
var run_time: float = 0.0
var finished: bool = false
var _msg_timer: float = 0.0
var _debug_accum: float = 0.0
var _debug_enabled: bool = false

func _ready() -> void:
	_cap_lights()
	_player.route = $RoutePath
	_player.died.connect(_on_player_died)
	_player.reset_at(0.0)
	# an Empty named "Spawn" in the world model overrides the default start
	_spawn_node = _level.find_child("Spawn*", true, false)
	if _spawn_node:
		_player.place_at(_spawn_node.global_position, _spawn_node.rotation.y)
	_spells.exploded.connect(func(_p: Vector3) -> void: _shake(0.35))
	_spells.exclude_rids = [_player.get_rid()]
	_build_reticle()
	if DisplayServer.is_touchscreen_available():
		_fire_button.button_down.connect(_begin_aim.bind("fire"))
		_bolt_button.button_down.connect(_begin_aim.bind("bolt"))
		_fire_button.button_up.connect(_release_aim)
		_bolt_button.button_up.connect(_release_aim)
		_fire_button.gui_input.connect(_aim_drag)
		_bolt_button.gui_input.connect(_aim_drag)
	else:
		_fire_button.pressed.connect(_cast_fire)
		_bolt_button.pressed.connect(_cast_bolt)
	_debug_enabled = _detect_debug()
	_debug_label.visible = _debug_enabled

func _build_reticle() -> void:
	_reticle = MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2(2.4, 2.4)
	quad.orientation = PlaneMesh.FACE_Y
	_reticle.mesh = quad
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://assets/shaders/reticle.gdshader")
	mat.render_priority = 3
	_reticle.material_override = mat
	_reticle.custom_aabb = AABB(Vector3(-1000, -1000, -1000), Vector3(2000, 2000, 2000))
	_reticle.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_reticle.visible = false
	add_child(_reticle)

func _begin_aim(kind: String) -> void:
	_aiming = kind
	_aim_vec = Vector2.ZERO

func _aim_drag(event: InputEvent) -> void:
	if _aiming == "":
		return
	if event is InputEventScreenDrag:
		_aim_vec += (event as InputEventScreenDrag).relative
	elif event is InputEventMouseMotion:
		var motion: InputEventMouseMotion = event as InputEventMouseMotion
		if motion.button_mask != 0:
			_aim_vec += motion.relative

func _release_aim() -> void:
	if _aiming == "":
		return
	_aim_target = _touch_aim_pos()
	var kind: String = _aiming
	_aiming = ""
	if kind == "fire":
		_cast_fire()
	else:
		_cast_bolt()
	_aim_target = Vector3.INF

func _touch_aim_pos() -> Vector3:
	var f: Vector3 = _player.facing_dir()
	var right := Vector3(-f.z, 0.0, f.x)
	var dist: float = clampf(8.0 - _aim_vec.y * 0.045, 4.0, 25.0)
	var lateral: float = clampf(_aim_vec.x * 0.045, -12.0, 12.0)
	return _ground_snap(_player.global_position + f * dist + right * lateral)

func _on_player_died(cause: String) -> void:
	deaths += 1
	var msg: String = "YOUR ASSETS HAVE BEEN LIQUIDATED"
	if cause == "lava":
		msg = "CONSUMED BY LIQUIDITY"
	elif cause == "obstacle":
		msg = "MARKET COLLISION — POSITION CLOSED"
	_show_message(msg)
	# cascade-breaker: dying seconds after a respawn means the spawn point
	# itself is bad — fall back one checkpoint instead of looping forever
	if _respawn_age < 3.0:
		last_checkpoint = maxf(0.0, last_checkpoint - Balance.CHECKPOINT_SPACING)
	_respawn_age = 0.0
	# respawn at the authored Spawn point in the open world, else the route
	if _spawn_node:
		_player.place_at(_spawn_node.global_position, _spawn_node.rotation.y)
	else:
		_player.reset_at(last_checkpoint)

func _aim_point(max_range: float) -> Vector3:
	## Desktop: raycast through the mouse cursor to the world. Touch devices
	## fall back to a fixed point ahead of the character's facing.
	var fallback: Vector3 = _player.global_position + _player.facing_dir() * 8.0
	if DisplayServer.is_touchscreen_available():
		return _ground_snap(fallback)
	var mouse: Vector2 = get_viewport().get_mouse_position()
	var from: Vector3 = _camera.project_ray_origin(mouse)
	var dir: Vector3 = _camera.project_ray_normal(mouse)
	var space := _player.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(from, from + dir * 140.0)
	var hit: Dictionary = space.intersect_ray(q)
	if hit.is_empty():
		return _ground_snap(fallback)
	var at: Vector3 = hit.position
	var offset: Vector3 = at - _player.global_position
	if offset.length() > max_range:
		at = _ground_snap(_player.global_position + offset.normalized() * max_range)
	return at

func _ground_snap(point: Vector3) -> Vector3:
	var space := _player.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(point + Vector3(0, 6, 0),
			point + Vector3(0, -12, 0))
	var hit: Dictionary = space.intersect_ray(q)
	return hit.position if not hit.is_empty() else point

func _cast_fire() -> void:
	if _fire_cooldown > 0.0 or _player.state != Player.State.RUNNING:
		return
	_fire_cooldown = 0.7
	_player.play_cast("attack_1", 1.0)
	_shake(0.1)
	var target: Vector3 = _aim_target if _aim_target != Vector3.INF else _aim_point(30.0)
	# release the fireball at the swing's apex
	get_tree().create_timer(0.45).timeout.connect(func() -> void:
		var origin: Vector3 = _player.staff_tip.global_position \
				if _player.staff_tip else _player.global_position + Vector3(0, 1.2, 0)
		var dir: Vector3 = (target + Vector3(0, 0.25, 0) - origin)
		if dir.length_squared() < 0.25:
			_spells.cast_fire(origin, _player.facing_dir(), 0.10)
		else:
			_spells.cast_fire(origin, dir.normalized(), 0.0, target))

func _cast_bolt() -> void:
	if _bolt_cooldown > 0.0 or _player.state != Player.State.RUNNING:
		return
	_bolt_cooldown = 1.2
	_player.play_cast("attack_1", 1.1)
	var at: Vector3 = _aim_target if _aim_target != Vector3.INF else _aim_point(25.0)
	get_tree().create_timer(0.75).timeout.connect(func() -> void:
		_spells.cast_bolt(at)
		_shake(0.45)
		_screen_flash(0.35))

func _screen_flash(strength: float) -> void:
	_flash_rect.color.a = strength
	var tween := create_tween()
	tween.tween_property(_flash_rect, "color:a", 0.0, 0.28)

func _shake(amount: float) -> void:
	_shake_amp = maxf(_shake_amp, amount)

func _show_message(text: String) -> void:
	_msg_label.text = text
	_msg_label.visible = true
	_msg_timer = 1.4

func _process(delta: float) -> void:
	if not finished:
		run_time += delta
	_respawn_age += delta

	# advance checkpoint marker
	var cp: float = floorf(_player.progress / Balance.CHECKPOINT_SPACING) * Balance.CHECKPOINT_SPACING
	if cp > last_checkpoint and _player.state != Player.State.DEAD:
		last_checkpoint = cp

	# look-then-walk: the standing camera orbit becomes the new heading
	var walking_now: bool = _player.is_walking()
	if walking_now and not _was_walking:
		_player.commit_look(_orbit_yaw)
		_orbit_yaw = 0.0
	_was_walking = walking_now

	# finish line (progress is a projection now, so also require proximity)
	if not finished and _player.progress >= _player.route_length() - 0.5 \
			and _player.distance_to_route_end() < 5.0:
		finished = true
		_player.stop()
		_show_message("GAUNTLET CLEARED — %d s · %d liquidation(s)" % [int(run_time), deaths])
		_msg_timer = 60.0

	if _fire_cooldown > 0.0:
		_fire_cooldown -= delta
	if _bolt_cooldown > 0.0:
		_bolt_cooldown -= delta

	# aiming reticle: touch shows it while holding a spell button; desktop
	# pins it to the mouse whenever the player is in control
	if _aiming != "":
		_reticle.visible = true
		_reticle.global_position = _touch_aim_pos() + Vector3(0, 0.08, 0)
	elif not DisplayServer.is_touchscreen_available() \
			and _player.state == Player.State.RUNNING:
		_reticle.visible = true
		_reticle.global_position = _aim_point(30.0) + Vector3(0, 0.08, 0)
	else:
		_reticle.visible = false
	_chase_camera(delta)
	_update_minimap()

	if _msg_timer > 0.0:
		_msg_timer -= delta
		if _msg_timer <= 0.0:
			_msg_label.visible = false

	if _debug_enabled:
		_update_debug(delta)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key: InputEventKey = event as InputEventKey
		if key.pressed and not key.echo and key.keycode == KEY_Z:
			_cast_fire()
			return
		if key.pressed and not key.echo and key.keycode == KEY_X:
			_cast_bolt()
			return
	# while standing (or in a scripted stop): drag orbits the camera
	var can_orbit: bool = _player.is_standing() or _player.state == Player.State.STOPPED
	if event is InputEventScreenDrag and can_orbit:
		_orbit_yaw += (event as InputEventScreenDrag).relative.x * 0.008
	elif event is InputEventMouseMotion and can_orbit:
		var motion: InputEventMouseMotion = event as InputEventMouseMotion
		if motion.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_orbit_yaw += motion.relative.x * 0.008

func _update_minimap() -> void:
	# world (x, z) -> map pixels; the image is a top-down ortho render centered
	# on the world origin covering MINIMAP_WORLD_SIZE meters
	var s: float = Balance.MINIMAP_WORLD_SIZE
	var pos: Vector3 = _player.global_position
	var uv: Vector2 = Vector2((pos.x + s * 0.5) / s, (pos.z + s * 0.5) / s)
	_map_blip.position = uv.clamp(Vector2.ZERO, Vector2.ONE) * _minimap.size
	var h: float = _player.rotation.y
	_map_blip.rotation = atan2(-sin(h), cos(h))

func _chase_camera(delta: float) -> void:
	var back: Vector3 = _player.global_transform.basis.z
	if _player.is_standing() or _player.state == Player.State.STOPPED:
		back = back.rotated(Vector3.UP, _orbit_yaw)
	else:
		_orbit_yaw = 0.0
	var target_pos: Vector3 = _player.global_position + back * 4.5 + Vector3(0.0, 2.2, 0.0)
	var w: float = 1.0 - exp(-6.0 * delta)
	_camera.global_position = _camera.global_position.lerp(target_pos, w)
	if _shake_amp > 0.003:
		_camera.global_position += Vector3(randf_range(-1, 1), randf_range(-1, 1),
				randf_range(-1, 1)) * _shake_amp * 0.12
		_shake_amp *= exp(-7.0 * delta)
	_camera.look_at(_player.global_position + Vector3(0.0, 1.2, 0.0))

func _cap_lights() -> void:
	var lights: Array[Node] = _level.find_children("*", "Light3D", true, false)
	var kept: int = 0
	for node: Node in lights:
		var light: Light3D = node as Light3D
		light.shadow_enabled = false
		kept += 1
		if kept > MAX_IMPORTED_LIGHTS:
			light.visible = false

func _detect_debug() -> bool:
	if OS.has_feature("editor"):
		return true
	if OS.has_feature("web"):
		var flagged: Variant = JavaScriptBridge.eval(
			"new URLSearchParams(window.location.search).has('debug')", true)
		return bool(flagged)
	return false

func _update_debug(delta: float) -> void:
	_debug_accum += delta
	if _debug_accum < 0.25:
		return
	_debug_accum = 0.0
	_debug_label.text = "FPS %d\nDraw calls %d\nPrimitives %dK\nTex mem %.1f MB\nProgress %dm / %dm\nDeaths %d\nState %s" % [
		int(Performance.get_monitor(Performance.TIME_FPS)),
		int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)),
		int(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME) / 1000.0),
		Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0,
		int(_player.progress), int(_player.route_length()),
		deaths,
		("WALKING" if _player.is_walking() else "STANDING")
				if _player.state == Player.State.RUNNING
				else Player.State.keys()[_player.state],
	] + "\nTaps %d · Jumps %d · Gait %s" % [_player.taps_registered, _player.jumps_done,
			"RUN" if _player.fast_gait else "WALK"]
