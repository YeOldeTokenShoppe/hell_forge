// Candle flame: upright (Y-axis) billboard quad with a procedural teardrop
// silhouette — wide low body, swaying tapered tip, per-candle flicker phase
// from world position. Deliberately NOT the fireball shell: at 10 cm scale a
// displaced sphere reads as a sparkler/orb, a shaped billboard reads as fire.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;

uniform vec3 col_cool: source_color = vec3(1.0, 0.35, 0.05);
uniform vec3 col_hot: source_color = vec3(1.0, 0.93, 0.55);
uniform float energy = 1.0;
uniform float sway = 0.18;
uniform float flicker_speed = 9.0;

void vertex() {
	// cylindrical billboard: face the camera but stay vertical
	vec3 up = vec3(0.0, 1.0, 0.0);
	vec3 to_cam = INV_VIEW_MATRIX[3].xyz - MODEL_MATRIX[3].xyz;
	to_cam.y = 0.0;
	vec3 fwd = normalize(to_cam + vec3(1e-4, 0.0, 0.0));
	vec3 right = normalize(cross(up, fwd));
	float sx = length(MODEL_MATRIX[0].xyz);
	float sy = length(MODEL_MATRIX[1].xyz);
	mat4 m = mat4(
			vec4(right * sx, 0.0),
			vec4(up * sy, 0.0),
			vec4(fwd * sx, 0.0),
			MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = VIEW_MATRIX * m;
}

void fragment() {
	float h = 1.0 - UV.y; // 0 at the wick, 1 at the tip
	float phase = MODEL_MATRIX[3].x * 7.7 + MODEL_MATRIX[3].z * 3.1;
	float t = TIME * flicker_speed + phase;
	float wob = sin(t * 0.7) * 0.5 + sin(t * 1.3 + 1.7) * 0.3
			+ sin(t * 2.9 + 4.0) * 0.2;
	// tip sways, base stays anchored on the wick
	float u = (UV.x - 0.5) * 2.0 - wob * sway * h * h;
	float width = 1.31 * pow(clamp(h * 4.0, 0.0, 1.0), 0.6) * pow(1.0 - h, 1.5);
	float d = width - abs(u);
	float body = smoothstep(0.0, 0.25, d);
	float flick = 0.85 + 0.15 * sin(t * 1.9 + 2.3);
	float core = smoothstep(0.15, 0.75, d) * (1.0 - h * 0.55);
	vec3 col = mix(col_cool, col_hot, core) * (0.55 + core * 1.6) * energy * flick;
	ALBEDO = col * body;
	ALPHA = clamp(body * (0.85 + 0.15 * flick), 0.0, 1.0);
}
