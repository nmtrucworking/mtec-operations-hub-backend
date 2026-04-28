import pytest
from fastapi.testclient import TestClient
import time

def test_rate_limit_enforcement(client: TestClient):
    """
    Xác thực cơ chế Sliding Window Log trên Redis.
    Điểm cuối (Endpoint) /api/auth/login giới hạn 5 requests / 60 giây.
    """
    payload = {"username": "admin_test", "password": "password_test"}
    
    # Thực thi 5 requests hợp lệ đầu tiên
    for _ in range(5):
        response = client.post("/api/auth/login", json=payload)
        # Bỏ qua xác thực thông tin đăng nhập (401), chỉ quan tâm đến trạng thái của Rate Limit
        assert response.status_code in [200, 401]

    # Cố ý thực thi request thứ 6, hệ thống bắt buộc phải từ chối với mã 429
    response_blocked = client.post("/api/auth/login", json=payload)
    assert response_blocked.status_code == 429
    assert response_blocked.json()["detail"] == "Vuot qua gioi han request, vui long thu lai sau"


def test_token_rotation_and_blacklist(client: TestClient):
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
    from app.db import get_session_factory

    # Khởi tạo dữ liệu người dùng ảo vào in-memory database
    factory = get_session_factory()
    db = factory()
    test_user_id = "TEST-USER-ID"
    db.add(User(id=test_user_id, username="test_rotation", password_hash=get_password_hash("123"), full_name="Test", role="member", is_active=True))
    db.commit()

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
    
    db.close()