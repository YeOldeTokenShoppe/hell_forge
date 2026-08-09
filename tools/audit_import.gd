@tool
extends SceneTree

func _init() -> void:
	var ps: PackedScene = load("res://assets/inferno_world.blend")
	if ps == null:
		print("AUDIT_FAIL: could not load scene")
		quit(1)
		return
	var root := ps.instantiate()
	var counts := {}
	var skeletons: Array[String] = []
	var lights: Array[String] = []
	var anim_names: Array[String] = []
	var stack: Array[Node] = [root]
	var total := 0
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		total += 1
		var cls := n.get_class()
		counts[cls] = int(counts.get(cls, 0)) + 1
		if n is Skeleton3D:
			skeletons.append(n.name)
		if n is Light3D:
			lights.append(n.name)
		if n is AnimationPlayer:
			for a in (n as AnimationPlayer).get_animation_list():
				anim_names.append(String(a))
		for c in n.get_children():
			stack.append(c)
	var top: Array[String] = []
	for c in root.get_children():
		top.append(String(c.name))
		if top.size() >= 25:
			break
	print("AUDIT_TOTAL_NODES: ", total)
	print("AUDIT_COUNTS: ", JSON.stringify(counts))
	print("AUDIT_SKELETONS: ", JSON.stringify(skeletons))
	print("AUDIT_LIGHTS: ", JSON.stringify(lights))
	print("AUDIT_ANIM_COUNT: ", anim_names.size())
	print("AUDIT_ANIMS: ", JSON.stringify(anim_names.slice(0, 40)))
	print("AUDIT_TOP_CHILDREN: ", JSON.stringify(top))
	root.free()
	quit(0)
