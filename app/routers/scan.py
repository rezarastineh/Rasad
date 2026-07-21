from datetime import datetime, timedelta

from celery import chain
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Target, ScanJob, ScanPhase, JobStatus, Subdomain, HttpxResult, TechDetectResult, FinalUrl
from app.routers.targets import get_owned_target
from app.tasks.enum_tasks import passive_enum_task
from app.tasks.resolve_tasks import dns_resolve_task
from app.tasks.techdetect_tasks import tech_detect_task
from app.tasks.httpx_tasks import httpx_probe_task
from app.tasks.finalize_tasks import finalize_task
from app.celery_app import celery_app

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ترتیب ثابت پایپ‌لاین کامل — این همون ترتیبیه که فازها باید پشت‌سرهم اجرا بشن
PIPELINE_STEPS = [
    (ScanPhase.passive_enum, passive_enum_task),
    (ScanPhase.dns_resolve, dns_resolve_task),
    (ScanPhase.tech_detect, tech_detect_task),
    (ScanPhase.httpx_probe, httpx_probe_task),
    (ScanPhase.finalize, finalize_task),
]

ACTIVE_STATUSES = (JobStatus.pending, JobStatus.running)

# اگه یک فاز بیشتر از این مدت روی pending/running بمونه، احتمالاً به‌خاطر کرش/کشته‌شدن
# دستیِ Celery worker (نه یک خطای پایتونی که JobRunner بتونه بگیرتش) گیر کرده، نه اینکه واقعاً
# در حال اجراست. در این حالت هیچ‌وقت exception ای پرتاب نمی‌شه که وضعیتش آپدیت بشه، پس بدون
# این ریکاوری خودکار، اسکن‌های بعدی روی همین تارگت برای همیشه بلاک می‌مونن.
STALE_JOB_THRESHOLD = timedelta(hours=3)


@router.post("/targets/{target_id}/scan/run")
def run_full_scan(
    target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = get_owned_target(target_id, user, db)

    if not user.subscription_active:
        raise HTTPException(403, "اشتراک شما فعال نیست یا منقضی شده. با پشتیبانی تماس بگیر.")

    # ریکاوری خودکار جاب‌های گیرکرده (مثلاً به‌خاطر کرش/کشته‌شدن Celery worker حین اجرا، که
    # هیچ‌وقت استثنایی پرتاب نشده تا وضعیتش آپدیت بشه). بدون این، یک worker کرش‌کرده می‌تونست
    # برای همیشه جلوی اسکن مجدد روی این تارگت رو بگیره.
    stale_cutoff = datetime.utcnow() - STALE_JOB_THRESHOLD
    stale_jobs = (
        db.query(ScanJob)
        .filter(
            ScanJob.target_id == target.id,
            ScanJob.status.in_(ACTIVE_STATUSES),
            ScanJob.created_at < stale_cutoff,
        )
        .all()
    )
    for sj in stale_jobs:
        sj.status = JobStatus.failed
        sj.finished_at = datetime.utcnow()
        sj.log = (sj.log or "") + "\n[!] این فاز بیش از حد معمول در صف/در حال اجرا مونده بود (احتمالاً کرش/ری‌استارت worker) و به‌صورت خودکار failed علامت‌گذاری شد."
    if stale_jobs:
        db.commit()

    # جلوگیری از اجرای هم‌زمان چند اسکن روی یک تارگت
    running = (
        db.query(ScanJob)
        .filter(ScanJob.target_id == target.id, ScanJob.status.in_(ACTIVE_STATUSES))
        .first()
    )
    if running:
        raise HTTPException(409, "یک اسکن روی این تارگت در حال اجراست، صبر کن تا تموم بشه.")

    # سقف تعداد اسکن هم‌زمان بر اساس پلن کاربر (روی کل تارگت‌های کاربر)
    if user.plan and user.plan.max_concurrent_scans is not None:
        user_running = (
            db.query(ScanJob)
            .join(Target, ScanJob.target_id == Target.id)
            .filter(ScanJob.status.in_(ACTIVE_STATUSES), Target.user_id == user.id)
            .count()
        )
        if user_running >= user.plan.max_concurrent_scans:
            raise HTTPException(
                403,
                f"سقف اسکن هم‌زمان پلن «{user.plan.name}» ({user.plan.max_concurrent_scans}) پر شده.",
            )

    # برای هر فاز یک رکورد ScanJob از قبل می‌سازیم تا تاریخچه و وضعیت لحظه‌ای در جدول دیده بشه
    jobs = []
    for phase, _task in PIPELINE_STEPS:
        job = ScanJob(target_id=target.id, phase=phase, status=JobStatus.pending)
        db.add(job)
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)

    # زنجیره‌ی Celery: هر فاز بعد از موفقیت فاز قبلی اجرا می‌شود (چون به فایل‌های workspace وابسته‌اند)
    signature_chain = chain(
        *[task.si(job.id, target.id, user.id) for (phase, task), job in zip(PIPELINE_STEPS, jobs)]
    )
    result = signature_chain.apply_async()

    # نگاشت هر فاز به همون task id ای که Celery بهش داده، تا اگه کاربر خواست لغوش کنه بشه
    # واقعاً همون تسکِ در حال اجرا رو (نه فقط رکورد دیتابیس رو) متوقف کرد. chain نتیجه‌ی آخرین
    # تسک رو برمی‌گردونه؛ id بقیه‌ی تسک‌ها از طریق زنجیره‌ی .parent در دسترسه.
    task_ids = []
    r = result
    while r is not None:
        task_ids.append(r.id)
        r = r.parent
    task_ids.reverse()  # الان دقیقاً هم‌ترتیب با PIPELINE_STEPS / jobs هست
    for job, tid in zip(jobs, task_ids):
        job.celery_task_id = tid
    db.commit()

    return RedirectResponse(url=f"/targets/{target.id}/results", status_code=303)


