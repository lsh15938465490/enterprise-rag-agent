"""
密码加密和 JWT 令牌。

密码只存哈希，不能还原；登录成功后发 access（短）和 refresh（长）两种令牌。
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

BCRYPT_ROUNDS = 12
ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


def hash_password(plain: str) -> str:
    """把明文密码变成不可逆哈希，存进数据库。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """登录时核对用户输入的密码和库里的哈希是否匹配。"""
    return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: uuid.UUID, tenant_id: uuid.UUID | None, token_type: TokenType) -> tuple[str, str]:
    """签发令牌。jti 是令牌身份证，登出时可以拉黑。"""
    now = datetime.now(timezone.utc)
    if token_type == "access":
        exp = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        exp = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else "",
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": exp,
    }
    token = jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict[str, Any]:
    """解开令牌。伪造或过期会抛异常。"""
    return jwt.decode(token, settings.APP_SECRET_KEY, algorithms=[ALGORITHM])
