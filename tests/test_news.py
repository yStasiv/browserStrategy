import asyncio
import json
from io import BytesIO

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select

from backend import database
from backend.models import News, User
from backend.routers import news, player
from backend.services import news as service
from test_guild import asgi_request, sessions


@pytest.fixture
def news_app(sessions, tmp_path, monkeypatch):
    with sessions.begin() as db:
        db.get(User, 10).is_admin = True
    directory = tmp_path / "images" / "news"
    monkeypatch.setattr(service, "IMAGE_DIR", directory)
    app = FastAPI()
    app.include_router(news.router)
    app.include_router(player.router)
    app.mount("/static", news.PublicStaticFiles(directory=str(tmp_path)), name="static")

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db
    return app, directory


def call(app, method, path, user="other", form=None):
    return asyncio.run(asgi_request(app, method, path, f"session_id={user}-session" if user else "", form=form))


async def upload(app, filename, mime, contents, path="/admin/news"):
    boundary = b"news-test-data"
    fields = {"title": "Оновлення", "text": "Повний текст новини.", "link_url": "https://example.com/news"}
    parts = [b"--" + boundary + f'\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
             for name, value in fields.items()]
    parts += [b"--" + boundary + f'\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
              f"Content-Type: {mime}\r\n\r\n".encode() + contents + b"\r\n", b"--" + boundary + b"--\r\n"]
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"".join(parts)}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "method": "POST", "path": path, "query_string": b"", "scheme": "http",
        "server": ("testserver", 80), "headers": [(b"cookie", b"session_id=reader-session"),
        (b"content-type", b"multipart/form-data; boundary=" + boundary)],
    }, receive, send)
    return messages[0]["status"]


def test_image_validation_storage_preview_and_draft_access(news_app, sessions):
    app, directory = news_app
    png = BytesIO()
    Image.new("RGBA", (4, 4)).save(png, "PNG")
    valid = png.getvalue()
    for filename, mime, data in (("test.svg", "image/svg+xml", valid),
                                  ("test.png", "image/jpeg", valid),
                                  ("test.png", "image/png", b"not an image")):
        assert asyncio.run(upload(app, filename, mime, data)) == 422
    assert not directory.exists()
    assert asyncio.run(upload(app, "../draft.png", "image/png", valid)) == 303
    with sessions() as db:
        item = db.scalar(select(News))
        url = item.image_url
        assert item.status == "draft" and item.published_at is None
    assert url.startswith("/static/images/news/") and (directory / url.rsplit("/", 1)[-1]).read_bytes() == valid
    assert call(app, "GET", url)[0] == call(app, "GET", url, None)[0] == 404
    assert call(app, "GET", url, "reader")[0] == 200
    assert call(app, "GET", url.replace("/news/", "/news//"))[0] == 404
    assert call(app, "GET", url.replace("/news/", "/./news/"))[0] == 404
    assert b'news-image-preview' in call(app, "GET", "/admin/news/1/edit", "reader")[1]
    assert call(app, "GET", "/news/1")[0] == 404
    assert call(app, "GET", "/news/1", "reader")[0] == 200
    assert "Оновлення".encode() not in call(app, "GET", "/player")[1]
    assert json.loads(call(app, "GET", "/api/news/latest")[1]) == {"news": None}
    assert call(app, "POST", "/api/news/1/acknowledge")[0] == 404
    assert call(app, "POST", "/admin/news/1/publish")[0] == 403
    assert call(app, "POST", "/admin/news/1/publish", "reader")[0] == 303
    assert call(app, "GET", url)[0] == 200
    status, page = call(app, "GET", "/news/1")
    assert status == 200 and url.encode() in page
    assert "Повний текст новини.".encode() in page and b"https://example.com/news" in page
    assert asyncio.run(upload(app, "new.png", "image/png", valid, "/admin/news/1/edit")) == 303
    with sessions() as db:
        item = db.get(News, 1)
        assert item.status == "published" and item.image_url != url and item.published_at is not None


def test_latest_replaces_unread_and_character_expands_to_all(news_app, sessions):
    app, _ = news_app
    for index in range(1, 6):
        form = {"title": f"Новина {index}", "text": "Текст"}
        assert call(app, "POST", "/admin/news", "reader", form=form)[0] == 303
        if index < 5:
            assert call(app, "POST", f"/admin/news/{index}/publish", "reader")[0] == 303
        if index == 1:
            assert json.loads(call(app, "GET", "/api/news/latest")[1])["news"]["id"] == 1
    latest = lambda user="other": json.loads(call(app, "GET", "/api/news/latest", user)[1])["news"]
    assert latest()["id"] == 4
    assert call(app, "POST", "/api/news/1/acknowledge")[0] == 204
    assert latest()["id"] == 4
    assert call(app, "POST", "/api/news/4/acknowledge")[0] == 204
    assert call(app, "POST", "/api/news/4/acknowledge")[0] == 204
    assert latest() is None and latest("reader")["id"] == 4
    with sessions() as db:
        published_at = db.get(News, 4).published_at
    assert call(app, "POST", "/admin/news/4/publish", "reader")[0] == 303
    with sessions() as db:
        assert db.get(News, 4).published_at == published_at
    status, page = call(app, "GET", "/player")
    assert status == 200
    first, rest = page.split(b'<details class="news-more">', 1)
    assert [first.index(f'href="/news/{index}"'.encode()) for index in [4, 3, 2]] == sorted(
        first.index(f'href="/news/{index}"'.encode()) for index in [4, 3, 2])
    assert b'href="/news/1"' not in first and b'href="/news/1"' in rest
    assert b'href="/news/5"' not in page
    assert "Показати всі".encode() in rest and "Згорнути".encode() in rest
    assert call(app, "GET", "/news/4")[0] == 200
    assert call(app, "POST", "/admin/news", "reader", form={
        "title": "Небезпечне посилання", "text": "Текст", "link_url": "javascript:alert(1)",
    })[0] == 422


def test_inline_links_render_on_detail_page_and_in_popup_payload(news_app):
    app, _ = news_app
    body = "Дивись [<Умови>](https://example.com/rules?a=1&b=2).\n[Небезпечне](javascript:alert)"
    assert call(app, "POST", "/admin/news", "reader", form={"title": "Правила", "text": body})[0] == 303
    assert call(app, "POST", "/admin/news/1/publish", "reader")[0] == 303
    status, page = call(app, "GET", "/news/1")
    assert status == 200
    assert b'href="https://example.com/rules?a=1&amp;b=2"' in page
    assert "&lt;Умови&gt;".encode() in page
    assert b'href="javascript:' not in page
    latest = json.loads(call(app, "GET", "/api/news/latest")[1])["news"]
    assert latest["text_parts"] == [
        {"text": "Дивись "},
        {"text": "<Умови>", "url": "https://example.com/rules?a=1&b=2"},
        {"text": ".\n[Небезпечне](javascript:alert)"},
    ]
