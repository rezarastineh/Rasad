import json
from datetime import datetime

from app.celery_app import celery_app
from app.database import SessionLocal
from app.config import target_workspace
from app.models import Target, HttpxResult
from app.tasks.tool_utils import run_cmd, is_tool_available, JobRunner, clean_text


@celery_app.task(name="tasks.httpx_probe")
def httpx_probe_task(job_id: int, target_id: int, user_id: int):
    db = SessionLocal()
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        db.close()
        return

    workdir = target_workspace(user_id, target_id)
    resolved_file = workdir / "resolved.txt"
    json_out = workdir / "httpx_output.json"

    with JobRunner(job_id) as jr:
        if not resolved_file.exists():
            jr.log("[!] فایل resolved.txt پیدا نشد. ابتدا فاز DNS Resolve را اجرا کنید.")
            db.close()
            return
        if not is_tool_available("httpx"):
            jr.log("[!] httpx نصب نیست.")
            db.close()
            return

        jr.log("[*] اجرای httpx برای گرفتن پورت/تایتل/کانتنت‌تایپ/تکنولوژی/آی‌پی/وب‌سرور...")
        cmd = (
            f"httpx -l {resolved_file} -silent -json -title -tech-detect -status-code "
            f"-content-type -web-server -ip -o {json_out}"
        )
        code, out, err = run_cmd(cmd, cwd=workdir, timeout=1800)
        if code != 0:
            jr.log(f"[!] httpx خطا داد: {err[:500]}")

        if not json_out.exists():
            jr.log("[!] خروجی httpx تولید نشد.")
            db.close()
            return

        # ریست فلگ‌های new/changed مربوط به اجرای قبلی
        existing_rows = {
            (r.subdomain, r.port): r
            for r in db.query(HttpxResult).filter(HttpxResult.target_id == target_id).all()
        }
        for r in existing_rows.values():
            r.is_new = False
            r.content_changed = False

        now = datetime.utcnow()
        new_count = 0
        changed_count = 0
        seen_keys = set()

        for line in json_out.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            subdomain = clean_text(data.get("input") or data.get("url") or data.get("host"))
            if not subdomain:
                continue
            port = str(data.get("port", "")) or "443"
            title = clean_text(data.get("title"))
            content_type = clean_text(data.get("content_type") or data.get("content-type"))
            content_length = data.get("content_length") or data.get("content-length")
            tech = ",".join(data.get("tech", [])) if isinstance(data.get("tech"), list) else data.get("tech")
            tech = clean_text(tech)
            ip = clean_text(data.get("host") or data.get("ip"))
            webserver = clean_text(data.get("webserver") or data.get("web-server"))
            status_code = data.get("status_code") or data.get("status-code")

            key = (subdomain, port)
            seen_keys.add(key)
            row = existing_rows.get(key)

            if not row:
                db.add(
                    HttpxResult(
                        target_id=target_id, subdomain=subdomain, port=port, title=title,
                        content_type=content_type, content_length=content_length, tech=tech,
                        ip=ip, webserver=webserver, status_code=status_code,
                        first_seen=now, last_seen=now, is_new=True, content_changed=False,
                    )
                )
                new_count += 1
            else:
                changed = (row.title != title) or (row.content_length != content_length)
                row.title = title
                row.content_type = content_type
                row.content_length = content_length
                row.tech = tech
                row.ip = ip
                row.webserver = webserver
                row.status_code = status_code
                row.last_seen = now
                row.content_changed = changed
                if changed:
                    changed_count += 1

        db.commit()
        jr.log(f"[+] ساب‌دامین/پورت جدید: {new_count} | تغییر محتوا نسبت به اجرای قبلی: {changed_count}")

    db.close()
