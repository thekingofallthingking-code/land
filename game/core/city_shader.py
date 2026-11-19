"""Lighting for the city's untextured, vertex-colored static meshes."""
from panda3d.core import Shader

VERTEX = """
#version 130
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ProjectionMatrix;
uniform mat3 p3d_NormalMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec3 view_position;
out vec3 view_normal;
out vec4 color;
void main() {
    vec4 view = p3d_ModelViewMatrix * p3d_Vertex;
    gl_Position = p3d_ProjectionMatrix * view;
    view_position = view.xyz;
    view_normal = p3d_NormalMatrix * p3d_Normal;
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
in vec3 view_position;
in vec3 view_normal;
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
    return texture(p3d_LightSource[0].shadowMap, coords);
}
void main() {
    vec3 normal = normalize(view_normal);
    vec3 light = p3d_LightModel.ambient.rgb + vec3(0.075, 0.083, 0.095);
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
        light += intensity * diffuse * 0.34;
    }
    float clear = exp(-length(view_position) * p3d_Fog.density);
    vec4 surface = color * p3d_ColorScale;
    result = vec4(mix(p3d_Fog.color.rgb, surface.rgb * light, clear), surface.a);
}
"""


def city_shader():
    return Shader.make(Shader.SL_GLSL, VERTEX, FRAGMENT)
