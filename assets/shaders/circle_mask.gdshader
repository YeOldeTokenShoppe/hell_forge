// Circular alpha mask for UI textures shown inside round frames.
shader_type canvas_item;

void fragment() {
	float r = length(UV - 0.5) * 2.0;
	COLOR.a *= smoothstep(1.0, 0.96, r);
}
