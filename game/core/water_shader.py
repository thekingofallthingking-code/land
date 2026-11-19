"""Animated coastal water with an analytic reflection of the changing sky."""
from panda3d.core import Shader

VERTEX = """
#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
out vec3 position;
void main() {
    position = (p3d_ModelMatrix * p3d_Vertex).xyz;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

FRAGMENT = """
#version 130
uniform vec3 harbor_eye;
uniform vec3 coastal_horizon;
uniform vec3 reflected_sky;
uniform vec3 coastal_sun;
uniform float haze_density;
uniform float sun_visible;
uniform float sun_strength;
uniform float wave_clock;
uniform float darkness;
in vec3 position;
out vec4 result;
float wave_filter(float phase) {
    return 1.0 - smoothstep(0.20, 1.25, fwidth(phase));
}
void main() {
    vec3 to_eye = harbor_eye - position;
    float distance = max(0.01, length(to_eye));
    vec3 eye = to_eye / distance;
    float waves_visible = 1.0 - smoothstep(85.0, 380.0, distance);
    float warp = sin(dot(position.xy, vec2(-0.12, 0.068)) + wave_clock * 0.26);
    float swell = dot(position.xy, vec2(0.35, 0.43)) - wave_clock * 1.10 + warp * 1.4;
    float ripple = dot(position.xy, vec2(-0.72, 0.81)) + wave_clock * 1.82 - warp * 1.15;
    float crosswave = dot(position.xy, vec2(1.85, 0.38)) - wave_clock * 2.06;
    float smooth_swell = wave_filter(swell);
    float smooth_ripple = wave_filter(ripple);
    vec3 normal = normalize(vec3(
        (cos(swell) * smooth_swell * 0.085 + sin(ripple) * smooth_ripple * 0.044) * waves_visible,
        (cos(ripple) * smooth_ripple * 0.063 + sin(crosswave) * wave_filter(crosswave) * 0.029) * waves_visible,
        1.0));
    float fresnel = 0.05 + 0.70 * pow(1.0 - max(dot(normal, eye), 0.0), 4.0);
    vec3 mirror = reflect(-eye, normal);
    vec3 base = mix(vec3(0.029, 0.16, 0.19), vec3(0.010, 0.031, 0.059), darkness);
    base *= 1.0 + (sin(swell) * smooth_swell + 0.33 * sin(ripple) * smooth_ripple) * 0.10 * waves_visible;
    vec3 reflected = reflected_sky * mix(0.72, 1.08, clamp(mirror.z, 0.0, 1.0));
    float glint = pow(max(dot(mirror, coastal_sun), 0.0), 48.0) * sun_strength * 0.62;
    vec3 color = mix(base, reflected, fresnel) + vec3(1.0, 0.68, 0.36) * glint;
    float sky_glow = pow(max(dot(-eye, coastal_sun), 0.0), 11.0) * sun_visible;
    vec3 haze = coastal_horizon + vec3(0.51, 0.18, 0.06) * sky_glow;
    float visibility = exp(-distance * haze_density * 1.55) * (1.0 - smoothstep(520.0, 1200.0, distance));
    result = vec4(mix(haze, color, visibility), 1.0);
}
"""


def water_shader():
    return Shader.make(Shader.SL_GLSL, VERTEX, FRAGMENT)
