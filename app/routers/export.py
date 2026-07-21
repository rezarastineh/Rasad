from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Subdomain, HttpxResult, TechDetectResult, FinalUrl
from app.routers.targets import get_owned_target

router = APIRouter()


def _fmt(v):
    if v is None:
        return ""
    return str(v)


def _html_page(title: str, target_name: str, headers: list[str], rows: list[list[str]]) -> str:
    thead = "".join(f"<th>{h}</th>" for h in headers)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{_fmt(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>{title} — {target_name}</title>
<style>
  body {{ font-family: Tahoma, sans-serif; background:#0f1115; color:#e6e6e6; padding:24px; }}
  h1 {{ font-size:18px; }}
  .meta {{ color:#9aa0aa; font-size:12px; margin-bottom:16px; }}
  table {{ border-collapse: collapse; width:100%; font-size:13px; }}
  th, td {{ border:1px solid #2a2d34; padding:6px 10px; text-align:right; }}
  th {{ background:#1a1d24; position: sticky; top:0; }}
  tr:nth-child(even) {{ background:#15171c; }}
</style>
</head>
<body>
  <h1>{title} — {target_name}</h1>
  <div class="meta">تعداد رکورد: {len(rows)} | تاریخ تولید: {generated_at}</div>
  <table>
    <thead><tr>{thead}</tr></thead>
    <tbody>{tbody}</tbody>
  </table>
</body>
</html>"""


CATEGORIES = ("subdomains", "httpx", "techdetect", "urls")


def _load_rows(category: str, target_id: int, db: Session):
    if category == "subdomains":
        headers = ["name", "ip", "resolved", "source", "first_seen"]
        items = db.query(Subdomain).filter(Subdomain.target_id == target_id).order_by(Subdomain.name).all()
        rows = [
            [s.name, s.ip, s.resolved, s.source, s.first_seen.strftime("%Y-%m-%d %H:%M") if s.first_seen else ""]
            for s in items
        ]
    elif category == "httpx":
        headers = ["subdomain", "port", "status_code", "title", "tech", "webserver", "content_type", "content_length", "ip"]
        items = db.query(HttpxResult).filter(HttpxResult.target_id == target_id).order_by(HttpxResult.subdomain).all()
        rows = [
            [h.subdomain, h.port, h.status_code, h.title, h.tech, h.webserver, h.content_type, h.content_length, h.ip]
            for h in items
        ]
    elif category == "techdetect":
        headers = ["host", "matched_template", "info"]
        items = db.query(TechDetectResult).filter(TechDetectResult.target_id == target_id).order_by(
            TechDetectResult.created_at.desc()
        ).all()
        rows = [[t.host, t.matched_template, t.info] for t in items]
    elif category == "urls":
        headers = ["url", "source", "first_seen"]
        items = db.query(FinalUrl).filter(FinalUrl.target_id == target_id).order_by(FinalUrl.first_seen.desc()).all()
        rows = [
            [u.url, u.source, u.first_seen.strftime("%Y-%m-%d %H:%M") if u.first_seen else ""]
            for u in items
        ]
    else:
        raise HTTPException(404, "دسته‌ی اکسپورت نامعتبر است.")
    return headers, rows


@router.get("/targets/{target_id}/export/{category}.txt", response_class=PlainTextResponse)
def export_txt(
    target_id: int, category: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = get_owned_target(target_id, user, db)
    headers, rows = _load_rows(category, target.id, db)
    lines = ["\t".join(headers)] + ["\t".join(_fmt(c) for c in row) for row in rows]
    content = "\n".join(lines) + "\n"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{target.name}_{category}.txt"'},
    )


@router.get("/targets/{target_id}/export/{category}.html", response_class=HTMLResponse)
def export_html(
    target_id: int, category: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = get_owned_target(target_id, user, db)
    headers, rows = _load_rows(category, target.id, db)
    titles = {
        "subdomains": "ساب‌دامین‌ها",
        "httpx": "نتایج HTTPX",
        "techdetect": "نتایج Tech-Detect",
        "urls": "URLها (Katana + Wayback)",
    }
    html = _html_page(titles.get(category, category), target.name, headers, rows)
    return HTMLResponse(
        html,
        headers={"Content-Disposition": f'attachment; filename="{target.name}_{category}.html"'},
    )
