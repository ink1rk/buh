#!/usr/bin/env python3
"""Text-to-speech with switchable voices.

Two engines: Silero (better Russian prosody, female voices) and Piper (tiny and
fast, the original male voice). Each preset can slow the delivery, drop the
pitch and pass the result through an ffmpeg chain — that is what turns a neutral
reading into a soft, velvety one.
"""
import io
import os
import re
import subprocess
import tempfile
import threading
import wave

SILERO_MODEL = os.environ.get("SILERO_MODEL", "/opt/assistant/voices/v4_ru.pt")
PIPER_DIR = os.environ.get("PIPER_DIR", "/opt/assistant/voices")
DEFAULT_VOICE = os.environ.get("TTS_VOICE", "baya_velvet")
SILERO_RATE = int(os.environ.get("SILERO_RATE", "48000"))
SILERO_THREADS = int(os.environ.get("SILERO_THREADS", "6"))

# Velvet: pitch a touch lower, unhurried pace, warm low-mids, softened
# sibilants, a hint of room so the voice sounds close and breathy.
FX_VELVET = ("asetrate=48000*0.94,aresample=48000,atempo=1.0638,"
             "equalizer=f=170:t=q:w=1.2:g=4,equalizer=f=320:t=q:w=1.5:g=2,"
             "equalizer=f=2800:t=q:w=2:g=-3,aecho=0.85:0.9:16:0.10,"
             "dynaudnorm=f=250:g=6")
FX_WARM = ("equalizer=f=200:t=q:w=1.2:g=2.5,equalizer=f=3000:t=q:w=2:g=-1.5,"
           "dynaudnorm=f=250:g=6")

VOICES = {
    "baya_velvet": {
        "engine": "silero", "speaker": "baya", "rate": "slow", "pitch": "low",
        "fx": FX_VELVET, "title": "Бая — бархатный, медленный",
        "hint": "низкий тёплый тембр, неспешно",
    },
    "baya": {
        "engine": "silero", "speaker": "baya", "rate": "medium", "pitch": "medium",
        "fx": FX_WARM, "title": "Бая — обычный",
        "hint": "тот же голос, но живее и быстрее",
    },
    "kseniya_velvet": {
        "engine": "silero", "speaker": "kseniya", "rate": "slow", "pitch": "low",
        "fx": FX_VELVET, "title": "Ксения — бархатный, медленный",
        "hint": "мягче и воздушнее, чем Бая",
    },
    "kseniya": {
        "engine": "silero", "speaker": "kseniya", "rate": "medium", "pitch": "medium",
        "fx": FX_WARM, "title": "Ксения — обычный",
        "hint": "спокойный женский",
    },
    "xenia_velvet": {
        "engine": "silero", "speaker": "xenia", "rate": "slow", "pitch": "low",
        "fx": FX_VELVET, "title": "Ксюша — бархатный, молодой",
        "hint": "моложе и звонче",
    },
    "irina": {
        "engine": "piper", "model": "ru_RU-irina-medium.onnx",
        "length_scale": 1.15, "noise_scale": 0.62, "noise_w_scale": 0.85,
        "fx": FX_VELVET, "title": "Ирина (Piper) — быстрый локальный",
        "hint": "чуть механичнее, зато мгновенно",
    },
    "dmitri": {
        "engine": "piper", "model": "ru_RU-dmitri-medium.onnx",
        "length_scale": 1.0, "noise_scale": 0.667, "noise_w_scale": 0.8,
        "fx": None, "title": "Дмитрий — мужской (как было)",
        "hint": "прежний голос ассистента",
    },
}

_lock = threading.Lock()
_silero = None
_pipers: dict = {}
_active = DEFAULT_VOICE if DEFAULT_VOICE in VOICES else "baya_velvet"
_on_change = None       # optional callback(name) to persist the choice


def voices():
    return {name: {"title": cfg["title"], "hint": cfg["hint"], "engine": cfg["engine"]}
            for name, cfg in VOICES.items()}


def active():
    return _active


def set_active(name, persist=True):
    global _active
    if name not in VOICES:
        raise ValueError(f"нет такого голоса: {name}")
    _active = name
    if persist and _on_change:
        _on_change(name)
    return _active


