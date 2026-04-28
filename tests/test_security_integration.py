# nmtrucworking/mtec-operations-hub-backend/mtec-operations-hub-backend-cc3a564342944b2409ea3505121159547923016f/tests/test_security_integration.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import time

def test_rate_limit_enforcement(client: TestClient):
    """
    Xác thực cơ chế Sliding Window Log trên Redis.
    Điểm cuối (Endpoint) /api/auth/login giới hạn 5 requests / 60 giây.
    """
    payload = {"username": "admin_test", "password": "password_test"}
    
    for _ in range(5):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code in [200, 401]

    response_blocked = client.post("/api/auth/login", json=payload)
    assert response_blocked.status_code == 429
    assert response_blocked.json()["detail"] == "Vuot qua gioi han request, vui long thu lai sau"


# Bổ sung tham số test_db: Session vào hàm
def test_token_rotation_and_blacklist(client: TestClient, test_db: Session):
    """
    Xác thực cơ chế Token Rotation và danh sách đen (Blacklist).
    Quy trình: 
    1. Giải lập việc sở hữu một refreshToken (Mã hóa trực tiếp thông qua hàm hệ thống).
    2. Sử dụng token để yêu cầu cấp lại (Refresh).
    3. Tái sử dụng token cũ, hệ thống phải chặn lại để chống Replay Attack.
    """
    from app.core.security import create_refresh_token
    from app.models import User
    from app.core.security import get_password_hash

    # Sử dụng trực tiếp test_db thay vì get_session_factory()
    test_user_id = "TEST-USER-ID"
    test_db.add(User(id=test_user_id, username="test_rotation", password_hash=get_password_hash("123"), full_name="Test", role="member", is_active=True))
    test_db.commit()

    # Cấp phát token hợp lệ
    valid_refresh_token = create_refresh_token(test_user_id)

    # 1. Gọi API Refresh lần 1 (Phải thành công và trả về cặp token mới)
    res_success = client.post("/api/auth/refresh", json={"refreshToken": valid_refresh_token})
    assert res_success.status_code == 200
    assert "accessToken" in res_success.json()["data"]

    # 2. Gọi API Refresh lần 2 với cùng token cũ (Phải thất bại do token đã bị đưa vào Redis Blacklist)
    res_blocked = client.post("/api/auth/refresh", json={"refreshToken": valid_refresh_token})
    assert res_blocked.status_code == 401
    assert res_blocked.json()["detail"] == "Token da bi thu hoi hoac het han"