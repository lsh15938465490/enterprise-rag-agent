"""密码哈希和 JWT 签发/解析的单元测试。"""

from app.core.security import create_token, decode_token, hash_password, verify_password
from uuid import uuid4


def test_password_hash_roundtrip():
    hashed = hash_password("Admin@123456")
    assert verify_password("Admin@123456", hashed)
    assert not verify_password("wrong-pass", hashed)


def test_jwt_contains_tenant():
    uid, tid = uuid4(), uuid4()
    token, jti = create_token(uid, tid, "access")
    payload = decode_token(token)
    assert payload["sub"] == str(uid)
    assert payload["tenant_id"] == str(tid)
    assert payload["type"] == "access"
    assert payload["jti"] == jti


def test_jwt_platform_super_admin_has_empty_tenant():
    uid = uuid4()
    token, _ = create_token(uid, None, "access")
    payload = decode_token(token)
    assert payload["sub"] == str(uid)
    assert payload["tenant_id"] == ""
