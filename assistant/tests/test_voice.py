"""Voice is input only: speech comes in, text goes out, nothing ever breaks."""
import asyncio


class Upload:
    """Достаточно того, что FastAPI отдаёт эндпоинту: асинхронное чтение."""

    def __init__(self, data=b""):
        self.data = data

    async def read(self):
        return self.data


class Deaf:
    """Модель, которая не смогла декодировать запись."""

    def transcribe(self, *args, **kwargs):
        raise RuntimeError("Invalid data found when processing input")


def test_broken_recording_becomes_a_typed_error(monkeypatch):
    import assistant
    monkeypatch.setattr(assistant, "get_whisper", lambda: Deaf())
    try:
        assistant.stt_bytes(b"not audio at all")
    except assistant.UnreadableAudio:
        return
    raise AssertionError("ожидали UnreadableAudio")


def test_stt_endpoint_answers_instead_of_failing(monkeypatch):
    import assistant

    def explode(_):
        raise assistant.UnreadableAudio("битый файл")

    monkeypatch.setattr(assistant, "stt_bytes", explode)
    result = asyncio.run(assistant.stt(Upload(b"junk")))
    assert result["text"] == "" and result["error"]


def test_voice_endpoint_answers_with_text_and_no_audio(monkeypatch):
    import assistant

    def explode(_):
        raise assistant.UnreadableAudio("битый файл")

    monkeypatch.setattr(assistant, "stt_bytes", explode)
    result = asyncio.run(assistant.api_voice(Upload(b"junk")))
    assert result["reply"] and result["error"] == "unreadable_audio"
    assert not any(key in result for key in ("audio", "audio_b64", "voice"))


def test_silence_is_reported_not_sent_to_the_model(monkeypatch):
    import assistant
    monkeypatch.setattr(assistant, "stt_bytes", lambda _: "")

    def fail(*args, **kwargs):
        raise AssertionError("тишину не за чем отправлять в модель")

    monkeypatch.setattr(assistant, "chat", fail)
    result = asyncio.run(assistant.api_voice(Upload(b"")))
    assert result["error"] == "empty_audio"
