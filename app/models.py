import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text,
    Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# کاربر
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # --- ادمین و اشتراک ---
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)  # False = کاربر مسدود شده
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    subscription_expires_at = Column(DateTime, nullable=True)  # None = بدون انقضا

    plan = relationship("Plan", back_populates="users")
    targets = relationship("Target", back_populates="owner", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="owner", cascade="all, delete-orphan")

    @property
    def subscription_active(self) -> bool:
        if not self.is_active:
            return False
        if self.subscription_expires_at is None:
            return True
        return self.subscription_expires_at >= datetime.utcnow()


# ---------------------------------------------------------------------------
# پلن اشتراک (توسط ادمین تعریف و به کاربرها اختصاص داده می‌شود)
# ---------------------------------------------------------------------------
class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    max_targets = Column(Integer, nullable=False, default=3)
    max_concurrent_scans = Column(Integer, nullable=False, default=1)
    is_default = Column(Boolean, default=False, nullable=False)  # پلنی که کاربر جدید موقع ثبت‌نام می‌گیرد
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="plan")


# ---------------------------------------------------------------------------
# API Key های شخصی هر کاربر برای ابزارهای فاز جمع‌آوری پسیو
# ---------------------------------------------------------------------------
class ApiToolName(str, enum.Enum):
    # --- کلیدهایی که هم به‌صورت مستقیم (باینری جدا) و هم داخل provider-config.yaml خودِ
    # subfinder استفاده می‌شوند ---
    chaos = "chaos"
    github_subdomains = "github_subdomains"   # GitHub token — هم برای ابزار github-subdomains و هم سورس github در subfinder
    shodan = "shodan"                          # هم برای shosubgo و هم سورس shodan در subfinder

    # --- سورس‌های subfinder که فقط از طریق provider-config.yaml استفاده می‌شوند ---
    bevigil = "bevigil"
    digitalyama = "digitalyama"
    pugrecon = "pugrecon"
    zoomeyeapi = "zoomeyeapi"
    fofa_email = "fofa_email"                  # فوفا کلید ترکیبی email:key می‌خواهد
    fofa_key = "fofa_key"

    # --- کلیدهای ابزارهای دیگر (خارج از subfinder) ---
    c99 = "c99"                                 # c99.nl subdomain finder
    censys_id = "censys_id"
    censys_secret = "censys_secret"


# نگاشت هر عضو ApiToolName به نام سورس داخل provider-config.yaml subfinder
# (فقط شامل مواردی است که خودِ subfinder می‌شناسد؛ چیزهایی مثل c99/censys اینجا نیستند
# چون همان‌طور که در enum_tasks استفاده شده به‌صورت مستقل با curl صدا زده می‌شوند)
SUBFINDER_SIMPLE_SOURCES: dict["ApiToolName", str] = {
    ApiToolName.chaos: "chaos",
    ApiToolName.github_subdomains: "github",
    ApiToolName.shodan: "shodan",
    ApiToolName.bevigil: "bevigil",
    ApiToolName.digitalyama: "digitalyama",
    ApiToolName.pugrecon: "pugrecon",
    ApiToolName.zoomeyeapi: "zoomeyeapi",
}


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("user_id", "tool_name", name="uq_user_tool"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(SAEnum(ApiToolName), nullable=False)
    key_value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="api_keys")


