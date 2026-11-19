"""Coastal sky, moving sunlight and a small HDR bloom pass."""
import math

import numpy as np

from panda3d.core import (
    AmbientLight, BitMask32, CullBinManager, DepthTestAttrib, DirectionalLight,
    Fog, FrameBufferProperties, Geom, GeomNode,
    GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    SamplerState, Shader, Texture, Vec3, Vec4,
)

from game.core.city_shader import city_shader
from game.core.water_shader import water_shader

START_HOUR = 16.37
DAY_SECONDS = 1080.0
SHADOW_MASK = BitMask32.bit(1)

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
uniform float storm;
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
    vec3 cloud_light = mix(vec3(0.72, 0.62, 0.54), vec3(0.044, 0.058, 0.087), darkness);
    cloud_light += vec3(0.26, 0.077, 0.019) * pow(sun, 5.0) * (1.0 - darkness);
    float bank = smoothstep(0.46, 0.70, cloud_noise + storm * 0.09) * smoothstep(0.02, 0.16, up);
    vec3 cloud_base = mix(cloud_light, vec3(0.095, 0.12, 0.17), storm);
    color = mix(color, cloud_base, max(wisps * 0.48, bank * (0.29 + storm * 0.48)));
    vec2 stars = vec2(atan(d.y,d.x)*106.0, d.z*210.0);
    float star = step(0.996, hash2(floor(stars))) *
                 (1.0-smoothstep(0.05,0.32,length(fract(stars)-0.5)));
    color += star * 0.5 * darkness * (1.0 - bank) * (1.0 - storm) * smoothstep(0.12,0.42,up);
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

BLOOM_FRAGMENT = """
#version 130
uniform sampler2D tex;
in vec2 uv;
out vec4 result;
vec3 hot(vec2 coord) {
    return max(texture(tex, coord).rgb - vec3(0.86), 0.0);
}
void main() {
    vec2 px = 1.0 / vec2(textureSize(tex, 0));
    vec3 fringe = hot(uv + px*vec2(2.0,2.0)) + hot(uv + px*vec2(-2.0,-2.0));
    fringe += hot(uv + px*vec2(-2.0,2.0)) + hot(uv + px*vec2(2.0,-2.0));
    result = vec4(fringe * 0.25, 1.0);
}
"""

