extends SceneTree
## Headless check: does the imported bake expose Candle_* roots with wicks
## the way scripts/candles.gd expects?
## Run: Godot --headless --path . --script tools/test_candles.gd


func _init() -> void:
	var ps: PackedScene = load("res://assets/inferno_baked.glb")
	var level: Node3D = ps.instantiate()
	var matches: int = 0
	var stations: int = 0
	for node: Node in level.find_children("Candle_*", "Node3D", true, false):
		matches += 1
		var wick: MeshInstance3D = null
		for child: Node in node.get_children():
			if child is MeshInstance3D and String(child.name).begins_with("Candle_Wick"):
				wick = child
		if wick != null:
			stations += 1
			if stations <= 3:
				print("root=", node.name, " class=", node.get_class(),
						" pos=", node.global_position, " wick=", wick.name)
	print("candle-named nodes: ", matches, "  stations with wick: ", stations)
	level.free()
	quit()
