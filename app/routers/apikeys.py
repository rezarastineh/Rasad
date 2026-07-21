from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, ApiKey, ApiToolName

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/apikeys", response_class=HTMLResponse)
def apikeys_form(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = {k.tool_name: k.key_value for k in db.query(ApiKey).filter(ApiKey.user_id == user.id).all()}
    return templates.TemplateResponse(
        "apikeys_form.html",
        {"request": request, "user": user, "tools": list(ApiToolName), "existing": existing},
    )


@router.post("/apikeys")
def apikeys_submit(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chaos: str = Form(""),
    github_subdomains: str = Form(""),
    shodan: str = Form(""),
    bevigil: str = Form(""),
    digitalyama: str = Form(""),
    pugrecon: str = Form(""),
    zoomeyeapi: str = Form(""),
    fofa_email: str = Form(""),
    fofa_key: str = Form(""),
    c99: str = Form(""),
    censys_id: str = Form(""),
    censys_secret: str = Form(""),
):
    values = {
        ApiToolName.chaos: chaos.strip(),
        ApiToolName.github_subdomains: github_subdomains.strip(),
        ApiToolName.shodan: shodan.strip(),
        ApiToolName.bevigil: bevigil.strip(),
        ApiToolName.digitalyama: digitalyama.strip(),
        ApiToolName.pugrecon: pugrecon.strip(),
        ApiToolName.zoomeyeapi: zoomeyeapi.strip(),
        ApiToolName.fofa_email: fofa_email.strip(),
        ApiToolName.fofa_key: fofa_key.strip(),
        ApiToolName.c99: c99.strip(),
        ApiToolName.censys_id: censys_id.strip(),
        ApiToolName.censys_secret: censys_secret.strip(),
    }
    for tool_name, value in values.items():
        row = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.tool_name == tool_name).first()
        if not value:
            if row:
                db.delete(row)
            continue
        if row:
            row.key_value = value
        else:
            db.add(ApiKey(user_id=user.id, tool_name=tool_name, key_value=value))
    db.commit()
    return RedirectResponse(url="/apikeys", status_code=303)
