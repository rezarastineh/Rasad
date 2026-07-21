from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import Base, engine
from app.bootstrap import ensure_default_plan
from app.routers import auth as auth_router
from app.routers import targets as targets_router
from app.routers import scope as scope_router
from app.routers import apikeys as apikeys_router
from app.routers import scan as scan_router
from app.routers import admin as admin_router
from app.routers import export as export_router

# ساخت جدول‌ها (برای پروژه‌های واقعی بهتره از Alembic استفاده بشه)
Base.metadata.create_all(bind=engine)
ensure_default_plan()

app = FastAPI(title="SubSpyder Panel")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router.router)
app.include_router(targets_router.router)
app.include_router(scope_router.router)
app.include_router(apikeys_router.router)
app.include_router(scan_router.router)
app.include_router(admin_router.router)
app.include_router(export_router.router)


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


# اگر کاربر لاگین نکرده بود و به یک صفحه‌ی محافظت‌شده رفت، به /login هدایتش کن
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    if exc.status_code == 303 and "Location" in (exc.headers or {}):
        return RedirectResponse(url=exc.headers["Location"], status_code=303)
    from starlette.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