@router.post("/targets/{target_id}/scan/cancel")
def cancel_scan(
    target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = get_owned_target(target_id, user, db)

    active_jobs = (
        db.query(ScanJob)
        .filter(ScanJob.target_id == target.id, ScanJob.status.in_(ACTIVE_STATUSES))
        .all()
    )
    if not active_jobs:
        raise HTTPException(409, "اسکن فعالی برای این تارگت وجود ندارد.")

    for job in active_jobs:
        if job.celery_task_id:
            try:
                # SIGKILL چون تسک‌ها دستور شل رو با subprocess.run (بلاکینگ) اجرا می‌کنن و به
                # SIGTERM معمولی جواب نمی‌دن؛ terminate=True یعنی پروسه‌ی worker همون تسک کشته بشه.
                celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGKILL")
            except Exception:
                pass
        job.status = JobStatus.cancelled
        job.finished_at = datetime.utcnow()
        job.log = (job.log or "") + "\n[!] این فاز توسط کاربر لغو شد."
    db.commit()

    return RedirectResponse(url=f"/targets/{target.id}/results", status_code=303)


@router.get("/targets/{target_id}/results", response_class=HTMLResponse)
def results(target_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = get_owned_target(target_id, user, db)

    jobs = db.query(ScanJob).filter(ScanJob.target_id == target.id).order_by(ScanJob.created_at.desc()).limit(20).all()
    subdomains = db.query(Subdomain).filter(Subdomain.target_id == target.id).order_by(Subdomain.name).all()
    httpx_results = db.query(HttpxResult).filter(HttpxResult.target_id == target.id).order_by(HttpxResult.subdomain).all()
    tech_results = db.query(TechDetectResult).filter(TechDetectResult.target_id == target.id).order_by(
        TechDetectResult.created_at.desc()
    ).limit(200).all()
    final_urls = db.query(FinalUrl).filter(FinalUrl.target_id == target.id).order_by(FinalUrl.first_seen.desc()).limit(500).all()

    running = any(j.status in ACTIVE_STATUSES for j in jobs[:len(PIPELINE_STEPS)]) if jobs else False

    latest_by_phase = {}
    for j in jobs:
        latest_by_phase.setdefault(j.phase, j)

    return templates.TemplateResponse(
        "scan_results.html",
        {
            "request": request,
            "user": user,
            "target": target,
            "jobs": jobs,
            "subdomains": subdomains,
            "httpx_results": httpx_results,
            "tech_results": tech_results,
            "final_urls": final_urls,
            "ScanPhase": ScanPhase,
            "PIPELINE_STEPS": [p for p, _ in PIPELINE_STEPS],
            "latest_by_phase": latest_by_phase,
            "is_running": running,
        },
    )
