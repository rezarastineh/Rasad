from app.database import SessionLocal
from app.models import Plan


def ensure_default_plan():
    """
    اگر هیچ پلنی در دیتابیس نباشد، یک پلن پیش‌فرض «Free» می‌سازد
    تا کاربرهای تازه‌ثبت‌نام‌شده خودکار به آن اختصاص پیدا کنند.
    """
    db = SessionLocal()
    try:
        existing_default = db.query(Plan).filter(Plan.is_default == True).first()  # noqa: E712
        if existing_default:
            return
        plan = db.query(Plan).filter(Plan.name == "Free").first()
        if not plan:
            plan = Plan(name="Free", max_targets=2, max_concurrent_scans=1, is_default=True)
            db.add(plan)
        else:
            plan.is_default = True
        db.commit()
    finally:
        db.close()
