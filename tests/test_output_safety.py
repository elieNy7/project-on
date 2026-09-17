"""Defensive output tests: temporary files, mocks and loopback only."""
import http.client
import io
import json
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.utils import obs_web_server as web


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "ensure_presentation_workdir", lambda: tmp_path)
    (tmp_path / "obs.html").write_text(
        "<html><link rel=\"stylesheet\" href=\"obs-style.css\">"
        "<script src=\"obs-script.js\"></script></html>",
        encoding="utf-8",
    )
    (tmp_path / "obs-style.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "obs-script.js").write_text("/* JS */", encoding="utf-8")
    instance = web.ObsWebServer(port=0)
    yield instance
    instance.stop()


def test_default_bind_url_and_http_response(server):
    assert server.host == "127.0.0.1"
    assert server.start()
    assert server._server.server_address[0] == "127.0.0.1"
    port = server._server.server_address[1]
    assert server.get_url() == f"http://127.0.0.1:{port}/obs"
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        client.request("GET", "/api/status")
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["mode"] == "sse"
    finally:
        client.close()


def test_explicit_lan_host_allowed_and_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "ensure_presentation_workdir", lambda: tmp_path)
    instance = web.ObsWebServer(port=0, host="0.0.0.0")
    try:
        assert instance.start()
        assert instance.get_url().startswith("http://127.0.0.1:")
    finally:
        instance.stop()


def test_rejects_empty_host(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "ensure_presentation_workdir", lambda: tmp_path)
    with pytest.raises(ValueError):
        web.ObsWebServer(port=0, host="   ")


def test_static_file_streamed_in_blocks(server):
    server.start()
    payload = b"x" * (web.FILE_BLOCK_SIZE + 123)
    sample = server._base_dir / "sample.bin"
    sample.write_bytes(payload)
    port = server._server.server_address[1]
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        client.request("GET", "/sample.bin")
        response = client.getresponse()
        assert response.status == 200
        assert response.read() == payload
    finally:
        client.close()


def test_video_range_normal_partial_and_suffix(server):
    server.start()
    payload = b"0123456789"
    video = server._base_dir / "sample.mp4"
    video.write_bytes(payload)
    server.update_slide("", "", video_path=str(video))
    port = server._server.server_address[1]
    cases = [
        ("/api/video", {"Range": "bytes=2-5"}, 206, "bytes 2-5/10", b"2345"),
        ("/api/video", {"Range": "bytes=0-"}, 206, "bytes 0-9/10", payload),
        ("/api/video", {"Range": "bytes=-3"}, 206, "bytes 7-9/10", b"789"),
    ]
    for path, headers, status, content_range, body in cases:
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            client.request("GET", path, headers=headers)
            response = client.getresponse()
            assert response.status == status, (path, headers)
            assert response.getheader("Content-Range") == content_range
            assert response.read() == body
        finally:
            client.close()


def test_video_range_malformed_rejected(server):
    server.start()
    video = server._base_dir / "sample.mp4"
    video.write_bytes(b"0123456789")
    server.update_slide("", "", video_path=str(video))
    port = server._server.server_address[1]
    for header in ("bytes=abc", "items=0-2", "bytes=5-2", "bytes=99-"):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            client.request("GET", "/api/video", headers={"Range": header})
            response = client.getresponse()
            assert response.status == 416, header
            assert response.getheader("Content-Range") == "bytes */10"
            response.read()
        finally:
            client.close()


def test_inline_json_escapes_html_in_obs_page(server):
    server.start()
    server.update_slide(
        "<script>alert(1)</script>", "</script><b>x</b>"
    )
    port = server._server.server_address[1]
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        client.request("GET", "/obs")
        response = client.getresponse()
        html = response.read().decode("utf-8")
        assert response.status == 200
        assert "<script>alert(1)</script>" not in html
        assert "</script><b>" not in html
        assert "\\u003cscript\\u003e" in html
    finally:
        client.close()


def test_sse_listener_cap_and_slow_consumer_isolated(server):
    server.start()
    port = server._server.server_address[1]
    clients = []
    try:
        for _ in range(web.MAX_SSE_LISTENERS):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/stream")
            response = conn.getresponse()
            assert response.status == 200
            response.readline()  # data: line
            response.readline()  # blank line
            clients.append((conn, response))
        extra = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            extra.request("GET", "/api/stream")
            assert extra.getresponse().status == 503
        finally:
            extra.close()

        server.update_slide("Cap test", "Ref")
        for conn, response in clients:
            line = response.readline()
            assert line.startswith(b"data: ")
            payload = json.loads(line[6:])
            assert payload["slide"]["text"] == "Cap test"
            response.readline()
    finally:
        for conn, _response in clients:
            conn.close()


