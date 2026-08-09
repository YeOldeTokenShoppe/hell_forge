// Aiming reticle: pulsing ring with a center ember, ground-projected.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;

uniform vec3 tint: source_color = vec3(1.0, 0.72, 0.35);

void fragment() {
	float r = length(UV - 0.5) * 2.0;
	float pulse = 0.75 + 0.25 * sin(TIME * 5.0);
	float ring = smoothstep(0.1, 0.0, abs(r - 0.82 * pulse));
	float ticks = step(0.92, abs(sin(atan(UV.y - 0.5, UV.x - 0.5) * 4.0))) *
			smoothstep(0.12, 0.0, abs(r - 0.55));
	float dot_c = smoothstep(0.12, 0.0, r);
	ALBEDO = tint * 2.2;
	ALPHA = clamp(ring + ticks * 0.6 + dot_c * 0.8, 0.0, 1.0) * 0.85;
}