POST_FRAGMENT = """
#version 130
uniform sampler2D tex;
uniform sampler2D bloom_tex;
uniform float exposure;
in vec2 uv;
out vec4 result;
void main() {
    vec3 c = (texture(tex, uv).rgb + texture(bloom_tex, uv).rgb * 0.40) * exposure;
    c = clamp((c*(2.51*c+0.03))/(c*(2.43*c+0.59)+0.14), 0.0, 1.0);
    float luminance = dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = clamp(mix(vec3(luminance), c, 1.14), 0.0, 1.0);
    float vignette = 1.0-0.075*dot((uv-0.5)*1.4,(uv-0.5)*1.4);
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
    bins = CullBinManager.get_global_ptr()
    if bins.find_bin("harbor sky") < 0:
        bins.add_bin("harbor sky", CullBinManager.BT_unsorted, 25)
    sky.set_bin("harbor sky", 0)
    sky.set_depth_write(False)
    sky.set_attrib(DepthTestAttrib.make(DepthTestAttrib.M_less_equal))
    sky.hide(SHADOW_MASK)
    sky.set_light_off()
    sky.set_fog_off()
    sky.set_shader(Shader.make(Shader.SL_GLSL, SKY_VERTEX, SKY_FRAGMENT), 10)
    return sky



def surface_grain():
    """Bake repeating fine grain and broad stone/asphalt variation."""
    rng = np.random.default_rng(871)
    size = 128
    fine = rng.random((size, size))
    broad = rng.random((size, size))
    for _ in range(6):
        broad = (broad * 2 + np.roll(broad, 1, 0) + np.roll(broad, -1, 0)
                 + np.roll(broad, 1, 1) + np.roll(broad, -1, 1)) / 6
    broad = np.clip((broad - broad.mean()) * 3.7 + .5, 0, 1)
    pixels = (np.stack((fine, broad, np.zeros_like(fine)), axis=-1) * 255).astype(np.uint8)
    texture = Texture("coastal surface grain")
    texture.setup_2d_texture(size, size, Texture.T_unsigned_byte, Texture.F_rgb8)
    texture.set_ram_image_as(pixels.tobytes(), "RGB")
    texture.generate_ram_mipmap_images()
    texture.set_wrap_u(SamplerState.WM_repeat)
    texture.set_wrap_v(SamplerState.WM_repeat)
    texture.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    texture.set_magfilter(SamplerState.FT_linear)
    return texture

def mix(a, b, t):
    return a * (1 - t) + b * t


class CityLighting:
    def __init__(self, base, preset, city_root, *, rendered=True):
        self.base = base
        self.hour = START_HOUR
        self.night = 0.0
        self.rendered = rendered
        self.pipeline = None
        self.wave_clock = 0.0
        self.wetness = 0.0
        if not rendered:
            return
        import simplepbr

        ambient = AmbientLight("sky fill")
        self.ambient = base.render.attach_new_node(ambient)
        base.render.set_light(self.ambient)
        sun = DirectionalLight("sun")
        sun.set_priority(10)
        self.sun = base.render.attach_new_node(sun)
        base.render.set_light(self.sun)
        self.shadow_size = preset["shadow"]
        self.shadow_active = bool(self.shadow_size)
        base.cam.node().set_camera_mask(BitMask32.bit(0))
        if preset["shadow"]:
            sun.set_camera_mask(SHADOW_MASK)
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
            use_emission_maps=False, exposure=-.17,
        )
        self.city_root = city_root
        city_root.set_shader(city_shader())
        city_root.set_shader_input("sun_shadows", self.shadow_active)
        city_root.set_shader_input("surface_detail", bool(preset["shadow"]))
        city_root.set_shader_input("surface_grain", surface_grain())
        city_root.set_shader_input("shadow_softness", 1.35 if preset["shadow"] >= 2048 else 0.0)
        self.water = city_root.find("Bay surface")
        if not self.water.is_empty():
            self.water.set_shader(water_shader())
            self.water.hide(SHADOW_MASK)
        if preset["shadow"]:
            self._init_bloom()

    def _init_bloom(self):
        # The pinned simplepbr pipeline owns the HDR scene buffer and window-resize handling.
        post = self.pipeline._post_process_quad
        source = post.get_shader_input("tex").get_texture()
        glow = Texture("quarter-resolution bloom")
        glow.set_minfilter(SamplerState.FT_linear)
        glow.set_magfilter(SamplerState.FT_linear)
        glow.set_wrap_u(SamplerState.WM_clamp)
        glow.set_wrap_v(SamplerState.WM_clamp)
        props = FrameBufferProperties()
        props.set_float_color(True)
        props.set_rgba_bits(16, 16, 16, 16)
        extract = self.pipeline._filtermgr.render_quad_into(
            "harbor bloom", div=4, colortex=glow, fbprops=props,
        )
        if extract is not None:
            self.bloom_quad = extract
            extract.set_shader(Shader.make(Shader.SL_GLSL, POST_VERTEX, BLOOM_FRAGMENT))
            extract.set_shader_input("tex", source)
            post.set_shader(Shader.make(Shader.SL_GLSL, POST_VERTEX, POST_FRAGMENT))
            post.set_shader_input("bloom_tex", glow)

    def update(self, dt, focus, camera_position, *, weather=0.0):
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
        sunlight = max(0.0, min(1.78, (day + .09) * 3.7)) * (1 - .67 * weather)
        show_shadow = bool(self.shadow_size and sunlight > .01)
        if show_shadow != self.shadow_active:
            self.sun.node().set_shadow_caster(show_shadow, self.shadow_size, self.shadow_size)
            self.shadow_active = show_shadow
            self.city_root.set_shader_input("sun_shadows", show_shadow)
        sun_color = mix(Vec3(1.0, .88, .72), Vec3(1.0, .47, .23), golden)
        self.sun.node().set_color(Vec4(*(sun_color * sunlight), 1))
        self.sun.set_pos(focus + sun_direction * 155)
        self.sun.look_at(focus)
        self.moon.look_at(-moon_direction)
        self.moon.node().set_color(Vec4(.10 * self.night, .17 * self.night, .33 * self.night, 1))
        ambient = mix(Vec3(.34, .41, .49), Vec3(.10, .145, .25), self.night)
        ambient = mix(ambient, Vec3(.21, .27, .36), weather * .58)
        self.ambient.node().set_color(Vec4(*ambient, 1))
        horizon = mix(Vec3(.40, .61, .75), Vec3(.57, .31, .21), golden)
        horizon = mix(horizon, Vec3(.065, .102, .17), self.night)
        zenith = mix(Vec3(.055, .195, .40), Vec3(.010, .021, .062), self.night)
        horizon = mix(horizon, Vec3(.17, .22, .28), weather * .77)
        zenith = mix(zenith, Vec3(.09, .12, .19), weather * .69)
        haze_density = .00135 + weather * .0028
        self.fog.set_exp_density(haze_density)
        self.fog.set_color(*(horizon * .88))
        self.wave_clock += dt
        if weather >= self.wetness:
            self.wetness = weather
        else:
            self.wetness = max(weather, self.wetness - dt * .055)
        self.city_root.set_shader_input("wetness", self.wetness)
        self.city_root.set_shader_input("harbor_eye", camera_position)
        self.city_root.set_shader_input("reflected_sky", mix(horizon, zenith, .29))
        self.city_root.set_shader_input("coastal_sun", sun_direction)
        self.city_root.set_shader_input("sun_strength", sunlight)
        if not self.water.is_empty():
            sun_edge = max(0.0, min(1.0, (sun_direction.z + .09) / .12))
            self.water.set_shader_input("sun_visible", sun_edge * sun_edge * (3 - 2 * sun_edge))
            self.water.set_shader_input("coastal_horizon", horizon)
            self.water.set_shader_input("haze_density", haze_density)
            self.water.set_shader_input("wave_clock", self.wave_clock)
            self.water.set_shader_input("darkness", self.night)
        self.sky.set_pos(camera_position)
        self.sky.set_shader_input("sun_dir", sun_direction)
        self.sky.set_shader_input("moon_dir", moon_direction)
        self.sky.set_shader_input("horizon", horizon)
        self.sky.set_shader_input("zenith", zenith)
        self.sky.set_shader_input("darkness", self.night)
        self.sky.set_shader_input("clock_angle", angle)
        self.sky.set_shader_input("storm", weather)
        return self.night

    def close(self):
        if self.pipeline:
            self.base.task_mgr.remove("simplepbr update")
            self.pipeline._filtermgr.cleanup()