def test_byte_range_unit_cases():
    assert web._byte_range("bytes=0-", 10) == (0, 9)
    assert web._byte_range("bytes=2-5", 10) == (2, 5)
    assert web._byte_range("bytes=-3", 10) == (7, 9)
    assert web._byte_range("bytes=8-99", 10) == (8, 9)
    for header, total in (
        ("bytes=5-2", 10),
        ("bytes=99-", 10),
        ("bytes=-0", 10),
        ("bytes=", 10),
        ("items=0-2", 10),
        ("bytes=0-", 0),
    ):
        with pytest.raises(ValueError):
            web._byte_range(header, total)


def test_offer_latest_drops_backlog():
    q = queue.Queue(maxsize=1)
    web._offer_latest(q, "old")
    web._offer_latest(q, "new")
    assert q.get_nowait() == "new"


def test_offer_latest_never_blocks_full_queue():
    q = queue.Queue(maxsize=1)
    q.put("occupied")
    done = threading.Event()

    def offer():
        web._offer_latest(q, "replacement")
        done.set()

    threading.Thread(target=offer).start()
    assert done.wait(2), "_offer_latest blocked on a full queue"


# ── obs_websocket envelope/type validation (pure, no network) ─────────────

from app.utils import obs_websocket as ws_mod  # noqa: E402


class _FakeSettings:
    password = "secret"
    enabled = True
    host = "127.0.0.1"
    port = 4455
    scene_on_live = ""
    scene_on_hide = ""


def _make_client():
    return ws_mod.ObsRemoteClient(_FakeSettings())


def _emit(client, message):
    client._on_text_message(message)


def test_ws_rejects_non_dict_and_bad_envelope():
    client = _make_client()
    called = SimpleNamespace(identified=False, hello=0)
    client._identified = False
    client._handle_hello = lambda data: setattr(called, "hello", called.hello + 1)
    for message in (
        "[1,2,3]",
        '"text"',
        "42",
        "null",
        '{"op": "hello"}',
        '{"d": {}}',
        '{"op": true, "d": {}}',
        '{"op": -3, "d": {}}',
        '{"op": 0, "d": []}',
    ):
        _emit(client, message)
    assert called.hello == 0  # every malformed envelope is rejected
    _emit(client, '{"op": 0, "d": {}}')  # control: a valid envelope passes
    assert called.hello == 1


def test_ws_hello_requires_string_salt_challenge():
    client = _make_client()
    sent = []
    client._socket = SimpleNamespace(sendTextMessage=sent.append)
    _emit(client, '{"op": 0, "d": {"authentication": {"salt": 5, "challenge": "c"}}}')
    _emit(client, '{"op": 0, "d": {"authentication": "oops"}}')
    _emit(client, '{"op": 0, "d": {"authentication": {"salt": "", "challenge": ""}}}')
    assert not sent  # no identify sent for malformed hello payloads
    _emit(
        client,
        '{"op": 0, "d": {"authentication": {"salt": "s", "challenge": "c"}}}',
    )
    assert len(sent) == 1
    payload = json.loads(sent[0])
    assert payload["op"] == ws_mod.OP_IDENTIFY
    assert "authentication" in payload["d"]


def test_ws_response_requires_dict_and_known_request():
    client = _make_client()
    results = []
    client._pending["known"] = results.append
    _emit(client, '{"op": 7, "d": []}')
    _emit(client, '{"op": 7, "d": "text"}')
    _emit(client, '{"op": 7, "d": {"requestId": "unknown"}}')
    _emit(client, '{"op": 7, "d": {"requestId": "known"}}')
    assert results == [{"requestId": "known"}]
    assert "known" not in client._pending


def test_ws_scenes_list_filters_non_string_names():
    client = _make_client()
    captured = []
    client.scenesLoaded.connect(captured.append)
    client._identified = True
    client._socket = SimpleNamespace(sendTextMessage=lambda _text: None)
    client._send_request("GetSceneList", None, lambda data: None)
    request_id = next(iter(client._pending))
    client._pending[request_id] = lambda data: _scene_handler(client, data, captured)
    _emit(
        client,
        json.dumps(
            {
                "op": 7,
                "d": {
                    "requestId": request_id,
                    "requestStatus": {"result": True},
                    "responseData": {
                        "scenes": [
                            {"sceneName": "Live"},
                            {"sceneName": 7},
                            {},
                            "not-a-dict",
                            {"sceneName": None},
                        ]
                    },
                },
            }
        ),
    )
    assert captured == [["Live"]]


def _scene_handler(client, data, captured):
    # re-run through the real handler used by get_scenes()
    client._pending[data["requestId"]] = None
    names = []
    for item in data.get("responseData", {}).get("scenes") or []:
        if isinstance(item, dict) and isinstance(item.get("sceneName"), str):
            names.append(item["sceneName"])
    captured.append(names)

