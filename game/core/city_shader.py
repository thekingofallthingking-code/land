"""World-space material and light shading for the city meshes."""
from panda3d.core import Shader

VERTEX = """
#version 130
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat4 p3d_ProjectionMatrix;
uniform mat3 p3d_NormalMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec3 view_position;
out vec3 view_normal;
out vec3 world_position;
out vec3 world_normal;
out vec4 color;
void main() {
    vec4 view = p3d_ModelViewMatrix * p3d_Vertex;
    gl_Position = p3d_ProjectionMatrix * view;
    view_position = view.xyz;
    view_normal = p3d_NormalMatrix * p3d_Normal;
    world_position = (p3d_ModelMatrix * p3d_Vertex).xyz;
    world_normal = mat3(p3d_ModelMatrix) * p3d_Normal;
    color = p3d_Color;
}
"""

FRAGMENT = """
#version 130
uniform struct Light {
    vec4 position;
    vec4 diffuse;
    vec3 attenuation;
    vec3 spotDirection;
    float spotCosCutoff;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[6];
uniform struct LightModel {
    vec4 ambient;
} p3d_LightModel;
uniform struct Fog {
    vec4 color;
    float density;
} p3d_Fog;
uniform vec4 p3d_ColorScale;
uniform bool sun_shadows;
uniform bool surface_detail;
uniform float shadow_softness;
uniform float wetness;
uniform sampler2D surface_grain;
uniform vec3 harbor_eye;
uniform vec3 reflected_sky;
uniform vec3 coastal_sun;
uniform float sun_strength;
in vec3 view_position;
in vec3 view_normal;
in vec3 world_position;
in vec3 world_normal;
in vec4 color;
out vec4 result;
float sunlight() {
    vec4 shadow = p3d_LightSource[0].shadowViewMatrix * vec4(view_position, 1.0);
    vec3 coords = shadow.xyz / shadow.w;
    if (coords.z < 0.0 || coords.z > 1.0 || any(lessThan(coords.xy, vec2(0.0))) ||
        any(greaterThan(coords.xy, vec2(1.0)))) {
        return 1.0;
    }
    coords.z -= 0.003;
    if (shadow_softness <= 0.0) {
        return texture(p3d_LightSource[0].shadowMap, coords);
    }
    vec2 texel = shadow_softness / vec2(textureSize(p3d_LightSource[0].shadowMap, 0));
    float coverage = texture(p3d_LightSource[0].shadowMap, coords + vec3(-texel.x, -texel.y, 0));
    coverage += texture(p3d_LightSource[0].shadowMap, coords + vec3(texel.x, -texel.y, 0));
    coverage += texture(p3d_LightSource[0].shadowMap, coords + vec3(-texel.x, texel.y, 0));
    coverage += texture(p3d_LightSource[0].shadowMap, coords + vec3(texel.x, texel.y, 0));
    return coverage * 0.25;
}
void main() {
    vec3 normal = normalize(view_normal);
    vec3 light = p3d_LightModel.ambient.rgb + vec3(0.045, 0.063, 0.086);
    for (int index = 0; index < 6; ++index) {
        vec3 intensity = p3d_LightSource[index].diffuse.rgb;
        if (dot(intensity, intensity) <= 0.0001) {
            continue;
        }
        vec4 position = p3d_LightSource[index].position;
        vec3 ray = position.xyz - view_position * position.w;
        float distance_squared = max(dot(ray, ray), 0.0001);
        float distance = sqrt(distance_squared);
        vec3 direction = ray / distance;
        float diffuse = max(dot(normal, direction), 0.0);
        if (diffuse <= 0.0) {
            continue;
        }
        if (position.w > 0.0) {
            float cone = p3d_LightSource[index].spotCosCutoff;
            if (cone > 0.0) {
                float alignment = dot(-direction, p3d_LightSource[index].spotDirection);
                diffuse *= smoothstep(cone - 0.025, cone + 0.025, alignment);
            }
            vec3 falloff = p3d_LightSource[index].attenuation;
            diffuse /= max(0.01, dot(falloff, vec3(1.0, distance, distance_squared)));
        } else if (index == 0 && sun_shadows) {
            diffuse *= sunlight();
        }
        light += intensity * diffuse * 0.41;
    }
    float view_distance = length(view_position);
    float clear = exp(-view_distance * p3d_Fog.density);
    vec4 surface = color * p3d_ColorScale;
    vec3 lit = surface.rgb * light;
    if (surface_detail && clear > 0.12) {
        vec3 up = normalize(world_normal);
        bool horizontal = abs(up.z) > 0.70;
        vec2 plane = horizontal ? world_position.xy :
                     abs(up.x) > abs(up.y) ? world_position.yz : world_position.xz;
        vec2 grain = texture(surface_grain, plane * 0.37).rg;
        float detail_weight = 1.0 - smoothstep(30.0, 125.0, view_distance);
        lit *= 1.0 + ((grain.r - 0.5) * 0.33 + (grain.g - 0.5) * 0.10) * detail_weight;
        if (wetness > 0.005 && up.z > 0.90 && world_position.z < 0.42) {
            float chroma = max(max(surface.r, surface.g), surface.b) -
                           min(min(surface.r, surface.g), surface.b);
            float damp = wetness * (1.0 - smoothstep(0.07, 0.22, chroma));
            float pools = smoothstep(0.30, 0.71, texture(surface_grain, plane * 0.12).g);
            vec3 eye = normalize(harbor_eye - world_position);
            float grazing = pow(1.0 - max(eye.z, 0.0), 3.0);
            float gleam = pow(max(dot(reflect(-eye, up), coastal_sun), 0.0), 24.0) * sun_strength;
            lit = mix(lit * (1.0 - damp * 0.27), reflected_sky,
                      damp * grazing * (0.14 + pools * 0.21));
            lit += vec3(0.76, 0.49, 0.28) * gleam * damp * pools * 0.25;
        }
    }
    result = vec4(mix(p3d_Fog.color.rgb, lit, clear), surface.a);
}
"""


def city_shader():
    return Shader.make(Shader.SL_GLSL, VERTEX, FRAGMENT)
