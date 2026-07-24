"""A1 — the vision path in `app.runware`.

Probed against the live API, only one shape works::

    task["images"] = [...]                                  unsupportedParameter
    content: [{type:"image_url", image_url:{url}}]          providerBadRequest
    content: [{type:"image", source:{type:"base64", ...}}]  OK
    source: {type:"url", url}                               providerBadRequest

These tests pin that shape by asserting the emitted task JSON, with `httpx`
stubbed — no network, no key.
"""

from __future__ import annotations

import base64
import io

import pytest

from app import runware
from app.runware import RunwareError

PNG_1PX = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    b"IQAAAABJRU5ErkJggg=="
)
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF_MAGIC = b"GIF89a" + b"\x00" * 32
WEBP_MAGIC = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 24


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "image/png", status: int = 200):
        self.content = content
        self.headers = {"content-type": content_type}
        self.status_code = status
        self._json: dict = {"data": [{"text": "ok"}]}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise runware.httpx.HTTPStatusError("boom", request=None, response=None)


@pytest.fixture
def captured(monkeypatch):
    """Stub httpx.get (image fetch) and httpx.post (the task call). Capture the task."""
    box: dict = {"task": None, "fetched": []}

    def fake_get(url, **kw):
        box["fetched"].append(url)
        return FakeResponse(PNG_1PX)

    def fake_post(url, **kw):
        box["task"] = kw["json"][0]
        return FakeResponse(b"", status=200)

    monkeypatch.setattr(runware.httpx, "get", fake_get)
    monkeypatch.setattr(runware.httpx, "post", fake_post)
    monkeypatch.setattr(runware, "API_KEY", "test-key")
    return box


def _image_blocks(task: dict) -> list[dict]:
    content = task["messages"][-1]["content"]
    return [b for b in content if b.get("type") == "image"]


# ── the three input forms ────────────────────────────────────────────────────


class TestInputForms:
    def test_data_uri_is_inlined(self, captured):
        uri = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
        runware.text_inference([{"role": "user", "content": "read it"}], images=[uri])

        blocks = _image_blocks(captured["task"])
        assert len(blocks) == 1
        assert blocks[0]["source"]["type"] == "base64"
        assert blocks[0]["source"]["media_type"] == "image/png"
        assert base64.b64decode(blocks[0]["source"]["data"]) == PNG_1PX
        assert captured["fetched"] == []  # a data URI must not hit the network

    def test_https_url_is_downloaded_and_inlined(self, captured):
        url = "https://media.linqapp.com/abc123.png"
        runware.text_inference([{"role": "user", "content": "read it"}], images=[url])

        assert captured["fetched"] == [url]  # Runware rejects source.type="url"
        blocks = _image_blocks(captured["task"])
        assert blocks[0]["source"]["type"] == "base64"
        assert base64.b64decode(blocks[0]["source"]["data"]) == PNG_1PX

    def test_raw_base64_is_passed_through(self, captured):
        runware.text_inference(
            [{"role": "user", "content": "read it"}],
            images=[base64.b64encode(PNG_1PX).decode()],
        )
        blocks = _image_blocks(captured["task"])
        assert base64.b64decode(blocks[0]["source"]["data"]) == PNG_1PX
        assert captured["fetched"] == []


# ── the emitted task shape ───────────────────────────────────────────────────


