class_name Spells
extends Node3D
## Fire spell manager — a Godot port of the battle-tested THREE.js SpellManager
## patterns: pooled lights, pooled scorch decals and shockwaves, pooled
## fireballs, CPU-particle bursts, and a prewarm pass at load so every pipeline
## compiles before the first real cast. Mobile budgets throughout.

const FIRE_SPEED: float = 17.0
const FIRE_RANGE: float = 45.0
const LIGHT_POOL_SIZE: int = 2
const FIREBALL_POOL: int = 3
const SCORCH_POOL: int = 6
const WAVE_POOL: int = 4
const TONGUES_PER_EXPLOSION: int = 6

var _shell_shader := preload("res://assets/shaders/fire_shell.gdshader")
var _scorch_shader := preload("res://assets/shaders/scorch.gdshader")
var _wave_shader := preload("res://assets/shaders/shockwave.gdshader")

var _snd_fire_fly := preload("res://sfx/spell-fire-flying.mp3")
var _snd_fire_boom := preload("res://sfx/spell-fire-explosion.mp3")
var _snd_bolt: Array[AudioStream] = [
	preload("res://sfx/spell-lightning-explosion-1.mp3"),
	preload("res://sfx/spell-lightning-explosion-2.mp3"),
]
var _audio_pool: Array[AudioStreamPlayer3D] = []
var _quiet: bool = false

var _fireballs: Array[Dictionary] = []
var _tongues: Array[Dictionary] = []
var _scorches: Array[Dictionary] = []
var _waves: Array[Dictionary] = []
var _lights: Array[Dictionary] = []
var _explosion_particles: Array[Dictionary] = []
var _trail_particles: Array[CPUParticles3D] = []
var _trail_i: int = 0
var _big_aabb := AABB(Vector3(-1000, -1000, -1000), Vector3(2000, 2000, 2000))
var exclude_rids: Array[RID] = []  # the caster; fireballs must not self-collide

signal exploded(position: Vector3)
signal bolt_struck(position: Vector3)

const BOLT_SEGMENTS: int = 14
const BOLT_BRANCHES: int = 2
const BOLT_BRANCH_SEGS: int = 5
const BOLT_LIFE: float = 0.38

var _bolt: Dictionary = {}
var _bolt_kits: Array[Dictionary] = []

func _ready() -> void:
	(_snd_fire_fly as AudioStreamMP3).loop = true
	_build_pools()
	# prewarm far below the map once the scene settles
	get_tree().create_timer(0.6).timeout.connect(_prewarm)

func _prewarm() -> void:
	_quiet = true
	var deep := Vector3(0, -300, 0)
	cast_fire(deep, Vector3.FORWARD)
	explode(deep + Vector3(6, 0, 0))
	cast_bolt(deep + Vector3(-6, 0, 0))
	_quiet = false

func _play_at(stream: AudioStream, pos: Vector3, db: float = 0.0) -> void:
	if _quiet:
		return
	var player: AudioStreamPlayer3D = null
	for p: AudioStreamPlayer3D in _audio_pool:
		if not p.playing:
			player = p
			break
	if player == null:
		player = _audio_pool[0]
	player.global_position = pos
	player.stream = stream
	player.volume_db = db
	player.play()

# ---------- pools ----------

func _flame_material(cool: Color, hot: Color, energy: float) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = _shell_shader
	m.set_shader_parameter("col_cool", Vector3(cool.r, cool.g, cool.b))
	m.set_shader_parameter("col_hot", Vector3(hot.r, hot.g, hot.b))
	m.set_shader_parameter("energy", energy)
	return m

