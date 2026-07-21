from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Target
from app.config import target_workspace
from app.validators import is_valid_target_name

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    targets = db.query(Target).filter(Target.user_id == user.id).order_by(Target.created_at.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "targets": targets, "error": None}
    )


@router.post("/targets/add")
def add_target(
    request: Request,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = name.strip().lower()

    if not user.subscription_active:
        targets = db.query(Target).filter(Target.user_id == user.id).all()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request, "user": user, "targets": targets,
                "error": "اشتراک شما فعال نیست یا منقضی شده. برای افزودن تارگت جدید با پشتیبانی تماس بگیرید.",
            },
        )

    if user.plan and user.plan.max_targets is not None:
        current_count = db.query(Target).filter(Target.user_id == user.id).count()
        if current_count >= user.plan.max_targets:
            targets = db.query(Target).filter(Target.user_id == user.id).all()
            return templates.TemplateResponse(
                "dashboard.html",
                {
                    "request": request, "user": user, "targets": targets,
                    "error": f"سقف تعداد تارگت پلن «{user.plan.name}» ({user.plan.max_targets} عدد) پر شده. برای افزایش سقف با پشتیبانی تماس بگیر.",
                },
            )

    if not is_valid_target_name(name):
        targets = db.query(Target).filter(Target.user_id == user.id).all()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request, "user": user, "targets": targets,
                "error": "نام تارگت فقط می‌تواند شامل حروف/عدد/نقطه/خط‌تیره باشد.",
            },
        )
    target = Target(user_id=user.id, name=name)
    db.add(target)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        targets = db.query(Target).filter(Target.user_id == user.id).all()
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": user, "targets": targets, "error": "این تارگت قبلاً اضافه شده است."},
        )
    db.refresh(target)
    # فضای مخصوص این تارگت روی دیسک ساخته می‌شود
    target_workspace(user.id, target.id)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/targets/{target_id}/delete")
def delete_target(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = db.query(Target).filter(Target.id == target_id, Target.user_id == user.id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(target)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


def get_owned_target(target_id: int, user: User, db: Session) -> Target:
    target = db.query(Target).filter(Target.id == target_id, Target.user_id == user.id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.get("/targets/{target_id}", response_class=HTMLResponse)
def target_detail(target_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = get_owned_target(target_id, user, db)
    return templates.TemplateResponse("target_detail.html", {"request": request, "user": user, "target": target})
