"""Generate Harbor City's original audio locally with NumPy and the wave module."""

from argparse import ArgumentParser
from math import tau
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Callable
import wave

import numpy as np
from numpy.typing import NDArray

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PROJECT_ROOT / "assets_generated"
SAMPLE_RATE = 44_100
AUDIO_VERSION = b"1\n"
Audio = NDArray[np.float64]


def _time(frames: int) -> Audio:
    return np.arange(frames, dtype=np.float64) / SAMPLE_RATE


def _band_noise(
    rng: np.random.Generator, frames: int, low: float, high: float
) -> Audio:
    """Shape periodic noise in the frequency domain to preserve loop boundaries."""
    spectrum = np.fft.rfft(rng.standard_normal(frames))
    frequencies = np.fft.rfftfreq(frames, 1 / SAMPLE_RATE)
    high_pass = 1 - 1 / (1 + (frequencies / low) ** 4)
    low_pass = 1 / (1 + (frequencies / high) ** 4)
    signal = np.fft.irfft(spectrum * high_pass * low_pass, n=frames)
    return signal / max(float(signal.std()), 1e-9)


def _engine(frames: int) -> Audio:
    t = _time(frames)
    rng = np.random.default_rng(208)
    # Four-stroke inline-four at 1,500 RPM. The breathing and crank texture
    # repeat with the two-revolution firing pattern.
    crank = tau * 25 * t
    crank += 0.055 * np.sin(tau * t) + 0.015 * np.sin(7 * tau * t / 2)
    firing = 2 * crank
    exhaust = np.zeros(frames)
    for harmonic in range(1, 16):
        falloff = 1 / harmonic ** 0.92
        exhaust += falloff * np.sin(harmonic * firing + 0.32 * harmonic**1.28)
    exhaust *= 0.83 + 0.09 * np.sin(crank) + 0.08 * np.sin(crank / 2.0)
    vibration = 0.22 * np.sin(crank) + 0.09 * np.sin(3 * crank + 0.8)
    intake = _band_noise(rng, frames, 90, 1100) * (0.04 + 0.035 * np.sin(firing))
    return np.tanh(exhaust + vibration + intake)


def _tire(frames: int) -> Audio:
    t = _time(frames)
    rng = np.random.default_rng(630)
    texture = 0.42 * _band_noise(rng, frames, 760, 5600)
    texture += 0.19 * _band_noise(rng, frames, 160, 1050)
    chatter = (0.91 + 0.06 * np.sin(2 * tau * t)) * (0.92 + 0.06 * np.sin(43 * tau * t))
    squeal_phase = 2030 * tau * t + 5.5 * np.sin(3 * tau * t) + 2 * np.sin(11 * tau * t / 2)
    squeal = 0.16 * np.sin(squeal_phase) + 0.07 * np.sin(2 * squeal_phase + 0.4)
    return np.tanh(chatter * (texture + squeal))


def _crash(frames: int) -> Audio:
    t = _time(frames)
    rng = np.random.default_rng(884)
    hit = (1 - np.exp(-780 * t)) * np.exp(-13 * t)
    thud = np.sin(tau * (48 * t + 38 * (1 - np.exp(-10 * t)) / 10))
    crush = _band_noise(rng, frames, 130, 1800)
    signal = hit * (0.78 * thud + 0.58 * crush)
    metal = _band_noise(rng, frames, 900, 6200)
    for delay, strength, damping in ((0.011, 0.43, 43), (0.056, 0.24, 32), (0.112, 0.12, 17)):
        age = np.maximum(0, t - delay)
        transient = (1 - np.exp(-600 * age)) * np.exp(-damping * age)
        rings = 0.49 * np.sin(tau * 387 * age) + 0.22 * np.sin(tau * 741 * age)
        signal += strength * transient * (metal + rings)
    return np.tanh(signal) * np.minimum(1, (t[-1] - t) / 0.05)


