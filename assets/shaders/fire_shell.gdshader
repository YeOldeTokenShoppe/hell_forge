// Fireball shell: noise gnaws at the silhouette while flames stream backwards
// along the flight axis; rim fades to embers, the heart runs white.
// Port of the THREE.js/TSL makeFireShellMaterial (chicken-game SpellManager).
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;

uniform float noise_scale = 3.2;
uniform float scroll_speed = 7.0;
uniform float displace = 0.42;
uniform vec3 col_cool: source_color = vec3(1.0, 0.16, 0.01);
uniform vec3 col_hot: source_color = vec3(1.0, 0.85, 0.35);
uniform float energy = 1.7;
uniform float heat_pow = 2.0;

varying float v_n;

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

float fnoise(vec3 p) {
	return vnoise(p) * 0.65 + vnoise(p * 2.3) * 0.35;
}

void vertex() {
	vec3 p = VERTEX * noise_scale + vec3(0.0, 0.0, TIME * scroll_speed);
	float n = fnoise(p);
	v_n = n;
	VERTEX += NORMAL * (n - 0.5) * displace;
}

void fragment() {
	float facing = abs(NORMAL.z);
	float heat = pow(facing, heat_pow) * (v_n * 0.8 + 0.4);
	vec3 col = mix(col_cool, col_hot, heat) * (heat * 2.4 + 0.6) * energy;
	ALBEDO = col;
	ALPHA = clamp(heat * 1.8 + v_n * 0.4 - 0.15, 0.0, 1.0);
}
