from app.celery_app import celery_app
from app.database import SessionLocal
from app.config import target_workspace
from app.models import Target, TechDetectResult
from app.tasks.tool_utils import run_cmd, is_tool_available, JobRunner, clean_text


@celery_app.task(name="tasks.tech_detect")
def tech_detect_task(job_id: int, target_id: int, user_id: int):
    db = SessionLocal()
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        db.close()
        return

    workdir = target_workspace(user_id, target_id)
    resolved_file = workdir / "resolved.txt"
    out_file = workdir / f"tech-detect-{target_id}.txt"

    with JobRunner(job_id) as jr:
        if not resolved_file.exists():
            jr.log("[!] فایل resolved.txt پیدا نشد. ابتدا فاز DNS Resolve را اجرا کنید.")
            db.close()
            return

        required = ["asnmap", "naabu", "httpx", "nuclei", "anew"]
        missing = [t for t in required if not is_tool_available(t)]
        if missing:
            jr.log(f"[!] ابزارهای زیر نصب نیستند و این فاز رد می‌شود: {', '.join(missing)}")
            db.close()
            return

        jr.log("[*] اجرای پایپ‌لاین asnmap | naabu | httpx | nuclei (tech-detect)...")
        cmd = (
            f"cat {resolved_file} | asnmap -silent | naabu -top-ports 100 -silent "
            f"| httpx -silent | nuclei -silent -tags tech | anew {out_file}"
        )
        code, out, err = run_cmd(cmd, cwd=workdir, timeout=3600)
        if code != 0:
            jr.log(f"[!] پایپ‌لاین با خطا مواجه شد: {err[:500]}")

        count = 0
        new_count = 0
        if out_file.exists():
            # جلوگیری از تکرار: اگه یک ترکیب (host, template) قبلاً ثبت شده، دوباره insert نمی‌کنیم
            # وگرنه هر بار که پایپ‌لاین کامل دوباره اجرا بشه، همون یافته‌ها بی‌نهایت تکرار می‌شدن.
            existing_keys = {
                (r.host, r.matched_template)
                for r in db.query(TechDetectResult).filter(TechDetectResult.target_id == target_id).all()
            }
            for line in out_file.read_text(errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                # فرمت خروجی nuclei تقریبا: [template-id] [protocol] host
                parts = line.split()
                template_id = clean_text(parts[0].strip("[]")) if parts else None
                host = clean_text(parts[-1]) if parts else clean_text(line)
                count += 1

                key = (host, template_id)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                db.add(
                    TechDetectResult(
                        target_id=target_id, host=host, matched_template=template_id, info=clean_text(line)
                    )
                )
                new_count += 1
            db.commit()

        jr.log(f"[+] تعداد نتایج tech-detect این اجرا: {count} | مورد جدید: {new_count}")

    db.close()
