from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, ScopeEntry, ScopeType
from app.routers.targets import get_owned_target
from app.validators import is_valid_domain_entry

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _parse_lines(raw: str) -> list[str]:
    """خط‌ها را تمیز می‌کند و فقط دامنه‌های معتبر (بدون کاراکتر خطرناک برای شل) را نگه می‌دارد."""
    lines = [line.strip().lower() for line in raw.splitlines() if line.strip()]
    return [line for line in lines if is_valid_domain_entry(line)]


@router.get("/targets/{target_id}/scope", response_class=HTMLResponse)
def scope_form(target_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = get_owned_target(target_id, user, db)
    entries = target.scope_entries
    return templates.TemplateResponse(
        "scope_form.html",
        {
            "request": request,
            "user": user,
            "target": target,
            "out_of_scope": [e for e in entries if e.scope_type == ScopeType.out_of_scope],
            "in_scope_wildcard": [e for e in entries if e.scope_type == ScopeType.in_scope_wildcard],
            "normal_domain": [e for e in entries if e.scope_type == ScopeType.normal_domain],
        },
    )


@router.post("/targets/{target_id}/scope")
def scope_submit(
    target_id: int,
    out_of_scope: str = Form(""),
    in_scope_wildcard: str = Form(""),
    normal_domain: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = get_owned_target(target_id, user, db)

    # هر بار فرم ثبت میشه، لیست قبلی همون نوع پاک و لیست جدید جایگزین می‌شود
    db.query(ScopeEntry).filter(ScopeEntry.target_id == target.id).delete()

    groups = {
        ScopeType.out_of_scope: _parse_lines(out_of_scope),
        ScopeType.in_scope_wildcard: _parse_lines(in_scope_wildcard),
        ScopeType.normal_domain: _parse_lines(normal_domain),
    }
    seen = set()
    for scope_type, lines in groups.items():
        for entry in lines:
            key = (target.id, entry)
            if key in seen:
                continue
            seen.add(key)
            db.add(ScopeEntry(target_id=target.id, entry=entry, scope_type=scope_type))
    db.commit()
    return RedirectResponse(url=f"/targets/{target.id}/scope", status_code=303)
