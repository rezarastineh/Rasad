import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from app.database import SessionLocal
from app.models import ScanJob, JobStatus, ApiKey, ApiToolName, SUBFINDER_SIMPLE_SOURCES


def is_tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def clean_text(value):
    """
    مقادیر متنی که از ابزارهای بیرونی (httpx, nuclei, ...) میان می‌تونن روی سایت‌های واقعی
    بایت NUL (\\x00) داخل title/header و مانند آن داشته باشن. ستون‌های متنی Postgres اصلاً
    این کاراکتر رو قبول نمی‌کنن و کل insert/update با DataError شکست می‌خوره (حتی وقتی
    خیلی از ردیف‌های دیگه‌ی همون batch مشکلی ندارن، چون insert چندردیفی یکجا rollback میشه).
    این تابع NUL رو حذف می‌کنه و برای غیر-رشته‌ها بدون تغییر برمی‌گردونه.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


def run_cmd(cmd: str, cwd: Path | None = None, timeout: int = 1800) -> tuple[int, str, str]:
    """یک دستور شل را اجرا می‌کند و (returncode, stdout, stderr) را برمی‌گرداند."""
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def get_user_api_key(db, user_id: int, tool_name: ApiToolName) -> str | None:
    row = db.query(ApiKey).filter(ApiKey.user_id == user_id, ApiKey.tool_name == tool_name).first()
    return row.key_value if row else None


def build_subfinder_provider_config(db, user_id: int, workdir: Path) -> Path | None:
    """
    از روی کلیدهای API ذخیره‌شده‌ی همان کاربر (جدول ApiKey)، یک provider-config.yaml
    مخصوص subfinder می‌سازد و مسیرش را برمی‌گرداند. اگر کاربر هیچ کلید مرتبطی وارد
    نکرده باشد None برمی‌گردد (یعنی subfinder بدون -pc و فقط با سورس‌های بدون کلید اجرا می‌شود).

    فرمت خروجی دقیقاً همان چیزی است که خودِ subfinder در
    $HOME/.config/subfinder/provider-config.yaml انتظار دارد: هر سورس یک لیست از
    رشته‌ها. برای فوفا که کلید ترکیبی email:key می‌خواهد، دو مقدار را با ':' ترکیب می‌کنیم.
    """
    config: dict[str, list[str]] = {}

    for tool_name, source_name in SUBFINDER_SIMPLE_SOURCES.items():
        value = get_user_api_key(db, user_id, tool_name)
        if value:
            config[source_name] = [value]

    fofa_key = get_user_api_key(db, user_id, ApiToolName.fofa_key)
    if fofa_key:
        fofa_email = get_user_api_key(db, user_id, ApiToolName.fofa_email) or ""
        # اگر ایمیل داده نشده باشد همان مقدار تنها را می‌گذاریم (بعضی نسخه‌ها/فورک‌ها
        # با کلید تنها هم کار می‌کنند)؛ ولی طبق مستندات رسمی subfinder فرمت درست email:key است.
        config["fofa"] = [f"{fofa_email}:{fofa_key}" if fofa_email else fofa_key]

    if not config:
        return None

    out_path = workdir / "subfinder-provider-config.yaml"
    # از yaml.safe_dump استفاده می‌کنیم تا هیچ مقدار ورودی کاربر به‌عنوان دستور شل تفسیر نشود؛
    # این فایل هیچ‌وقت مستقیم داخل رشته‌ی دستور شل ساخته نمی‌شود، فقط مسیرش (که کنترل‌شده و
    # داخل workspace خودمان است) با shlex.quote به subfinder داده می‌شود.
    out_path.write_text(yaml.safe_dump(config, default_flow_style=False, allow_unicode=True))
    return out_path


class JobRunner:
    """کانتکست‌منیجر برای آپدیت وضعیت ScanJob در دیتابیس حین اجرای یک فاز."""

    def __init__(self, job_id: int):
        self.job_id = job_id
        self.db = SessionLocal()
        self.job: ScanJob | None = None
        self._log_lines: list[str] = []

    def __enter__(self):
        self.job = self.db.query(ScanJob).filter(ScanJob.id == self.job_id).first()
        if self.job:
            self.job.status = JobStatus.running
            self.job.started_at = datetime.utcnow()
            self.db.commit()
        return self

    def log(self, line: str):
        self._log_lines.append(line)
        if self.job:
            self.job.log = "\n".join(self._log_lines)
            self.db.commit()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.job:
            self.job.finished_at = datetime.utcnow()
            self.job.status = JobStatus.failed if exc_type else JobStatus.success
            if exc_type:
                self.log(f"[ERROR] {exc_val}")
            self.db.commit()

            if exc_type:
                # فازهای پایپ‌لاین با یک Celery chain غیرقابل‌تغییر (immutable signatures) پشت
                # سر هم اجرا می‌شن؛ وقتی یک فاز شکست بخوره، Celery بقیه‌ی زنجیره رو صدا نمی‌زنه
                # و رکورد ScanJob فازهای بعدی برای همیشه روی "در صف" (pending) می‌مونه. چون
                # وضعیت pending/running یعنی "اسکن فعال"، این باعث می‌شد دیگه هیچ‌وقت نشه اسکن
                # جدیدی روی همین تارگت زد. این‌جا صریحاً بقیه‌ی فازهای هنوز در صفِ همین تارگت
                # رو هم failed علامت می‌زنیم تا این قفلِ همیشگی باز بشه.
                pending_siblings = (
                    self.db.query(ScanJob)
                    .filter(ScanJob.target_id == self.job.target_id, ScanJob.status == JobStatus.pending)
                    .all()
                )
                for sib in pending_siblings:
                    sib.status = JobStatus.failed
                    sib.finished_at = datetime.utcnow()
                    sib.log = "[!] این فاز به‌خاطر شکست یکی از فازهای قبلیِ پایپ‌لاین اجرا نشد."
                if pending_siblings:
                    self.db.commit()
        self.db.close()
        # exception را قورت نمی‌دهیم، فقط وضعیت را ثبت می‌کنیم؛ Celery خودش خطا را لاگ می‌کند
        return False
