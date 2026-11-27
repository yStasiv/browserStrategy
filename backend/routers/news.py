from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend import database
from backend.models import News, User
from backend.routers.admin import world_admin
from backend.services import global_events, news
from backend.services.world import utc_now

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")
NO_CACHE = {"Cache-Control": "no-store"}


class PublicStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        if Path(path).parts[:2] == ("images", "news"):
            raise HTTPException(404)
        url = global_events.canonical_stage_url(f"/static/{path}")
        return await super().get_response(url.removeprefix("/static/"), scope)


def find_item(db, news_id, viewer):
    item = db.get(News, news_id)
    if item is None or item.event_id is not None or (item.status != "published" and not (viewer and viewer.is_admin)):
        raise HTTPException(404, "Новину не знайдено.")
    return item


@router.get("/news/{news_id}")
def detail(news_id: int, request: Request, db: Session = Depends(database.get_db),
           viewer: User = Depends(database.get_current_user)):
    item = find_item(db, news_id, viewer)
    return templates.TemplateResponse("news_detail.html", {
        "request": request, "nav_player": viewer, "player": viewer, "article": item,
        "text_parts": news.text_parts(item.text),
        "news_date": news.display_date,
    }, headers=NO_CACHE)


@router.api_route("/static/images/news/{filename}", methods=["GET", "HEAD"], include_in_schema=False)
def news_image(filename: str, db: Session = Depends(database.get_db),
               viewer: User = Depends(database.get_current_user)):
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpe?g|webp|gif)", filename):
        raise HTTPException(404)
    query = select(News.id).where(News.image_url == news.IMAGE_PREFIX + filename)
    if not (viewer and viewer.is_admin):
        query = query.where(News.status == "published")
    file = news.IMAGE_DIR / filename
    if db.scalar(query.limit(1)) is None or not file.is_file():
        raise HTTPException(404, headers=NO_CACHE)
    return FileResponse(file, media_type=news.IMAGE_TYPES[Path(filename).suffix][1],
                        headers={**NO_CACHE, "X-Content-Type-Options": "nosniff"})


@router.get("/api/news/latest")
def latest(response: Response, db: Session = Depends(database.get_db),
           player: User = Depends(database.get_current_user)):
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    response.headers.update(NO_CACHE)
    item = news.latest_unread(db, player.id)
    return {"news": {
        "id": item.id, "title": item.title, "text": item.text, "text_parts": news.text_parts(item.text),
        "image_url": item.image_url, "link_url": item.link_url, "event_id": item.event_id,
        "published_at": news.display_date(item.published_at),
    } if item else None}


@router.post("/api/news/{news_id}/acknowledge", status_code=204)
def acknowledge(news_id: int, db: Session = Depends(database.get_db),
                player: User = Depends(database.get_current_user)):
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    news.acknowledge(db, player.id, news_id)
    db.commit()
    return Response(status_code=204, headers=NO_CACHE)


def admin_form(request, db, player, item=None, *, values=None, error=None, status=200):
    return templates.TemplateResponse("admin/news.html", {
        "request": request, "player": player, "editing": item, "values": values or item or {},
        "articles": db.scalars(select(News).where(News.event_id.is_(None)).order_by(News.created_at.desc(), News.id.desc())).all(),
        "news_date": news.display_date, "error": error,
    }, status_code=status, headers=NO_CACHE)


@router.get("/admin/news")
def admin_list(request: Request, db: Session = Depends(database.get_db), player: User = Depends(world_admin)):
    return admin_form(request, db, player)


@router.get("/admin/news/{news_id}/edit")
def admin_edit(news_id: int, request: Request, db: Session = Depends(database.get_db),
               player: User = Depends(world_admin)):
    return admin_form(request, db, player, find_item(db, news_id, player))


def save(request, db, player, item, title, text, link_url, image):
    try:
        values = news.fields(title, text, link_url)
        uploaded = news.store_image(image)
    except HTTPException as exc:
        return admin_form(request, db, player, item, values={"title": title, "text": text, "link_url": link_url},
                          error=exc.detail, status=exc.status_code)
    try:
        if item is None:
            item = News(created_at=utc_now(), status="draft", image_url=uploaded, **values)
            db.add(item)
        else:
            if uploaded is not None:
                values["image_url"] = uploaded
            db.execute(update(News).where(News.id == item.id).values(**values))
        db.flush()
        news_id = item.id
        db.commit()
    except Exception:
        db.rollback()
        news.remove_upload(uploaded)
        raise
    return RedirectResponse(f"/admin/news/{news_id}/edit", status_code=303)


@router.post("/admin/news")
def create_news(request: Request, title: str = Form(...), text: str = Form(...), link_url: str = Form(""),
                image: UploadFile | None = File(None), db: Session = Depends(database.get_db),
                player: User = Depends(world_admin)):
    return save(request, db, player, None, title, text, link_url, image)


@router.post("/admin/news/{news_id}/edit")
def edit_news(news_id: int, request: Request, title: str = Form(...), text: str = Form(...), link_url: str = Form(""),
              image: UploadFile | None = File(None), db: Session = Depends(database.get_db),
              player: User = Depends(world_admin)):
    return save(request, db, player, find_item(db, news_id, player), title, text, link_url, image)


@router.post("/admin/news/{news_id}/publish")
def publish_news(news_id: int, db: Session = Depends(database.get_db), player: User = Depends(world_admin)):
    find_item(db, news_id, player)
    db.execute(update(News).where(News.id == news_id, News.status == "draft")
               .values(status="published", published_at=utc_now()))
    db.commit()
    return RedirectResponse(f"/admin/news/{news_id}/edit", status_code=303)
