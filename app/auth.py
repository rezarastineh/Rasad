from fastapi import Request, Depends, HTTPException, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="subspyder-session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_session_cookie(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def read_session_cookie(token: str) -> int | None:
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = read_session_cookie(token)
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user and not user.is_active:
        return None  # کاربر مسدود شده — طوری رفتار می‌کنیم که انگار لاگین نیست
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="دسترسی ادمین لازم است.")
    return user