# ---------------------------------------------------------------------------
# تارگت (فضای هر تارگت جدا)
# ---------------------------------------------------------------------------
class Target(Base):
    __tablename__ = "targets"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_target_name"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # مثلا نام برنامه‌ی باگ‌بانتی
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="targets")
    scope_entries = relationship("ScopeEntry", back_populates="target", cascade="all, delete-orphan")
    scan_jobs = relationship("ScanJob", back_populates="target", cascade="all, delete-orphan")
    subdomains = relationship("Subdomain", back_populates="target", cascade="all, delete-orphan")
    httpx_results = relationship("HttpxResult", back_populates="target", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# اسکوپ: اوت‌آف‌اسکوپ / این‌اسکوپ وایلدکارت (فاز ساب‌دامین روش انجام می‌شود) / دامنه‌ی عادی
# ---------------------------------------------------------------------------
class ScopeType(str, enum.Enum):
    out_of_scope = "out_of_scope"
    in_scope_wildcard = "in_scope_wildcard"
    normal_domain = "normal_domain"


class ScopeEntry(Base):
    __tablename__ = "scope_entries"
    __table_args__ = (UniqueConstraint("target_id", "entry", name="uq_target_entry"),)

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    entry = Column(String(255), nullable=False)  # مثلا example.com یا *.example.com
    scope_type = Column(SAEnum(ScopeType), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    target = relationship("Target", back_populates="scope_entries")


# ---------------------------------------------------------------------------
# جاب‌های اسکن (هر فاز پایپ‌لاین به عنوان یک ردیف job ثبت می‌شود)
# ---------------------------------------------------------------------------
class ScanPhase(str, enum.Enum):
    passive_enum = "passive_enum"          # subfinder/chaos/assetfinder/findomain/crtsh/abuseipdb/amass/c99/shosubgo/github-subdomains
    dns_resolve = "dns_resolve"            # shuffledns + massdns brute
    tech_detect = "tech_detect"            # asnmap|naabu|httpx|nuclei tech-detect
    httpx_probe = "httpx_probe"            # httpx table + diff
    finalize = "finalize"                  # katana + waybackurls روی زیردامنه‌های فعال


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    phase = Column(SAEnum(ScanPhase), nullable=False)
    status = Column(SAEnum(JobStatus), default=JobStatus.pending, nullable=False)
    celery_task_id = Column(String(64), nullable=True)
    log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    target = relationship("Target", back_populates="scan_jobs")


# ---------------------------------------------------------------------------
# ساب‌دامین‌های جمع‌آوری/ریزالو شده
# ---------------------------------------------------------------------------
class Subdomain(Base):
    __tablename__ = "subdomains"
    __table_args__ = (UniqueConstraint("target_id", "name", name="uq_target_subdomain"),)

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(512), nullable=False, index=True)
    source = Column(String(64), nullable=True)  # subfinder/chaos/amass/... (اولین منبعی که پیدایش کرد)
    resolved = Column(Boolean, default=False)
    ip = Column(String(64), nullable=True)
    is_wildcard_scope = Column(Boolean, default=False)  # از اسکوپ وایلدکارت اومده یا دامنه‌ی عادی
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    target = relationship("Target", back_populates="subdomains")


# ---------------------------------------------------------------------------
# نتایج httpx (پورت/تایتل/کانتنت‌تایپ/تکنولوژی/آی‌پی/وب‌سرور) + وضعیت دیف با اجرای قبلی
# ---------------------------------------------------------------------------
class HttpxResult(Base):
    __tablename__ = "httpx_results"
    __table_args__ = (UniqueConstraint("target_id", "subdomain", "port", name="uq_target_subdomain_port"),)

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    subdomain = Column(String(512), nullable=False, index=True)
    port = Column(String(16), nullable=True)
    title = Column(String(512), nullable=True)
    content_type = Column(String(128), nullable=True)
    content_length = Column(Integer, nullable=True)
    tech = Column(String(512), nullable=True)  # comma-separated
    ip = Column(String(64), nullable=True)
    webserver = Column(String(128), nullable=True)
    status_code = Column(Integer, nullable=True)

    # فیلدهای مربوط به دیف نسبت به اجرای قبلی
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_new = Column(Boolean, default=True)          # در آخرین اسکن، ساب‌دامین/پورت جدید بوده
    content_changed = Column(Boolean, default=False)  # نسبت به دفعه قبل تایتل/کانتنت‌لن تغییر کرده

    target = relationship("Target", back_populates="httpx_results")


# ---------------------------------------------------------------------------
# نتایج فاز tech-detect (asnmap|naabu|httpx|nuclei -id tech-detect)
# ---------------------------------------------------------------------------
class TechDetectResult(Base):
    __tablename__ = "tech_detect_results"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    host = Column(String(512), nullable=False)
    matched_template = Column(String(255), nullable=True)  # nuclei template-id
    info = Column(Text, nullable=True)                       # raw nuclei output line
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# نتایج نهایی: کاتانا (crawling) + waybackurls روی زیردامنه‌های فعال
# ---------------------------------------------------------------------------
class FinalUrl(Base):
    __tablename__ = "final_urls"
    __table_args__ = (UniqueConstraint("target_id", "url", name="uq_target_url"),)

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    source = Column(String(32), nullable=True)  # katana / wayback
    first_seen = Column(DateTime, default=datetime.utcnow)
