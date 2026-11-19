"""Create the in-game city map directly from the shared road grid."""

from pathlib import Path
from random import Random

from PIL import Image, ImageDraw

from .roads import CHUNK_MAX, CHUNK_MIN, CITY_MAX, CITY_MIN, ROAD_HALF_WIDTH, RoadGraph, district_at


_DISTRICT_PALETTE = {
    "downtown": ("#293d50", "#577084"),
    "residential": ("#263844", "#405764"),
    "harbor": ("#3b3b47", "#715e68"),
    "park": ("#234348", "#35615c"),
    "beachfront": ("#5a544b", "#89765d"),
}


def _draw_block(draw: ImageDraw.ImageDraw, rect: tuple[int, ...], district: str, rng: Random) -> None:
    left, top, right, bottom = rect
    size = right - left
    ground, accent = _DISTRICT_PALETTE[district]

    def xy(x: float, y: float) -> tuple[int, int]:
        return round(left + x * size), round(top + y * size)

    def box(x: float, y: float, width: float, height: float, color: str = accent) -> None:
        draw.rectangle((xy(x, y), xy(x + width, y + height)), fill=color)

    draw.rectangle((left, top, right, bottom), fill=ground)
    if district == "park":
        draw.line([xy(0.08, 0.72), xy(0.37, 0.54), xy(0.65, 0.59), xy(0.92, 0.28)], fill="#557367", width=2)
        for _ in range(14):
            x, y = rng.uniform(0.15, 0.82), rng.uniform(0.14, 0.81)
            draw.ellipse((xy(x, y), xy(x + 0.072, y + 0.072)), fill=accent)
    elif district == "harbor":
        box(0.12, 0.16, 0.45, 0.64)
        for row in range(3):
            box(0.64, 0.19 + row * 0.22, 0.23, 0.10, "#81636a")
    elif district == "beachfront":
        box(0.08, 0.10, 0.84, 0.17)
        box(0.08, 0.73, 0.84, 0.20, "#4f6570")
        box(0.25, 0.79, 0.56, 0.025, "#6c8188")
    else:
        footprint = 0.22 if district == "downtown" else 0.15
        for row in range(3):
            for column in range(3):
                x = 0.105 + column * 0.275 + rng.uniform(0, 0.035)
                y = 0.105 + row * 0.275 + rng.uniform(0, 0.035)
                box(x, y, footprint, footprint - rng.uniform(0, 0.06))


def write_minimap(path: str | Path, seed: int = 4812, size: int = 1024) -> Path:
    """Write a north-up square PNG. All pixels align with the city bounds."""
    path = Path(path)
    graph = RoadGraph()
    image = Image.new("RGB", (1024, 1024), "#14242f")
    draw = ImageDraw.Draw(image)
    scale = (image.width - 1) / (CITY_MAX - CITY_MIN)
    rng = Random(seed)

    def pixel(point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        return round((x - CITY_MIN) * scale), round((CITY_MAX - y) * scale)

    for column in range(CHUNK_MIN, CHUNK_MAX + 1):
        for row in range(CHUNK_MIN, CHUNK_MAX + 1):
            left, top = pixel(graph.position((column, row + 1)))
            right, bottom = pixel(graph.position((column + 1, row)))
            _draw_block(draw, (left, top, right, bottom), district_at(column, row), rng)

    pavement = round(2 * ROAD_HALF_WIDTH * scale)
    for width, local, main in (
        (pavement + 3, "#263340", "#384858"),
        (pavement, "#81909b", "#b5bbc0"),
    ):
        for origin, destination in graph.segments:
            axis = origin[1] if origin[1] == destination[1] else origin[0]
            point_a, point_b = pixel(graph.position(origin)), pixel(graph.position(destination))
            draw.line((point_a, point_b), fill=main if axis % 4 == 0 else local, width=width)

    if size != image.width:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path
