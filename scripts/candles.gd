extends Node3D
class_name Candles
## Votive candle stations from the world bake: each Candle_### root with a
## Candle_Wick child becomes lightable. An aimed FIRE explosion within
## IGNITE_RADIUS of the wick ignites a persistent flame (same fire_shell
## shader as the spell, so no extra prewarm). The reserved "light" anim
## stays for M2's manual lighting interaction.

signal candle_lit(lit_count: int, total: int)

const IGNITE_RADIUS: float = 5.0

var _shell_shader: Shader = preload("res://assets/shaders/fire_shell.gdshader")
var _stations: Array[Dictionary] = []
var lit_count: int = 0


func setup(level: Node3D) -> void:
	var flame_mesh := SphereMesh.new()
	flame_mesh.radius = 0.16
	flame_mesh.height = 0.32
	flame_mesh.radial_segments = 10
	flame_mesh.rings = 6
	var flame_mat := _flame_material(
			Color(1.0, 0.25, 0.02), Color(1.0, 0.9, 0.45), 1.15)
	# the shell shader's defaults are fireball-sized: 0.42 m of vertex
	# displacement dwarfs a 7 cm flame (reads as a sparkler). Candle-size it.
	flame_mat.set_shader_parameter("displace", 0.03)
	flame_mat.set_shader_parameter("noise_scale", 14.0)
	flame_mat.set_shader_parameter("scroll_speed", 1.6)
	flame_mat.set_shader_parameter("heat_pow", 1.6)
	for node: Node in level.find_children("Candle_*", "Node3D", true, false):
		var wick: MeshInstance3D = null
		var wax: MeshInstance3D = null
		for child: Node in node.get_children():
			if child is MeshInstance3D and String(child.name).begins_with("Candle_Wick"):
				wick = child
			elif child is MeshInstance3D and String(child.name).begins_with("Candle_Wax"):
				wax = child
		if wick == null:
			continue
		var flame := MeshInstance3D.new()
		flame.mesh = flame_mesh
		flame.material_override = flame_mat
		flame.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		flame.visible = false
		var aabb: AABB = wick.mesh.get_aabb()
		wick.add_child(flame)
		flame.position = aabb.get_center() + Vector3(0.0, aabb.size.y * 0.55, 0.0)
		# constant WORLD size (~0.22 m tall) no matter how the candle prop
		# is scaled in Blender — flames must not shrink with the props
		var ws: Vector3 = wick.global_transform.basis.get_scale()
		flame.scale = Vector3(0.44 / maxf(ws.x, 0.001), 0.7 / maxf(ws.y, 0.001),
				0.44 / maxf(ws.z, 0.001))
		_stations.append({"root": node, "flame": flame, "wax": wax, "lit": false})
	_prewarm_lit_wax()


func total() -> int:
	return _stations.size()


func on_explosion(pos: Vector3) -> void:
	for st: Dictionary in _stations:
		if st["lit"]:
			continue
		# ground-snapped explosions land at the base; tall candles put the
		# wick well above it — accept whichever is closer
		var d: float = minf(
				pos.distance_to((st["flame"] as MeshInstance3D).global_position),
				pos.distance_to((st["root"] as Node3D).global_position))
		if d <= IGNITE_RADIUS:
			light_station(st)


func nearest_unlit(pos: Vector3, radius: float) -> Dictionary:
	var best: Dictionary = {}
	var best_d: float = radius
	for st: Dictionary in _stations:
		if st["lit"]:
			continue
		var d: float = pos.distance_to((st["root"] as Node3D).global_position)
		if d <= best_d:
			best_d = d
			best = st
	return best


func light_station(st: Dictionary) -> void:
	if st.is_empty() or st["lit"]:
		return
	st["lit"] = true
	(st["flame"] as MeshInstance3D).visible = true
	# blessed wax: red -> green (texture can't be tinted green, so swap)
	var wax: MeshInstance3D = st["wax"]
	if wax != null:
		wax.material_override = _lit_wax_material()
	lit_count += 1
	candle_lit.emit(lit_count, _stations.size())


var _lit_wax_mat: StandardMaterial3D = null


func _lit_wax_material() -> StandardMaterial3D:
	if _lit_wax_mat == null:
		_lit_wax_mat = StandardMaterial3D.new()
		_lit_wax_mat.albedo_color = Color(0.2, 0.72, 0.34)
		_lit_wax_mat.roughness = 0.9
		_lit_wax_mat.emission_enabled = true
		_lit_wax_mat.emission = Color(0.1, 0.5, 0.2)
		_lit_wax_mat.emission_energy_multiplier = 0.6
	return _lit_wax_mat


func _prewarm_lit_wax() -> void:
	# compile the lit-wax pipeline at load (first-light must never hitch)
	var quad := MeshInstance3D.new()
	quad.mesh = QuadMesh.new()
	quad.material_override = _lit_wax_material()
	quad.custom_aabb = AABB(Vector3(-2000, -2000, -2000), Vector3(4000, 4000, 4000))
	quad.position = Vector3(0, -180, 0)
	add_child(quad)
	get_tree().create_timer(2.0).timeout.connect(quad.queue_free)


func attach_pilot(tip: Node3D) -> void:
	## Small ever-burning flame on the staff tip — the pilgrim carries fire.
	var mesh := SphereMesh.new()
	mesh.radius = 0.07
	mesh.height = 0.14
	mesh.radial_segments = 8
	mesh.rings = 5
	var mat := _flame_material(
			Color(1.0, 0.3, 0.03), Color(1.0, 0.92, 0.5), 1.4)
	mat.set_shader_parameter("displace", 0.035)
	mat.set_shader_parameter("noise_scale", 16.0)
	mat.set_shader_parameter("scroll_speed", 2.0)
	mat.set_shader_parameter("heat_pow", 1.6)
	var flame := MeshInstance3D.new()
	flame.mesh = mesh
	flame.material_override = mat
	flame.scale = Vector3(1.0, 1.8, 1.0)
	flame.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	tip.add_child(flame)


func _flame_material(cool: Color, hot: Color, energy: float) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = _shell_shader
	m.set_shader_parameter("col_cool", Vector3(cool.r, cool.g, cool.b))
	m.set_shader_parameter("col_hot", Vector3(hot.r, hot.g, hot.b))
	m.set_shader_parameter("energy", energy)
	return m
