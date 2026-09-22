import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proedu.settings')
django.setup()

from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from quiz.models import UserProfile, Quiz, ExamResult
from quiz.avatars import PRESET_AVATARS, VALID_AVATAR_IDS

def run_tests():
    print("--- 1. Verify PRESET_AVATARS ---")
    assert len(PRESET_AVATARS) == 16, f"Expected 16 preset avatars, found {len(PRESET_AVATARS)}"
    assert 'avatar-1' in VALID_AVATAR_IDS
    assert 'avatar-16' in VALID_AVATAR_IDS
    print("✓ 16 preset avatars verified")

    print("\n--- 2. Verify Anonymous Access to Profile ---")
    client = Client()
    resp = client.get(reverse('profile'))
    assert resp.status_code == 302
    assert '/dang-nhap/' in resp.url
    print("✓ Anonymous redirected to login")

    print("\n--- 3. Create/Retrieve Test User & Login ---")
    user, created = User.objects.get_or_create(username='test_avatar_user')
    user.set_password('Password123!')
    user.first_name = 'Thành'
    user.last_name = 'Trịnh'
    user.email = 'thanh@example.com'
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.avatar = 'avatar-2'
    profile.save()

    logged_in = client.login(username='test_avatar_user', password='Password123!')
    assert logged_in, "Client login failed"
    print("✓ Test user logged in successfully")

    print("\n--- 4. Verify Navbar User Dropdown in HTML ---")
    resp = client.get(reverse('home'))
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'userMenuDropdown' in content
    assert 'navbarUserAvatar' in content
    assert '/thong-tin-ca-nhan/' in content
    assert '/dang-xuat/' in content
    assert 'avatar-2.svg' in content
    print("✓ Navbar displays user dropdown with avatar, profile link, and logout")

    print("\n--- 5. Verify Profile Page GET & Rendering ---")
    resp = client.get(reverse('profile'))
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'Chỉnh Sửa Thông Tin' in content
    assert 'Chọn Ảnh Đại Diện' in content
    assert 'Thay Đổi Mật Khẩu' in content
    assert 'avatar-1' in content
    assert 'avatar-16' in content
    print("✓ Profile page loaded with information form, 16 avatars, and password tab")

    print("\n--- 6. Test Update Profile & Avatar via Form POST ---")
    resp = client.post(reverse('profile'), {
        'action': 'update_profile',
        'first_name': 'Văn',
        'last_name': 'Nguyễn',
        'email': 'nguyenvan@gmail.com',
        'avatar': 'avatar-5'
    }, follow=True)
    assert resp.status_code == 200
    user.refresh_from_db()
    profile.refresh_from_db()
    assert user.first_name == 'Văn'
    assert user.last_name == 'Nguyễn'
    assert user.email == 'nguyenvan@gmail.com'
    assert profile.avatar == 'avatar-5'
    assert 'avatar-5.svg' in profile.avatar_url
    print("✓ Profile information and avatar updated successfully")

    print("\n--- 7. Test AJAX Avatar Update ---")
    resp = client.post(reverse('api_update_avatar'), {'avatar': 'avatar-10'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'success'
    assert data['avatar'] == 'avatar-10'
    profile.refresh_from_db()
    assert profile.avatar == 'avatar-10'
    print("✓ AJAX avatar update works instantly")

    print("\n--- 8. Test Change Password ---")
    # Wrong old password
    resp = client.post(reverse('profile'), {
        'action': 'change_password',
        'old_password': 'WrongPassword!',
        'new_password': 'NewPassword123!',
        'confirm_password': 'NewPassword123!'
    }, follow=True)
    assert 'không chính xác' in resp.content.decode('utf-8')

    # Valid password change
    resp = client.post(reverse('profile'), {
        'action': 'change_password',
        'old_password': 'Password123!',
        'new_password': 'NewPassword123!',
        'confirm_password': 'NewPassword123!'
    }, follow=True)
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.check_password('NewPassword123!')
    print("✓ Password change validated and updated successfully")

    print("\n--- 9. Verify Avatar Display in Exam Results & Detail ---")
    quiz = Quiz.objects.first()
    assert quiz is not None
    # Create an exam result with user's avatar
    result = ExamResult.objects.create(
        user=user,
        candidate_name=user.get_full_name(),
        candidate_avatar=profile.avatar,
        quiz=quiz,
        score=9.5,
        total_questions=20,
        correct_count=19,
        time_spent=600
    )
    assert 'avatar-10.svg' in result.avatar_url

    # Check exam results view (as manager/admin)
    profile.role = 'manager'
    profile.save()
    resp = client.get(reverse('exam_results_view', kwargs={'quiz_id': quiz.id}))
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'Bảng Điểm Thí Sinh' in content
    assert 'avatar-10.svg' in content
    assert user.get_full_name() in content

    # Check exam detail view
    resp = client.get(reverse('exam_detail', kwargs={'quiz_id': quiz.id}))
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'Danh Sách Thí Sinh & Kết Quả Làm Bài' in content
    assert 'avatar-10.svg' in content
    print("✓ Avatar correctly rendered in Exam Results List and Exam Detail")

    print("\n==========================================")
    print("ALL USER PROFILE & AVATAR TESTS PASSED!")
    print("==========================================")

if __name__ == '__main__':
    run_tests()