class TestTaskShape:
    def test_no_top_level_images_key(self, captured):
        """The exact shape that returned unsupportedParameter."""
        runware.text_inference([{"role": "user", "content": "hi"}], images=[
            "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()])
        assert "images" not in captured["task"]

    def test_never_emits_a_url_source(self, captured):
        runware.text_inference([{"role": "user", "content": "hi"}],
                               images=["https://example.com/a.png"])
        for block in _image_blocks(captured["task"]):
            assert block["source"]["type"] == "base64"
            assert "url" not in block["source"]

    def test_text_comes_before_the_image(self, captured):
        runware.text_inference([{"role": "user", "content": "what price?"}],
                               images=["https://example.com/a.png"])
        content = captured["task"]["messages"][-1]["content"]
        assert content[0] == {"type": "text", "text": "what price?"}
        assert content[1]["type"] == "image"

    def test_empty_text_block_is_omitted(self, captured):
        """Anthropic rejects an empty text block outright."""
        runware.text_inference([{"role": "user", "content": ""}],
                               images=["https://example.com/a.png"])
        content = captured["task"]["messages"][-1]["content"]
        assert all(b["type"] != "text" for b in content)

    def test_several_images_ride_one_message(self, captured):
        runware.text_inference(
            [{"role": "user", "content": "both"}],
            images=["https://example.com/a.png", "https://example.com/b.png"],
        )
        assert len(_image_blocks(captured["task"])) == 2
        assert len(captured["task"]["messages"]) == 1

    def test_no_images_leaves_content_a_plain_string(self, captured):
        runware.text_inference([{"role": "user", "content": "text only"}])
        assert captured["task"]["messages"][-1]["content"] == "text only"

    def test_system_prompt_still_lifts_into_settings(self, captured):
        runware.text_inference(
            [{"role": "system", "content": "be terse"},
             {"role": "user", "content": "hi"}],
            images=["https://example.com/a.png"],
        )
        assert captured["task"]["settings"]["systemPrompt"] == "be terse"
        assert all(m["role"] != "system" for m in captured["task"]["messages"])


# ── message-list handling ────────────────────────────────────────────────────


class TestMessageHandling:
    def test_caller_messages_are_not_mutated(self, captured):
        """text_inference rewrites `content`; the caller's dicts must survive."""
        messages = [{"role": "user", "content": "read it"}]
        runware.text_inference(messages, images=["https://example.com/a.png"])
        assert messages == [{"role": "user", "content": "read it"}]

    def test_images_open_a_new_turn_after_an_assistant_message(self, captured):
        """Anthropic only accepts images on a user message."""
        runware.text_inference(
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
            images=["https://example.com/a.png"],
        )
        messages = captured["task"]["messages"]
        assert messages[-1]["role"] == "user"
        assert _image_blocks(captured["task"])
        assert messages[1]["content"] == "hello"  # assistant turn untouched

    def test_images_with_no_messages_at_all(self, captured):
        runware.text_inference([], images=["https://example.com/a.png"])
        messages = captured["task"]["messages"]
        assert len(messages) == 1 and messages[0]["role"] == "user"
        assert _image_blocks(captured["task"])


# ── media-type sniffing ──────────────────────────────────────────────────────


class TestMediaSniffing:
    @pytest.mark.parametrize("raw,expected", [
        (PNG_1PX, "image/png"),
        (JPEG_MAGIC, "image/jpeg"),
        (GIF_MAGIC, "image/gif"),
        (WEBP_MAGIC, "image/webp"),
    ])
    def test_magic_bytes_win_over_a_useless_content_type(self, raw, expected):
        # Linq media URLs routinely serve application/octet-stream.
        assert runware._sniff_media(raw, "application/octet-stream") == expected

    def test_declared_type_is_trusted_when_valid(self):
        assert runware._sniff_media(JPEG_MAGIC, "image/webp") == "image/webp"

    def test_image_jpg_is_normalised(self):
        assert runware._sniff_media(JPEG_MAGIC, "image/jpg") == "image/jpeg"

    def test_unknown_bytes_default_to_png(self):
        assert runware._sniff_media(b"not an image at all", "") == "image/png"

    def test_url_content_type_is_honoured(self, captured, monkeypatch):
        monkeypatch.setattr(
            runware.httpx, "get",
            lambda url, **kw: FakeResponse(JPEG_MAGIC, "image/jpeg; charset=binary"),
        )
        runware.text_inference([{"role": "user", "content": "x"}],
                               images=["https://example.com/a.jpg"])
        assert _image_blocks(captured["task"])[0]["source"]["media_type"] == "image/jpeg"


# ── downscaling ──────────────────────────────────────────────────────────────


class TestDownscale:
    def _big_png(self, w: int, h: int) -> bytes:
        Image = pytest.importorskip("PIL.Image")
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (200, 40, 40)).save(buf, format="PNG")
        return buf.getvalue()

    def test_large_screenshot_is_capped_at_the_long_edge(self):
        Image = pytest.importorskip("PIL.Image")
        raw, media = runware._downscale(self._big_png(3000, 1500), "image/png")
        assert max(Image.open(io.BytesIO(raw)).size) <= runware.MAX_IMAGE_EDGE
        assert media == "image/jpeg"

    def test_downscaling_shrinks_a_realistic_screenshot(self):
        """A flat colour would compress *better* as PNG; use real-ish content."""
        Image = pytest.importorskip("PIL.Image")
        import numpy as np

        pixels = np.random.default_rng(0).integers(0, 255, (1500, 3000, 3), dtype="uint8")
        buf = io.BytesIO()
        Image.fromarray(pixels).save(buf, format="PNG")
        big = buf.getvalue()

        raw, _ = runware._downscale(big, "image/png")
        assert len(raw) < len(big) / 2  # ~4x fewer pixels, plus lossy encoding

    def test_small_image_is_left_untouched(self):
        pytest.importorskip("PIL.Image")
        small = self._big_png(400, 300)
        raw, media = runware._downscale(small, "image/png")
        assert raw == small and media == "image/png"

    def test_undecodable_bytes_pass_through(self):
        """A resize failure must never cost the user their negotiation turn."""
        raw, media = runware._downscale(b"definitely not an image", "image/png")
        assert raw == b"definitely not an image" and media == "image/png"

    def test_missing_pillow_degrades_to_passthrough(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def no_pillow(name, *a, **kw):
            if name.startswith("PIL"):
                raise ModuleNotFoundError("No module named 'PIL'")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", no_pillow)
        raw, media = runware._downscale(PNG_1PX, "image/png")
        assert raw == PNG_1PX and media == "image/png"


# ── failure modes ────────────────────────────────────────────────────────────


class TestFailures:
    def test_unfetchable_url_raises_runware_error(self, captured, monkeypatch):
        def boom(url, **kw):
            raise runware.httpx.ConnectError("dns failure")

        monkeypatch.setattr(runware.httpx, "get", boom)
        with pytest.raises(RunwareError, match="could not fetch image"):
            runware.text_inference([{"role": "user", "content": "x"}],
                                   images=["https://example.com/gone.png"])

    def test_malformed_base64_raises_runware_error(self, captured):
        with pytest.raises(RunwareError, match="base64"):
            runware.text_inference([{"role": "user", "content": "x"}],
                                   images=["!!!! not base64 !!!!"])

    def test_empty_image_raises_runware_error(self, captured, monkeypatch):
        monkeypatch.setattr(runware.httpx, "get", lambda url, **kw: FakeResponse(b""))
        with pytest.raises(RunwareError, match="empty"):
            runware.text_inference([{"role": "user", "content": "x"}],
                                   images=["https://example.com/empty.png"])

    def test_missing_key_still_raises_before_any_fetch(self, monkeypatch):
        monkeypatch.setattr(runware, "API_KEY", "")
        fetched = []
        monkeypatch.setattr(runware.httpx, "get",
                            lambda url, **kw: fetched.append(url) or FakeResponse(PNG_1PX))
        with pytest.raises(RunwareError, match="RUNWARE_API_KEY"):
            runware.text_inference([{"role": "user", "content": "x"}],
                                   images=["https://example.com/a.png"])
        assert fetched == []  # don't burn a download when the call can't happen
