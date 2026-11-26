import asyncio
import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend import database
from backend.config import SYSTEM_PLAYER_ID
from backend.engine import battle_api
from backend.models import Item, PlayerModerationEvent, RewardTransaction, ShopItem, User
from backend.routers import admin, auth, castle, map as world_map, player, presence, shop
from backend.services import player_moderation
from backend.utils import hash_password
from test_guild import asgi_request, sessions


@pytest.fixture
def moderation_app(sessions, monkeypatch):
    with sessions.begin() as db:
        db.get(User, 10).is_admin = True
        subject = db.get(User, 2)
        subject.password = hash_password("known-password")
        db.add_all([
            User(id=33, username="moderator", is_moderator=True, session_id="moderator-session"),
            User(id=34, username="ordinary", session_id="ordinary-session"),
            ShopItem(id=21, item_template=Item(name="Пояс", item_type="belt", durability=8, max_durability=8),
                     price=10, quantity=1),
            RewardTransaction(issuer_id=SYSTEM_PLAYER_ID, recipient_id=2, source="guild_quest",
                              source_key="existing", gold=9, wood=0, stone=0, created_at=datetime(2026, 11, 1)),
        ])
    monkeypatch.setattr(player_moderation, "utc_now", lambda: datetime(2026, 11, 25, 14, 5))
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    for module in (auth, admin, player, battle_api, castle, shop, presence, world_map):
        app.include_router(module.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db
    return app


def call(app, method, path, account="other", *, form=None, payload=None):
    cookie = f"session_id={account}-session" if account else ""
    return asyncio.run(asgi_request(app, method, path, cookie, form=form, payload=payload))


@pytest.mark.parametrize(("account", "actor_id"), [("reader", 10), ("moderator", 33)])
def test_block_unblock_and_audit(moderation_app, sessions, account, actor_id):
    request = lambda method, path, **kwargs: call(moderation_app, method, path, account, **kwargs)
    block = "/admin/player/2/block"
    unblock = "/admin/player/2/unblock"
    assert request("POST", block, form={"reason": "  "})[0] == 422
    assert request("POST", block, form={"reason": " Порушення правил "})[0] == 303
    assert request("POST", block, form={"reason": "Повтор"})[0] == 409
    blocked = "25-11-2026 16:05 Гравець заблокований: Порушення правил"
    status, body = request("GET", "/player_info?id=2")
    assert status == 200 and blocked in body.decode() and unblock.encode() in body
    assert request("POST", unblock)[0] == 303
    assert request("POST", unblock)[0] == 409
    unblocked = "25-11-2026 16:05 Гравець розблокований"
    status, body = request("GET", "/player_info/transfers?id=2")
    page = body.decode()
    assert status == 200 and page.index(unblocked) < page.index(blocked)
    assert "Золото · 9" in page
    with sessions() as db:
        user = db.get(User, 2)
        assert user.ban_reason is None and user.session_id is None
        events = db.scalars(select(PlayerModerationEvent).order_by(PlayerModerationEvent.id)).all()
        assert [(row.actor_id, row.action, row.reason) for row in events] == [
            (actor_id, "block", "Порушення правил"), (actor_id, "unblock", None),
        ]


def test_moderator_role_controls_and_permissions(moderation_app):
    path = "/admin/player/2/moderator"
    block = "/admin/player/2/block"
    for account in ("ordinary", "moderator"):
        assert call(moderation_app, "POST", path, account, form={"enabled": "true"})[0] == 403
        assert path.encode() not in call(moderation_app, "GET", "/player_info?id=2", account)[1]
    assert call(moderation_app, "POST", block, "ordinary", form={"reason": "Перевірка"})[0] == 403
    assert call(moderation_app, "POST", "/admin/player/10/block", "moderator", form={"reason": "Перевірка"})[0] == 403
    assert call(moderation_app, "GET", "/admin/api/stats", "moderator")[0] == 403
    assert path.encode() in call(moderation_app, "GET", "/player_info?id=2", "reader")[1]
    assert call(moderation_app, "POST", path, "reader", form={"enabled": "true"})[0] == 303
    assert "Відкликати роль модератора" in call(moderation_app, "GET", "/player_info?id=2", "reader")[1].decode()
    assert call(moderation_app, "POST", "/admin/player/34/block", form={"reason": "Перевірка"})[0] == 303
    assert call(moderation_app, "POST", path, "reader", form={"enabled": "false"})[0] == 303
    assert call(moderation_app, "POST", "/admin/player/34/unblock")[0] == 403


def test_blocked_login_and_gameplay(moderation_app, sessions):
    assert call(moderation_app, "POST", "/admin/player/2/block", "reader", form={"reason": "Причина <тест>"})[0] == 303
    credentials = {"username": "other", "password": "known-password"}
    status, body = call(moderation_app, "POST", "/login", None, form=credentials)
    assert status == 403 and "Причина &lt;тест&gt;" in body.decode()
    assert call(moderation_app, "POST", "/login", None, form=dict(credentials, password="wrong"))[0] == 401
    for path, kwargs in [
        ("/api/battles/21/actions", {"payload": {"version": 0, "action": {"type": "defend"}}}),
        ("/api/battles/hunt/goblin", {}),
        ("/move-to-sector", {"payload": {"sector": "Forest"}}),
        ("/shop/buy/21", {}),
        ("/castle/metalworking/repair", {"form": {"item_id": "21", "durability": "5"}}),
        ("/api/presence", {}),
    ]:
        status, body = call(moderation_app, "POST", path, **kwargs)
        assert status == 403 and json.loads(body)["detail"] == "Гравець заблокований: Причина <тест>"
    with sessions() as db:
        user = db.get(User, 2)
        assert (user.gold, user.map_sector, user.last_seen_at) == (100, "Castle", None)
        assert db.get(ShopItem, 21).quantity == 1
    assert call(moderation_app, "POST", "/admin/player/2/unblock", "reader")[0] == 303
    assert call(moderation_app, "POST", "/api/presence")[0] == 401
    assert call(moderation_app, "POST", "/login", None, form=credentials)[0] == 303
    with sessions() as db:
        token = db.get(User, 2).session_id
    status, body = asyncio.run(asgi_request(moderation_app, "POST", "/api/presence", f"session_id={token}"))
    assert status == 200 and json.loads(body)["online"] >= 1
    status, _ = asyncio.run(asgi_request(moderation_app, "POST", "/shop/buy/21", f"session_id={token}"))
    assert status == 200
    with sessions() as db:
        assert db.get(User, 2).gold == 90
        assert db.get(ShopItem, 21).quantity == 0


def test_account_status_panel_visibility(moderation_app, sessions):
    from backend.config import SYSTEM_PLAYER_ID

    with sessions.begin() as db:
        db.get(User, SYSTEM_PLAYER_ID).session_id = "system-session"
    for account in (None, "ordinary", "other"):
        status, body = call(moderation_app, "GET", "/player_info?id=2", account)
        assert status == 200 and b'id="moderation-title"' not in body
    for account in ("reader", "moderator", "system"):
        status, body = call(moderation_app, "GET", "/player_info?id=2", account)
        assert status == 200 and b'id="moderation-title"' in body
        assert (b"/reset-nickname" in body) == (account != "system")


@pytest.mark.parametrize("staff", ["reader", "moderator"])
def test_nickname_reset_and_replacement(moderation_app, sessions, staff):
    path = "/admin/player/2/reset-nickname"
    for account in ("ordinary", None):
        assert call(moderation_app, "POST", path, account)[0] == 403
    assert call(moderation_app, "POST", "/admin/player/10/reset-nickname", "moderator")[0] == 403
    assert call(moderation_app, "POST", path, staff)[0] == 303
    assert call(moderation_app, "POST", path, staff)[0] == 409
    assert call(moderation_app, "POST", "/api/presence")[0] == 401
    with sessions() as db:
        subject = db.get(User, 2)
        temporary = subject.username
        assert temporary.startswith("Гравець-2-") and subject.nickname_reset_from == "other"
    assert temporary.encode() in call(moderation_app, "GET", "/player_info?id=2", staff)[1]
    credentials = {"username": "other", "password": "known-password"}
    assert call(moderation_app, "POST", "/register", None, form=dict(credentials, fraction="elves"))[0] == 422
    assert call(moderation_app, "POST", "/login", None, form=credentials)[0] == 303
    with sessions() as db:
        token = db.get(User, 2).session_id

    def active(method, route, **kwargs):
        return asyncio.run(asgi_request(moderation_app, method, route, f"session_id={token}", **kwargs))

    status, body = active("GET", "/choose-nickname")
    assert status == 200 and temporary.encode() in body
    assert active("POST", "/api/presence")[0] == 409
    assert active("POST", "/shop/buy/21")[0] == 409
    for invalid in ("   ", "Гравець-новий", "reader", "other"):
        assert active("POST", "/choose-nickname", form={"username": invalid})[0] == 422
    assert active("POST", "/choose-nickname", form={"username": " Новий Мисливець "})[0] == 303
    assert active("POST", "/api/presence")[0] == 200
    assert call(moderation_app, "POST", "/login", None, form=credentials)[0] == 401
    assert call(moderation_app, "POST", "/login", None, form=dict(credentials, username="Новий Мисливець"))[0] == 303
    with sessions() as db:
        subject = db.get(User, 2)
        assert subject.username == "Новий Мисливець" and subject.nickname_reset_from is None
        assert subject.gold == 100
