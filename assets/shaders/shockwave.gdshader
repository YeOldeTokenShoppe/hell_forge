// Expanding noise-broken energy ring with a faint interior afterglow.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;

uniform float progress = 0.0;
uniform vec3 ring_color: source_color = vec3(1.0, 0.73, 0.4);

varying vec3 v_world;

float hash13(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float vnoise(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(
		mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x),
			mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x),
			mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float r = length(UV - 0.5) * 2.0;
	float n = vnoise(v_world * 2.6) * 0.5 + 0.5;
	float band = smoothstep(0.22, 0.0, abs(r - progress));
	float trail = smoothstep(0.0, 0.5, progress - r) * 0.25;
	float fade = pow(clamp(1.0 - progress, 0.0, 1.0), 1.3);
	ALBEDO = ring_color * 2.4;
	ALPHA = (band + trail) * (n * 0.7 + 0.3) * fade;
}