func _fx_mesh(mesh: Mesh, mat: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.custom_aabb = _big_aabb  # never frustum-culled: prewarm must compile it
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.visible = false
	add_child(mi)
	return mi

func _burst(count: int, color: Color, vel: float, scale: float, life: float,
		gravity: float) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.emitting = false
	p.one_shot = true
	p.explosiveness = 1.0
	p.amount = count
	p.lifetime = life
	p.direction = Vector3.UP
	p.spread = 75.0
	p.initial_velocity_min = vel * 0.45
	p.initial_velocity_max = vel
	p.gravity = Vector3(0, -gravity, 0)
	p.scale_amount_min = scale * 0.6
	p.scale_amount_max = scale
	p.scale_amount_curve = _fade_curve()
	var mesh := SphereMesh.new()
	mesh.radius = 0.05
	mesh.height = 0.1
	mesh.radial_segments = 6
	mesh.rings = 3
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.no_depth_test = false
	mat.albedo_color = color
	mat.disable_fog = true
	mesh.material = mat
	p.mesh = mesh
	p.visibility_aabb = _big_aabb
	add_child(p)
	return p

func _fade_curve() -> Curve:
	var c := Curve.new()
	c.add_point(Vector2(0.0, 1.0))
	c.add_point(Vector2(0.7, 0.85))
	c.add_point(Vector2(1.0, 0.0))
	return c

func _build_pools() -> void:
	var shell_mesh := SphereMesh.new()
	shell_mesh.radius = 0.34
	shell_mesh.height = 0.68
	shell_mesh.radial_segments = 16
	shell_mesh.rings = 10
	var core_mesh := SphereMesh.new()
	core_mesh.radius = 0.16
	core_mesh.height = 0.32
	core_mesh.radial_segments = 10
	core_mesh.rings = 6

	var shell_mat := _flame_material(Color(1.0, 0.16, 0.01), Color(1.0, 0.85, 0.35), 1.7)
	var core_mat := _flame_material(Color(1.0, 0.55, 0.12), Color(1.0, 0.97, 0.8), 3.0)
	var tongue_mat := _flame_material(Color(1.6, 0.12, 0.0), Color(2.2, 0.95, 0.12), 1.1)

	for i: int in FIREBALL_POOL:
		var root := Node3D.new()
		add_child(root)
		var shell := _fx_mesh(shell_mesh, shell_mat)
		shell.reparent(root)
		shell.scale = Vector3(1, 1, 1.8)
		shell.visible = true
		var core := _fx_mesh(core_mesh, core_mat)
		core.reparent(root)
		core.position.z = 0.06
		core.scale = Vector3(1, 1, 1.5)
		core.visible = true
		var loop := AudioStreamPlayer3D.new()
		loop.name = "Loop"
		loop.stream = _snd_fire_fly
		loop.max_distance = 45.0
		loop.volume_db = -4.0
		root.add_child(loop)
		root.visible = false
		_fireballs.append({"root": root, "vel": Vector3.ZERO, "traveled": 0.0,
				"active": false, "light": null})

	for i: int in 4:
		var p := AudioStreamPlayer3D.new()
		p.max_distance = 55.0
		add_child(p)
		_audio_pool.append(p)

	for i: int in FIREBALL_POOL * TONGUES_PER_EXPLOSION:
		var mi := _fx_mesh(shell_mesh, tongue_mat)
		_tongues.append({"mesh": mi, "age": 0.0, "life": 0.3, "base": 0.2,
				"vel": Vector3.ZERO, "active": false})

	var quad := QuadMesh.new()
	quad.size = Vector2(2, 2)
	for i: int in SCORCH_POOL:
		var m := ShaderMaterial.new()
		m.shader = _scorch_shader
		m.render_priority = 1
		var mi := _fx_mesh(quad, m)
		_scorches.append({"mesh": mi, "mat": m, "age": 0.0, "life": 8.0, "active": false})
	for i: int in WAVE_POOL:
		var m := ShaderMaterial.new()
		m.shader = _wave_shader
		m.render_priority = 2
		var mi := _fx_mesh(quad, m)
		_waves.append({"mesh": mi, "mat": m, "age": 0.0, "life": 0.5, "active": false})

	for i: int in LIGHT_POOL_SIZE:
		var light := OmniLight3D.new()
		light.light_energy = 0.0
		light.omni_range = 9.0
		light.shadow_enabled = false
		add_child(light)
		_lights.append({"light": light, "in_use": false})

	# explosion particle kits (one per fireball pool slot)
	for i: int in FIREBALL_POOL:
		_explosion_particles.append({
			"hot": _burst(20, Color(2.6, 1.5, 0.5), 12.0, 1.4, 0.45, 14.0),
			"cool": _burst(24, Color(2.2, 0.8, 0.15), 7.0, 1.1, 0.9, 11.0),
			"spark": _burst(14, Color(2.8, 1.8, 0.7), 16.0, 0.7, 0.5, 24.0),
			"smoke": _burst(8, Color(0.16, 0.15, 0.14, 0.55), 2.5, 3.5, 1.3, -1.5),
		})
	# small trail puff emitters reused round-robin
	for i: int in 4:
		_trail_particles.append(_burst(6, Color(2.2, 0.8, 0.15), 1.2, 0.8, 0.3, 0.0))

	_build_bolt_pool()
	for i: int in 2:
		_bolt_kits.append({
			"spark": _burst(14, Color(2.8, 1.8, 0.7), 14.0, 0.7, 0.5, 26.0),
			"ember": _burst(10, Color(1.4, 1.7, 2.6), 8.0, 0.9, 0.6, 16.0),
		})

func _build_bolt_pool() -> void:
	var root := Node3D.new()
	add_child(root)
	var cyl := CylinderMesh.new()
	cyl.top_radius = 1.0
	cyl.bottom_radius = 1.0
	cyl.height = 1.0
	cyl.radial_segments = 5
	cyl.rings = 1

	var core_mat := StandardMaterial3D.new()
	core_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	core_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	core_mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	core_mat.albedo_color = Color(2.4, 2.7, 3.0)
	core_mat.disable_fog = true
	var glow_mat := StandardMaterial3D.new()
	glow_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glow_mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	glow_mat.albedo_color = Color(0.5, 0.71, 1.0, 0.3)
	glow_mat.disable_fog = true

	var cores: Array[MeshInstance3D] = []
	var glows: Array[MeshInstance3D] = []
	var branches: Array[MeshInstance3D] = []
	for i: int in BOLT_SEGMENTS:
		var c := _fx_mesh(cyl, core_mat)
		c.reparent(root)
		cores.append(c)
		var g := _fx_mesh(cyl, glow_mat)
		g.reparent(root)
		glows.append(g)
	for i: int in BOLT_BRANCHES * BOLT_BRANCH_SEGS:
		var b := _fx_mesh(cyl, core_mat)
		b.reparent(root)
		branches.append(b)
	root.visible = false
	_bolt = {"root": root, "cores": cores, "glows": glows, "branches": branches,
			"core_mat": core_mat, "glow_mat": glow_mat, "age": 0.0,
			"rebuild": 0.0, "active": false, "top": Vector3.ZERO,
			"target": Vector3.ZERO, "light": {}}

func cast_bolt(target: Vector3) -> void:
	_bolt.active = true
	_bolt.age = 0.0
	_bolt.rebuild = 0.0
	_bolt.target = target
	_bolt.top = target + Vector3(randf_range(-3, 3), 22.0, randf_range(-3, 3))
	(_bolt.root as Node3D).visible = true
	_bolt.light = _acquire_light(Color(0.66, 0.78, 1.0), 90.0, 20.0)
	((_bolt.light as Dictionary).light as OmniLight3D).global_position = target + Vector3(0, 2, 0)
	_rebuild_bolt()
	bolt_struck.emit(target)
	_play_at(_snd_bolt[randi() % _snd_bolt.size()], target, 2.0)

	# electric ground kit + blue scorch + ring
	for kit: Dictionary in _bolt_kits:
		var sp: CPUParticles3D = kit.spark
		if sp.emitting:
			continue
		for key: String in ["spark", "ember"]:
			var p: CPUParticles3D = kit[key]
			p.global_position = target + Vector3(0, 0.3, 0)
			p.restart()
		break
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(target + Vector3(0, 1, 0),
			target + Vector3(0, -3, 0))
	var hit: Dictionary = space.intersect_ray(q)
	var at: Vector3 = target
	var normal := Vector3.UP
	if not hit.is_empty():
		at = hit.position + hit.normal * 0.04
		normal = hit.normal
	_spawn_quad(_scorches, at, normal, 1.3, 8.0,
			{"char_color": Vector3(0.063, 0.078, 0.11), "ember_color": Vector3(0.5, 0.7, 1.6)})
	_spawn_quad(_waves, at + normal * 0.05, normal, 4.5, 0.4,
			{"ring_color": Vector3(0.53, 0.71, 1.0)})

func _bolt_points(from: Vector3, to: Vector3, segments: int, jitter: float) -> Array[Vector3]:
	var pts: Array[Vector3] = [from]
	for i: int in range(1, segments):
		var t: float = float(i) / float(segments)
		var p: Vector3 = from.lerp(to, t)
		var amp: float = jitter * sin(t * PI)
		p.x += randf_range(-amp, amp)
		p.z += randf_range(-amp, amp)
		pts.append(p)
	pts.append(to)
	return pts

func _place_segment(mi: MeshInstance3D, a: Vector3, b: Vector3, radius: float) -> void:
	var d: Vector3 = b - a
	var len: float = d.length()
	if len < 0.001:
		mi.visible = false
		return
	mi.visible = true
	mi.global_position = a + d * 0.5
	mi.global_transform.basis = Basis(Quaternion(Vector3.UP, d / len)) \
			.scaled_local(Vector3(radius, len, radius))

func _rebuild_bolt() -> void:
	var main: Array[Vector3] = _bolt_points(_bolt.top, _bolt.target, BOLT_SEGMENTS, 2.2)
	var cores: Array[MeshInstance3D] = _bolt.cores
	var glows: Array[MeshInstance3D] = _bolt.glows
	for i: int in BOLT_SEGMENTS:
		_place_segment(cores[i], main[i], main[i + 1], 0.055)
		_place_segment(glows[i], main[i], main[i + 1], 0.2)
	var branches: Array[MeshInstance3D] = _bolt.branches
	var bi: int = 0
	for b: int in BOLT_BRANCHES:
		var start: Vector3 = main[3 + randi() % (main.size() - 6)]
		var drop: float = maxf(1.0, (start.y - (_bolt.target as Vector3).y) * 0.6)
		var endp: Vector3 = start + Vector3(randf_range(-4, 4),
				-randf_range(2.0, drop), randf_range(-4, 4))
		endp.y = maxf(endp.y, (_bolt.target as Vector3).y)
		var pts: Array[Vector3] = _bolt_points(start, endp, BOLT_BRANCH_SEGS, 1.0)
		for i: int in BOLT_BRANCH_SEGS:
			if bi < branches.size():
				_place_segment(branches[bi], pts[i], pts[i + 1], 0.03)
				bi += 1

# ---------- lights ----------

func _acquire_light(color: Color, energy: float, rng: float) -> Dictionary:
	var slot: Dictionary = {}
	for s: Dictionary in _lights:
		if not s.in_use:
			slot = s
			break
	if slot.is_empty():
		slot = _lights[0]
	slot.in_use = true
	var light: OmniLight3D = slot.light
	light.light_color = color
	light.light_energy = energy
	light.omni_range = rng
	return slot

func _release_light(slot: Dictionary) -> void:
	if slot.is_empty():
		return
	(slot.light as OmniLight3D).light_energy = 0.0
	slot.in_use = false

# ---------- fireball ----------

func cast_fire(origin: Vector3, dir: Vector3, droop: float = 0.0,
		target: Vector3 = Vector3.INF) -> void:
	var f: Dictionary = {}
	for c: Dictionary in _fireballs:
		if not c.active:
			f = c
			break
	if f.is_empty():
		return
	f.active = true
	f.traveled = 0.0
	f.target = target
	f.target_dist = origin.distance_to(target) if target.is_finite() else INF
	var aim: Vector3 = (dir.normalized() + Vector3(0, -droop, 0)).normalized()
	f.vel = aim * FIRE_SPEED
	var root: Node3D = f.root
	root.global_position = origin
	root.look_at(origin + aim, Vector3.UP)
	root.visible = true
	f.light = _acquire_light(Color(1.0, 0.4, 0.13), 24.0, 9.0)
	if not _quiet:
		(root.get_node("Loop") as AudioStreamPlayer3D).play()

func explode(point: Vector3) -> void:
	exploded.emit(point)
	_play_at(_snd_fire_boom, point, 2.0)
	# flash on a pooled light
	var flash := _acquire_light(Color(1.0, 0.45, 0.13), 60.0, 14.0)
	(flash.light as OmniLight3D).global_position = point + Vector3(0, 0.6, 0)
	get_tree().create_timer(0.3).timeout.connect(_release_light.bind(flash))

	# flame tongues scatter
	var spawned: int = 0
	for t: Dictionary in _tongues:
		if t.active:
			continue
		t.active = true
		t.age = 0.0
		t.life = randf_range(0.16, 0.32)
		t.base = randf_range(0.1, 0.24)
		var a: float = randf() * TAU
		var s: float = randf_range(2.0, 6.5)
		t.vel = Vector3(cos(a) * s, randf_range(1.0, 4.5), sin(a) * s)
		var mi: MeshInstance3D = t.mesh
		mi.global_position = point + Vector3(randf_range(-0.5, 0.5),
				randf_range(0.1, 0.9), randf_range(-0.5, 0.5))
		mi.rotation = Vector3(randf() * TAU, randf() * TAU, randf() * TAU)
		mi.visible = true
		spawned += 1
		if spawned >= TONGUES_PER_EXPLOSION:
			break

	# particle kit (round-robin by whichever is free)
	for kit: Dictionary in _explosion_particles:
		var hot: CPUParticles3D = kit.hot
		if hot.emitting:
			continue
		for key: String in ["hot", "cool", "spark", "smoke"]:
			var p: CPUParticles3D = kit[key]
			p.global_position = point + Vector3(0, 0.3, 0)
			p.restart()
		break

	# ground decals (skip during prewarm below the map)
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(point + Vector3(0, 1, 0),
			point + Vector3(0, -3, 0))
	var hit: Dictionary = space.intersect_ray(q)
	var at: Vector3 = point
	var normal := Vector3.UP
	if not hit.is_empty():
		at = hit.position + hit.normal * 0.04
		normal = hit.normal
	_spawn_quad(_scorches, at, normal, randf_range(1.6, 2.0), 8.0,
			{"char_color": Vector3(0.08, 0.063, 0.047), "ember_color": Vector3(1.4, 0.45, 0.08)})
	_spawn_quad(_waves, at + normal * 0.04, normal, 4.2, 0.45,
			{"ring_color": Vector3(0.85, 0.44, 0.18)})
	_spawn_quad(_waves, at + normal * 0.06, normal, 2.4, 0.32,
			{"ring_color": Vector3(0.65, 0.26, 0.09)})

func _spawn_quad(pool: Array[Dictionary], at: Vector3, normal: Vector3,
		size: float, life: float, params: Dictionary = {}) -> void:
	var s: Dictionary = {}
	var oldest: Dictionary = pool[0]
	for c: Dictionary in pool:
		if not c.active:
			s = c
			break
		if c.age > oldest.age:
			oldest = c
	if s.is_empty():
		s = oldest
	s.active = true
	s.age = 0.0
	s.life = life
	var mi: MeshInstance3D = s.mesh
	mi.global_position = at
	var basis := Basis()
	var up: Vector3 = normal.normalized()
	var tangent: Vector3 = up.cross(Vector3.RIGHT)
	if tangent.length_squared() < 0.01:
		tangent = up.cross(Vector3.FORWARD)
	tangent = tangent.normalized()
	basis.x = tangent
	basis.y = up.cross(tangent).normalized()
	basis.z = up
	mi.global_transform.basis = basis.scaled(Vector3.ONE * size * 0.5)
	(s.mat as ShaderMaterial).set_shader_parameter("progress",
			-0.3 if s.life > 2.0 else 0.0)
	for key: String in params:
		(s.mat as ShaderMaterial).set_shader_parameter(key, params[key])
	mi.visible = true

# ---------- update ----------

func _physics_process(delta: float) -> void:
	var space := get_world_3d().direct_space_state

	for f: Dictionary in _fireballs:
		if not f.active:
			continue
		var root: Node3D = f.root
		var step: Vector3 = (f.vel as Vector3) * delta
		var q := PhysicsRayQueryParameters3D.create(root.global_position,
				root.global_position + step * 1.4)
		q.exclude = exclude_rids
		var hit: Dictionary = space.intersect_ray(q)
		root.global_position += step
		root.rotate_object_local(Vector3(0, 0, 1), 9.0 * delta)
		f.traveled += step.length()
		if f.light != null and not (f.light as Dictionary).is_empty():
			var light: OmniLight3D = (f.light as Dictionary).light
			light.global_position = root.global_position
			light.light_energy = 20.0 + sin(f.traveled * 4.0) * 8.0
		# ember trail puffs
		if fmod(f.traveled, 1.1) < step.length():
			var tp: CPUParticles3D = _trail_particles[_trail_i]
			_trail_i = (_trail_i + 1) % _trail_particles.size()
			tp.global_position = root.global_position
			tp.restart()
		var reached: bool = f.traveled >= (f.target_dist as float)
		if not hit.is_empty() or reached or f.traveled > FIRE_RANGE:
			var at: Vector3 = root.global_position
			if not hit.is_empty():
				at = hit.position
			elif reached:
				at = f.target
			(root.get_node("Loop") as AudioStreamPlayer3D).stop()
			root.visible = false
			f.active = false
			_release_light(f.light)
			f.light = {}
			explode(at)

	if _bolt.get("active", false):
		_bolt.age += delta
		_bolt.rebuild -= delta
		if _bolt.rebuild <= 0.0 and _bolt.age < BOLT_LIFE * 0.75:
			_bolt.rebuild = 0.05
			_rebuild_bolt()
		var bk: float = maxf(0.0, 1.0 - (_bolt.age as float) / BOLT_LIFE)
		var slot: Dictionary = _bolt.light
		if not slot.is_empty():
			(slot.light as OmniLight3D).light_energy = bk * (60.0 + randf() * 60.0)
		var gm: StandardMaterial3D = _bolt.glow_mat
		gm.albedo_color.a = 0.3 * bk
		var cm: StandardMaterial3D = _bolt.core_mat
		cm.albedo_color.a = clampf(bk * 1.5, 0.0, 1.0)
		if _bolt.age >= BOLT_LIFE:
			_bolt.active = false
			(_bolt.root as Node3D).visible = false
			_release_light(_bolt.light)
			_bolt.light = {}

	for t: Dictionary in _tongues:
		if not t.active:
			continue
		t.age += t.get("age_scale", 1.0) * delta
		var k: float = t.age / t.life
		var mi: MeshInstance3D = t.mesh
		if k >= 1.0:
			t.active = false
			mi.visible = false
			continue
		mi.global_position += (t.vel as Vector3) * delta
		var grow: float = (0.4 + 1.5 * (1.0 - pow(1.0 - k, 3.0))) * (t.base as float)
		var collapse: float = 1.0 if k <= 0.65 else maxf(0.001, 1.0 - (k - 0.65) / 0.35)
		mi.scale = Vector3.ONE * grow * collapse * 3.0

	for s: Dictionary in _scorches:
		if not s.active:
			continue
		s.age += delta
		var k: float = s.age / s.life
		(s.mat as ShaderMaterial).set_shader_parameter("progress",
				-0.3 + maxf(0.0, (k - 0.35) / 0.65) * 1.6)
		if k >= 1.0:
			s.active = false
			(s.mesh as MeshInstance3D).visible = false

	for w: Dictionary in _waves:
		if not w.active:
			continue
		w.age += delta
		var k: float = minf(1.0, w.age / w.life)
		(w.mat as ShaderMaterial).set_shader_parameter("progress", k)
		if w.age >= w.life:
			w.active = false
			(w.mesh as MeshInstance3D).visible = false
