from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.database import get_db
from app.auth import get_current_admin
from app.models import User, Plan, Target

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _parse_expiry(raw: str | None):
    """ورودی <input type=date> رو به datetime تبدیل می‌کنه؛ خالی = بدون انقضا."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None


@router.get("/admin", response_class=HTMLResponse)
def admin_users(request: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    target_counts = {
        uid: count for uid, count in (
            db.query(Target.user_id, func.count(Target.id))
            .group_by(Target.user_id)
            .all()
        )
    }
    plans = db.query(Plan).order_by(Plan.name).all()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "users": users,
            "plans": plans,
            "target_counts": target_counts,
            "now": datetime.utcnow(),
        },
    )


@router.post("/admin/users/{user_id}/plan")
def admin_set_plan(
    user_id: int,
    plan_id: str = Form(""),
    expires_at: str = Form(""),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "کاربر پیدا نشد.")

    target_user.plan_id = int(plan_id) if plan_id else None
    target_user.subscription_expires_at = _parse_expiry(expires_at)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/toggle_active")
def admin_toggle_active(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "کاربر پیدا نشد.")
    if target_user.id == admin.id:
        raise HTTPException(400, "نمی‌تونی خودت رو مسدود کنی.")
    target_user.is_active = not target_user.is_active
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/toggle_admin")
def admin_toggle_admin(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "کاربر پیدا نشد.")
    if target_user.id == admin.id:
        raise HTTPException(400, "نمی‌تونی دسترسی ادمین خودت رو از همینجا برداری.")
    target_user.is_admin = not target_user.is_admin
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def admin_delete_user(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "کاربر پیدا نشد.")
    if target_user.id == admin.id:
        raise HTTPException(400, "نمی‌تونی حساب خودت رو حذف کنی.")
    db.delete(target_user)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------------------------------------------------------
# مدیریت پلن‌ها
# ---------------------------------------------------------------------------
@router.get("/admin/plans", response_class=HTMLResponse)
def admin_plans(request: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    plans = db.query(Plan).order_by(Plan.name).all()
    return templates.TemplateResponse("admin_plans.html", {"request": request, "user": admin, "plans": plans, "error": None})


@router.post("/admin/plans/add")
def admin_add_plan(
    request: Request,
    name: str = Form(...),
    max_targets: int = Form(3),
    max_concurrent_scans: int = Form(1),
    is_default: bool = Form(False),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "نام پلن نمی‌تونه خالی باشه.")

    if is_default:
        db.query(Plan).update({Plan.is_default: False})

    plan = Plan(name=name, max_targets=max_targets, max_concurrent_scans=max_concurrent_scans, is_default=is_default)
    db.add(plan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        plans = db.query(Plan).order_by(Plan.name).all()
        return templates.TemplateResponse(
            "admin_plans.html",
            {"request": request, "user": admin, "plans": plans, "error": "پلنی با این نام از قبل وجود داره."},
        )
    return RedirectResponse(url="/admin/plans", status_code=303)


@router.post("/admin/plans/{plan_id}/delete")
def admin_delete_plan(plan_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if plan:
        db.delete(plan)
        db.commit()
    return RedirectResponse(url="/admin/plans", status_code=303)
