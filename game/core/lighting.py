"""Coastal sky, moving sunlight and a small HDR bloom pass."""
import math

from panda3d.core import (
    AmbientLight, DirectionalLight, Fog, Geom, GeomNode,
    GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    Shader, Vec3, Vec4,
)

START_HOUR = 16.37
DAY_SECONDS = 1080.0

SKY_VERTEX = """
#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
out vec3 ray;
void main() {
    ray = p3d_Vertex.xyz;
    vec4 output_pos = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    gl_Position = output_pos.xyww;
}
"""

SKY_FRAGMENT = """
#version 130
uniform vec3 sun_dir;
uniform vec3 moon_dir;
uniform vec3 horizon;
uniform vec3 zenith;
uniform float darkness;
uniform float clock_angle;
in vec3 ray;
out vec4 result;
float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise2(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 s = f*f*(3.0-2.0*f);
    return mix(mix(hash2(i), hash2(i+vec2(1,0)),s.x),
               mix(hash2(i+vec2(0,1)), hash2(i+vec2(1,1)),s.x),s.y);
}
void main() {
    vec3 d = normalize(ray);
    float up = max(d.z, 0.0);
    vec3 color = mix(horizon, zenith, pow(up, 0.57));
    float sun = max(dot(d, sun_dir), 0.0);
    float moon = max(dot(d, moon_dir), 0.0);
    float sun_visible = smoothstep(-0.09, 0.03, sun_dir.z);
    color += vec3(0.51, 0.18, 0.06) * pow(sun, 11.0) * sun_visible;
    color += vec3(5.8, 3.4, 1.6) * smoothstep(0.99957, 0.99986, sun) * sun_visible;
    color += vec3(0.49, 0.64, 0.93) * darkness * smoothstep(0.99964, 0.99984, moon);
    vec2 cloud = d.xy / (0.30 + max(d.z, 0.0)) * vec2(2.2, 6.5);
    cloud.x += sin(clock_angle * 0.25) * 2.0;
    float cloud_noise = noise2(cloud) * 0.64 + noise2(cloud*2.15+0.72)*0.24 + noise2(cloud*4.4)*0.12;
    float wisps = smoothstep(0.53, 0.80, cloud_noise) * smoothstep(0.012, 0.15, up);
    vec3 paper = mix(vec3(0.43, 0.26, 0.22), vec3(0.038, 0.052, 0.072), darkness);
    color = mix(color, paper, wisps * 0.60);
    vec2 stars = vec2(atan(d.y,d.x)*106.0, d.z*210.0);
    float star = step(0.996, hash2(floor(stars))) *
                 (1.0-smoothstep(0.05,0.32,length(fract(stars)-0.5)));
    color += star * 0.5 * darkness * smoothstep(0.12,0.42,up);
    result = vec4(color,1.0);
}
"""

