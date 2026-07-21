"""
ساخت یا ارتقای یک کاربر به ادمین، از طریق خط فرمان (نه از داخل خودِ وب‌اپ) —
تا هیچ کاربر عادی‌ای نتونه خودش رو ادمین کنه.

استفاده:
    python -m app.create_admin --username admin --email admin@example.com --password 'یه-رمز-قوی'

اگه یوزری با همون username از قبل وجود داشته باشه، فقط فلگ is_admin=True روش ست می‌شه
(و اگه --password داده بشه، رمزش هم آپدیت می‌شه).
"""

import argparse
import getpass
import sys

from app.database import SessionLocal, Base, engine
from app.models import User, Plan
from app.auth import hash_password
from app.bootstrap import ensure_default_plan


def main():
    parser = argparse.ArgumentParser(description="ساخت/ارتقای کاربر ادمین SubSpyder")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=False)
    parser.add_argument("--password", required=False, help="اگه ندی، به‌صورت امن ازت می‌پرسه")
    args = parser.parse_args()

    password = args.password or getpass.getpass("رمز عبور ادمین: ")
    if len(password) < 8:
        print("رمز عبور باید حداقل ۸ کاراکتر باشد.", file=sys.stderr)
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    ensure_default_plan()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        default_plan = db.query(Plan).filter(Plan.is_default == True).first()  # noqa: E712

        if user:
            user.is_admin = True
            user.is_active = True
            user.password_hash = hash_password(password)
            if args.email:
                user.email = args.email
            print(f"کاربر «{args.username}» به ادمین ارتقا پیدا کرد.")
        else:
            if not args.email:
                print("برای ساخت کاربر جدید، --email هم لازمه.", file=sys.stderr)
                sys.exit(1)
            user = User(
                username=args.username,
                email=args.email,
                password_hash=hash_password(password),
                is_admin=True,
                is_active=True,
                plan_id=default_plan.id if default_plan else None,
            )
            db.add(user)
            print(f"کاربر ادمین «{args.username}» ساخته شد.")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