def _harbor(frames: int) -> Audio:
    t = _time(frames)
    rng = np.random.default_rng(112)
    phase = tau * t / (frames / SAMPLE_RATE)
    wash = (0.62 + 0.23 * np.sin(3 * phase - 1) + 0.12 * np.sin(5 * phase + 0.8)) ** 2
    water = wash * _band_noise(rng, frames, 180, 1950)
    wind = 0.32 * _band_noise(rng, frames, 60, 570)
    motor = 0.11 * np.sin(tau * 37.5 * t + 0.7 * np.sin(2 * phase))
    width = 0.20 * _band_noise(rng, frames, 170, 2900)
    middle = water + wind + motor
    return np.stack((middle + width, middle - width), axis=1)


_AUDIO = {
    "engine.wav": (_engine, 2 * SAMPLE_RATE, 1, 0.79),
    "tire.wav": (_tire, 2 * SAMPLE_RATE, 1, 0.61),
    "crash.wav": (_crash, SAMPLE_RATE, 1, 0.90),
    "harbor.wav": (_harbor, 12 * SAMPLE_RATE, 2, 0.38),
}


def _frequency(note: int) -> float:
    return 440 * 2 ** ((note - 69) / 12)


def _synth(t: Audio, note: int, color: float, detune: float = 1.0) -> Audio:
    phase = tau * _frequency(note) * detune * t
    phase += color * np.sin(2 * phase)
    return np.sin(phase) + 0.26 * np.sin(2 * phase) + 0.11 * np.sin(3 * phase)


def _add_clip(track: Audio, clip: Audio, start: int, pan: float) -> None:
    left = np.cos((pan + 1) * np.pi / 4)
    right = np.sin((pan + 1) * np.pi / 4)
    positions = (np.arange(len(clip)) + start) % len(track)
    track[positions, 0] += clip * left
    track[positions, 1] += clip * right


RADIO_BPM = 112
_RADIO_FRAMES = round(64 * 60 / RADIO_BPM * SAMPLE_RATE)


def _radio(frames: int) -> Audio:
    """Compose a sixteen-bar instrumental with an original harbor-night motif."""
    rng = np.random.default_rng(1055)
    track = np.zeros((frames, 2))
    beat_frames = frames / 64

    t = _time(round(0.28 * SAMPLE_RATE))
    kick_phase = tau * (47 * t + 112 * (1 - np.exp(-28 * t)) / 28)
    kick = 0.47 * np.sin(kick_phase) * np.exp(-16 * t) * (1 - np.exp(-850 * t))
    t = _time(round(0.24 * SAMPLE_RATE))
    snare = 0.105 * _band_noise(rng, len(t), 920, 7700) * np.exp(-24 * t)
    snare += 0.072 * np.sin(tau * 178 * t) * np.exp(-34 * t)
    snare *= np.minimum(1, 850 * t)
    t = _time(round(0.13 * SAMPLE_RATE))
    hat = 0.032 * _band_noise(rng, len(t), 5100, 12400) * np.exp(-45 * t)
    hat *= np.minimum(1, 1700 * t)

    # Chords, bass syncopation and a three-note hook are authored here. The
    # final note of each four-bar phrase changes to lead back into the verse.
    chords = ((38, 53, 57, 60, 64), (34, 50, 53, 57, 60),
              (41, 53, 57, 60, 67), (36, 52, 55, 62, 67))
    hook = ((69, 72, 65), (65, 69, 60), (72, 67, 69), (74, 67, 64))
    for bar in range(16):
        start = round(bar * 4 * beat_frames)
        root, *voices = chords[bar % 4]
        for beat in range(4):
            offset = start + round(beat * beat_frames)
            _add_clip(track, kick, offset, 0.0)
            if beat % 2:
                _add_clip(track, snare, offset, 0.04)
            _add_clip(track, hat, offset + round(0.51 * beat_frames), 0.35)
            if bar % 4 != 0:
                _add_clip(track, hat * 0.48, offset + round(0.8 * beat_frames), -0.30)

        t = _time(round(4.4 * beat_frames))
        fade = np.minimum(t / 0.37, (t[-1] - t) / 0.36).clip(0, 1)
        for voice, note in enumerate(voices):
            pan = (-0.76, 0.72, -0.38, 0.43)[voice]
            pad = 0.048 * _synth(t, note, 0.09, 1 + pan * 0.0018) * fade
            _add_clip(track, pad, start, pan)

        t = _time(round(0.58 * beat_frames))
        envelope = (1 - np.exp(-240 * t)) * np.exp(-9.3 * t) * np.minimum(1, (t[-1] - t) / 0.035)
        for beat, octave in ((0, 0), (0.75, 0), (1.55, 12), (2, 0), (2.75, 0), (3.52, 7)):
            bass = 0.20 * _synth(t, root + octave, 0.48) * envelope
            _add_clip(track, bass, start + round(beat * beat_frames), 0)

        if bar % 8 >= 2:
            t = _time(round(1.25 * beat_frames))
            envelope = (1 - np.exp(-150 * t)) * np.exp(-7 * t) * np.minimum(1, (t[-1] - t) / 0.07)
            for beat, note in zip((0.23, 1.7, 2.86), hook[bar % 4], strict=True):
                note_audio = 0.084 * _synth(t, note, 0.19) * envelope
                offset = start + round(beat * beat_frames)
                _add_clip(track, note_audio, offset, -0.22)
                _add_clip(track, note_audio * 0.30, offset + round(0.74 * beat_frames), 0.52)
    return np.tanh(track)


