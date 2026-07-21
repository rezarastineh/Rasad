from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import User, Plan
from app.auth import hash_password, verify_password, create_session_cookie, get_current_user_optional
from app.config import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, user=Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != password_confirm:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "رمز عبور و تکرار آن یکسان نیستند."}
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "رمز عبور باید حداقل ۸ کاراکتر باشد."}
        )

    default_plan = db.query(Plan).filter(Plan.is_default == True).first()  # noqa: E712
    user = User(
        username=username.strip(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
        plan_id=default_plan.id if default_plan else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "این نام کاربری یا ایمیل قبلاً ثبت شده است."}
        )
    db.refresh(user)

    response = RedirectResponse(url="/dashboard", status_code=303)
    token = create_session_cookie(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, max_age=SESSION_MAX_AGE_SECONDS, httponly=True, samesite="lax"
    )
    return response


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, user=Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "نام کاربری یا رمز عبور اشتباه است."}
        )
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "حساب شما مسدود شده است. با پشتیبانی تماس بگیرید."}
        )

    response = RedirectResponse(url="/dashboard", status_code=303)
    token = create_session_cookie(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, max_age=SESSION_MAX_AGE_SECONDS, httponly=True, samesite="lax"
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
