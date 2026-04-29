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
    from app.services.report_service import generate_member_profile_docx
    
    # Create mock data
    member = MockMember(
        id="test-id",
        mssv="20210001",
        name="Nguyễn Văn A",
        gender="Nam",
        dob=date(2003, 5, 20),
        ban="Ban Công nghệ",
        role_title="Thành viên",
        phone="0987654321",
        email="test@example.com",
        goal="Học hỏi và phát triển",
        orientation="Backend Developer",
        khoa="CNTT",
        chuyen_nganh="Kỹ thuật phần mềm"
    )
    
    skills = [
        MockSkill(name="Lập trình Python", level="Tốt"),
        MockSkill(name="Thiết kế UI/UX", level="Cơ bản"),
    ]
    
    # Run generation
    print("Generating DOCX...")
    buffer = generate_member_profile_docx(member, skills)
    
    # Save to file for manual check if needed
    with open("test_output.docx", "wb") as f:
        f.write(buffer.getvalue())
    
    print("Success! DOCX generated and saved to test_output.docx")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
