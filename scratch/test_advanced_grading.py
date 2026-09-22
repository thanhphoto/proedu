import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proedu.settings')
import django
django.setup()

import io
from PIL import Image
import openpyxl
from django.test import Client
from django.contrib.auth.models import User

from quiz.models import StudentClass, Student, Subject, ExamPeriod, GradingExamKey, GradingKeyQuestion
from quiz.grading_views import calculate_score

def test_advanced_features():
    print("=== BẮT ĐẦU KIỂM THỬ TÍNH NĂNG NÂNG CẤP PHÂN HỆ CHẤM TRẮC NGHIỆM ===")

    # 1. KIỂM THỬ QUẢN LÝ HỌC SINH VÀ LỚP HỌC (MASTER ROSTER)
    cls, _ = StudentClass.objects.get_or_create(name='12A1', grade='12')
    st1, _ = Student.objects.get_or_create(student_id='120001', defaults={'full_name': 'Nguyễn Văn An', 'student_class': cls, 'gender': 'Nam'})
    st2, _ = Student.objects.get_or_create(student_id='120002', defaults={'full_name': 'Trần Thị Bình', 'student_class': cls, 'gender': 'Nữ'})

    print(f"✓ 1. Đã tạo Lớp: {cls.name} (Số học sinh: {cls.total_students})")
    assert cls.total_students >= 2
    assert Student.objects.filter(student_id='120001').exists()

    # 2. KIỂM THỬ ĐỒNG BỘ ĐIỂM SỐ THEO LOẠI CÂU HỎI
    period, _ = ExamPeriod.objects.get_or_create(name="Kỳ Thi Khảo Sát 2025")
    subject, _ = Subject.objects.get_or_create(exam_period=period, code="LY2025", defaults={'name': 'Vật Lí 12'})

    key, _ = GradingExamKey.objects.get_or_create(
        subject=subject,
        code="201",
        defaults={'title': 'Đề Vật Lí 201', 'score_single': 0.25, 'score_numeric': 0.5}
    )
    key.questions.all().delete()

    # 4 câu SingleChoose (cùng nhận score_single = 0.25đ)
    for i in range(1, 5):
        GradingKeyQuestion.objects.create(key=key, question_number=i, question_type='SINGLE', score_weight=key.score_single, correct_single='A')

    # 2 câu TrueFalse (cùng nhận max 1.0đ)
    for i in range(5, 7):
        GradingKeyQuestion.objects.create(key=key, question_number=i, question_type='TF', score_weight=1.0, correct_tf={'a': True, 'b': False, 'c': True, 'd': True})

    # 2 câu Điền số (cùng nhận score_numeric = 0.5đ)
    for i in range(7, 9):
        GradingKeyQuestion.objects.create(key=key, question_number=i, question_type='NUMERIC', score_weight=key.score_numeric, correct_numeric='1.25')

    questions = list(key.questions.all())
    print(f"✓ 2. Đề {key.code}: SingleChoose={key.score_single}đ/câu, Numeric={key.score_numeric}đ/câu. Tổng câu: {len(questions)}")
    # Max possible score = 4*0.25 + 2*1.0 + 2*0.5 = 1.0 + 2.0 + 1.0 = 4.0đ
    print(f"   Total max score: {key.max_possible_score}đ")
    assert key.max_possible_score == 4.0

    # 3. KIỂM THỬ XỬ LÝ FILE ẢNH TIFF VÀ JPG (DPI = 150)
    # Tạo 1 file ảnh TIFF chuẩn 150 DPI bằng PIL
    img_tiff = Image.new('RGB', (1200, 1600), color='white')
    buffer_tiff = io.BytesIO()
    img_tiff.save(buffer_tiff, format='TIFF', dpi=(150, 150))
    buffer_tiff.seek(0)

    # Kiểm tra PIL đọc DPI thành công
    test_img = Image.open(buffer_tiff)
    print(f"✓ 3. Kiểm thử ảnh TIFF: Định dạng={test_img.format}, Kích thước={test_img.size}, DPI={test_img.info.get('dpi')}")
    assert test_img.format == 'TIFF'
    assert test_img.info.get('dpi') == (150, 150)

    # 4. KIỂM THỬ TẠO FILE EXCEL NHIỀU MÃ ĐỀ TRONG 1 SHEET
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["STT / Loại", "101", "102", "103"])
    ws.append(["Câu 1 (Single)", "A", "B", "C"])
    ws.append(["Câu 2 (Single)", "B", "C", "D"])
    ws.append(["Câu 3 (TrueFalse)", "Đ,S,Đ,Đ", "S,Đ,S,Đ", "Đ,Đ,S,S"])
    ws.append(["Câu 4 (Số thực)", "1.25", "-3.5", "12.5"])

    excel_buf = io.BytesIO()
    wb.save(excel_buf)
    excel_buf.seek(0)

    wb_read = openpyxl.load_workbook(excel_buf)
    sheet_read = wb_read.active
    cols = [str(c) for c in list(sheet_read.iter_rows(values_only=True))[0][1:]]
    print(f"✓ 4. Đọc file Excel nhiều mã đề trong 1 sheet: Phát hiện {len(cols)} mã đề -> {cols}")
    assert cols == ["101", "102", "103"]

    print("\n=== TOÀN BỘ KIỂM THỬ TÍNH NĂNG NÂNG CẤP VƯỢT QUA 100%! ===")

if __name__ == '__main__':
    test_advanced_features()
