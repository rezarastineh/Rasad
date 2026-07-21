import json
import os
from datetime import datetime
import tempfile

from app.celery_app import celery_app
from app.database import SessionLocal
from app.config import target_workspace, RESOLVERS_FILE
from app.models import Target, Subdomain
from app.tasks.tool_utils import run_cmd, is_tool_available, JobRunner


@celery_app.task(name="tasks.dns_resolve")
def dns_resolve_task(job_id: int, target_id: int, user_id: int):
    db = SessionLocal()
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        db.close()
        return

    workdir = target_workspace(user_id, target_id)
    all_raw = workdir / "all_raw.txt"
    resolved_file = workdir / "resolved.txt"

    with JobRunner(job_id) as jr:
        if not all_raw.exists():
            jr.log("[!] فایل ورودی از فاز اول پیدا نشد. ابتدا فاز جمع‌آوری پسیو را اجرا کنید.")
            db.close()
            return

        # حل مشکل تداخل دانلود هم‌زمان ریزالورها
        if not RESOLVERS_FILE.exists():
            jr.log("[*] دانلود ایمن لیست resolvers...")
            # فایل موقت را داخل همون پوشه‌ی مقصد می‌سازیم (نه /tmp سیستم) تا os.replace
            # همیشه atomic و روی یک فایل‌سیستم انجام بشه؛ اگه /tmp روی یک mount جدا باشه
            # (مثلاً tmpfs داخل کانتینر)، os.replace بین دو فایل‌سیستم مختلف با خطای
            # "Invalid cross-device link" شکست می‌خورد.
            RESOLVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_resolver = tempfile.NamedTemporaryFile(dir=str(RESOLVERS_FILE.parent), delete=False)
            temp_resolver.close()
            try:
                # ابتدا در یک فایل موقت دانلود می‌شود
                code, _, err = run_cmd(
                    f"curl -s -f https://raw.githubusercontent.com/trickest/resolvers/main/resolvers.txt -o {temp_resolver.name}"
                )
                # قبل از جایگزینی مطمئن می‌شویم دانلود واقعاً موفق بوده و فایل خالی نیست؛
                # وگرنه (مثلاً قطعی اینترنت) resolvers.txt خراب/خالی برای همیشه جایگزین می‌شد
                # و چون دیگه RESOLVERS_FILE.exists() هست، هیچ‌وقت دوباره دانلود نمی‌شد.
                if code != 0 or os.path.getsize(temp_resolver.name) == 0:
                    raise RuntimeError(f"دانلود ناموفق (exit={code}): {err[:300]}")
                os.replace(temp_resolver.name, RESOLVERS_FILE)
            except Exception as e:
                jr.log(f"[!] خطا در دانلود ریزالورها: {str(e)}")
                if os.path.exists(temp_resolver.name):
                    os.unlink(temp_resolver.name)

        # اجرای ابزارهای اسکن
        if is_tool_available("shuffledns") and is_tool_available("massdns"):
            jr.log("[*] اجرای Shuffledns برای resolve و حذف wildcard...")
            code, out, err = run_cmd(
                f"shuffledns -l {all_raw} -r {RESOLVERS_FILE} -mode resolve -sw -o {resolved_file}"
            )
            if code != 0:
                jr.log(f"[!] shuffledns خطا داد: {err[:500]}")
        else:
            jr.log("[!] shuffledns/massdns نصب نیست، از massdns مستقیم استفاده می‌شود در صورت وجود...")
            if is_tool_available("massdns"):
                run_cmd(
                    f"massdns -r {RESOLVERS_FILE} -t A -o S -w {workdir / 'massdns_raw.txt'} {all_raw}"
                )
                run_cmd(
                    f"cut -d' ' -f1 {workdir / 'massdns_raw.txt'} | sed 's/\\.$//' | sort -u > {resolved_file}"
                )
            else:
                jr.log("[!] هیچ‌کدام از ابزارهای resolve موجود نیست، کپی لیست خام به‌عنوان resolved.")
                resolved_file.write_text(all_raw.read_text())

        resolved_names = set()
        if resolved_file.exists():
            resolved_names = {
                line.strip().lower() for line in resolved_file.read_text(errors="ignore").splitlines() if line.strip()
            }

        # --- تشخیص IP هر ساب‌دامین ریزالوشده (اختیاری، فقط اگه dnsx نصب باشه) ---
        # ستون Subdomain.ip قبلاً هیچ‌جای پایپ‌لاین پر نمی‌شد؛ dnsx دقیقاً ابزار مناسب برای
        # این کاره (بخشی از همون خانواده‌ی ابزارهای ProjectDiscovery که بقیه‌ی پایپ‌لاین استفاده می‌کنه).
        ip_by_host: dict[str, str] = {}
        if resolved_names and is_tool_available("dnsx"):
            jr.log("[*] اجرای dnsx برای تشخیص IP هر ساب‌دامین...")
            dnsx_json = workdir / "dnsx.json"
            code, out, err = run_cmd(
                f"dnsx -l {resolved_file} -a -json -silent -o {dnsx_json}", timeout=1800
            )
            if code != 0:
                jr.log(f"[!] dnsx خطا داد: {err[:500]}")
            if dnsx_json.exists():
                for line in dnsx_json.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    host = (data.get("host") or "").strip().lower()
                    a_records = data.get("a") or []
                    if host and a_records:
                        ip_by_host[host] = a_records[0]
        elif resolved_names:
            jr.log("[!] dnsx نصب نیست، ستون IP پر نمی‌شود (بقیه‌ی فاز طبیعی ادامه پیدا می‌کند).")

        now = datetime.utcnow()
        
        # حل فاجعه کارایی با استفاده از Bulk Update (آپدیت یکجای دیتابیس)
        if resolved_names:
            resolved_list = list(resolved_names)
            
            # آپدیت تمام رکوردهایی که نامشان در لیست پیدا شده است به صورت یکجا در یک کوئری
            updated_count = db.query(Subdomain).filter(
                Subdomain.target_id == target_id,
                Subdomain.name.in_(resolved_list)
            ).update(
                {Subdomain.resolved: True, Subdomain.last_seen: now},
                synchronize_session=False
            )
            
            db.commit()
            jr.log(f"[+] تعداد زیردامنه‌های ریزالو‌شده و آپدیت شده در دیتابیس: {updated_count}")

            # آپدیت یکجای ستون IP (bulk_update_mappings) — به‌جای یک کوئری جدا برای هر
            # ساب‌دامین، فقط دو کوئری اضافه (یک SELECT برای گرفتن id ها + یک UPDATE دسته‌ای)
            if ip_by_host:
                rows = db.query(Subdomain.id, Subdomain.name).filter(
                    Subdomain.target_id == target_id,
                    Subdomain.name.in_(list(ip_by_host.keys()))
                ).all()
                mappings = [{"id": rid, "ip": ip_by_host[name]} for rid, name in rows if name in ip_by_host]
                if mappings:
                    db.bulk_update_mappings(Subdomain, mappings)
                    db.commit()
                    jr.log(f"[+] IP برای {len(mappings)} ساب‌دامین ثبت شد.")
        else:
            jr.log("[!] هیچ ساب‌دامینی ریزالو نشد.")

    db.close()