def bind_storage(load, save):
    """Wire the preset to persistent storage so it survives restarts."""
    global _active, _on_change
    _on_change = save
    stored = load()
    if stored in VOICES:
        _active = stored


def _get_silero():
    global _silero
    if _silero is None:
        with _lock:
            if _silero is None:
                import torch
                torch.set_num_threads(SILERO_THREADS)
                model = torch.package.PackageImporter(SILERO_MODEL).load_pickle(
                    "tts_models", "model")
                model.to("cpu")
                _silero = model
    return _silero


def _get_piper(model_name):
    voice = _pipers.get(model_name)
    if voice is None:
        with _lock:
            voice = _pipers.get(model_name)
            if voice is None:
                from piper import PiperVoice
                voice = PiperVoice.load(os.path.join(PIPER_DIR, model_name))
                _pipers[model_name] = voice
    return voice


def _chunks(text, limit=700):
    """Silero degrades on very long input, so feed it sentence by sentence."""
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    out, current = [], ""
    for sentence in sentences:
        while len(sentence) > limit:
            out.append(sentence[:limit])
            sentence = sentence[limit:]
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out or [text]


def _ssml(text, rate, pitch):
    safe = (text.replace("&", "и").replace("<", " ").replace(">", " "))
    return f'<speak><prosody rate="{rate}" pitch="{pitch}">{safe}</prosody></speak>'


def _silero_wav(text, cfg):
    import numpy as np
    model = _get_silero()
    pieces = []
    for chunk in _chunks(text):
        audio = model.apply_tts(ssml_text=_ssml(chunk, cfg["rate"], cfg["pitch"]),
                                speaker=cfg["speaker"], sample_rate=SILERO_RATE)
        pieces.append(audio.numpy())
        pieces.append(np.zeros(int(SILERO_RATE * 0.12), dtype=pieces[-1].dtype))
    data = np.concatenate(pieces) if pieces else np.zeros(1, dtype="float32")
    peak = float(abs(data).max()) or 1.0
    samples = (data / max(peak, 0.2) * 0.92 * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SILERO_RATE)
        wav.writeframes(samples.tobytes())
    return buf.getvalue()


def _piper_wav(text, cfg):
    from piper import SynthesisConfig
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        _get_piper(cfg["model"]).synthesize_wav(
            text or "…", wav,
            syn_config=SynthesisConfig(length_scale=cfg.get("length_scale", 1.0),
                                       noise_scale=cfg.get("noise_scale", 0.667),
                                       noise_w_scale=cfg.get("noise_w_scale", 0.8),
                                       normalize_audio=True))
    return buf.getvalue()


def _apply_fx(wav_bytes, chain):
    if not chain:
        return wav_bytes
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        src = f.name
    dst = src + ".fx.wav"
    try:
        subprocess.run(["ffmpeg", "-y", "-i", src, "-af", chain, dst],
                       capture_output=True, check=True, timeout=120)
        with open(dst, "rb") as f:
            return f.read()
    except Exception as e:
        print("tts fx failed:", e)
        return wav_bytes
    finally:
        for path in (src, dst):
            try:
                os.unlink(path)
            except OSError:
                pass


def synthesize(text, name=None):
    """Return WAV bytes for the given (or active) preset."""
    cfg = VOICES.get(name or _active) or VOICES[_active]
    text = (text or "…").strip()
    raw = _silero_wav(text, cfg) if cfg["engine"] == "silero" else _piper_wav(text, cfg)
    return _apply_fx(raw, cfg.get("fx"))


def warm_up():
    """Load the active engine in the background: first reply shouldn't wait."""
    def loop():
        try:
            synthesize("Готова.", _active)
        except Exception as e:
            print("tts warm-up failed:", e)

    threading.Thread(target=loop, daemon=True, name="tts-warm").start()


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else _active
    sample = (sys.argv[2] if len(sys.argv) > 2
              else "Привет. Я на связи и всё для тебя сделаю.")
    out = f"/tmp/{name}.wav"
    with open(out, "wb") as f:
        f.write(synthesize(sample, name))
    print(out)
