import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Database ---
DB_USER = os.getenv("SUBSPYDER_DB_USER", "subspyder")
DB_PASSWORD = os.getenv("SUBSPYDER_DB_PASSWORD", "changeme")
DB_HOST = os.getenv("SUBSPYDER_DB_HOST", "localhost")
DB_PORT = os.getenv("SUBSPYDER_DB_PORT", "5432")
DB_NAME = os.getenv("SUBSPYDER_DB_NAME", "subspyder")

DATABASE_URL = os.getenv(
    "SUBSPYDER_DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# --- Sessions / Security ---
SECRET_KEY = os.getenv("SUBSPYDER_SECRET_KEY", "PLEASE-CHANGE-ME-IN-PROD")
SESSION_COOKIE_NAME = "subspyder_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days

# --- Celery / Redis ---
REDIS_URL = os.getenv("SUBSPYDER_REDIS_URL", "redis://localhost:6379/0")

# --- Filesystem workspace per user/target ---
# هر کاربر یک پوشه‌ی جدا زیر این مسیر می‌گیرد، و هر تارگت زیرپوشه‌ی جدا داخل آن
WORKSPACE_ROOT = Path(os.getenv("SUBSPYDER_WORKSPACE_ROOT", str(BASE_DIR / "workspace")))
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

# مسیر resolvers.txt مشترک (برای shuffledns / massdns)
RESOLVERS_FILE = Path(os.getenv("SUBSPYDER_RESOLVERS_FILE", str(BASE_DIR / "resolvers.txt")))


def user_workspace(user_id: int) -> Path:
    p = WORKSPACE_ROOT / f"user_{user_id}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def target_workspace(user_id: int, target_id: int) -> Path:
    p = user_workspace(user_id) / f"target_{target_id}"
    p.mkdir(parents=True, exist_ok=True)
    return p
