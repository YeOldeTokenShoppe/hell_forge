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
			Color(1.0, 0.25, 0.02), Color(1.0, 0.9, 0.45), 2.6)
	for node: Node in level.find_children("Candle_*", "Node3D", true, false):
		var wick: MeshInstance3D = null
		for child: Node in node.get_children():
			if child is MeshInstance3D and String(child.name).begins_with("Candle_Wick"):
				wick = child
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
		flame.scale = Vector3(1.0, 2.2, 1.0)
		_stations.append({"root": node, "flame": flame, "lit": false})


func total() -> int:
	return _stations.size()


func on_explosion(pos: Vector3) -> void:
	for st: Dictionary in _stations:
		if st["lit"]:
			continue
		var flame: MeshInstance3D = st["flame"]
		var root: Node3D = st["root"]
		# ground-snapped explosions land at the base; tall candles put the
		# wick well above it — accept whichever is closer
		var d: float = minf(pos.distance_to(flame.global_position),
				pos.distance_to(root.global_position))
		if d <= IGNITE_RADIUS:
			st["lit"] = true
			flame.visible = true
			lit_count += 1
			candle_lit.emit(lit_count, _stations.size())


func _flame_material(cool: Color, hot: Color, energy: float) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = _shell_shader
	m.set_shader_parameter("col_cool", Vector3(cool.r, cool.g, cool.b))
	m.set_shader_parameter("col_hot", Vector3(hot.r, hot.g, hot.b))
	m.set_shader_parameter("energy", energy)
	return m
