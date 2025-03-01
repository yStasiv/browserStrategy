from fastapi import APIRouter, Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from .. import database, models

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

def get_current_user(request: Request, db: Session = Depends(database.get_db)):
    username = request.cookies.get("username")
    if username:
        return db.query(models.User).filter(models.User.username == username).first()
    return None

@router.get("/admin/enterprises")
async def admin_enterprises(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")
    
    enterprises = db.query(models.Enterprise).all()
    return templates.TemplateResponse(
        "admin_enterprises.html",
        {"request": request, "user": current_user, "enterprises": enterprises}
    )

@router.post("/admin/enterprises/add")
async def add_enterprise(
    request: Request,
    name: str = Form(...),
    sector: str = Form(...),
    resource_type: str = Form(...),
    area: int = Form(...),
    storage_multiplier: int = Form(...),
    production_type: str = Form(...),
    salary: int = Form(...),
    item_price: int = Form(...),
    db: Session = Depends(database.get_db)
):
    # Перевіряємо чи адмін
    user = get_current_user(request, db)
    if not user or user.id != 1:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    new_enterprise = models.Enterprise(
        name=name,
        sector=sector,
        resource_type=resource_type,
        area=area,
        storage_multiplier=storage_multiplier,
        production_type=production_type,
        salary=salary,
        item_price=item_price,
        max_workers=area * 3,  # Встановлюємо початкові значення
        max_storage=area * storage_multiplier
    )
    
    db.add(new_enterprise)
    db.commit()
    
    return RedirectResponse(url="/admin/enterprises", status_code=303)

@router.post("/admin/enterprises/delete/{enterprise_id}")
async def delete_enterprise(
    enterprise_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")
    
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
    if enterprise:
        db.delete(enterprise)
        db.commit()
    
    return RedirectResponse(url="/admin/enterprises", status_code=303) 
