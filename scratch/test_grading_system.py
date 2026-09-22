import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proedu.settings')
import django
django.setup()

from django.contrib.auth.models import User
from quiz.models import ExamPeriod, Subject, GradingExamKey, GradingKeyQuestion, GradingRecord
from quiz.grading_views import calculate_score

def test_scoring_system():
    print("=== BẮT ĐẦU KIỂM THỬ PHÂN HỆ CHẤM TRẮC NGHIỆM ===")

    # 1. Tạo hoặc lấy User test
    user, _ = User.objects.get_or_create(username='test_teacher', defaults={'email': 'teacher@test.com'})

    # 2. Tạo Kỳ thi & Môn thi
    period, _ = ExamPeriod.objects.get_or_create(
        name="Kỳ Thi Khảo Sát Năng Lực 2025",
        defaults={'description': 'Đợt khảo sát kiểm tra toàn diện'}
    )
    print(f"✓ 1. Kỳ thi: {period.name} (ID: {period.id})")

    subject, _ = Subject.objects.get_or_create(
        exam_period=period,
        code="TOAN25",
        defaults={'name': 'Toán Học 12'}
    )
    print(f"✓ 2. Môn thi: {subject.name} - Mã {subject.code} (ID: {subject.id})")

    # 3. Tạo Bộ Đáp Án Chuẩn
    key, _ = GradingExamKey.objects.get_or_create(
        subject=subject,
        code="101",
        defaults={'title': 'Bộ đáp án chính thức Đề 101', 'created_by': user}
    )
    key.questions.all().delete() # Clean for fresh test

    # Tạo các câu hỏi mẫu đủ 3 loại
    # Câu 1: SingleChoose (0.25đ, đáp án A)
    q1 = GradingKeyQuestion.objects.create(
        key=key, question_number=1, question_type='SINGLE', score_weight=0.25, correct_single='A'
    )
    # Câu 2: SingleChoose (0.5đ, đáp án C)
    q2 = GradingKeyQuestion.objects.create(
        key=key, question_number=2, question_type='SINGLE', score_weight=0.5, correct_single='C'
    )
    # Câu 3: TrueFalse (Chuẩn 1.0đ, đáp án: a:Đ, b:S, c:Đ, d:Đ)
    q3 = GradingKeyQuestion.objects.create(
        key=key, question_number=3, question_type='TF', score_weight=1.0,
        correct_tf={'a': True, 'b': False, 'c': True, 'd': True}
    )
    # Câu 4: Điền số thực (0.5đ, đáp án '1.25' - 4 ký tự)
    q4 = GradingKeyQuestion.objects.create(
        key=key, question_number=4, question_type='NUMERIC', score_weight=0.5, correct_numeric='1.25'
    )
    # Câu 5: Điền số thực (1.0đ, đáp án '-3.5' - 4 ký tự)
    q5 = GradingKeyQuestion.objects.create(
        key=key, question_number=5, question_type='NUMERIC', score_weight=1.0, correct_numeric='-3.5'
    )

    questions = list(key.questions.order_by('question_number').all())
    print(f"✓ 3. Đã tạo {len(questions)} câu hỏi chuẩn cho Đề {key.code}, điểm tối đa: {key.max_possible_score}đ")
    assert len(questions) == 5
    assert key.max_possible_score == 0.25 + 0.5 + 1.0 + 0.5 + 1.0 # = 3.25đ

    # 4. Kiểm thử các tình huống chấm điểm True/False theo thang điểm chuẩn
    print("\n--- KIỂM THỬ THANG ĐIỂM ĐÚNG/SAI (TRUE/FALSE) ---")
    # Tình huống 4/4 ý đúng -> 1.0 điểm
    ans_4_sub = {'3': {'a': True, 'b': False, 'c': True, 'd': True}}
    score, _, _, details = calculate_score([q3], ans_4_sub)
    print(f"  + Đúng 4/4 ý: Điểm = {score} (Kỳ vọng: 1.0) -> {'PASS' if score == 1.0 else 'FAIL'}")
    assert score == 1.0

    # Tình huống 3/4 ý đúng -> 0.5 điểm
    ans_3_sub = {'3': {'a': True, 'b': False, 'c': True, 'd': False}} # d sai
    score, _, _, details = calculate_score([q3], ans_3_sub)
    print(f"  + Đúng 3/4 ý: Điểm = {score} (Kỳ vọng: 0.5) -> {'PASS' if score == 0.5 else 'FAIL'}")
    assert score == 0.5

    # Tình huống 2/4 ý đúng -> 0.25 điểm
    ans_2_sub = {'3': {'a': True, 'b': True, 'c': True, 'd': False}} # b, d sai
    score, _, _, details = calculate_score([q3], ans_2_sub)
    print(f"  + Đúng 2/4 ý: Điểm = {score} (Kỳ vọng: 0.25) -> {'PASS' if score == 0.25 else 'FAIL'}")
    assert score == 0.25

    # Tình huống 1/4 ý đúng -> 0.1 điểm
    ans_1_sub = {'3': {'a': True, 'b': True, 'c': False, 'd': False}} # chỉ a đúng
    score, _, _, details = calculate_score([q3], ans_1_sub)
    print(f"  + Đúng 1/4 ý: Điểm = {score} (Kỳ vọng: 0.1) -> {'PASS' if score == 0.1 else 'FAIL'}")
    assert score == 0.1

    # Tình huống 0/4 ý đúng -> 0.0 điểm
    ans_0_sub = {'3': {'a': False, 'b': True, 'c': False, 'd': False}}
    score, _, _, details = calculate_score([q3], ans_0_sub)
    print(f"  + Đúng 0/4 ý: Điểm = {score} (Kỳ vọng: 0.0) -> {'PASS' if score == 0.0 else 'FAIL'}")
    assert score == 0.0

    # 5. Kiểm thử Điền số thực (Numeric <= 4 ký tự)
    print("\n--- KIỂM THỬ ĐIỀN SỐ THỰC (NUMERIC) ---")
    # Đúng chuẩn dấu chấm '1.25'
    score_dot, _, _, _ = calculate_score([q4], {'4': '1.25'})
    print(f"  + Nhập '1.25': Điểm = {score_dot} (Kỳ vọng: 0.5) -> {'PASS' if score_dot == 0.5 else 'FAIL'}")
    assert score_dot == 0.5

    # Đúng chuẩn dấu phẩy '1,25'
    score_comma, _, _, _ = calculate_score([q4], {'4': '1,25'})
    print(f"  + Nhập '1,25' (dấu phẩy): Điểm = {score_comma} (Kỳ vọng: 0.5) -> {'PASS' if score_comma == 0.5 else 'FAIL'}")
    assert score_comma == 0.5

    # Số âm '-3.5'
    score_neg, _, _, _ = calculate_score([q5], {'5': '-3.5'})
    print(f"  + Nhập '-3.5': Điểm = {score_neg} (Kỳ vọng: 1.0) -> {'PASS' if score_neg == 1.0 else 'FAIL'}")
    assert score_neg == 1.0

    # Nhập sai '1.26'
    score_wrong, _, _, _ = calculate_score([q4], {'4': '1.26'})
    print(f"  + Nhập sai '1.26': Điểm = {score_wrong} (Kỳ vọng: 0.0) -> {'PASS' if score_wrong == 0.0 else 'FAIL'}")
    assert score_wrong == 0.0

    # 6. Kiểm thử bài thi hoàn chỉnh của thí sinh
    print("\n--- KIỂM THỬ BÀI THI HOÀN CHỈNH ---")
    student_ans = {
        '1': 'A',                                           # Đúng -> 0.25đ
        '2': 'B',                                           # Sai (đáp án đúng C) -> 0.0đ
        '3': {'a': True, 'b': False, 'c': True, 'd': False},# Đúng 3/4 ý -> 0.5đ
        '4': '1,25',                                        # Đúng -> 0.5đ
        '5': '-3.5',                                        # Đúng -> 1.0đ
    }
    # Tổng điểm kỳ vọng: 0.25 + 0.0 + 0.5 + 0.5 + 1.0 = 2.25đ trên 3.25đ
    tot_score, max_score, correct_cnt, full_details = calculate_score(questions, student_ans)
    print(f"  + Tổng điểm đạt được: {tot_score} / {max_score}")
    print(f"  + Số câu đúng tuyệt đối: {correct_cnt} / {len(questions)}")
    assert tot_score == 2.25
    assert max_score == 3.25
    assert correct_cnt == 3 # Câu 1, Câu 4, Câu 5 đúng tuyệt đối

    # Lưu vào GradingRecord
    record = GradingRecord.objects.create(
        key=key,
        student_id='TS12001',
        student_name='Lê Hoàng Nam',
        student_class='12A1',
        exam_code=key.code,
        total_score=tot_score,
        max_score=max_score,
        correct_count=correct_cnt,
        student_answers=student_ans,
        grading_details=full_details,
        graded_by=user,
    )
    print(f"✓ 4. Đã lưu bài chấm: {record} (ID: {record.id})")
    assert record.id is not None

    print("\n=== TOÀN BỘ KIỂM THỬ BACKEND ĐÃ VƯỢT QUA 100%! ===")

if __name__ == '__main__':
    test_scoring_system()
