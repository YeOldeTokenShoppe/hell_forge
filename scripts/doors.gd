extends Node3D
class_name Doors
## Ferry/door teleports from the world bake: empties named Door_<Name>_A
## and Door_<Name>_B become a linked pair. Walking within TRIGGER_RADIUS
## of one fades the screen and places the player at its twin, facing the
## twin's -Z. Bidirectional; any number of routes by naming alone.

signal traveled(route: String)

const TRIGGER_RADIUS: float = 2.2
const REARM_DISTANCE: float = 4.0  # walk this far from the twin to re-arm
const FADE_TIME: float = 0.45

var _pairs: Array[Dictionary] = []
var _player: Node3D = null
var _fade: ColorRect = null
var _cooldown_until_clear: Node3D = null


func setup(level: Node3D, player: Node3D, overlay: CanvasLayer) -> void:
	_player = player
	var ends: Dictionary = {}
	for node: Node in level.find_children("Door_*", "Node3D", true, false):
		var parts: PackedStringArray = String(node.name).split("_")
		if parts.size() < 3:
			continue
		var route: String = parts[1]
		ends.setdefault(route, {})
		ends[route][parts[2].to_upper()] = node
	for route: String in ends:
		if ends[route].has("A") and ends[route].has("B"):
			_pairs.append({"route": route,
					"a": ends[route]["A"], "b": ends[route]["B"]})
	if _pairs.is_empty():
		return
	_fade = ColorRect.new()
	_fade.color = Color(0, 0, 0, 0)
	_fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.add_child(_fade)


func total() -> int:
	return _pairs.size()


func _physics_process(_delta: float) -> void:
	if _pairs.is_empty() or _player == null:
		return
	if _cooldown_until_clear != null:
		if _player.global_position.distance_to(
				_cooldown_until_clear.global_position) > REARM_DISTANCE:
			_cooldown_until_clear = null
		return
	for pair: Dictionary in _pairs:
		for key: Array in [["a", "b"], ["b", "a"]]:
			var from_node: Node3D = pair[key[0]]
			var to_node: Node3D = pair[key[1]]
			if _player.global_position.distance_to(
					from_node.global_position) <= TRIGGER_RADIUS:
				_travel(pair["route"], to_node)
				return


func _travel(route: String, dest: Node3D) -> void:
	_cooldown_until_clear = dest
	var tween: Tween = create_tween()
	tween.tween_property(_fade, "color:a", 1.0, FADE_TIME)
	tween.tween_callback(func() -> void:
		if _player.has_method("place_at"):
			_player.place_at(dest.global_position, dest.rotation.y)
		traveled.emit(route))
	tween.tween_property(_fade, "color:a", 0.0, FADE_TIME)
