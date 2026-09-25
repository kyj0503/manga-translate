import http.client
import threading

import httpx
import pytest

from manga_translate.server import ApiError, Response, make_server

TOKEN = "secret-token"


@pytest.fixture
def base_url(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text('<script src="/static/app.js?token={{TOKEN}}"></script>', encoding="utf-8")
    (web / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (web / "notes.txt").write_text("no", encoding="utf-8")

    def boom(query):
        raise RuntimeError("kaboom")

    def busy(query):
        raise ApiError(409, "다른 작업이 진행 중입니다.")

    routes = {
        ("GET", "/api/echo"): lambda query: {"query": query},
        ("POST", "/api/echo"): lambda query: {"posted": query},
        ("GET", "/api/bytes"): lambda query: Response(b"\x89PNG", "image/png"),
        ("GET", "/api/busy"): busy,
        ("GET", "/api/boom"): boom,
    }
    server = make_server(routes, TOKEN, web)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(base_url, path, **kwargs):
    return httpx.get(base_url + path, trust_env=False, **kwargs)


def test_requests_without_the_token_are_forbidden(base_url):
    assert get(base_url, "/api/echo").status_code == 403
    assert get(base_url, "/api/echo?token=wrong").status_code == 403
    assert get(base_url, "/?token=wrong").status_code == 403


def test_token_in_query_or_header(base_url):
    assert get(base_url, f"/api/echo?token={TOKEN}&book=2").json() == {"query": {"book": "2"}}
    assert get(base_url, "/api/echo?index=1", headers={"X-Token": TOKEN}).json() == {"query": {"index": "1"}}


def test_post_route(base_url):
    response = httpx.post(f"{base_url}/api/echo?token={TOKEN}&a=1", trust_env=False)
    assert response.json() == {"posted": {"a": "1"}}


def test_index_gets_the_token(base_url):
    response = get(base_url, f"/?token={TOKEN}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f"app.js?token={TOKEN}" in response.text


def test_static_files(base_url):
    response = get(base_url, f"/static/app.js?token={TOKEN}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert get(base_url, f"/static/notes.txt?token={TOKEN}").status_code == 404
    assert get(base_url, f"/static/.hidden?token={TOKEN}").status_code == 404


def test_static_rejects_paths_outside_the_web_folder(base_url):
    host, port = base_url.removeprefix("http://").split(":")
    for path in (f"/static/../web/app.js?token={TOKEN}", f"/static/sub%2Fapp.js?token={TOKEN}"):
        connection = http.client.HTTPConnection(host, int(port))
        connection.request("GET", path)
        assert connection.getresponse().status == 404
        connection.close()


def test_bytes_response(base_url):
    response = get(base_url, f"/api/bytes?token={TOKEN}")
    assert response.content == b"\x89PNG"
    assert response.headers["content-type"] == "image/png"


def test_errors(base_url):
    busy = get(base_url, f"/api/busy?token={TOKEN}")
    assert busy.status_code == 409
    assert busy.json() == {"error": "다른 작업이 진행 중입니다."}
    boom = get(base_url, f"/api/boom?token={TOKEN}")
    assert boom.status_code == 500
    assert "kaboom" in boom.json()["error"]
    assert get(base_url, f"/api/nothing?token={TOKEN}").status_code == 404
