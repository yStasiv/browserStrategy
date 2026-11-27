"""News publishing, acknowledgment and validated local image storage."""
from datetime import UTC
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import or_, select

from backend.models import GlobalEvent, News, NewsAcknowledgment
from backend.services.guild import insert_once

IMAGE_DIR = Path(__file__).resolve().parents[2] / "frontend/static/images/news"
IMAGE_PREFIX = "/static/images/news/"
IMAGE_TYPES = {
    ".png": ("PNG", "image/png"), ".jpg": ("JPEG", "image/jpeg"), ".jpeg": ("JPEG", "image/jpeg"),
    ".webp": ("WEBP", "image/webp"), ".gif": ("GIF", "image/gif"),
}
MAX_BYTES = 8 * 1024 * 1024
KYIV = ZoneInfo("Europe/Kyiv")


def published():
    return select(News).where(News.status == "published", News.event_id.is_(None)).order_by(News.published_at.desc(), News.id.desc())


def latest_unread(db, player_id):
    event_notice = db.scalar(select(News).join(GlobalEvent, GlobalEvent.id == News.event_id).where(
        News.status == "published",
        or_(News.recipient_id == player_id,
            (News.recipient_id.is_(None) & GlobalEvent.status.in_(("ACTIVE", "COMPLETED", "REWARDED")))),
        ~select(NewsAcknowledgment.player_id).where(
            NewsAcknowledgment.player_id == player_id, NewsAcknowledgment.news_id == News.id
        ).exists(),
    ).order_by(News.published_at, News.id).limit(1))
    if event_notice:
        return event_notice
    item = db.scalar(published().limit(1))
    if item is None or db.get(NewsAcknowledgment, (player_id, item.id)) is not None:
        return None
    return item


def acknowledge(db, player_id, news_id):
    item = db.get(News, news_id)
    if item is None or item.status != "published" or item.recipient_id not in (None, player_id):
        raise HTTPException(404, "Новину не знайдено.")
    if item.event_id is not None and db.get(GlobalEvent, item.event_id).status == "CANCELLED":
        raise HTTPException(404, "Новину не знайдено.")
    insert_once(db, NewsAcknowledgment, player_id=player_id, news_id=news_id)


def display_date(date):
    return date.replace(tzinfo=UTC).astimezone(KYIV).strftime("%d.%m.%Y %H:%M") if date else ""


INLINE_LINK = re.compile(r"\[([^\[\]\r\n]+)\]\(([^\s()]+)\)")


def valid_link(value):
    if len(value) > 2048 or any(char.isspace() or ord(char) < 32 for char in value):
        return False
    try:
        link = urlsplit(value)
        return bool(link.scheme in ("http", "https") and link.hostname and not link.username)
    except ValueError:
        return False


def text_parts(text):
    parts = []
    offset = 0
    for match in INLINE_LINK.finditer(text):
        label, url = match.groups()
        if not valid_link(url):
            continue
        if match.start() > offset:
            parts.append({"text": text[offset:match.start()]})
        parts.append({"text": label, "url": url})
        offset = match.end()
    if offset < len(text):
        parts.append({"text": text[offset:]})
    return parts


def fields(title, text, link_url):
    title, text, link_url = title.strip(), text.strip(), link_url.strip()
    if not title or len(title) > 200 or not text or len(text) > 30000:
        raise HTTPException(422, "Вкажи заголовок до 200 символів і текст до 30 000 символів.")
    if link_url and not valid_link(link_url):
        raise HTTPException(422, "Посилання має бути повною адресою HTTP або HTTPS.")
    return {"title": title, "text": text, "link_url": link_url or None}


def store_image(upload, *, directory=None, prefix=None):
    if upload is None or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    expected = IMAGE_TYPES.get(suffix)
    if not expected or upload.content_type != expected[1]:
        raise HTTPException(422, "Дозволені зображення PNG, JPEG, WebP і GIF.")
    contents = upload.file.read(MAX_BYTES + 1)
    if len(contents) > MAX_BYTES:
        raise HTTPException(413, "Зображення має бути не більше 8 МБ.")
    try:
        with Image.open(BytesIO(contents)) as picture:
            if picture.format != expected[0] or picture.width * picture.height > 25_000_000:
                raise ValueError
            picture.verify()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Файл не є коректним зображенням вибраного типу.") from exc
    filename = uuid4().hex + suffix
    directory = directory or IMAGE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    with path.open("xb") as target:
        try:
            target.write(contents)
        except OSError:
            path.unlink(missing_ok=True)
            raise
    return (prefix or IMAGE_PREFIX) + filename


def remove_upload(url):
    if url and url.startswith(IMAGE_PREFIX):
        (IMAGE_DIR / Path(url).name).unlink(missing_ok=True)
