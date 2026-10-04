"""Serving the UI, from docs/ui-design.md. What the page does is checked by hand."""

from pathlib import Path

import pytest

import app

STATIC = Path(app.__file__).parent / "static"
CONTENT_TYPES = {".css": "text/css", ".js": "text/javascript"}


def test_the_page_is_served_without_a_known_user(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == (STATIC / "index.html").read_text()


def test_every_ui_file_is_served_as_its_own_type(client):
    files = [path for path in STATIC.iterdir() if path.suffix in CONTENT_TYPES]
    # A browser does not run a module that arrives with another content type.
    assert {path.suffix for path in files} == set(CONTENT_TYPES)

    for path in files:
        response = client.get(f"/static/{path.name}")

        assert response.status_code == 200, path.name
        assert response.headers["content-type"].startswith(CONTENT_TYPES[path.suffix]), path.name


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unknown_route_keeps_the_framework_answer(client, method):
    response = client.request(method, "/no-such-page")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
