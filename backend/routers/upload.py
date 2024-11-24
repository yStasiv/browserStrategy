from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from backend import models, database, utils
from PIL import Image
import os

logger = utils.setup_logger(__name__)

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../../frontend/user_resourses/avatars")

@router.post("/upload-avatar", response_class=RedirectResponse)
async def upload_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(database.get_db)
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        if not os.path.exists(UPLOAD_DIR):
            os.makedirs(UPLOAD_DIR)

        image = Image.open(avatar.file)
        image = image.resize((150, 150))
        avatar_path = os.path.join(UPLOAD_DIR, f"{user.id}.png")
        image.save(avatar_path)

        # Оновлення URL аватарки користувача
        user.avatar_url = f"/avatars/{user.id}.png"
        db.commit()
    except Exception as e:
        logger.error(HTTPException(status_code=400, detail=f"Error processing the image: {e}"))
        pass

    return RedirectResponse(url="/character", status_code=303)
