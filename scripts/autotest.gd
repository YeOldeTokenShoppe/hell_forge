extends Node
## Temporary headless playtest bot: taps jump rhythmically, logs deaths.

var _t: float = 0.0
var _player: Player

func _physics_process(delta: float) -> void:
	_t += delta
	if _player == null:
		for m: Node in get_tree().root.get_children():
			var p: Node = m.get_node_or_null("Player")
			if p is Player:
				_player = p as Player
				_player.died.connect(_on_died)
				print("BOT attached")
				break
		return
	if fmod(_t, 0.6) < delta:
		_player.queue_jump()
	if fmod(_t, 2.0) < delta:
		print("T=%.1f prog=%.1f pos=(%.1f, %.1f, %.1f) state=%d" % [
			_t, _player.progress, _player.global_position.x,
			_player.global_position.y, _player.global_position.z, _player.state])

func _on_died(cause: String) -> void:
	print("DIED cause=%s prog=%.1f pos=(%.1f, %.1f, %.1f) t=%.1f" % [
		cause, _player.progress, _player.global_position.x,
		_player.global_position.y, _player.global_position.z, _t])
