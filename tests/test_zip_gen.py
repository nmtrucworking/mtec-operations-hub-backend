import sys
import os
from datetime import date
from io import BytesIO

# Add project root to sys.path
sys.path.append(os.getcwd())

# Mock Member and MemberSkill
class MockMember:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class MockSkill:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# Import the service
try:
    from app.services.report_service import generate_members_zip
    
    # Create mock data
    members_data = [
        (
            MockMember(
                id="id-1", mssv="20210001", name="Nguyễn Văn A", gender="Nam", 
                dob=date(2003, 5, 20), ban="Ban Công nghệ", role_title="Thành viên",
                phone="0987654321", email="a@example.com", goal="Học hỏi",
                orientation="Backend", khoa="CNTT", chuyen_nganh="KTPM"
            ),
            [MockSkill(name="Lập trình Python", level="Tốt")]
        ),
        (
            MockMember(
                id="id-2", mssv="20210002", name="Trần Thị B", gender="Nữ", 
                dob=date(2003, 8, 15), ban="Ban Truyền thông", role_title="Trưởng ban",
                phone="0123456789", email="b@example.com", goal="Phát triển CLB",
                orientation="Marketing", khoa="Kinh tế", chuyen_nganh="Marketing"
            ),
            [MockSkill(name="Thiết kế", level="Trung bình")]
        )
    ]
    
    # Run generation
    print("Generating ZIP...")
    buffer = generate_members_zip(members_data)
    
    # Save to file for manual check
    with open("test_profiles.zip", "wb") as f:
        f.write(buffer.getvalue())
    
    print("Success! ZIP generated and saved to test_profiles.zip")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
