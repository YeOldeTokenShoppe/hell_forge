// Ground scorch decal: noise-broken char circle with a creeping ember front
// that dissolves outward as the mark cools. progress -0.3 -> 1.3 over life.
shader_type spatial;
render_mode unshaded, depth_draw_never, fog_disabled;

uniform float progress = -0.3;
uniform vec3 char_color: source_color = vec3(0.08, 0.063, 0.047);
uniform vec3 ember_color: source_color = vec3(1.4, 0.45, 0.08);

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
	float n = vnoise(v_world * 2.4) * 0.65 + vnoise(v_world * 5.1) * 0.35;
	float shape = smoothstep(1.0, 0.45, r + n * 0.5 - 0.25);
	float alive = smoothstep(progress, progress + 0.16, n);
	float edge = alive * smoothstep(progress + 0.3, progress + 0.16, n)
			* clamp(progress + 0.3, 0.0, 1.0);
	ALBEDO = mix(char_color, ember_color * 3.0, edge);
	ALPHA = shape * alive * 0.9;
}
