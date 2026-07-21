import shlex
from datetime import datetime
from pathlib import Path

from app.celery_app import celery_app
from app.database import SessionLocal
from app.config import target_workspace
from app.models import Target, ScopeEntry, ScopeType, Subdomain, ApiToolName
from app.tasks.tool_utils import (
    run_cmd, is_tool_available, get_user_api_key, JobRunner, build_subfinder_provider_config,
)


def _domain_matches_out_of_scope(name: str, out_of_scope_entries: list[str]) -> bool:
    for oos in out_of_scope_entries:
        oos = oos.lstrip("*.")
        if name == oos or name.endswith("." + oos):
            return True
    return False


@celery_app.task(name="tasks.passive_enum")
def passive_enum_task(job_id: int, target_id: int, user_id: int):
    db = SessionLocal()
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        db.close()
        return

    scope = db.query(ScopeEntry).filter(ScopeEntry.target_id == target_id).all()
    wildcard_roots = [s.entry.lstrip("*.") for s in scope if s.scope_type == ScopeType.in_scope_wildcard]
    normal_domains = [s.entry for s in scope if s.scope_type == ScopeType.normal_domain]
    out_of_scope = [s.entry for s in scope if s.scope_type == ScopeType.out_of_scope]

    workdir = target_workspace(user_id, target_id)
    tmp_dir = workdir / ".tmp_enum"
    tmp_dir.mkdir(exist_ok=True)

    found: dict[str, str] = {}  # subdomain -> source tool

    # کلیدهای subfinder (chaos, github, shodan, bevigil, digitalyama, pugrecon, zoomeyeapi, fofa)
    # را از تنظیمات API-key همین کاربر می‌خوانیم و یک provider-config.yaml اختصاصی می‌سازیم؛
    # اگر کاربر هیچ‌کدام را وارد نکرده باشد subfinder بدون -pc و فقط با سورس‌های رایگان اجرا می‌شود.
    subfinder_pc = build_subfinder_provider_config(db, user_id, tmp_dir)

    def collect(path: Path, source: str):
        if not path.exists():
            return
        for line in path.read_text(errors="ignore").splitlines():
            name = line.strip().lower().lstrip("*.")
            if name and name not in found:
                found[name] = source

    with JobRunner(job_id) as jr:
        for root in wildcard_roots:
            # همه‌ی ورودی‌های کاربر (دامنه، API-key) قبل از رفتن به دستور شل quote می‌شوند
            # تا امکان Command Injection حتی در صورت عبور از فیلتر regex ورودی وجود نداشته باشد.
            root_q = shlex.quote(root)
            jr.log(f"[+] شروع جمع‌آوری پسیو برای {root}")

            if is_tool_available("subfinder"):
                out = tmp_dir / f"subfinder_{root}.txt"
                pc_flag = f" -pc {shlex.quote(str(subfinder_pc))}" if subfinder_pc else ""
                run_cmd(f"subfinder -d {root_q} -silent{pc_flag} -o {shlex.quote(str(out))}")
                collect(out, "subfinder")

            chaos_key = get_user_api_key(db, user_id, ApiToolName.chaos)
            if is_tool_available("chaos") and chaos_key:
                out = tmp_dir / f"chaos_{root}.txt"
                run_cmd(f"chaos -d {root_q} -key {shlex.quote(chaos_key)} -silent -o {shlex.quote(str(out))}")
                collect(out, "chaos")

            if is_tool_available("assetfinder"):
                out = tmp_dir / f"assetfinder_{root}.txt"
                run_cmd(f"assetfinder --subs-only {root_q} > {shlex.quote(str(out))}")
                collect(out, "assetfinder")

            if is_tool_available("findomain"):
                out = tmp_dir / f"findomain_{root}.txt"
                run_cmd(f"findomain -t {root_q} -u {shlex.quote(str(out))}")
                collect(out, "findomain")

            # crt.sh
            out = tmp_dir / f"crtsh_{root}.txt"
            run_cmd(
                f"curl -s 'https://crt.sh/?q=%.{root}&output=json' "
                f"| jq -r '.[] | .name_value | split(\"\\n\")[]' "
                f"| sed 's/\\*\\.//g' | sort -u > {shlex.quote(str(out))}"
            )
            collect(out, "crtsh")

            # abuseipdb whois page
            out = tmp_dir / f"abuseipdb_{root}.txt"
            run_cmd(
                f"curl -s 'https://www.abuseipdb.com/whois/{root}' -H 'user-agent: Mozilla/5.0' "
                f"| grep -E '<li>.*</li>' | sed -E 's/<\\/?li>//g' | sed -e 's/$/.{root}/' > {shlex.quote(str(out))}"
            )
            collect(out, "abuseipdb")

            if is_tool_available("amass"):
                out = tmp_dir / f"amass_{root}.txt"
                run_cmd(f"amass enum -passive -d {root_q} -o {shlex.quote(str(out))}")
                collect(out, "amass")

            # c99.nl subdomain finder (نیازمند API key کاربر)
            c99_key = get_user_api_key(db, user_id, ApiToolName.c99)
            if c99_key:
                out = tmp_dir / f"c99_{root}.txt"
                run_cmd(
                    f"curl -s 'https://api.c99.nl/subdomainfinder?key={shlex.quote(c99_key)}&domain={root}&json' "
                    f"| jq -r '.subdomains[]?.subdomain' > {shlex.quote(str(out))}"
                )
                collect(out, "c99")

            # shosubgo (Shodan) - نیازمند API key کاربر
            shodan_key = get_user_api_key(db, user_id, ApiToolName.shodan)
            if is_tool_available("shosubgo") and shodan_key:
                out = tmp_dir / f"shosubgo_{root}.txt"
                run_cmd(f"shosubgo -d {root_q} -s {shlex.quote(shodan_key)} | sort -u > {shlex.quote(str(out))}")
                collect(out, "shosubgo")

            # github-subdomains - نیازمند GitHub token کاربر
            github_token = get_user_api_key(db, user_id, ApiToolName.github_subdomains)
            if is_tool_available("github-subdomains") and github_token:
                out = tmp_dir / f"github_{root}.txt"
                run_cmd(f"github-subdomains -d {root_q} -t {shlex.quote(github_token)} -o {shlex.quote(str(out))}")
                collect(out, "github-subdomains")

            jr.log(f"[+] پایان جمع‌آوری برای {root} — تعداد فعلی: {len(found)}")

        # دامنه‌های عادی (غیر وایلدکارت) مستقیم اضافه می‌شوند
        for nd in normal_domains:
            if nd not in found:
                found[nd] = "manual"

        # فیلتر کردن اوت‌آف‌اسکوپ‌ها
        before = len(found)
        found = {name: src for name, src in found.items() if not _domain_matches_out_of_scope(name, out_of_scope)}
        jr.log(f"[+] حذف اوت‌آف‌اسکوپ: {before - len(found)} مورد حذف شد")

        # ذخیره در دیتابیس
        now = datetime.utcnow()
        for name, source in found.items():
            existing = db.query(Subdomain).filter(Subdomain.target_id == target_id, Subdomain.name == name).first()
            is_wc = name not in normal_domains
            if existing:
                existing.last_seen = now
            else:
                db.add(
                    Subdomain(
                        target_id=target_id, name=name, source=source,
                        is_wildcard_scope=is_wc, first_seen=now, last_seen=now,
                    )
                )
        db.commit()

        # فایل all_raw برای فازهای بعدی
        all_raw = workdir / "all_raw.txt"
        all_raw.write_text("\n".join(sorted(found.keys())) + "\n")
        jr.log(f"[+] مجموع نهایی پس از حذف اوت‌آف‌اسکوپ: {len(found)}")

    db.close()
