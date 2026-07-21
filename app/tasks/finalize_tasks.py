import subprocess
from datetime import datetime

from app.celery_app import celery_app
from app.database import SessionLocal
from app.config import target_workspace
from app.models import Target, HttpxResult, ScopeEntry, ScopeType, FinalUrl
from app.tasks.tool_utils import run_cmd, is_tool_available, JobRunner


@celery_app.task(name="tasks.finalize")
def finalize_task(job_id: int, target_id: int, user_id: int):
    db = SessionLocal()
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        db.close()
        return

    workdir = target_workspace(user_id, target_id)

    with JobRunner(job_id) as jr:
        # زیردامنه‌های فعال (از جدول httpx) + دامنه‌های عادی که در فاز اول ثبت شدند
        active_subdomains = {
            r.subdomain for r in db.query(HttpxResult).filter(HttpxResult.target_id == target_id).all()
        }
        normal_domains = {
            s.entry for s in db.query(ScopeEntry).filter(
                ScopeEntry.target_id == target_id, ScopeEntry.scope_type == ScopeType.normal_domain
            ).all()
        }
        all_hosts = sorted(active_subdomains | normal_domains)

        if not all_hosts:
            jr.log("[!] هیچ زیردامنه‌ی فعالی برای این فاز پیدا نشد.")
            db.close()
            return

        hosts_file = workdir / "active_hosts.txt"
        hosts_file.write_text("\n".join(all_hosts) + "\n")

        found_urls: dict[str, str] = {}

        if is_tool_available("katana"):
            jr.log("[*] اجرای Katana برای کراول زیردامنه‌های فعال...")
            katana_out = workdir / "katana_urls.txt"
            try:
                run_cmd(f"katana -list {hosts_file} -silent -o {katana_out}", timeout=3600)
            except subprocess.TimeoutExpired:
                # katana فایل -o را به‌صورت پیوسته حین کراول می‌نویسد، پس حتی اگه به سقف زمانی
                # بخوریم، هرچی تا اون لحظه پیدا کرده روی دیسک مونده؛ به‌جای از دست‌دادن کامل
                # نتایج و متوقف‌شدن کل فاز، همون بخش جزئی رو برمی‌داریم و ادامه می‌دیم.
                jr.log("[!] Katana به سقف زمانی (۱ ساعت) رسید؛ نتایج جزئیِ تا این لحظه استفاده می‌شود.")
            if katana_out.exists():
                for line in katana_out.read_text(errors="ignore").splitlines():
                    url = line.strip()
                    if url:
                        found_urls.setdefault(url, "katana")
        else:
            jr.log("[!] katana نصب نیست، این بخش رد می‌شود.")

        if is_tool_available("waybackurls"):
            jr.log("[*] اجرای waybackurls روی زیردامنه‌های فعال...")
            wayback_out = workdir / "wayback_urls.txt"
            try:
                run_cmd(f"cat {hosts_file} | waybackurls > {wayback_out}", timeout=1800)
            except subprocess.TimeoutExpired:
                jr.log("[!] waybackurls به سقف زمانی رسید؛ نتایج جزئیِ تا این لحظه استفاده می‌شود.")
            if wayback_out.exists():
                for line in wayback_out.read_text(errors="ignore").splitlines():
                    url = line.strip()
                    if url:
                        found_urls.setdefault(url, "wayback")
        else:
            jr.log("[!] waybackurls نصب نیست، این بخش رد می‌شود.")

        now = datetime.utcnow()
        new_count = 0
        for url, source in found_urls.items():
            exists = db.query(FinalUrl).filter(FinalUrl.target_id == target_id, FinalUrl.url == url).first()
            if not exists:
                db.add(FinalUrl(target_id=target_id, url=url, source=source, first_seen=now))
                new_count += 1
        db.commit()
        jr.log(f"[+] تعداد URL جدید ذخیره‌شده: {new_count} (از مجموع {len(found_urls)})")

    db.close()