POST_VERTEX = """
#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;
void main() {
    uv = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

POST_FRAGMENT = """
#version 130
uniform sampler2D tex;
uniform float exposure;
in vec2 uv;
out vec4 result;
vec3 hot(vec2 coord) {
    return max(texture(tex, coord).rgb - vec3(0.86), 0.0);
}
void main() {
    vec3 scene = texture(tex, uv).rgb;
    vec2 px = 1.0 / vec2(textureSize(tex, 0));
    vec3 fringe = hot(uv + px*vec2(3.5,1.5)) + hot(uv + px*vec2(-3.5,-1.5));
    fringe += hot(uv + px*vec2(-1.5,3.5)) + hot(uv + px*vec2(1.5,-3.5));
    fringe += (hot(uv + px*vec2(8.5,4.5)) + hot(uv + px*vec2(-8.5,-4.5))) * 0.55;
    fringe += (hot(uv + px*vec2(-4.5,8.5)) + hot(uv + px*vec2(4.5,-8.5))) * 0.55;
    vec3 c = (scene + fringe * 0.064) * exposure;
    c = clamp((c*(2.51*c+0.03))/(c*(2.43*c+0.59)+0.14), 0.0, 1.0);
    float vignette = 1.0-0.13*dot((uv-0.5)*1.4,(uv-0.5)*1.4);
    result = vec4(pow(c,vec3(1.0/2.2)) * vignette,1.0);
}
"""


def sky_mesh(parent):
    data = GeomVertexData("sky hemisphere", GeomVertexFormat.get_v3(), Geom.UH_static)
    positions = GeomVertexWriter(data, "vertex")
    triangles = GeomTriangles(Geom.UH_static)
    segments, rings = 48, 24
    for ring in range(rings + 1):
        elevation = -math.pi / 2 + math.pi * ring / rings
        for segment in range(segments + 1):
            azimuth = 2 * math.pi * segment / segments
            positions.add_data3(math.cos(elevation) * math.cos(azimuth),
                                math.cos(elevation) * math.sin(azimuth), math.sin(elevation))
    for ring in range(rings):
        for segment in range(segments):
            index = ring * (segments + 1) + segment
            next_ring = index + segments + 1
            triangles.add_vertices(index, index + 1, next_ring)
            triangles.add_vertices(next_ring, index + 1, next_ring + 1)
    geometry = Geom(data)
    geometry.add_primitive(triangles)
    node = GeomNode("coastal sky")
    node.add_geom(geometry)
    sky = parent.attach_new_node(node)
    sky.set_scale(100)
    sky.set_two_sided(True)
    sky.set_bin("background", 1)
    sky.set_depth_write(False)
    sky.set_depth_test(False)
    sky.set_light_off()
    sky.set_fog_off()
    sky.set_shader(Shader.make(Shader.SL_GLSL, SKY_VERTEX, SKY_FRAGMENT), 10)
    return sky


def mix(a, b, t):
    return a * (1 - t) + b * t


class CityLighting:
    def __init__(self, base, preset, *, rendered=True):
        self.base = base
        self.hour = START_HOUR
        self.night = 0.0
        self.rendered = rendered
        self.pipeline = None
        if not rendered:
            return
        import simplepbr

        ambient = AmbientLight("sky fill")
        self.ambient = base.render.attach_new_node(ambient)
        base.render.set_light(self.ambient)
        sun = DirectionalLight("sun")
        self.sun = base.render.attach_new_node(sun)
        base.render.set_light(self.sun)
        if preset["shadow"]:
            sun.set_shadow_caster(True, preset["shadow"], preset["shadow"])
            sun.get_lens().set_film_size(120, 120)
            sun.get_lens().set_near_far(5, 350)
        self.moon = base.render.attach_new_node(DirectionalLight("moon"))
        base.render.set_light(self.moon)
        self.fog = Fog("maritime haze")
        self.fog.set_exp_density(.00175)
        base.render.set_fog(self.fog)
        self.sky = sky_mesh(base.render)
        self.pipeline = simplepbr.init(
            render_node=base.render, window=base.win, camera_node=base.cam,
            taskmgr=base.task_mgr, max_lights=6, enable_fog=True,
            enable_shadows=bool(preset["shadow"]), msaa_samples=preset["msaa"],
            exposure=-.17,
        )
        if preset["shadow"]:
            # Use the existing simplepbr HDR render target, avoiding a second scene render.
            self.pipeline._post_process_quad.set_shader(
                Shader.make(Shader.SL_GLSL, POST_VERTEX, POST_FRAGMENT)
            )

    def update(self, dt, focus, camera_position):
        self.hour = (self.hour + dt * 24.0 / DAY_SECONDS) % 24.0
        angle = (self.hour - 6.0) * math.tau / 24.0
        day = math.sin(angle)
        self.night = 1.0 - min(1.0, max(0.0, (day + .085) / .34))
        if not self.rendered:
            return self.night
        sun_direction = Vec3(math.cos(angle), .53, day * .88)
        sun_direction.normalize()
        moon_direction = Vec3(-sun_direction.x, -.27, -sun_direction.z + .14)
        moon_direction.normalize()
        golden = max(0.0, 1.0 - abs(day) * 1.65)
        sunlight = max(0.0, min(1.65, (day + .09) * 3.7))
        sun_color = mix(Vec3(1.0, .87, .70), Vec3(1.0, .43, .24), golden)
        self.sun.node().set_color(Vec4(*(sun_color * sunlight), 1))
        self.sun.set_pos(focus + sun_direction * 155)
        self.sun.look_at(focus)
        self.moon.look_at(-moon_direction)
        self.moon.node().set_color(Vec4(.10 * self.night, .17 * self.night, .33 * self.night, 1))
        ambient = mix(Vec3(.39, .43, .48), Vec3(.13, .17, .28), self.night)
        self.ambient.node().set_color(Vec4(*ambient, 1))
        horizon = mix(Vec3(.39, .55, .64), Vec3(.50, .25, .19), golden)
        horizon = mix(horizon, Vec3(.065, .102, .17), self.night)
        zenith = mix(Vec3(.105, .275, .46), Vec3(.014, .025, .068), self.night)
        self.fog.set_color(*horizon)
        self.sky.set_pos(camera_position)
        self.sky.set_shader_input("sun_dir", sun_direction)
        self.sky.set_shader_input("moon_dir", moon_direction)
        self.sky.set_shader_input("horizon", horizon)
        self.sky.set_shader_input("zenith", zenith)
        self.sky.set_shader_input("darkness", self.night)
        self.sky.set_shader_input("clock_angle", angle)
        return self.night

    def close(self):
        if self.pipeline:
            self.base.task_mgr.remove("simplepbr update")
