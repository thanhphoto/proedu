import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proedu.settings')
django.setup()

from django.test import RequestFactory, Client
from django.urls import reverse, resolve
from django.utils import timezone
from datetime import timedelta
from quiz.models import Quiz, Subject, ExamPeriod, ExamResult, QuestionBank, QuizQuestion

def run_tests():
    client = Client()
    print("--- 1. Testing URL reverses and resolves ---")
    assert reverse('enter_exam_code') == '/vao-thi/'
    assert reverse('take_exam', kwargs={'exam_code': '279861'}) == '/thi/279861/'
    assert reverse('submit_exam', kwargs={'exam_code': '279861'}) == '/nop-bai/279861/'
    print("✓ URL reversal verified")

    print("\n--- 2. Testing Home page for VÀO THI button and modal ---")
    resp = client.get(reverse('home'))
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'VÀO THI' in content
    assert 'enterExamCodeModal' in content
    assert 'modalExamCodeInput' in content
    print("✓ Home page contains VÀO THI button and modal")

    print("\n--- 3. Testing enter_exam_code view ---")
    resp = client.get(reverse('enter_exam_code'))
    assert resp.status_code == 200
    assert 'VÀO PHÒNG THI' in resp.content.decode('utf-8')

    # Test invalid code
    resp = client.post(reverse('enter_exam_code'), {'exam_code': '000000'})
    assert resp.status_code == 200
    assert 'Không tìm thấy' in resp.content.decode('utf-8') or 'không tồn tại' in resp.content.decode('utf-8')

    # Find or create a test quiz
    quiz = Quiz.objects.first()
    assert quiz is not None, "At least one Quiz must exist"
    exam_code = quiz.exam_code
    print(f"Using test quiz: ID={quiz.id}, exam_code={exam_code}, title='{quiz.title}'")

    # Test valid code POST redirects to /thi/<exam_code>/
    resp = client.post(reverse('enter_exam_code'), {'exam_code': exam_code})
    assert resp.status_code == 302
    assert resp.url == f'/thi/{exam_code}/'
    print(f"✓ Valid code redirect works: {resp.url}")

    print("\n--- 4. Testing take_exam view ---")
    # A. Normal / current time
    quiz.start_time = timezone.now() - timedelta(minutes=5)
    quiz.deadline = timezone.now() + timedelta(hours=2)
    quiz.save()

    resp = client.get(f'/thi/{exam_code}/')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert f'MÃ ĐỀ: {exam_code}' in content
    assert 'startScreen' in content
    assert 'examMainArea' in content
    assert 'smartquiz_exam_' in content
    print("✓ Normal take_exam renders correctly")

    # B. Future start_time (Waiting Room)
    quiz.start_time = timezone.now() + timedelta(minutes=30)
    quiz.save()
    resp = client.get(f'/thi/{exam_code}/')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'PHÒNG CHỜ BÀI THI' in content
    assert 'waitingCountdownDisplay' in content
    print("✓ Future start_time triggers Waiting Room correctly")

    # C. Past deadline (Expired)
    quiz.start_time = timezone.now() - timedelta(hours=3)
    quiz.deadline = timezone.now() - timedelta(hours=1)
    quiz.save()
    resp = client.get(f'/thi/{exam_code}/')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'BÀI THI ĐÃ KẾT THÚC' in content
    print("✓ Past deadline triggers Expired Screen correctly")

    # Reset quiz to normal
    quiz.start_time = timezone.now() - timedelta(minutes=10)
    quiz.deadline = timezone.now() + timedelta(hours=2)
    quiz.save()

    print("\n--- 5. Testing submit_exam validation & processing ---")
    # A. Anonymous without candidate name should be rejected
    resp = client.post(f'/nop-bai/{exam_code}/', {})
    assert resp.status_code == 302
    assert resp.url == f'/thi/{exam_code}/'
    print("✓ Anonymous without name rejected and redirected")

    # B. Anonymous with candidate name
    post_data = {
        'candidate_name': 'Thí Sinh Tự Do Test',
        'time_spent': '125'
    }
    # Populate some question answers
    for qq in quiz.quiz_questions.all():
        if qq.bank_question.question_type == 'SINGLE':
            choice = qq.bank_question.choices.first()
            if choice:
                post_data[f'q_{qq.id}_single'] = str(choice.id)

    resp = client.post(f'/nop-bai/{exam_code}/', post_data)
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'HOÀN THÀNH BÀI THI' in content or 'Kết Quả Làm Bài' in content
    assert 'Thí Sinh Tự Do Test' in content
    assert f'smartquiz_exam_{exam_code}' in content
    print("✓ Submission succeeded and result rendered with localStorage cleanup")

    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")

if __name__ == '__main__':
    run_tests()