def _check_project_path(path: Path) -> None:
    if not path.resolve().is_relative_to(PROJECT_ROOT):
        raise ValueError(f"Asset path is outside the project: {path}")


def _atomic_write(destination: Path, write: Callable[[BinaryIO], object]) -> None:
    _check_project_path(destination)
    temporary = None
    try:
        with NamedTemporaryFile(dir=ASSET_DIR, prefix=".audio-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            write(stream)
        _check_project_path(temporary)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            _check_project_path(temporary)
            temporary.unlink(missing_ok=True)


def _valid_wave(path: Path, frames: int, channels: int) -> bool:
    _check_project_path(path)
    try:
        if path.stat().st_size < 44 + frames * channels * 2:
            return False
        with wave.open(str(path), "rb") as sound:
            return (sound.getnchannels(), sound.getsampwidth(), sound.getframerate(), sound.getnframes()) == (
                channels, 2, SAMPLE_RATE, frames
            )
    except (OSError, EOFError, wave.Error):
        return False


def _write_wave(path: Path, signal: Audio, peak: float, channels: int) -> None:
    scale = peak / max(float(np.max(np.abs(signal))), 1e-9)
    samples = np.rint(signal * scale * 32767).astype("<i2")

    def write(stream: BinaryIO) -> None:
        with wave.open(stream, "wb") as sound:
            sound.setnchannels(channels)
            sound.setsampwidth(2)
            sound.setframerate(SAMPLE_RATE)
            sound.writeframes(samples.tobytes())

    _atomic_write(path, write)


def _ensure_group(assets: dict, stamp_name: str) -> None:
    _check_project_path(ASSET_DIR)
    ASSET_DIR.mkdir(exist_ok=True)
    stamp = ASSET_DIR / stamp_name
    _check_project_path(stamp)
    current = stamp.is_file() and stamp.read_bytes() == AUDIO_VERSION
    for name, (generate, frames, channels, peak) in assets.items():
        path = ASSET_DIR / name
        if not current or not _valid_wave(path, frames, channels):
            _write_wave(path, generate(frames), peak, channels)
    if not current:
        _atomic_write(stamp, lambda stream: stream.write(AUDIO_VERSION))


def ensure_assets() -> Path:
    """Generate the base game audio if missing and return its directory."""
    _ensure_group(_AUDIO, ".audio-version")
    return ASSET_DIR


def ensure_radio() -> Path:
    """Generate the optional radio track and return its filename."""
    _ensure_group({"radio.wav": (_radio, _RADIO_FRAMES, 2, 0.83)}, ".radio-version")
    return ASSET_DIR / "radio.wav"


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--radio", action="store_true", help="also generate the optional radio track")
    args = parser.parse_args()
    directory = ensure_assets()
    if args.radio:
        ensure_radio()
    print(f"Procedural audio ready in {directory}")


if __name__ == "__main__":
    main()
