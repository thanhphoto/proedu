import json
import re
import io
import base64
import uuid
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Avg, Max, Min, Q
from django.core.paginator import Paginator
from django.core.files.base import ContentFile
from django.utils import timezone

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from PIL import Image
import cv2
import numpy as np

from .models import ExamPeriod, Subject, GradingExamKey, GradingKeyQuestion, GradingRecord, StudentClass, Student
from .decorators import manager_required


# =====================================================================
# THUẬT TOÁN CHẤM ĐIỂM TRẮC NGHIỆM CHUẨN 3 LOẠI CÂU HỎI
# =====================================================================

def calculate_score(key_questions, student_answers):
    """
    key_questions: queryset hoặc list các GradingKeyQuestion
    student_answers: dict chứa câu trả lời của thí sinh, dạng:
      {
        "1": "A",
        "2": {"a": True, "b": False, "c": True, "d": False},
        "3": "1.25"
      }
    """
    total_score = 0.0
    max_score = 0.0
    correct_count = 0
    details = []

    for q in key_questions:
        q_num = str(q.question_number)
        ans = student_answers.get(q_num)
        q.selected = ans

        q_detail = {
            'number': q.question_number,
            'type': q.question_type,
            'student_ans': ans,
            'correct_ans': None,
            'is_correct': False,
            'sub_results': None,
            'sub_correct_count': 0,
            'score': 0.0,
            'max_score': 0.0,
        }

        if q.question_type == 'SINGLE':
            q_detail['max_score'] = q.score_weight
            max_score += q.score_weight
            q_detail['correct_ans'] = q.correct_single

            user_str = str(ans or '').strip().upper()
            correct_str = str(q.correct_single or '').strip().upper()
            if user_str and user_str == correct_str:
                q_detail['is_correct'] = True
                q_detail['score'] = q.score_weight
                total_score += q.score_weight
                correct_count += 1
            else:
                q_detail['score'] = 0.0

        elif q.question_type == 'TF':
            q_detail['max_score'] = 1.0  # Chuẩn Đúng/Sai 4 ý tối đa 1.0 điểm
            max_score += 1.0
            correct_tf = q.correct_tf or {}
            q_detail['correct_ans'] = correct_tf

            sub_results = {}
            sub_correct = 0

            def parse_bool(val):
                if val in [True, 'true', 'True', '1', 'T', 'Đ', 'D', 'true', 'd']:
                    return True
                if val in [False, 'false', 'False', '0', 'F', 'S', 'false', 's']:
                    return False
                return None

            if isinstance(ans, dict):
                for sub in ['a', 'b', 'c', 'd']:
                    expected = parse_bool(correct_tf.get(sub))
                    user_sub = parse_bool(ans.get(sub))
                    is_sub_match = (user_sub is not None and expected is not None and user_sub == expected)
                    if is_sub_match:
                        sub_correct += 1
                    sub_results[sub] = {
                        'user': user_sub,
                        'expected': expected,
                        'is_correct': is_sub_match
                    }
            else:
                for sub in ['a', 'b', 'c', 'd']:
                    expected = parse_bool(correct_tf.get(sub))
                    sub_results[sub] = {'user': None, 'expected': expected, 'is_correct': False}

            q_detail['sub_results'] = sub_results
            q_detail['sub_correct_count'] = sub_correct

            # Thang điểm chuẩn: 1 ý = 0.1đ, 2 ý = 0.25đ, 3 ý = 0.5đ, 4 ý = 1.0đ
            if sub_correct == 4:
                tf_score = 1.0
                q_detail['is_correct'] = True
                correct_count += 1
            elif sub_correct == 3:
                tf_score = 0.5
            elif sub_correct == 2:
                tf_score = 0.25
            elif sub_correct == 1:
                tf_score = 0.1
            else:
                tf_score = 0.0

            q_detail['score'] = tf_score
            total_score += tf_score

        elif q.question_type == 'NUMERIC':
            q_detail['max_score'] = q.score_weight
            max_score += q.score_weight
            q_detail['correct_ans'] = q.correct_numeric

            def normalize_numeric_str(val):
                if val is None:
                    return None
                s = str(val).strip().replace(' ', '').replace(',', '.')
                try:
                    return float(s)
                except (ValueError, TypeError):
                    return None

            user_val = normalize_numeric_str(ans)
            correct_val = normalize_numeric_str(q.correct_numeric)

            if user_val is not None and correct_val is not None and abs(user_val - correct_val) <= 0.0001:
                q_detail['is_correct'] = True
                q_detail['score'] = q.score_weight
                total_score += q.score_weight
                correct_count += 1
            else:
                q_detail['score'] = 0.0

        details.append(q_detail)

    return round(total_score, 3), round(max_score, 3), correct_count, details


# =====================================================================
# 1. TRANG DASHBOARD TỔNG QUAN CHẤM TRẮC NGHIỆM
# =====================================================================

@manager_required
def grading_dashboard(request):
    """Trang chủ Layout Chấm Trắc Nghiệm với các phím tắt nhanh và thống kê"""
    total_periods = ExamPeriod.objects.count()
    total_subjects = Subject.objects.count()
    total_keys = GradingExamKey.objects.count()
    total_records = GradingRecord.objects.count()
    total_students = Student.objects.count()

    recent_records = GradingRecord.objects.select_related('key__subject__exam_period')[:8]
    recent_keys = GradingExamKey.objects.select_related('subject__exam_period').prefetch_related('questions')[:6]

    context = {
        'total_periods': total_periods,
        'total_subjects': total_subjects,
        'total_keys': total_keys,
        'total_records': total_records,
        'total_students': total_students,
        'recent_records': recent_records,
        'recent_keys': recent_keys,
        'active_tab': 'dashboard',
    }
    return render(request, 'quiz/grading/dashboard.html', context)


# =====================================================================
# 2. QUẢN LÝ HỌC SINH THEO LỚP & SỐ BÁO DANH (MASTER ROSTER)
# =====================================================================

@manager_required
def master_students_view(request):
    """Layout Quản lý Học sinh theo Lớp có Số Báo Danh (SBD) dùng chung tất cả kỳ thi"""
    classes = StudentClass.objects.prefetch_related('students').all()
    selected_class_id = request.GET.get('class_id', '')
    search_q = request.GET.get('q', '').strip()

    students = Student.objects.select_related('student_class').all()

    if selected_class_id:
        students = students.filter(student_class_id=selected_class_id)
    if search_q:
        students = students.filter(
            Q(student_id__icontains=search_q) |
            Q(full_name__icontains=search_q)
        )

    paginator = Paginator(students, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'classes': classes,
        'page_obj': page_obj,
        'selected_class_id': selected_class_id,
        'search_q': search_q,
        'total_students': Student.objects.count(),
        'active_tab': 'students',
    }
    return render(request, 'quiz/grading/students.html', context)


@manager_required
def api_create_class(request):
    """API Tạo mới lớp học"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    name = request.POST.get('name', '').strip()
    grade = request.POST.get('grade', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập tên lớp.'}, status=400)

    if StudentClass.objects.filter(name=name).exists():
        return JsonResponse({'status': 'error', 'message': f'Lớp "{name}" đã tồn tại.'}, status=400)

    cls = StudentClass.objects.create(name=name, grade=grade, description=description)
    return JsonResponse({
        'status': 'success',
        'message': f'Đã tạo lớp "{cls.name}" thành công!',
        'class': {'id': cls.id, 'name': cls.name}
    })


@manager_required
def api_create_student(request):
    """API Tạo mới hoặc cập nhật thông tin học sinh"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    student_id = request.POST.get('student_id', '').strip()
    full_name = request.POST.get('full_name', '').strip()
    class_id = request.POST.get('class_id', '')
    gender = request.POST.get('gender', '').strip()

    if not student_id or not full_name:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng điền Số báo danh và Họ tên.'}, status=400)

    if Student.objects.filter(student_id=student_id).exists():
        return JsonResponse({'status': 'error', 'message': f'Số báo danh "{student_id}" đã tồn tại trong hệ thống.'}, status=400)

    cls_obj = StudentClass.objects.filter(id=class_id).first() if class_id else None

    student = Student.objects.create(
        student_id=student_id,
        full_name=full_name,
        student_class=cls_obj,
        gender=gender
    )
    return JsonResponse({
        'status': 'success',
        'message': f'Đã thêm học sinh "{student.full_name}" (SBD: {student.student_id}) thành công!',
        'student': {
            'id': student.id,
            'student_id': student.student_id,
            'full_name': student.full_name,
            'class_name': cls_obj.name if cls_obj else ''
        }
    })


@manager_required
def api_update_student(request, student_pk):
    """API Sửa thông tin học sinh và đồng bộ các bài thi đã chấm"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    student = get_object_or_404(Student, id=student_pk)
    old_sbd = student.student_id

    student_id = request.POST.get('student_id', '').strip()
    full_name = request.POST.get('full_name', '').strip()
    class_id = request.POST.get('class_id', '')
    gender = request.POST.get('gender', '').strip()

    if not student_id or not full_name:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng điền Số báo danh và Họ tên.'}, status=400)

    # Kiểm tra nếu đổi SBD sang SBD khác đã có người dùng
    if student_id != old_sbd and Student.objects.filter(student_id=student_id).exclude(id=student_pk).exists():
        return JsonResponse({'status': 'error', 'message': f'Số báo danh "{student_id}" đã được sử dụng bởi học sinh khác.'}, status=400)

    cls_obj = StudentClass.objects.filter(id=class_id).first() if class_id else None

    student.student_id = student_id
    student.full_name = full_name
    student.student_class = cls_obj
    student.gender = gender
    student.save()

    # Đồng bộ thông tin học sinh sang các bài chấm đã lưu (GradingRecord)
    updated_records_count = GradingRecord.objects.filter(student_id=old_sbd).update(
        student_id=student_id,
        student_name=full_name,
        student_class=cls_obj.name if cls_obj else ''
    )

    return JsonResponse({
        'status': 'success',
        'message': f'Đã cập nhật thông tin học sinh "{student.full_name}" (SBD: {student.student_id}) thành công! Đã đồng bộ {updated_records_count} bài thi đã chấm.',
        'student': {
            'id': student.id,
            'student_id': student.student_id,
            'full_name': student.full_name,
            'class_name': cls_obj.name if cls_obj else '',
            'class_id': cls_obj.id if cls_obj else '',
            'gender': student.gender
        }
    })


@manager_required
def api_delete_student(request, student_pk):
    """API Xóa học sinh và tự động xóa tất cả các bài thi đã chấm của học sinh này"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)
    st = get_object_or_404(Student, id=student_pk)
    name = st.full_name
    sbd = st.student_id

    # Xóa tất cả các bài thi đã chấm của học sinh này
    deleted_records_count, _ = GradingRecord.objects.filter(student_id=sbd).delete()

    st.delete()
    return JsonResponse({
        'status': 'success',
        'message': f'Đã xóa học sinh "{name}" (SBD: {sbd}) cùng toàn bộ {deleted_records_count} bài thi đã chấm tương ứng.'
    })


@manager_required
def api_search_student_by_sbd(request):
    """API Tra cứu thông tin học sinh theo Số Báo Danh (SBD) cho giao diện chấm bài"""
    sbd = request.GET.get('sbd', '').strip()
    if not sbd:
        return JsonResponse({'found': False})

    student = Student.objects.select_related('student_class').filter(student_id=sbd).first()
    if student:
        applied_classes_str = request.GET.get('applied_classes', '').strip()
        applied_classes = [c.strip() for c in applied_classes_str.split(',') if c.strip()] if applied_classes_str else []
        class_match = True
        class_error = ''
        if applied_classes:
            cls_name = student.student_class.name if student.student_class else ''
            cls_id = str(student.student_class.id) if student.student_class else ''
            if cls_name not in applied_classes and cls_id not in applied_classes:
                class_match = False
                class_error = f"Học sinh {student.full_name} (Lớp {cls_name or 'Chưa xếp'}) không thuộc danh sách lớp đã áp dụng vào bài thi"

        return JsonResponse({
            'found': True,
            'student_id': student.student_id,
            'full_name': student.full_name,
            'class_name': student.student_class.name if student.student_class else '',
            'class_match': class_match,
            'class_error': class_error
        })
    return JsonResponse({'found': False})


@manager_required
def api_import_students_excel(request):
    """API Nhập danh sách học sinh từ File Excel (.xlsx, .xls)"""
    if request.method != 'POST' or 'excel_file' not in request.FILES:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn file Excel để tải lên.'}, status=400)

    excel_file = request.FILES['excel_file']
    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
        ws = wb.active
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Không thể đọc file Excel: {str(e)}'}, status=400)

    added_count = 0
    updated_count = 0

    # Giả định hàng 1 là tiêu đề: SBD | Họ tên | Lớp | Giới tính
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not any(row):
            continue

        sbd = str(row[0] or '').strip()
        full_name = str(row[1] or '').strip()
        class_name = str(row[2] or '').strip() if len(row) > 2 else ''
        gender = str(row[3] or '').strip() if len(row) > 3 else ''

        if not sbd or not full_name:
            continue

        cls_obj = None
        if class_name:
            cls_obj, _ = StudentClass.objects.get_or_create(name=class_name)

        student, created = Student.objects.get_or_create(
            student_id=sbd,
            defaults={'full_name': full_name, 'student_class': cls_obj, 'gender': gender}
        )

        if not created:
            student.full_name = full_name
            if cls_obj:
                student.student_class = cls_obj
            if gender:
                student.gender = gender
            student.save()
            updated_count += 1
        else:
            added_count += 1

    return JsonResponse({
        'status': 'success',
        'message': f'Nhập Excel thành công! Đã thêm mới {added_count} học sinh, cập nhật {updated_count} học sinh.',
    })


@manager_required
def export_students_excel(request):
    """Xuất danh sách học sinh master sang file Excel"""
    students = Student.objects.select_related('student_class').all()

    class_id = request.GET.get('class_id', '')
    if class_id:
        students = students.filter(student_class_id=class_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Danh Sách Học Sinh"

    headers = ["STT", "Số Báo Danh (SBD)", "Họ và Tên", "Lớp Học", "Giới Tính"]
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, st in enumerate(students, start=1):
        ws.append([
            idx,
            st.student_id,
            st.full_name,
            st.student_class.name if st.student_class else '',
            st.gender or ''
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="Danh_Sach_Hoc_Sinh_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    wb.save(response)
    return response


@manager_required
def download_sample_student_excel(request):
    """Tải file Excel mẫu danh sách học sinh để nhập liệu"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mau_Hoc_Sinh"

    headers = ["Số Báo Danh (SBD)", "Họ và Tên", "Lớp", "Giới Tính"]
    ws.append(headers)

    sample_data = [
        ["120001", "Nguyễn Văn An", "12A1", "Nam"],
        ["120002", "Trần Thị Bình", "12A1", "Nữ"],
        ["120003", "Lê Hoàng Cường", "12A2", "Nam"],
        ["120004", "Phạm Thu Dung", "12A2", "Nữ"],
    ]
    for row in sample_data:
        ws.append(row)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="Mau_Danh_Sach_Hoc_Sinh.xlsx"'
    wb.save(response)
    return response


# =====================================================================
# 3. QUẢN LÝ KỲ THI & MÔN THI
# =====================================================================

@manager_required
def grading_manage_exams(request):
    """Giao diện quản lý Kỳ thi và các Môn thi thuộc kỳ thi"""
    periods = ExamPeriod.objects.prefetch_related('subjects__grading_keys', 'subjects__assigned_classes').order_by('-id')
    classes = StudentClass.objects.all().order_by('grade', 'name')
    context = {
        'periods': periods,
        'classes': classes,
        'active_tab': 'exams',
    }
    return render(request, 'quiz/grading/manage_exams.html', context)


@manager_required
def api_create_exam_period(request):
    """API Tạo mới kỳ thi"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập tên kỳ thi.'}, status=400)

    period = ExamPeriod.objects.create(name=name, description=description)
    return JsonResponse({
        'status': 'success',
        'message': f'Đã tạo kỳ thi "{period.name}" thành công!',
        'period': {'id': period.id, 'name': period.name}
    })


@manager_required
def api_create_subject(request):
    """API Tạo mới môn thi trong kỳ thi kèm ràng buộc số điểm / 1 câu và danh sách lớp áp dụng"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    period_id = request.POST.get('exam_period_id')
    name = request.POST.get('name', '').strip()
    code = request.POST.get('code', '').strip().upper()

    try:
        num_single = int(request.POST.get('num_single', 24))
        score_per_single = float(request.POST.get('score_per_single', 0.25))

        num_tf = int(request.POST.get('num_tf', 4))
        score_per_tf = float(request.POST.get('score_per_tf', 1.0))

        num_numeric = int(request.POST.get('num_numeric', 6))
        score_per_numeric = float(request.POST.get('score_per_numeric', 0.5))

        max_score_single = round(num_single * score_per_single, 3)
        max_score_numeric = round(num_numeric * score_per_numeric, 3)
    except ValueError:
        num_single, num_tf, num_numeric = 24, 4, 6
        score_per_single, score_per_tf, score_per_numeric = 0.25, 1.0, 0.5
        max_score_single, max_score_numeric = 6.0, 3.0

    if not period_id or not name or not code:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng điền đầy đủ thông tin môn thi.'}, status=400)

    period = get_object_or_404(ExamPeriod, id=period_id)
    subject = Subject.objects.create(
        exam_period=period,
        name=name,
        code=code,
        num_single=num_single,
        score_per_single_val=score_per_single,
        num_tf=num_tf,
        score_per_tf_val=score_per_tf,
        num_numeric=num_numeric,
        score_per_numeric_val=score_per_numeric,
        max_score_single=max_score_single,
        max_score_numeric=max_score_numeric
    )

    # Gán các lớp áp dụng (nếu người dùng chọn các lớp cụ thể)
    class_ids = request.POST.getlist('class_ids')
    if class_ids:
        subject.assigned_classes.set(class_ids)

    assigned_class_names = list(subject.assigned_classes.values_list('name', flat=True))
    class_info = ", ".join(assigned_class_names) if assigned_class_names else "Tất cả các lớp"

    return JsonResponse({
        'status': 'success',
        'message': f'Đã tạo môn thi "{subject.name}" ({subject.code}) thành công!\nCấu hình: {subject.num_single} Single ({score_per_single}đ/câu) + {subject.num_tf} TF ({score_per_tf}đ/câu) + {subject.num_numeric} Số ({score_per_numeric}đ/câu).\nLớp áp dụng: {class_info}.',
        'subject': {
            'id': subject.id,
            'name': subject.name,
            'code': subject.code,
            'num_single': subject.num_single,
            'score_per_single': score_per_single,
            'num_tf': subject.num_tf,
            'score_per_tf': score_per_tf,
            'num_numeric': subject.num_numeric,
            'score_per_numeric': score_per_numeric,
            'classes': class_info
        }
    })


@manager_required
def api_update_subject(request, subject_id):
    """API Cập nhật thông tin môn thi: tên, mã môn, ràng buộc điểm từng phần và danh sách lớp áp dụng"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    subject = get_object_or_404(Subject, id=subject_id)
    name = request.POST.get('name', '').strip()
    code = request.POST.get('code', '').strip().upper()

    if not name or not code:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng điền đầy đủ tên và mã môn thi.'}, status=400)

    try:
        num_single = int(request.POST.get('num_single', subject.num_single))
        score_per_single = float(request.POST.get('score_per_single', subject.score_per_single))

        num_tf = int(request.POST.get('num_tf', subject.num_tf))
        score_per_tf = float(request.POST.get('score_per_tf', subject.score_per_tf))

        num_numeric = int(request.POST.get('num_numeric', subject.num_numeric))
        score_per_numeric = float(request.POST.get('score_per_numeric', subject.score_per_numeric))

        max_score_single = round(num_single * score_per_single, 3)
        max_score_numeric = round(num_numeric * score_per_numeric, 3)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Giá trị số câu hoặc điểm mỗi câu không hợp lệ.'}, status=400)

    subject.name = name
    subject.code = code
    subject.num_single = num_single
    subject.score_per_single_val = score_per_single
    subject.num_tf = num_tf
    subject.score_per_tf_val = score_per_tf
    subject.num_numeric = num_numeric
    subject.score_per_numeric_val = score_per_numeric
    subject.max_score_single = max_score_single
    subject.max_score_numeric = max_score_numeric
    subject.save()

    # Cập nhật danh sách lớp áp dụng
    # Nếu check "Áp dụng tất cả các lớp" thì class_ids rỗng, subject.assigned_classes.clear()
    class_ids = request.POST.getlist('class_ids')
    subject.assigned_classes.set(class_ids)

    assigned_class_names = list(subject.assigned_classes.values_list('name', flat=True))
    class_info = ", ".join(assigned_class_names) if assigned_class_names else "Tất cả các lớp"

    return JsonResponse({
        'status': 'success',
        'message': f'Đã cập nhật môn thi "{subject.name}" ({subject.code}) thành công!\nLớp áp dụng: {class_info}.',
        'subject': {
            'id': subject.id,
            'name': subject.name,
            'code': subject.code,
            'num_single': subject.num_single,
            'score_per_single': score_per_single,
            'num_tf': subject.num_tf,
            'score_per_tf': score_per_tf,
            'num_numeric': subject.num_numeric,
            'score_per_numeric': score_per_numeric,
            'classes': class_info
        }
    })


@manager_required
def api_delete_exam_period(request, period_id):
    """API xóa kỳ thi (xóa toàn bộ môn thi, đáp án, bài làm thí sinh liên quan)"""
    period = get_object_or_404(ExamPeriod, id=period_id)
    name = period.name
    period.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'status': 'success', 'message': f'Đã xóa kỳ thi "{name}" và toàn bộ dữ liệu bên trong.'})
    messages.success(request, f'Đã xóa kỳ thi "{name}" và toàn bộ dữ liệu bên trong thành công.')
    return redirect('grading_manage_exams')


@manager_required
def api_delete_subject(request, subject_id):
    """API xóa môn thi (xóa toàn bộ đáp án và bài làm thí sinh liên quan)"""
    subject = get_object_or_404(Subject, id=subject_id)
    name = subject.name
    subject.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'status': 'success', 'message': f'Đã xóa môn thi "{name}" và toàn bộ dữ liệu bên trong.'})
    messages.success(request, f'Đã xóa môn thi "{name}" và toàn bộ dữ liệu bên trong thành công.')
    return redirect('grading_manage_exams')



# =====================================================================
# 4. QUẢN LÝ ĐÁP ÁN CHUẨN & NHẬP EXCEL NHIỀU MÃ ĐỀ / LƯỚI MA TRẬN
# =====================================================================

@manager_required
def grading_key_list(request):
    """Danh sách các bộ đáp án chuẩn (Mã đề)"""
    keys = GradingExamKey.objects.select_related('subject__exam_period').prefetch_related('questions', 'submissions').order_by('-id')

    filter_period = request.GET.get('period_id', '')
    filter_subject = request.GET.get('subject_id', '')

    if filter_period:
        keys = keys.filter(subject__exam_period_id=filter_period)
    if filter_subject:
        keys = keys.filter(subject_id=filter_subject)

    periods = ExamPeriod.objects.prefetch_related('subjects').all().order_by('name')

    context = {
        'keys': keys,
        'periods': periods,
        'filter_period': filter_period,
        'filter_subject': filter_subject,
        'active_tab': 'keys',
    }
    return render(request, 'quiz/grading/key_list.html', context)


@manager_required
def grading_key_form(request, key_id=None):
    """Trang tạo mới hoặc chỉnh sửa Bộ đáp án chuẩn (SingleChoose, TrueFalse, Numeric)"""
    key_obj = None
    questions = []
    target_subject_id = request.GET.get('subject_id')

    if key_id:
        key_obj = get_object_or_404(GradingExamKey, id=key_id)
        questions = key_obj.questions.order_by('question_number').all()

    sub_id = int(target_subject_id) if target_subject_id and target_subject_id.isdigit() else (key_obj.subject_id if key_obj else None)
    selected_subject = Subject.objects.filter(id=sub_id).select_related('exam_period').first() if sub_id else None

    periods = ExamPeriod.objects.prefetch_related('subjects').all().order_by('name')

    subjects_config = {}
    for p in periods:
        for s in p.subjects.all():
            subjects_config[s.id] = {
                'num_single': s.num_single,
                'num_tf': s.num_tf,
                'num_numeric': s.num_numeric,
                'max_score_single': s.max_score_single,
                'max_score_numeric': s.max_score_numeric,
                'score_per_single': s.score_per_single,
                'score_per_numeric': s.score_per_numeric,
                'total_max_score': s.total_subject_max_score,
            }

    questions_json = []
    if questions:
        for q in questions:
            questions_json.append({
                'number': q.question_number,
                'type': q.question_type,
                'score_weight': q.score_weight,
                'correct_single': q.correct_single or 'A',
                'correct_tf': q.correct_tf or {'a': True, 'b': False, 'c': True, 'd': False},
                'correct_numeric': q.correct_numeric or '',
            })
    elif sub_id and sub_id in subjects_config:
        cfg = subjects_config[sub_id]
        q_idx = 1
        for i in range(cfg['num_single']):
            questions_json.append({
                'number': q_idx,
                'type': 'SINGLE',
                'score_weight': 0.25,
                'correct_single': ['A', 'B', 'C', 'D'][(q_idx - 1) % 4],
                'correct_tf': {'a': True, 'b': False, 'c': True, 'd': False},
                'correct_numeric': '',
            })
            q_idx += 1
        for i in range(cfg['num_tf']):
            questions_json.append({
                'number': q_idx,
                'type': 'TF',
                'score_weight': 1.0,
                'correct_single': 'A',
                'correct_tf': {'a': True, 'b': False, 'c': True, 'd': False},
                'correct_numeric': '',
            })
            q_idx += 1
        for i in range(cfg['num_numeric']):
            questions_json.append({
                'number': q_idx,
                'type': 'NUMERIC',
                'score_weight': 0.5,
                'correct_single': 'A',
                'correct_tf': {'a': True, 'b': False, 'c': True, 'd': False},
                'correct_numeric': '1.25',
            })
            q_idx += 1

    context = {
        'key_obj': key_obj,
        'selected_subject': selected_subject,
        'questions_json': json.dumps(questions_json),
        'subjects_config_json': json.dumps(subjects_config),
        'target_subject_id': sub_id,
        'periods': periods,
        'active_tab': 'keys',
    }
    return render(request, 'quiz/grading/key_form.html', context)



@manager_required
def api_save_grading_key(request):
    """API Lưu bộ đáp án chuẩn với điểm đồng nhất theo từng loại câu hỏi"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Dữ liệu JSON không hợp lệ: {str(e)}'}, status=400)

    key_id = data.get('key_id')
    subject_id = data.get('subject_id')
    code = str(data.get('code', '')).strip().upper()
    title = str(data.get('title', '')).strip()
    description = str(data.get('description', '')).strip()
    score_single = float(data.get('score_single', 0.25))
    score_numeric = float(data.get('score_numeric', 0.5))
    questions_data = data.get('questions', [])

    if not subject_id or not code:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn Môn thi và nhập Mã đề.'}, status=400)

    if not questions_data:
        return JsonResponse({'status': 'error', 'message': 'Bộ đáp án phải có ít nhất 1 câu hỏi.'}, status=400)

    subject = get_object_or_404(Subject, id=subject_id)

    check_dup = GradingExamKey.objects.filter(subject=subject, code=code)
    if key_id:
        check_dup = check_dup.exclude(id=key_id)
    if check_dup.exists():
        return JsonResponse({'status': 'error', 'message': f'Mã đề "{code}" đã tồn tại trong môn {subject.name}.'}, status=400)

    with transaction.atomic():
        if key_id:
            key_obj = get_object_or_404(GradingExamKey, id=key_id)
            key_obj.subject = subject
            key_obj.code = code
            key_obj.title = title
            key_obj.description = description
            key_obj.score_single = score_single
            key_obj.score_numeric = score_numeric
            key_obj.save()
            key_obj.questions.all().delete()
        else:
            key_obj = GradingExamKey.objects.create(
                subject=subject,
                code=code,
                title=title,
                description=description,
                score_single=score_single,
                score_numeric=score_numeric,
                created_by=request.user
            )

        new_questions = []
        for idx, q_item in enumerate(questions_data, start=1):
            q_type = q_item.get('type', 'SINGLE')
            correct_single = q_item.get('correct_single', 'A')
            correct_tf = q_item.get('correct_tf', {'a': True, 'b': False, 'c': True, 'd': False})
            correct_numeric = str(q_item.get('correct_numeric', '')).strip()[:4]

            # Điểm số đồng nhất theo loại câu hỏi!
            if q_type == 'SINGLE':
                score_w = score_single
            elif q_type == 'NUMERIC':
                score_w = score_numeric
            else:
                score_w = 1.0  # TF cố định 1.0đ

            new_questions.append(
                GradingKeyQuestion(
                    key=key_obj,
                    question_number=idx,
                    question_type=q_type,
                    score_weight=score_w,
                    correct_single=correct_single,
                    correct_tf=correct_tf,
                    correct_numeric=correct_numeric,
                )
            )
        GradingKeyQuestion.objects.bulk_create(new_questions)

    redirect_url = f"/cham-trac-nghiem/mon-thi/{subject.id}/?tab=keys"
    return JsonResponse({
        'status': 'success',
        'message': f'Đã lưu thành công Bộ đáp án mã đề {key_obj.code} ({len(new_questions)} câu)!',
        'key_id': key_obj.id,
        'subject_id': subject.id,
        'redirect_url': redirect_url,
    })


@manager_required
def api_delete_grading_key(request, key_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)
    key_obj = get_object_or_404(GradingExamKey, id=key_id)
    code = key_obj.code
    key_obj.delete()
    return JsonResponse({'status': 'success', 'message': f'Đã xóa bộ đáp án mã đề "{code}".'})


@manager_required
def api_batch_delete_grading_keys(request):
    """API Xóa hàng loạt mã đề hoặc xóa tất cả mã đề của môn thi"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    key_ids = request.POST.getlist('key_ids')
    subject_id = request.POST.get('subject_id')
    delete_all = request.POST.get('delete_all') == '1'

    if delete_all and subject_id:
        subject = get_object_or_404(Subject, id=subject_id)
        count = subject.grading_keys.count()
        subject.grading_keys.all().delete()
        return JsonResponse({'status': 'success', 'message': f'Đã xóa toàn bộ {count} mã đề của môn "{subject.name}".'})

    if not key_ids:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn ít nhất một mã đề để xóa.'}, status=400)

    deleted_count, _ = GradingExamKey.objects.filter(id__in=key_ids).delete()
    return JsonResponse({'status': 'success', 'message': f'Đã xóa {len(key_ids)} mã đề thành công.'})


@manager_required
def api_get_exam_key_questions(request, key_id):
    key_obj = get_object_or_404(GradingExamKey.objects.select_related('subject__exam_period').prefetch_related('subject__assigned_classes'), id=key_id)
    questions = key_obj.questions.order_by('question_number').all()

    assigned_classes = list(key_obj.subject.assigned_classes.all())
    assigned_class_ids = [c.id for c in assigned_classes]
    assigned_class_names = [c.name for c in assigned_classes]

    q_list = []
    for q in questions:
        q_list.append({
            'number': q.question_number,
            'type': q.question_type,
            'score_weight': q.score_weight,
            'correct_single': q.correct_single or 'A',
            'correct_tf': q.correct_tf or {'a': True, 'b': False, 'c': True, 'd': False},
            'correct_numeric': q.correct_numeric or '',
            'selected': q.selected,
            'seleted': q.selected,
        })

    return JsonResponse({
        'status': 'success',
        'key': {
            'id': key_obj.id,
            'code': key_obj.code,
            'title': key_obj.title or f"Mã đề {key_obj.code}",
            'subject_id': key_obj.subject.id,
            'subject_name': key_obj.subject.name,
            'period_name': key_obj.subject.exam_period.name,
            'total_questions': len(q_list),
            'max_score': key_obj.max_possible_score,
            'score_single': key_obj.score_single,
            'score_numeric': key_obj.score_numeric,
            'score_per_single': key_obj.subject.score_per_single,
            'score_per_tf': key_obj.subject.score_per_tf,
            'score_per_numeric': key_obj.subject.score_per_numeric,
            'assigned_class_ids': assigned_class_ids,
            'assigned_class_names': assigned_class_names,
        },
        'questions': q_list,
    })


@manager_required
def download_sample_key_excel(request):
    """Tải file Excel mẫu đáp án cho NHIỀU MÃ ĐỀ TRONG CÙNG 1 SHEET (Mỗi mã đề 1 cột)"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dap_An_Cac_Ma_De"

    # Header Row: Cột 1 = STT / Loại câu, Cột 2 = 101, Cột 3 = 102, Cột 4 = 103...
    headers = ["Câu / Loại", "101", "102", "103", "104"]
    ws.append(headers)

    # 24 câu SingleChoose (A, B, C, D)
    for i in range(1, 25):
        row = [f"Câu {i} (Single)", "A" if i % 4 == 1 else ("B" if i % 4 == 2 else ("C" if i % 4 == 3 else "D")),
               "B" if i % 4 == 1 else ("C" if i % 4 == 2 else ("D" if i % 4 == 3 else "A")),
               "C" if i % 4 == 1 else ("D" if i % 4 == 2 else ("A" if i % 4 == 3 else "B")),
               "D" if i % 4 == 1 else ("A" if i % 4 == 2 else ("B" if i % 4 == 3 else "C"))]
        ws.append(row)

    # 4 câu TrueFalse (Đ,S,Đ,Đ)
    for i in range(25, 29):
        row = [f"Câu {i} (TrueFalse)", "Đ,S,Đ,Đ", "S,Đ,S,Đ", "Đ,Đ,S,S", "S,S,Đ,Đ"]
        ws.append(row)

    # 6 câu Numeric (1.25, -3.5...)
    sample_nums = ["1.25", "-3.5", "12.5", "1000", "0.25", "-0.5"]
    for idx, i in enumerate(range(29, 35)):
        row = [f"Câu {i} (Số thực)", sample_nums[idx % 6], sample_nums[(idx + 1) % 6], sample_nums[(idx + 2) % 6], sample_nums[(idx + 3) % 6]]
        ws.append(row)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="Mau_Dap_An_Nhieu_Ma_De.xlsx"'
    wb.save(response)
    return response


@manager_required
def api_import_keys_excel(request):
    """API Nhập đáp án từ file Excel chứa NHIỀU MÃ ĐỀ TRONG CÙNG 1 SHEET"""
    if request.method != 'POST' or 'excel_file' not in request.FILES:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng tải lên file Excel đáp án.'}, status=400)

    subject_id = request.POST.get('subject_id')
    if not subject_id:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn Môn thi cần nhập đáp án.'}, status=400)

    subject = get_object_or_404(Subject, id=subject_id)
    score_single = float(request.POST.get('score_single', subject.score_per_single))
    score_numeric = float(request.POST.get('score_numeric', subject.score_per_numeric))
    excel_file = request.FILES['excel_file']

    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
        ws = wb.active
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Không thể đọc file Excel: {str(e)}'}, status=400)

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return JsonResponse({'status': 'error', 'message': 'File Excel phải chứa dòng Tiêu đề (Mã đề) và ít nhất 1 câu hỏi.'}, status=400)

    header = [str(cell or '').strip() for cell in rows[0]]
    if len(header) < 2:
        return JsonResponse({'status': 'error', 'message': 'Cột B trở đi phải chứa các Mã đề (VD: 101, 102...).'}, status=400)

    # Xác định danh sách Mã đề từ các cột
    codes_map = {} # col_idx -> code
    for col_idx in range(1, len(header)):
        code = header[col_idx].upper()
        if code:
            codes_map[col_idx] = code

    if not codes_map:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy Mã đề thi nào ở dòng 1.'}, status=400)

    imported_keys = []
    with transaction.atomic():
        for col_idx, code in codes_map.items():
            # Validate question counts per section against subject config
            count_single = 0
            count_tf = 0
            count_numeric = 0
            parsed_questions = []

            for row_idx, row in enumerate(rows[1:], start=1):
                if not row or not any(row):
                    continue

                cell_val = str(row[col_idx] or '').strip() if col_idx < len(row) else ''
                q_label = str(row[0] or '').strip()

                # Nhận diện loại câu hỏi
                q_type = 'SINGLE'
                if 'TF' in q_label.upper() or 'ĐÚNG' in q_label.upper() or ',' in cell_val or (len(cell_val) == 4 and cell_val.replace('Đ','').replace('S','').replace('T','').replace('F','') == ''):
                    q_type = 'TF'
                elif 'SỐ' in q_label.upper() or 'NUMERIC' in q_label.upper() or (re.match(r'^-?\d+(\.\d+)?$', cell_val.replace(',', '.')) and len(cell_val) <= 4 and cell_val not in ['A','B','C','D']):
                    q_type = 'NUMERIC'

                if q_type == 'SINGLE':
                    count_single += 1
                elif q_type == 'TF':
                    count_tf += 1
                elif q_type == 'NUMERIC':
                    count_numeric += 1

                parsed_questions.append((q_type, cell_val))

            # Kiểm tra ràng buộc cấu hình môn thi
            if subject.num_single != count_single or subject.num_tf != count_tf or subject.num_numeric != count_numeric:
                transaction.set_rollback(True)
                return JsonResponse({
                    'status': 'error',
                    'message': f'File Excel của Mã đề "{code}" không khớp cấu hình môn {subject.name}!\n'
                               f'• Cấu hình môn thi: {subject.num_single} SingleChoose + {subject.num_tf} Đúng/Sai + {subject.num_numeric} Điền số.\n'
                               f'• File Excel nhận diện: {count_single} SingleChoose + {count_tf} Đúng/Sai + {count_numeric} Điền số.\n'
                               f'Vui lòng kiểm tra lại file Excel đúng số lượng câu hỏi.'
                }, status=400)

            key_obj, _ = GradingExamKey.objects.get_or_create(
                subject=subject,
                code=code,
                defaults={'title': f'Mã đề {code}', 'score_single': score_single, 'score_numeric': score_numeric, 'created_by': request.user}
            )
            key_obj.score_single = score_single
            key_obj.score_numeric = score_numeric
            key_obj.save()
            key_obj.questions.all().delete()

            new_questions = []
            for row_idx, (q_type, cell_val) in enumerate(parsed_questions, start=1):
                score_w = score_single if q_type == 'SINGLE' else (score_numeric if q_type == 'NUMERIC' else 1.0)

                correct_single = 'A'
                correct_tf = {'a': True, 'b': False, 'c': True, 'd': True}
                correct_numeric = ''

                if q_type == 'SINGLE':
                    correct_single = cell_val.upper() if cell_val.upper() in ['A', 'B', 'C', 'D'] else 'A'
                elif q_type == 'TF':
                    parts = [p.strip().upper() for p in cell_val.replace(';', ',').split(',')]
                    tf_dict = {}
                    for sub_idx, sub in enumerate(['a', 'b', 'c', 'd']):
                        if sub_idx < len(parts):
                            tf_dict[sub] = parts[sub_idx] in ['Đ', 'D', 'T', 'TRUE', '1']
                        else:
                            tf_dict[sub] = True
                    correct_tf = tf_dict
                elif q_type == 'NUMERIC':
                    correct_numeric = cell_val[:4]

                new_questions.append(
                    GradingKeyQuestion(
                        key=key_obj,
                        question_number=row_idx,
                        question_type=q_type,
                        score_weight=score_w,
                        correct_single=correct_single,
                        correct_tf=correct_tf,
                        correct_numeric=correct_numeric
                    )
                )
            GradingKeyQuestion.objects.bulk_create(new_questions)
            imported_keys.append(code)

    return JsonResponse({
        'status': 'success',
        'message': f'Nhập Excel thành công! Đã cập nhật đáp án cho {len(imported_keys)} Mã đề: {", ".join(imported_keys)}.',
    })


@manager_required
def matrix_grid_view(request, subject_id=None):
    """Giao diện Lưới Ma Trận trực quan chỉnh sửa đáp án cho tất cả mã đề của môn thi cùng lúc"""
    subjects = Subject.objects.select_related('exam_period').prefetch_related('grading_keys__questions').all()

    selected_subject = None
    if subject_id:
        selected_subject = get_object_or_404(Subject, id=subject_id)
    elif subjects.exists():
        selected_subject = subjects.first()

    keys = []
    matrix_data = []
    if selected_subject:
        keys = list(selected_subject.grading_keys.prefetch_related('questions').order_by('code'))
        max_q = 0
        for k in keys:
            max_q = max(max_q, k.questions.count())

        for q_num in range(1, max_q + 1):
            row_item = {'number': q_num, 'codes': {}}
            for k in keys:
                q_obj = k.questions.filter(question_number=q_num).first()
                if q_obj:
                    row_item['codes'][k.code] = {
                        'type': q_obj.question_type,
                        'single': q_obj.correct_single,
                        'tf': q_obj.correct_tf,
                        'numeric': q_obj.correct_numeric,
                    }
                else:
                    row_item['codes'][k.code] = None
            matrix_data.append(row_item)

    context = {
        'subjects': subjects,
        'selected_subject': selected_subject,
        'keys': keys,
        'matrix_data': matrix_data,
        'active_tab': 'keys',
    }
    return render(request, 'quiz/grading/matrix_grid.html', context)


# =====================================================================
# 5. GIAO DIỆN CHẤM BÀI TRẮC NGHIỆM & XỬ LÝ ẢNH JPG/TIFF (DPI 150)
# =====================================================================

@manager_required
def grading_sheet_view(request):
    """Giao diện phiếu chấm bài trắc nghiệm điện tử tương tác hỗ trợ upload ảnh JPG/TIFF"""
    periods = ExamPeriod.objects.prefetch_related('subjects__grading_keys', 'subjects__assigned_classes').all().order_by('name')
    subject_id = request.GET.get('subject_id', '')
    selected_key_id = request.GET.get('key_id', '')

    selected_subject = None
    subject_keys = []
    if subject_id and subject_id.isdigit():
        selected_subject = Subject.objects.filter(id=int(subject_id)).prefetch_related('assigned_classes').first()
        if selected_subject:
            subject_keys = list(selected_subject.grading_keys.order_by('code').all())
    elif selected_key_id and selected_key_id.isdigit():
        key_obj = GradingExamKey.objects.filter(id=int(selected_key_id)).select_related('subject').first()
        if key_obj and key_obj.subject:
            selected_subject = Subject.objects.filter(id=key_obj.subject_id).prefetch_related('assigned_classes').first()
            if selected_subject:
                subject_keys = list(selected_subject.grading_keys.order_by('code').all())

    classes = StudentClass.objects.all().order_by('grade', 'name')
    assigned_class_ids = set(selected_subject.assigned_classes.values_list('id', flat=True)) if selected_subject else set()

    context = {
        'periods': periods,
        'selected_subject': selected_subject,
        'subject_keys': subject_keys,
        'selected_key_id': str(selected_key_id) if selected_key_id else '',
        'classes': classes,
        'assigned_class_ids': assigned_class_ids,
        'active_tab': 'grading',
    }
    return render(request, 'quiz/grading/scoring_sheet.html', context)



@manager_required
def api_grade_submission(request):
    """API Nhận bài làm thí sinh, đối chiếu đáp án, tính điểm và lưu kết quả"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Dữ liệu JSON không hợp lệ: {str(e)}'}, status=400)

    key_id = data.get('key_id')
    student_id = str(data.get('student_id', '')).strip()
    student_name = str(data.get('student_name', '')).strip()
    student_class = str(data.get('student_class', '')).strip()
    student_answers = data.get('answers', {})
    force_zero = data.get('force_zero', False)

    if not key_id and not force_zero:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn Mã đề thi cần chấm.'}, status=400)
    if not student_id or not student_name:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập Số báo danh và Họ tên thí sinh.'}, status=400)

    key_obj = None
    questions = []
    if key_id:
        key_obj = get_object_or_404(GradingExamKey.objects.select_related('subject__exam_period'), id=key_id)
        questions = list(key_obj.questions.order_by('question_number').all())

    # Đồng bộ thông tin vào Master Student Roster nếu chưa có
    if student_id:
        cls_obj = None
        if student_class:
            cls_obj, _ = StudentClass.objects.get_or_create(name=student_class)
        st, created = Student.objects.get_or_create(
            student_id=student_id,
            defaults={'full_name': student_name, 'student_class': cls_obj}
        )
        if not created and student_name:
            st.full_name = student_name
            if cls_obj:
                st.student_class = cls_obj
            st.save()

    total_score, max_score, correct_count, details = calculate_score(questions, student_answers)
    
    # Nếu bị ép buộc lưu rỗng điểm do không có mã đề hợp lệ
    if force_zero:
        total_score = 0.0
        correct_count = 0
        exam_code = ''
        for d in details:
            d['is_correct'] = False
            d['earned_score'] = 0.0
    else:
        exam_code = key_obj.code

    record = GradingRecord.objects.create(
        key=key_obj,
        student_id=student_id,
        student_name=student_name,
        student_class=student_class,
        exam_code=exam_code,
        total_score=total_score,
        max_score=max_score,
        correct_count=correct_count,
        student_answers=student_answers,
        grading_details=details,
        graded_by=request.user,
    )

    # Lưu ảnh phiếu thi có vẽ nhận diện OMR nếu có
    annotated_b64 = data.get('annotated_image') or data.get('annotated_image_b64')
    if annotated_b64 and isinstance(annotated_b64, str):
        try:
            if 'base64,' in annotated_b64:
                _, img_data_str = annotated_b64.split('base64,', 1)
            else:
                img_data_str = annotated_b64
            img_bytes = base64.b64decode(img_data_str)
            fn = f"annotated_{record.id}_{uuid.uuid4().hex[:8]}.jpg"
            record.annotated_image.save(fn, ContentFile(img_bytes), save=True)
        except Exception as e:
            print(f"Error saving annotated_image for record {record.id}: {e}")

    # Lưu ảnh phiếu thi gốc nếu có
    original_b64 = data.get('original_image') or data.get('original_image_b64')
    if original_b64 and isinstance(original_b64, str):
        try:
            if 'base64,' in original_b64:
                _, orig_data_str = original_b64.split('base64,', 1)
            else:
                orig_data_str = original_b64
            orig_bytes = base64.b64decode(orig_data_str)
            fn_orig = f"original_{record.id}_{uuid.uuid4().hex[:8]}.jpg"
            record.original_image.save(fn_orig, ContentFile(orig_bytes), save=True)
        except Exception as e:
            print(f"Error saving original_image for record {record.id}: {e}")

    percent = (total_score / max_score * 100) if max_score > 0 else 0
    if percent >= 85:
        rank, badge = "Xuất sắc", "success"
    elif percent >= 70:
        rank, badge = "Khá", "primary"
    elif percent >= 50:
        rank, badge = "Trung bình", "warning"
    else:
        rank, badge = "Chưa đạt", "danger"

    return JsonResponse({
        'status': 'success',
        'message': f'Chấm thành công bài thi của thí sinh {student_name} (SBD: {student_id})!',
        'record_id': record.id,
        'total_score': total_score,
        'max_score': max_score,
        'correct_count': correct_count,
        'total_questions': len(questions),
        'percent': round(percent, 1),
        'rank': rank,
        'badge': badge,
        'student': {
            'id': student_id,
            'name': student_name,
            'class': student_class,
            'exam_code': key_obj.code if key_obj else '',
            'subject_name': key_obj.subject.name if key_obj else '',
            'period_name': key_obj.subject.exam_period.name if key_obj else '',
        },
        'details': details,
    })


def score_to_vietnamese_words(score):
    """
    Chuyển đổi điểm số sang chữ Tiếng Việt chuẩn Bộ GD&ĐT:
    Ví dụ: 8.5 -> Tám phẩy năm điểm, 10 -> Mười điểm, 0 -> Không điểm
    """
    try:
        score = float(score)
    except (ValueError, TypeError):
        return "Không điểm"

    score = round(score, 2)
    if score <= 0:
        return "Không điểm"

    digits = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười"]

    int_part = int(score)
    dec_part = int(round((score - int_part) * 100))

    int_str = digits[int_part] if 0 <= int_part <= 10 else str(int_part)
    int_str = int_str.capitalize()

    if dec_part == 0:
        return f"{int_str} điểm"

    if dec_part % 10 == 0:
        d = dec_part // 10
        dec_str = "năm" if d == 5 else digits[d]
        return f"{int_str} phẩy {dec_str} điểm"

    tens = dec_part // 10
    units = dec_part % 10
    tens_words = {
        1: "mười", 2: "hai mươi", 3: "ba mươi", 4: "bốn mươi", 5: "năm mươi",
        6: "sáu mươi", 7: "bảy mươi", 8: "tám mươi", 9: "chín mươi"
    }
    unit_word = digits[units]
    if units == 5:
        unit_word = "lăm"
    elif units == 1 and tens > 1:
        unit_word = "mốt"

    t_str = tens_words.get(tens, digits[tens])
    if units == 0:
        return f"{int_str} phẩy {t_str} điểm"
    else:
        return f"{int_str} phẩy {t_str} {unit_word} điểm"


def get_vietnamese_font(size=16):
    """Tìm font TrueType hỗ trợ tiếng Việt trên hệ thống"""
    import os
    from PIL import ImageFont
    font_candidates = [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/SFCompact.ttf',
        '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        'arial.ttf',
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_score_badge(img_bgr, score, score_text, ox, oy, is_matched=True, sbd="", exam_code=""):
    """
    Vẽ khung ghi điểm tại toạ độ chỉ định (120, 340) bằng số và chữ Tiếng Việt:
    - SBD & Mã đề (sau điều chỉnh hoặc nhận diện)
    - Số: Điểm: X.XX điểm
    - Chữ: Bằng chữ: [Điểm bằng chữ]
    """
    from PIL import ImageDraw
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    font_header = get_vietnamese_font(12)
    font_title = get_vietnamese_font(18)
    font_sub = get_vietnamese_font(13)

    header_line = f"SBD: {sbd or '---'} | Đề: {exam_code or '---'}"
    if is_matched:
        line1 = f"Điểm: {score:.2f} điểm"
        line2 = f"Bằng chữ: {score_text}"
        border_color = (22, 163, 74)   # Green
        title_color = (185, 28, 28)    # Dark red
        bg_color = (255, 255, 240)     # Warm light
    else:
        line1 = f"Điểm: 0.0 (Mã đề {exam_code or '---'} không khớp)"
        line2 = "Bằng chữ: Không điểm"
        border_color = (220, 38, 38)   # Red
        title_color = (220, 38, 38)
        bg_color = (254, 242, 242)

    bbox_h = draw.textbbox((0, 0), header_line, font=font_header)
    bbox1 = draw.textbbox((0, 0), line1, font=font_title)
    bbox2 = draw.textbbox((0, 0), line2, font=font_sub)

    wh, hh = bbox_h[2] - bbox_h[0], bbox_h[3] - bbox_h[1]
    w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
    w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]

    box_w = max(wh, w1, w2) + 24
    box_h = hh + h1 + h2 + 24

    rect_coords = [ox - 6, oy - 6, ox + box_w, oy + box_h]
    draw.rectangle(rect_coords, fill=bg_color, outline=border_color, width=2)
    draw.text((ox + 6, oy), header_line, font=font_header, fill=(71, 85, 105))
    draw.text((ox + 6, oy + hh + 4), line1, font=font_title, fill=title_color)
    draw.text((ox + 6, oy + hh + h1 + 8), line2, font=font_sub, fill=(30, 41, 59))

    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def detect_omr_sheet(img_input, num_single=24, num_tf=4, num_numeric=6):
    """
    Trích xuất OMR bài làm thí sinh từ ảnh phiếu chuẩn Bộ GD&ĐT:
    - Tìm 4 điểm neo màu đen đặc ở 4 góc và perspective transform
    - Trích xuất SBD (Box 7) & Mã đề (Box 8)
    - Trích xuất Phần I, Phần II, Phần III
    - Trả về dữ liệu OMR và metadata toạ độ
    """
    if len(img_input.shape) == 3:
        img_bgr = img_input.copy()
        gray = cv2.cvtColor(img_input, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_input
        img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # 1. Perspective Transform canh chỉnh khung bằng 4 điểm neo màu đen ở 4 góc phiếu
    _, thresh_orig = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh_orig, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidate_pts = []
    candidate_boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        aspect = float(w) / h
        area = cv2.contourArea(c)
        if 0.65 <= aspect <= 1.35 and 80 <= area <= 2500:
            M_c = cv2.moments(c)
            if M_c['m00'] != 0:
                cx = float(M_c['m10'] / M_c['m00'])
                cy = float(M_c['m01'] / M_c['m00'])
                candidate_pts.append((cx, cy))
                candidate_boxes.append((x, y, w, h, cx, cy))

    corner_indices = []
    M_inv = None
    if len(candidate_pts) >= 4:
        pts = np.array(candidate_pts, dtype='float32')
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)

        idx_tl = np.argmin(s)
        idx_br = np.argmax(s)
        idx_tr = np.argmin(diff)
        idx_bl = np.argmax(diff)
        corner_indices = [idx_tl, idx_tr, idx_br, idx_bl]

        tl = candidate_pts[idx_tl]
        br = candidate_pts[idx_br]
        tr = candidate_pts[idx_tr]
        bl = candidate_pts[idx_bl]

        src_pts = np.array([tl, tr, br, bl], dtype='float32')
        dst_pts = np.array([[30, 30], [970, 30], [970, 1370], [30, 1370]], dtype='float32')

        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        _, M_inv = cv2.invert(M)
        warped_gray = cv2.warpPerspective(gray, M, (1000, 1400))
    else:
        warped_gray = cv2.resize(gray, (1000, 1400), interpolation=cv2.INTER_AREA)

    detected_sbd = ""
    detected_code = ""
    detected_answers = {}

    sbd_marks = []
    code_marks = []
    part1_marks = {}
    part2_marks = {}
    part3_marks = {}

    y_rows = [int(130.7 + d * 28.8) for d in range(10)]

    # 2. TRÍCH XUẤT SBD & MÃ ĐỀ
    try:
        sbd_x_list = [688.8, 708.8, 728.8, 748.8, 768.8, 795.3, 811.8, 831.9]
        sbd_chars = []
        for col_idx, cx in enumerate(sbd_x_list):
            row_means = []
            for d in range(10):
                cy = y_rows[d]
                cell = warped_gray[cy-7:cy+7, int(cx)-7:int(cx)+7]
                row_means.append(cell.mean())

            avg_col_g = float(np.mean(row_means))
            marked_digits = []
            for d in range(10):
                cy = y_rows[d]
                if (avg_col_g - row_means[d]) > 20:
                    marked_digits.append(d)
                    sbd_marks.append((cx, cy))

            if len(marked_digits) == 0:
                sbd_chars.append("-")
            elif len(marked_digits) == 1:
                sbd_chars.append(str(marked_digits[0]))
            else:
                sbd_chars.append("*")
        detected_sbd = "".join(sbd_chars)
    except Exception:
        pass

    try:
        code_x_list = [881.5, 905.0, 924.0, 946.0]
        code_chars = []
        for col_idx, cx in enumerate(code_x_list):
            row_means = []
            for d in range(10):
                cy = y_rows[d]
                cell = warped_gray[cy-7:cy+7, int(cx)-7:int(cx)+7]
                row_means.append(cell.mean())

            avg_col_g = float(np.mean(row_means))
            marked_digits = []
            for d in range(10):
                cy = y_rows[d]
                if (avg_col_g - row_means[d]) > 20:
                    marked_digits.append(d)
                    code_marks.append((cx, cy))

            if len(marked_digits) == 0:
                code_chars.append("-")
            elif len(marked_digits) == 1:
                code_chars.append(str(marked_digits[0]))
            else:
                code_chars.append("*")
        detected_code = "".join(code_chars)
    except Exception:
        pass

    # 3. TRÍCH XUẤT PHẦN I (SINGLE CHOOSE)
    opts = ['A', 'B', 'C', 'D']
    col_a_x = [113.9, 335.5, 557.0, 778.5]
    opt_step_x = 43.5
    q1_y = 527.4
    q_row_step_y = 22.1

    part1_answers = {}
    part2_answers = {}
    part3_answers = {}

    for q_idx in range(1, num_single + 1):
        col_no = (q_idx - 1) // 10
        row_no = (q_idx - 1) % 10
        if col_no < len(col_a_x):
            xa = col_a_x[col_no]
            qy = int(q1_y + row_no * q_row_step_y)

            opt_means = []
            for o_idx in range(4):
                ox = int(xa + o_idx * opt_step_x)
                cell = warped_gray[qy-7:qy+7, ox-7:ox+7]
                opt_means.append(cell.mean())

            avg_g = float(np.mean(opt_means))
            marked_opts = []
            for o_idx, opt in enumerate(opts):
                ox = int(xa + o_idx * opt_step_x)
                if (avg_g - opt_means[o_idx]) > 25:
                    marked_opts.append(opt)
                    part1_marks.setdefault(q_idx, []).append((opt, ox, qy))

            if len(marked_opts) == 1:
                detected_answers[str(q_idx)] = marked_opts[0]
                part1_answers[q_idx] = marked_opts[0]
            elif len(marked_opts) > 1:
                val = "*".join(marked_opts)
                detected_answers[str(q_idx)] = val
                part1_answers[q_idx] = val

    # 4. TRÍCH XUẤT PHẦN II (TRUE FALSE)
    col_dung_x = [113.9, 203.5, 335.5, 423.1, 556.5, 644.0, 777.5, 864.0]
    col_sai_x  = [157.4, 246.5, 379.0, 467.0, 600.0, 687.5, 821.0, 907.5]
    row_tf_y   = [846.5, 868.5, 890.5, 912.5]
    sub_labels = ['a', 'b', 'c', 'd']

    tf_start_q = num_single + 1
    for i in range(min(num_tf, 8)):
        q_num = tf_start_q + i
        xd = int(round(col_dung_x[i]))
        xs = int(round(col_sai_x[i]))
        q_tf_data = {}
        for s_idx, sub in enumerate(sub_labels):
            qy = int(round(row_tf_y[s_idx]))
            cell_d = warped_gray[qy-7:qy+7, xd-7:xd+7]
            cell_s = warped_gray[qy-7:qy+7, xs-7:xs+7]
            mean_d = float(cell_d.mean())
            mean_s = float(cell_s.mean())

            marked_d = (mean_d < 140 and (mean_s - mean_d) > 30)
            marked_s = (mean_s < 140 and (mean_d - mean_s) > 30)

            if marked_d and not marked_s:
                q_tf_data[sub] = True
                part2_marks[(q_num, sub)] = (True, xd, qy)
            elif marked_s and not marked_d:
                q_tf_data[sub] = False
                part2_marks[(q_num, sub)] = (False, xs, qy)
            elif marked_d and marked_s:
                q_tf_data[sub] = "*"
                part2_marks[(q_num, sub)] = ("*", xd, qy)

        if q_tf_data:
            detected_answers[str(q_num)] = q_tf_data
            part2_answers[i + 1] = q_tf_data

    # 5. TRÍCH XUẤT PHẦN III (NUMERIC)
    num_start_q = num_single + num_tf + 1
    q_base_x = [106.7, 248.0, 389.0, 530.0, 671.5, 813.0]
    col_step_x = 30.5

    row_y_minus = 1041.5
    row_y_comma = 1063.8
    row_y_digits = [1087.5 + d * 22.58 for d in range(10)]

    for i in range(min(num_numeric, 6)):
        q_num = num_start_q + i
        parsed_chars = []
        for c_idx in range(4):
            cx = int(round(q_base_x[i] + c_idx * col_step_x))
            options = []
            if c_idx == 0:
                options.append(('-', row_y_minus))
            elif c_idx in [1, 2]:
                options.append((',', row_y_comma))
            for d in range(10):
                options.append((str(d), row_y_digits[d]))

            opt_means = []
            for label, ry in options:
                qy = int(round(ry))
                patch = warped_gray[qy-6:qy+6, cx-6:cx+6]
                opt_means.append((label, qy, float(patch.mean())))

            marked = [o for o in opt_means if o[2] < 140]
            if len(marked) == 1:
                val, my, _ = marked[0]
                parsed_chars.append(val)
                part3_marks.setdefault(q_num, []).append((val, cx, my))
            elif len(marked) > 1:
                parsed_chars.append('*')
                for val, my, _ in marked:
                    part3_marks.setdefault(q_num, []).append((val, cx, my))
            else:
                parsed_chars.append(' ')

        result_str = "".join(parsed_chars).strip()
        if result_str:
            detected_answers[str(q_num)] = result_str
            part3_answers[i + 1] = result_str

    raw_parts = {
        'part1': part1_answers,
        'part2': part2_answers,
        'part3': part3_answers,
    }
    detected_answers['_raw_parts'] = raw_parts

    extracted_marks = {
        'sbd_marks': sbd_marks,
        'code_marks': code_marks,
        'part1_marks': part1_marks,
        'part2_marks': part2_marks,
        'part3_marks': part3_marks,
    }

    return detected_sbd, detected_code, detected_answers, M_inv, candidate_boxes, corner_indices, extracted_marks


def draw_score_badge(img_bgr, score, score_text, ox, oy, is_matched=True, sbd="", exam_code="", has_errors=False, error_count=0):
    """
    Vẽ khung ghi điểm tại toạ độ chỉ định (120, 340) bằng số và chữ Tiếng Việt:
    - SBD & Mã đề (sau điều chỉnh hoặc nhận diện)
    - Số: Điểm: X.XX điểm (vẫn thông báo điểm các câu đúng ngay cả khi bài có lỗi)
    - Chữ: Bằng chữ: [Điểm bằng chữ]
    """
    from PIL import ImageDraw
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    font_header = get_vietnamese_font(12)
    font_title = get_vietnamese_font(18)
    font_sub = get_vietnamese_font(13)

    if is_matched:
        if has_errors:
            header_line = f"SBD: {sbd or '---'} | Đề: {exam_code or '---'} [CÓ {error_count} LỖI CẦN XEM]"
            line1 = f"Điểm câu đúng: {score:.2f} điểm"
            line2 = f"Bằng chữ: {score_text}"
            border_color = (234, 88, 12)   # Orange
            title_color = (194, 65, 12)
            bg_color = (255, 251, 235)
        else:
            header_line = f"SBD: {sbd or '---'} | Đề: {exam_code or '---'}"
            line1 = f"Điểm: {score:.2f} điểm"
            line2 = f"Bằng chữ: {score_text}"
            border_color = (22, 163, 74)   # Green
            title_color = (185, 28, 28)    # Dark red
            bg_color = (255, 255, 240)     # Warm light
    else:
        header_line = f"SBD: {sbd or '---'} | Đề: {exam_code or '---'} (Không khớp)"
        line1 = f"Điểm: 0.0 (Mã đề {exam_code or '---'} không khớp)"
        line2 = "Bằng chữ: Không điểm"
        border_color = (220, 38, 38)   # Red
        title_color = (220, 38, 38)
        bg_color = (254, 242, 242)

    bbox_h = draw.textbbox((0, 0), header_line, font=font_header)
    bbox1 = draw.textbbox((0, 0), line1, font=font_title)
    bbox2 = draw.textbbox((0, 0), line2, font=font_sub)

    wh, hh = bbox_h[2] - bbox_h[0], bbox_h[3] - bbox_h[1]
    w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
    w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]

    box_w = max(wh, w1, w2) + 24
    box_h = hh + h1 + h2 + 24

    rect_coords = [ox - 6, oy - 6, ox + box_w, oy + box_h]
    draw.rectangle(rect_coords, fill=bg_color, outline=border_color, width=2)
    draw.text((ox + 6, oy), header_line, font=font_header, fill=(71, 85, 105))
    draw.text((ox + 6, oy + hh + 4), line1, font=font_title, fill=title_color)
    draw.text((ox + 6, oy + hh + h1 + 8), line2, font=font_sub, fill=(30, 41, 59))

    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def render_annotated_sheet(img_bgr, M_inv, candidate_boxes, corner_indices,
                           detected_sbd, detected_code, detected_answers,
                           key_questions=None, is_matched=True, score=0.0, score_text="",
                           details=None, num_single=24, num_tf=4, num_numeric=6, extracted_marks=None,
                           has_errors=False, error_count=0):
    """
    Vẽ ảnh xem trước phiếu thi đã chấm điểm và tô màu theo chuẩn:
    - 4 góc neo định vị phiếu: Màu xanh lá (thickness 3)
    - Toạ độ 120x340: Ghi điểm bằng số và chữ Tiếng Việt
    - Câu đúng: Vẽ màu Xanh Lá
    - Câu sai / Ý sai / Cột sai:
      + Vẽ 1 hình chữ nhật bọc lấy câu tô sai hoặc ý sai, cột sai
      + Đáp án của đề: Vẽ màu Xanh Lam
      + Phương án chọn sai của thí sinh: Vẽ màu Đỏ
    - Nếu không khớp mã đề (is_matched=False): Ghi 0 điểm, vẽ các ô thí sinh tô bằng màu Đỏ
    """
    annotated = img_bgr.copy()

    # BGR Color palette
    COLOR_CORRECT = (0, 185, 0)      # Xanh lá
    COLOR_KEY = (235, 120, 25)       # Xanh lam
    COLOR_WRONG = (0, 0, 240)        # Đỏ
    COLOR_INFO = (255, 144, 30)      # Xanh ngọc / Lam nhạt

    # 1. Vẽ 4 góc định vị
    if candidate_boxes and corner_indices:
        labels = ['1. Goc Tren-Trai', '2. Goc Tren-Phai', '3. Goc Duoi-Phai', '4. Goc Duoi-Trai']
        for i, idx in enumerate(corner_indices):
            if idx < len(candidate_boxes):
                x, y, w, h, cx, cy = candidate_boxes[idx]
                cv2.rectangle(annotated, (x - 4, y - 4), (x + w + 4, y + h + 4), (0, 255, 0), 3)
                cv2.circle(annotated, (int(cx), int(cy)), 3, (0, 0, 255), -1)
                cv2.putText(annotated, labels[i], (x - 10, max(y - 8, 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

    def draw_circle(wx, wy, color, radius=11, thickness=3):
        if M_inv is not None:
            pt_arr = np.array([[[wx, wy]]], dtype='float32')
            out = cv2.perspectiveTransform(pt_arr, M_inv)
            ox, oy = int(out[0][0][0]), int(out[0][0][1])
            cv2.circle(annotated, (ox, oy), radius, color, thickness)
        else:
            cv2.circle(annotated, (int(wx), int(wy)), radius, color, thickness)

    # Hàm vẽ hình chữ nhật bọc lấy câu sai, ý sai, cột sai theo phép biến đổi phối cảnh OMR
    def draw_rect_box(wx1, wy1, wx2, wy2, color=COLOR_WRONG, thickness=2):
        if M_inv is not None:
            pts = np.array([[[wx1, wy1]], [[wx2, wy1]], [[wx2, wy2]], [[wx1, wy2]]], dtype='float32')
            out = cv2.perspectiveTransform(pts, M_inv)
            pts_int = np.int32(out)
            cv2.polylines(annotated, [pts_int], isClosed=True, color=color, thickness=thickness)
        else:
            cv2.rectangle(annotated, (int(wx1), int(wy1)), (int(wx2), int(wy2)), color, thickness)

    marks = extracted_marks or {}
    sbd_marks = marks.get('sbd_marks', [])
    code_marks = marks.get('code_marks', [])
    part1_marks = marks.get('part1_marks', {})
    part2_marks = marks.get('part2_marks', {})
    part3_marks = marks.get('part3_marks', {})

    # 2. Vẽ SBD & Mã đề
    for cx, cy in sbd_marks:
        draw_circle(cx, cy, COLOR_INFO, radius=10, thickness=2)

    code_color = COLOR_CORRECT if is_matched else COLOR_WRONG
    for cx, cy in code_marks:
        draw_circle(cx, cy, code_color, radius=10, thickness=3)

    if not is_matched:
        # Khoanh đỏ ô mã đề nếu không khớp
        draw_rect_box(870, 115, 960, 400, COLOR_WRONG, thickness=3)

    # 3. Vẽ Phần I, II, III theo kết quả so khớp
    opts = ['A', 'B', 'C', 'D']
    col_a_x = [113.9, 335.5, 557.0, 778.5]
    opt_step_x = 43.5
    q1_y = 527.4
    q_row_step_y = 22.1

    col_dung_x = [113.9, 203.5, 335.5, 423.1, 556.5, 644.0, 777.5, 864.0]
    col_sai_x  = [157.4, 246.5, 379.0, 467.0, 600.0, 687.5, 821.0, 907.5]
    row_tf_y   = [846.5, 868.5, 890.5, 912.5]
    sub_labels = ['a', 'b', 'c', 'd']

    if is_matched and details:
        detail_map = {d['number']: d for d in details}

        # PHẦN I: Trắc nghiệm đơn
        for q_idx in range(1, num_single + 1):
            col_no = (q_idx - 1) // 10
            row_no = (q_idx - 1) % 10
            if col_no < len(col_a_x):
                xa = col_a_x[col_no]
                qy = int(q1_y + row_no * q_row_step_y)
                d = detail_map.get(q_idx)
                if d:
                    is_corr = d.get('is_correct', False)
                    corr_opt = str(d.get('correct_ans') or '').strip().upper()
                    stud_opt = str(d.get('student_ans') or '').strip().upper()

                    if is_corr:
                        # Câu đúng: vẽ màu xanh lá
                        if stud_opt in opts:
                            ox = int(xa + opts.index(stud_opt) * opt_step_x)
                            draw_circle(ox, qy, COLOR_CORRECT, radius=7, thickness=2)
                    else:
                        # Chỉ vẽ rect khi tô nhiều hơn 1 lựa chọn ('*') hoặc không tô (rỗng)
                        is_multi = '*' in stud_opt
                        is_empty = not stud_opt or stud_opt in ['-', '']
                        if is_multi or is_empty:
                            draw_rect_box(xa - 12, qy - 8, xa + 3 * opt_step_x + 12, qy + 8, COLOR_WRONG, thickness=2)

                        # 1. Đáp án của đề: vẽ màu xanh lam
                        if corr_opt in opts:
                            ox = int(xa + opts.index(corr_opt) * opt_step_x)
                            draw_circle(ox, qy, COLOR_KEY, radius=7, thickness=2)
                        # 2. Phương án chọn sai của thí sinh: vẽ màu đỏ
                        if stud_opt in opts:
                            ox = int(xa + opts.index(stud_opt) * opt_step_x)
                            draw_circle(ox, qy, COLOR_WRONG, radius=7, thickness=2)
                        elif is_multi:
                            # Tô trùng 2+ lựa chọn
                            for m_opt, ox, qy_mark in part1_marks.get(q_idx, []):
                                draw_circle(ox, qy_mark, COLOR_WRONG, radius=7, thickness=2)
                else:
                    # Không có data (câu hỏi không khớp): luôn vẽ rect
                    draw_rect_box(xa - 12, qy - 8, xa + 3 * opt_step_x + 12, qy + 8, COLOR_WRONG, thickness=2)
                    for m_opt, ox, qy_mark in part1_marks.get(q_idx, []):
                        draw_circle(ox, qy_mark, COLOR_WRONG, radius=7, thickness=2)

        # PHẦN II: Đúng / Sai 4 ý
        tf_start_q = num_single + 1
        for i in range(min(num_tf, 8)):
            q_num = tf_start_q + i
            xd = int(round(col_dung_x[i]))
            xs = int(round(col_sai_x[i]))
            d = detail_map.get(q_num)
            if d and d.get('sub_results'):
                sub_res = d['sub_results']
                for s_idx, sub in enumerate(sub_labels):
                    qy = int(round(row_tf_y[s_idx]))
                    sub_info = sub_res.get(sub) or {}
                    u_val = sub_info.get('user')
                    e_val = sub_info.get('expected')
                    sub_ok = sub_info.get('is_correct', False)

                    if sub_ok:
                        # Câu/ý đúng: vẽ màu xanh lá
                        if u_val is True:
                            draw_circle(xd, qy, COLOR_CORRECT, radius=7, thickness=2)
                        elif u_val is False:
                            draw_circle(xs, qy, COLOR_CORRECT, radius=7, thickness=2)
                    else:
                        # Chỉ vẽ rect khi tô cả 2 (u_val == '*') hoặc không tô (u_val là None)
                        is_multi_tf = (u_val == '*')
                        is_empty_tf = (u_val is None)
                        if is_multi_tf or is_empty_tf:
                            draw_rect_box(xd - 12, qy - 8, xs + 12, qy + 8, COLOR_WRONG, thickness=2)

                        # Đáp án đề: màu xanh lam
                        if e_val is True:
                            draw_circle(xd, qy, COLOR_KEY, radius=7, thickness=2)
                        elif e_val is False:
                            draw_circle(xs, qy, COLOR_KEY, radius=7, thickness=2)
                        # Phương án thí sinh chọn sai: màu đỏ
                        if u_val is True:
                            draw_circle(xd, qy, COLOR_WRONG, radius=7, thickness=2)
                        elif u_val is False:
                            draw_circle(xs, qy, COLOR_WRONG, radius=7, thickness=2)
                        elif is_multi_tf:
                            draw_circle(xd, qy, COLOR_WRONG, radius=7, thickness=2)
                            draw_circle(xs, qy, COLOR_WRONG, radius=7, thickness=2)
            else:
                for s_idx, sub in enumerate(sub_labels):
                    qy = int(round(row_tf_y[s_idx]))
                    draw_rect_box(xd - 12, qy - 8, xs + 12, qy + 8, COLOR_WRONG, thickness=2)
                    if (q_num, sub) in part2_marks:
                        val_bool, wx, qy_mark = part2_marks[(q_num, sub)]
                        draw_circle(wx, qy_mark, COLOR_WRONG, radius=7, thickness=2)

        # PHẦN III: Điền số
        num_start_q = num_single + num_tf + 1
        q_base_x = [106.7, 248.0, 389.0, 530.0, 671.5, 813.0]
        col_step_x = 30.5
        for i in range(min(num_numeric, 6)):
            q_num = num_start_q + i
            d = detail_map.get(q_num)
            p3_list = part3_marks.get(q_num, [])
            stud_ans = str(d.get('student_ans') or '').strip() if d else ''
            corr_ans = str(d.get('correct_ans') or '').strip() if d else ''
            is_num_corr = d.get('is_correct', False) if d else False

            if is_num_corr:
                for val_char, cx, my in p3_list:
                    draw_circle(cx, my, COLOR_CORRECT, radius=11, thickness=3)
            else:
                # Phần III sai: chỉ vẽ rect cột khi tô trùng (duplicate) trong cột đó
                for c_idx in range(4):
                    cx = int(round(q_base_x[i] + c_idx * col_step_x))
                    col_marks = [m for m in p3_list if abs(m[1] - cx) < 15]
                    is_col_duplicate = len(col_marks) > 1
                    s_char = stud_ans[c_idx] if c_idx < len(stud_ans) else ''
                    is_col_empty = not s_char or s_char in [' ', '-']

                    # Vẽ rect chỉ khi tô trùng trong cột hoặc không tô cột nào
                    if is_col_duplicate or is_col_empty:
                        draw_rect_box(cx - 14, 1030, cx + 14, 1302, COLOR_WRONG, thickness=2)

                for val_char, cx, my in p3_list:
                    draw_circle(cx, my, COLOR_WRONG, radius=11, thickness=3)
    else:
        # Nếu không khớp mã đề: vẽ vòng tròn cho các ô đã tô. CHỈ vẽ hình chữ nhật đỏ khi tô lỗi (chọn nhiều đáp án) hoặc không tô.
        
        # PHẦN I
        for q_idx in range(1, num_single + 1):
            col_no = (q_idx - 1) // 10
            row_no = (q_idx - 1) % 10
            if col_no < len(col_a_x):
                xa = col_a_x[col_no]
                qy = int(q1_y + row_no * q_row_step_y)
                m_list = part1_marks.get(q_idx, [])
                if len(m_list) != 1:
                    draw_rect_box(xa - 12, qy - 8, xa + 3 * opt_step_x + 12, qy + 8, COLOR_WRONG, thickness=2)
                for m_opt, ox, qy_mark in m_list:
                    draw_circle(ox, qy_mark, COLOR_WRONG, radius=7, thickness=2)

        # PHẦN II
        tf_start_q = num_single + 1
        for i in range(min(num_tf, 8)):
            q_num = tf_start_q + i
            xd = int(round(col_dung_x[i]))
            xs = int(round(col_sai_x[i]))
            for s_idx, sub in enumerate(sub_labels):
                qy = int(round(row_tf_y[s_idx]))
                if (q_num, sub) not in part2_marks:
                    draw_rect_box(xd - 12, qy - 8, xs + 12, qy + 8, COLOR_WRONG, thickness=2)
                else:
                    val_bool, wx, qy_mark = part2_marks[(q_num, sub)]
                    if val_bool == '*':
                        draw_rect_box(xd - 12, qy - 8, xs + 12, qy + 8, COLOR_WRONG, thickness=2)
                        draw_circle(xd, qy, COLOR_WRONG, radius=7, thickness=2)
                        draw_circle(xs, qy, COLOR_WRONG, radius=7, thickness=2)
                    else:
                        draw_circle(wx, qy_mark, COLOR_WRONG, radius=7, thickness=2)

        # PHẦN III
        num_start_q = num_single + num_tf + 1
        q_base_x = [106.7, 248.0, 389.0, 530.0, 671.5, 813.0]
        col_step_x = 30.5
        for i in range(min(num_numeric, 6)):
            q_num = num_start_q + i
            p3_list = part3_marks.get(q_num, [])
            for c_idx in range(4):
                cx = int(round(q_base_x[i] + c_idx * col_step_x))
                col_marks = [m for m in p3_list if abs(m[1] - cx) < 15]
                if len(col_marks) != 1:
                    draw_rect_box(cx - 14, 1030, cx + 14, 1302, COLOR_WRONG, thickness=2)
            
            for val_char, cx, my in p3_list:
                draw_circle(cx, my, COLOR_WRONG, radius=11, thickness=3)

    # 4. Ghi điểm vào phiếu – toạ độ cố định (140, 330) trên ảnh thực (1925×2419 @ DPI=150)
    # Không qua perspective transform vì (140, 330) đã là pixel toạ độ thực trên ảnh gốc
    score_ox, score_oy = 140, 330

    annotated = draw_score_badge(
        annotated, score, score_text, score_ox, score_oy,
        is_matched=is_matched, sbd=detected_sbd, exam_code=detected_code
    )
    # 5. Crop ảnh về vùng trong 4 điểm neo góc
    if candidate_boxes and corner_indices and len(corner_indices) == 4:
        try:
            corner_pts = []
            for idx in corner_indices:
                if idx < len(candidate_boxes):
                    x, y, w, h, cx, cy = candidate_boxes[idx]
                    corner_pts.append((int(cx), int(cy)))

            if len(corner_pts) == 4:
                xs = [p[0] for p in corner_pts]
                ys = [p[1] for p in corner_pts]
                x1, x2 = min(xs), max(xs)
                y1, y2 = min(ys), max(ys)

                # Thêm margin nhỏ (10px) để không cắt sát vào điểm neo
                margin = 10
                ih, iw = annotated.shape[:2]
                x1 = max(0, x1 - margin)
                y1 = max(0, y1 - margin)
                x2 = min(iw, x2 + margin)
                y2 = min(ih, y2 + margin)

                if x2 > x1 and y2 > y1:
                    annotated = annotated[y1:y2, x1:x2]
        except Exception:
            pass  # Giữ nguyên ảnh gốc nếu có lỗi crop

    return annotated


@manager_required
def api_process_sheet_image(request):
    """
    API Tải và xử lý file ảnh bài làm phiếu thi định dạng JPG & TIFF (DPI=150).
    - Nhận diện OMR SBD, Mã đề, và câu trả lời.
    - So khớp với đáp án bộ đề để tính điểm và chấm bài.
    - Nếu không tìm thấy mã đề trong danh sách: Ghi 0 điểm và thông báo mã đề không khớp.
    - Cho phép người chấm điều chỉnh mã đề / SBD và chấm lại theo dữ liệu sau sửa.
    - Ghi điểm vào phiếu tại toạ độ 120x340 bằng số và bằng chữ.
    - Câu đúng: màu xanh lá; Câu sai: đáp án đề màu xanh lam, phương án sai màu đỏ.
    """
    if request.method != 'POST' or 'sheet_image' not in request.FILES:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn file ảnh JPG hoặc TIFF.'}, status=400)

    image_file = request.FILES['sheet_image']
    subject_id = request.POST.get('subject_id')
    override_key_id = request.POST.get('key_id') or request.POST.get('override_key_id')
    override_exam_code = request.POST.get('exam_code') or request.POST.get('override_exam_code')
    override_student_id = request.POST.get('student_id') or request.POST.get('override_student_id')
    override_answers_json = request.POST.get('student_answers') or request.POST.get('override_answers')
    applied_classes_str = request.POST.get('applied_classes', '').strip()
    applied_classes = [c.strip() for c in applied_classes_str.split(',') if c.strip()] if applied_classes_str else []

    file_name = image_file.name.lower()
    if not (file_name.endswith('.jpg') or file_name.endswith('.jpeg') or file_name.endswith('.tif') or file_name.endswith('.tiff')):
        return JsonResponse({'status': 'error', 'message': 'Chỉ chấp nhận file ảnh định dạng JPG (.jpg, .jpeg) hoặc TIFF (.tif, .tiff).'}, status=400)

    try:
        # 1. Đọc bằng Pillow để trích xuất DPI & chuẩn hóa màu
        pil_img = Image.open(image_file)
        dpi_info = pil_img.info.get('dpi', (150, 150))
        dpi_val = int(dpi_info[0]) if isinstance(dpi_info, tuple) else int(dpi_info or 150)

        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')

        img_np = np.array(pil_img)
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        # 2. Threshold nhị phân
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_blur = cv2.GaussianBlur(img_gray, (5, 5), 0)
        _, img_thresh = cv2.threshold(img_blur, 160, 255, cv2.THRESH_BINARY_INV)

        # Lấy thông số môn thi nếu có
        num_single, num_tf, num_numeric = 24, 4, 6
        subject_obj = None
        if subject_id and str(subject_id).isdigit():
            subject_obj = Subject.objects.filter(id=int(subject_id)).first()
            if subject_obj:
                num_single, num_tf, num_numeric = subject_obj.num_single, subject_obj.num_tf, subject_obj.num_numeric

        # 3. Trích xuất OMR
        det_sbd, det_code, det_answers, M_inv, candidate_boxes, corner_indices, extracted_marks = detect_omr_sheet(
            img_bgr, num_single, num_tf, num_numeric
        )

        effective_sbd = (override_student_id or det_sbd or '').strip()

        # Áp dụng câu trả lời điều chỉnh nếu có
        if override_answers_json:
            try:
                ov_ans = json.loads(override_answers_json)
                if isinstance(ov_ans, dict):
                    for k, v in ov_ans.items():
                        if not k.startswith('_'):
                            det_answers[str(k)] = v
            except Exception:
                pass

        # 4. So khớp bộ đề thi (Exam Key)
        matched_key = None
        if override_key_id and str(override_key_id).isdigit():
            matched_key = GradingExamKey.objects.filter(id=int(override_key_id)).first()

        clean_override_code = str(override_exam_code or '').replace('-', '').replace('*', '').strip()
        if not matched_key and clean_override_code:
            if subject_obj:
                # Chỉ tìm trong môn đang chấm
                matched_key = (
                    subject_obj.grading_keys.filter(code=clean_override_code).first() or
                    subject_obj.grading_keys.filter(code=clean_override_code.lstrip('0')).first() or
                    subject_obj.grading_keys.filter(code=clean_override_code.zfill(3)).first() or
                    subject_obj.grading_keys.filter(code=clean_override_code.zfill(4)).first()
                )
            else:
                # Không có subject – tìm toàn bộ (fallback khi không truyền subject_id)
                matched_key = (
                    GradingExamKey.objects.filter(code=clean_override_code).first() or
                    GradingExamKey.objects.filter(code=clean_override_code.lstrip('0')).first() or
                    GradingExamKey.objects.filter(code=clean_override_code.zfill(3)).first()
                )

        clean_det_code = str(det_code or '').replace('-', '').replace('*', '').strip()
        if not matched_key and clean_det_code:
            if subject_obj:
                # Chỉ tìm trong môn đang chấm
                matched_key = (
                    subject_obj.grading_keys.filter(code=clean_det_code).first() or
                    subject_obj.grading_keys.filter(code=clean_det_code.lstrip('0')).first() or
                    subject_obj.grading_keys.filter(code=clean_det_code.zfill(3)).first() or
                    subject_obj.grading_keys.filter(code=clean_det_code.zfill(4)).first()
                )
            else:
                # Không có subject – tìm toàn bộ (fallback)
                matched_key = GradingExamKey.objects.filter(code=clean_det_code).first()

        effective_code = (clean_override_code or (matched_key.code if matched_key else det_code) or '').strip()

        is_code_matched = (matched_key is not None)
        total_score = 0.0
        max_score = 10.0
        correct_count = 0
        grading_details = []

        if is_code_matched:
            key_questions = list(matched_key.questions.all().order_by('question_number'))
            total_score, max_score, correct_count, grading_details = calculate_score(key_questions, det_answers)
            score_text = score_to_vietnamese_words(total_score)
        else:
            # Không tìm thấy đề trong danh sách đề (không khớp) -> ghi 0 điểm
            total_score = 0.0
            score_text = f"Không điểm (Mã đề {effective_code or '---'} không khớp)"

        # --- KIỂM TRA TOÀN BỘ CÁC LỖI TRÊN PHIẾU THI ---
        # 1. Lỗi Số Báo Danh (chưa tô, tô lỗi, không khớp master, không khớp lớp áp dụng)
        student = None
        student_found = False
        student_class_name = ''
        student_error = None

        if not effective_sbd or '-' in effective_sbd or '*' in effective_sbd:
            student_error = "Số báo danh chưa tô hoặc tô lỗi"
        else:
            student = Student.objects.select_related('student_class').filter(student_id=effective_sbd).first()
            if not student:
                student_error = f"Số báo danh '{effective_sbd}' không khớp với danh sách học sinh"
            else:
                student_found = True
                student_class_name = student.student_class.name if student.student_class else ''
                if applied_classes:
                    cls_match = False
                    if student.student_class:
                        if str(student.student_class.id) in applied_classes or student.student_class.name in applied_classes:
                            cls_match = True
                    if not cls_match:
                        student_error = f"Học sinh {student.full_name} (Lớp {student_class_name or 'Chưa xếp'}) không thuộc danh sách lớp đã áp dụng vào bài thi"

        # 2. Lỗi Mã Đề (chưa tô, tô lỗi, không tồn tại trong danh sách mã đề đã nhập)
        code_error = None
        if not effective_code or '-' in effective_code or '*' in effective_code:
            code_error = "Mã đề chưa tô hoặc tô lỗi"
        elif not is_code_matched:
            code_error = f"Mã đề '{effective_code}' không tồn tại trong danh sách mã đề đã nhập"

        # 3. Lỗi Tô đáp án trùng nhau:
        # - Tô 2 lựa chọn cho 1 câu (Phần I)
        # - 1 phương án đúng sai chọn cả 2 (Phần II)
        # - Tô ô trên cùng 1 cột (loại câu điền số - Phần III)
        duplicate_errors = []

        # Phần I
        for q_idx in range(1, num_single + 1):
            q_str = str(q_idx)
            ans = det_answers.get(q_str)
            if ans and isinstance(ans, str) and ('*' in ans or len(ans.split('*')) > 1 or len(ans) > 1):
                duplicate_errors.append(f"Câu {q_idx}: Tô trùng 2 lựa chọn ({ans}) (Phần I)")

        # Phần II
        for i in range(min(num_tf, 8)):
            q_num = num_single + 1 + i
            q_str = str(q_num)
            tf_data = det_answers.get(q_str)
            if isinstance(tf_data, dict):
                for sub in ['a', 'b', 'c', 'd']:
                    val = tf_data.get(sub)
                    if val == '*' or str(val) == '*':
                        duplicate_errors.append(f"Câu {q_num} ý {sub.upper()}: Chọn cả Đúng và Sai (Phần II)")

        # Phần III
        for i in range(min(num_numeric, 6)):
            q_num = num_single + num_tf + 1 + i
            q_str = str(q_num)
            num_ans = det_answers.get(q_str)
            if num_ans and isinstance(num_ans, str) and '*' in num_ans:
                duplicate_errors.append(f"Câu {q_num}: Tô trùng nhiều ô trên cùng 1 cột (Phần III)")

        all_errors = []
        if student_error:
            all_errors.append(student_error)
        if code_error:
            all_errors.append(code_error)
        all_errors.extend(duplicate_errors)

        has_errors = (len(all_errors) > 0)

        # 5. Vẽ ảnh xem trước có chấm điểm & tô màu
        annotated_bgr = render_annotated_sheet(
            img_bgr, M_inv, candidate_boxes, corner_indices,
            effective_sbd, effective_code, det_answers,
            key_questions=matched_key.questions.all() if is_code_matched else None,
            is_matched=is_code_matched,
            score=total_score,
            score_text=score_text,
            details=grading_details,
            num_single=num_single,
            num_tf=num_tf,
            num_numeric=num_numeric,
            extracted_marks=extracted_marks,
            has_errors=has_errors,
            error_count=len(all_errors)
        )

        # 6. Mã hóa Base64
        _, buffer_orig = cv2.imencode('.jpg', annotated_bgr)
        orig_b64 = base64.b64encode(buffer_orig).decode('utf-8')

        _, buffer_thresh = cv2.imencode('.jpg', img_thresh)
        thresh_b64 = base64.b64encode(buffer_thresh).decode('utf-8')

        return JsonResponse({
            'status': 'success',
            'filename': image_file.name,
            'dpi': dpi_val,
            'width': pil_img.width,
            'height': pil_img.height,
            'original_b64': orig_b64,
            'thresh_b64': thresh_b64,
            'detected_sbd': effective_sbd,
            'original_detected_sbd': det_sbd,
            'detected_code': effective_code,
            'original_detected_code': det_code,
            'detected_answers': det_answers,
            'raw_parts': det_answers.get('_raw_parts', {}),
            'is_code_matched': is_code_matched,
            'matched_key_id': matched_key.id if matched_key else None,
            'matched_key_code': matched_key.code if matched_key else (effective_code or None),
            'total_score': total_score,
            'max_score': max_score,
            'score_text': score_text,
            'correct_count': correct_count,
            'grading_details': grading_details,
            'has_errors': has_errors,
            'errors': all_errors,
            'student_error': student_error,
            'code_error': code_error,
            'duplicate_errors': duplicate_errors,
            'student_info': {
                'found': student_found,
                'full_name': student.full_name if student else '',
                'class_name': student_class_name,
            },
            'message': f'Đã xử lý thành công ảnh {image_file.name} (DPI: {dpi_val}).'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': f'Lỗi xử lý file ảnh: {str(e)}'}, status=400)


# =====================================================================
# 6. BẢNG ĐIỂM & QUẢN LÝ KẾT QUẢ CHẤM
# =====================================================================

@manager_required
def period_scorecard_view(request, period_id):
    """Xem bảng điểm tổng hợp của một kỳ thi"""
    from django.shortcuts import get_object_or_404
    from collections import defaultdict
    
    period = get_object_or_404(ExamPeriod, id=period_id)
    records_qs = GradingRecord.objects.filter(key__subject__exam_period=period).select_related('key__subject')
    
    # Lấy danh sách các lớp có trong kỳ thi này để làm bộ lọc
    raw_classes = records_qs.exclude(student_class='').values_list('student_class', flat=True)
    all_classes = sorted(list(set(c.strip() for c in raw_classes if c and c.strip())))

    subject_ids = request.GET.getlist('subject_ids')
    class_names = request.GET.getlist('class_names')
    
    if subject_ids:
        subject_ids = [s for s in subject_ids if s]
        if subject_ids:
            records_qs = records_qs.filter(key__subject_id__in=subject_ids)
            
    if class_names:
        class_names = [c for c in class_names if c]
        if class_names:
            records_qs = records_qs.filter(student_class__in=class_names)

    sort_by = request.GET.get('sort_by', 'score_desc')
    
    # Gom nhóm theo student_id
    grouped = defaultdict(lambda: {
        'student_id': '',
        'student_name': '',
        'student_class': '',
        'total_score': 0.0,
        'subjects': set(),
        'subject_scores': {},
    })
    
    for r in records_qs:
        sid = r.student_id or 'UNKNOWN'
        g = grouped[sid]
        g['student_id'] = r.student_id
        if not g['student_name'] and r.student_name:
            g['student_name'] = r.student_name
        if not g['student_class'] and r.student_class:
            g['student_class'] = r.student_class
        g['total_score'] += float(r.total_score)
        g['subjects'].add(r.key.subject.name)
        g['subject_scores'][r.key.subject.id] = float(r.total_score)
        
    records_list = []
    for sid, data in grouped.items():
        data['subject_names'] = ", ".join(sorted(list(data['subjects'])))
        records_list.append(data)
        
    # Calculate ranks based on score descending
    records_for_rank = sorted(records_list, key=lambda x: x['total_score'], reverse=True)
    rank = 1
    prev_score = None
    for i, r in enumerate(records_for_rank):
        # Allow small floating point diffs
        if prev_score is not None and abs(r['total_score'] - prev_score) > 0.001:
            rank = i + 1
        r['rank'] = rank
        prev_score = r['total_score']

    # Apply sorting as requested by user
    if sort_by == 'sbd_asc':
        records_list = sorted(records_list, key=lambda x: str(x['student_id']).lower() if x['student_id'] else '')
    else:
        records_list = records_for_rank # Already sorted by score desc

    all_period_subjects = list(period.subjects.all())
    display_subjects = [s for s in all_period_subjects if str(s.id) in subject_ids] if subject_ids else all_period_subjects

    for r in records_list:
        r['scores_list'] = [r['subject_scores'].get(s.id, None) for s in display_subjects]

    context = {
        'period': period,
        'records': records_list,
        'subjects': all_period_subjects,
        'display_subjects': display_subjects,
        'all_classes': all_classes,
        'selected_subject_ids': [int(s) for s in subject_ids if s.isdigit()],
        'selected_class_names': class_names,
        'sort_by': sort_by,
        'active_tab': 'exams',
    }
    return render(request, 'quiz/grading/period_scorecard.html', context)


@manager_required
def export_aggregated_scorecard_excel(request):
    """Xuất file Excel cho bảng điểm gom nhóm"""
    from collections import defaultdict
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    
    period_id = request.GET.get('period_id')
    period = get_object_or_404(ExamPeriod, id=period_id)
    records_qs = GradingRecord.objects.filter(key__subject__exam_period=period).select_related('key__subject')

    subject_ids = request.GET.getlist('subject_ids')
    class_names = request.GET.getlist('class_names')
    
    if subject_ids:
        subject_ids = [s for s in subject_ids if s]
        if subject_ids:
            records_qs = records_qs.filter(key__subject_id__in=subject_ids)
            
    if class_names:
        class_names = [c for c in class_names if c]
        if class_names:
            records_qs = records_qs.filter(student_class__in=class_names)

    sort_by = request.GET.get('sort_by', 'score_desc')
    
    grouped = defaultdict(lambda: {
        'student_id': '',
        'student_name': '',
        'student_class': '',
        'total_score': 0.0,
        'subjects': set(),
        'subject_scores': {},
    })
    
    for r in records_qs:
        sid = r.student_id or 'UNKNOWN'
        g = grouped[sid]
        g['student_id'] = r.student_id
        if not g['student_name'] and r.student_name:
            g['student_name'] = r.student_name
        if not g['student_class'] and r.student_class:
            g['student_class'] = r.student_class
        g['total_score'] += float(r.total_score)
        g['subjects'].add(r.key.subject.name)
        g['subject_scores'][r.key.subject.id] = float(r.total_score)
        
    records_list = []
    for sid, data in grouped.items():
        data['subject_names'] = ", ".join(sorted(list(data['subjects'])))
        records_list.append(data)
        
    records_for_rank = sorted(records_list, key=lambda x: x['total_score'], reverse=True)
    rank = 1
    prev_score = None
    for i, r in enumerate(records_for_rank):
        if prev_score is not None and abs(r['total_score'] - prev_score) > 0.001:
            rank = i + 1
        r['rank'] = rank
        prev_score = r['total_score']

    if sort_by == 'sbd_asc':
        records_list = sorted(records_list, key=lambda x: str(x['student_id']).lower() if x['student_id'] else '')
    else:
        records_list = records_for_rank

    all_period_subjects = list(period.subjects.all())
    display_subjects = [s for s in all_period_subjects if str(s.id) in subject_ids] if subject_ids else all_period_subjects

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bảng Điểm Tổng Hợp"

    # Merge until len(headers) - 1, which will be calculated later, but let's just make it dynamic
    headers = ["STT", "SBD / Mã TS", "Họ và Tên", "Lớp / Phòng"]
    for s in display_subjects:
        headers.append(f"Điểm {s.name}")
    headers.extend(["Tổng Điểm", "Hạng"])

    last_col = openpyxl.utils.get_column_letter(len(headers))

    ws.merge_cells(f'A1:{last_col}1')
    ws['A1'] = f"BẢNG ĐIỂM TỔNG HỢP - KỲ THI: {period.name.upper()}"
    ws['A1'].font = Font(name="Arial", size=16, bold=True, color="1E3A8A")
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 35

    ws.merge_cells(f'A2:{last_col}2')
    ws['A2'] = f"Thời gian xuất: {timezone.now().strftime('%d/%m/%Y %H:%M')} | Tổng số thí sinh: {len(records_list)}"
    ws['A2'].font = Font(name="Arial", size=10, italic=True, color="4B5563")
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    ws.row_dimensions[4].height = 25

    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_num, h_text in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_num, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    row_idx = 5
    for idx, r in enumerate(records_list, start=1):
        row_data = [
            idx,
            r['student_id'],
            r['student_name'],
            r['student_class'] or ''
        ]
        
        for s in display_subjects:
            score = r['subject_scores'].get(s.id, 0)
            row_data.append(round(score, 2))
            
        row_data.extend([
            round(r['total_score'], 2),
            r['rank']
        ])

        for col_num, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_num, value=val)
            cell.font = Font(name="Arial", size=10)
            cell.border = thin_border
            # STT, SBD, and all scores + rank should be center aligned
            if col_num in [1, 2] or col_num > 4:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        row_idx += 1

    for col in ws.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        if col_letter == 'A':
            ws.column_dimensions[col_letter].width = 5
        else:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="Bang_Diem_Tong_Hop_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    wb.save(response)
    return response

@manager_required
def grading_results_list(request):
    """Danh sách các bài thi đã chấm, kèm bộ lọc và thống kê"""
    records = GradingRecord.objects.select_related('key__subject__exam_period', 'graded_by').all()

    filter_period = request.GET.get('period_id', '')
    filter_subject = request.GET.get('subject_id', '')
    filter_key = request.GET.get('key_id', '')
    search_q = request.GET.get('q', '').strip()

    if filter_period:
        records = records.filter(key__subject__exam_period_id=filter_period)
    if filter_subject:
        records = records.filter(key__subject_id=filter_subject)
    if filter_key:
        records = records.filter(key_id=filter_key)
    if search_q:
        records = records.filter(
            Q(student_id__icontains=search_q) |
            Q(student_name__icontains=search_q) |
            Q(student_class__icontains=search_q)
        )

    stats = records.aggregate(
        avg_score=Avg('total_score'),
        max_score=Max('total_score'),
        min_score=Min('total_score'),
        count=Count('id')
    )

    paginator = Paginator(records, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    periods = ExamPeriod.objects.prefetch_related('subjects__grading_keys').all().order_by('name')

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'periods': periods,
        'filter_period': filter_period,
        'filter_subject': filter_subject,
        'filter_key': filter_key,
        'search_q': search_q,
        'active_tab': 'results',
    }
    return render(request, 'quiz/grading/results_list.html', context)


@manager_required
def api_get_grading_record_detail(request, record_id):
    record = get_object_or_404(
        GradingRecord.objects.select_related('key__subject__exam_period', 'graded_by'),
        id=record_id
    )

    percent = (record.total_score / record.max_score * 100) if record.max_score > 0 else 0

    # Lấy thông tin các câu hỏi trong mã đề để hỗ trợ giao diện sửa đáp án
    questions_list = []
    for q in record.key.questions.order_by('question_number').all():
        questions_list.append({
            'number': q.question_number,
            'type': q.question_type,
            'score_weight': q.score_weight,
            'correct_single': q.correct_single or '',
            'correct_tf': q.correct_tf or {},
            'correct_numeric': q.correct_numeric or '',
        })

    return JsonResponse({
        'status': 'success',
        'record': {
            'id': record.id,
            'student_id': record.student_id,
            'student_name': record.student_name,
            'student_class': record.student_class,
            'exam_code': record.exam_code,
            'key_id': record.key_id,
            'subject_id': record.key.subject.id,
            'subject_name': record.key.subject.name,
            'period_name': record.key.subject.exam_period.name,
            'total_score': record.total_score,
            'max_score': record.max_score,
            'correct_count': record.correct_count,
            'percent': round(percent, 1),
            'graded_at': record.created_at.strftime('%d/%m/%Y %H:%M'),
            'graded_by': record.graded_by.username if record.graded_by else 'Hệ thống',
            'student_answers': record.student_answers or {},
            'details': record.grading_details,
            'annotated_image_url': record.annotated_image.url if record.annotated_image else '',
            'original_image_url': record.original_image.url if record.original_image else '',
            'questions': questions_list,
        }
    })


@manager_required
def api_regrade_record(request, record_id):
    """
    API Chấm lại bài thi của thí sinh bằng cách cập nhật trực tiếp đáp án (student_answers).
    - Tính lại điểm chuẩn Bộ GD&ĐT cho Phần I (trắc nghiệm đơn), Phần II (Đúng/Sai), Phần III (Điền số).
    - Cập nhật total_score, max_score, correct_count, grading_details.
    - Nếu có ảnh gốc (original_image), tự động vẽ lại ảnh nhận diện đã chấm (annotated_image).
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)

    record = get_object_or_404(
        GradingRecord.objects.select_related('key__subject__exam_period'),
        id=record_id
    )

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Dữ liệu JSON không hợp lệ: {str(e)}'}, status=400)

    new_answers = data.get('answers', {})
    if not isinstance(new_answers, dict):
        return JsonResponse({'status': 'error', 'message': 'Dữ liệu đáp án mới không đúng định dạng.'}, status=400)

    # Cho phép sửa đổi SBD, Họ tên, Lớp nếu có
    if 'student_name' in data and str(data['student_name']).strip():
        record.student_name = str(data['student_name']).strip()
    if 'student_id' in data and str(data['student_id']).strip():
        record.student_id = str(data['student_id']).strip()
    if 'student_class' in data:
        record.student_class = str(data['student_class']).strip()

    # Tính lại điểm số theo bộ câu hỏi của mã đề
    key_questions = list(record.key.questions.order_by('question_number').all())
    total_score, max_score, correct_count, details = calculate_score(key_questions, new_answers)

    record.student_answers = new_answers
    record.total_score = total_score
    record.max_score = max_score
    record.correct_count = correct_count
    record.grading_details = details

    # Nếu có ảnh gốc hoặc ảnh chấm trước đó, thử vẽ lại nhãn điểm và đáp án mới
    if record.original_image and record.original_image.name:
        try:
            orig_path = record.original_image.path
            img_bgr = cv2.imread(orig_path)
            if img_bgr is not None:
                num_single = record.key.subject.num_single if record.key.subject else 24
                num_tf = record.key.subject.num_tf if record.key.subject else 4
                num_numeric = record.key.subject.num_numeric if record.key.subject else 6
                
                det_sbd, det_code, _, M_inv, candidate_boxes, corner_indices, extracted_marks = detect_omr_sheet(
                    img_bgr, num_single, num_tf, num_numeric
                )
                score_text = score_to_vietnamese_words(total_score)
                re_annotated_bgr = render_annotated_sheet(
                    img_bgr, M_inv, candidate_boxes, corner_indices,
                    record.student_id, record.exam_code, new_answers,
                    key_questions=key_questions,
                    is_matched=True,
                    score=total_score,
                    score_text=score_text,
                    details=details,
                    num_single=num_single,
                    num_tf=num_tf,
                    num_numeric=num_numeric,
                    extracted_marks=extracted_marks
                )
                _, buffer = cv2.imencode('.jpg', re_annotated_bgr)
                fn = f"annotated_{record.id}_{uuid.uuid4().hex[:8]}.jpg"
                record.annotated_image.save(fn, ContentFile(buffer.tobytes()), save=False)
        except Exception as err:
            print(f"Không thể vẽ lại ảnh cho record {record.id}: {err}")

    record.save()

    percent = (total_score / max_score * 100) if max_score > 0 else 0
    if percent >= 85:
        rank, badge = "Xuất sắc", "success"
    elif percent >= 70:
        rank, badge = "Khá", "primary"
    elif percent >= 50:
        rank, badge = "Trung bình", "warning"
    else:
        rank, badge = "Chưa đạt", "danger"

    return JsonResponse({
        'status': 'success',
        'message': f'Đã chấm lại thành công cho thí sinh {record.student_name}: {total_score}/{max_score} điểm!',
        'record': {
            'id': record.id,
            'student_id': record.student_id,
            'student_name': record.student_name,
            'student_class': record.student_class,
            'exam_code': record.exam_code,
            'total_score': total_score,
            'max_score': max_score,
            'correct_count': correct_count,
            'percent': round(percent, 1),
            'rank': rank,
            'badge': badge,
            'details': details,
            'student_answers': new_answers,
            'annotated_image_url': record.annotated_image.url if record.annotated_image else '',
        }
    })


@manager_required
def api_upload_record_image(request, record_id):
    """
    API Cho phép tải lên file ảnh bài làm cho một thí sinh đã chấm:
    - Quét OMR hoặc vẽ trực tiếp kết quả chấm hiện tại lên ảnh.
    - Lưu vào record.original_image và record.annotated_image.
    """
    if request.method != 'POST' or ('sheet_image' not in request.FILES and 'image' not in request.FILES):
        return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn file ảnh JPG hoặc TIFF.'}, status=400)

    record = get_object_or_404(
        GradingRecord.objects.select_related('key__subject__exam_period'),
        id=record_id
    )
    image_file = request.FILES.get('sheet_image') or request.FILES.get('image')

    try:
        # Đọc ảnh
        pil_img = Image.open(image_file)
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        img_np = np.array(pil_img)
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        num_single = record.key.subject.num_single if record.key.subject else 24
        num_tf = record.key.subject.num_tf if record.key.subject else 4
        num_numeric = record.key.subject.num_numeric if record.key.subject else 6

        # Chạy OMR để tìm các góc neo và khung
        _, _, _, M_inv, candidate_boxes, corner_indices, extracted_marks = detect_omr_sheet(
            img_bgr, num_single, num_tf, num_numeric
        )

        key_questions = list(record.key.questions.order_by('question_number').all())
        score_text = score_to_vietnamese_words(record.total_score)

        annotated_bgr = render_annotated_sheet(
            img_bgr, M_inv, candidate_boxes, corner_indices,
            record.student_id, record.exam_code, record.student_answers,
            key_questions=key_questions,
            is_matched=True,
            score=record.total_score,
            score_text=score_text,
            details=record.grading_details,
            num_single=num_single,
            num_tf=num_tf,
            num_numeric=num_numeric,
            extracted_marks=extracted_marks
        )

        # Lưu ảnh gốc
        image_file.seek(0)
        record.original_image.save(f"orig_{record.id}_{uuid.uuid4().hex[:8]}.jpg", image_file, save=False)

        # Lưu ảnh đã vẽ nhận diện
        _, buffer = cv2.imencode('.jpg', annotated_bgr)
        record.annotated_image.save(f"annotated_{record.id}_{uuid.uuid4().hex[:8]}.jpg", ContentFile(buffer.tobytes()), save=False)
        record.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Đã tải lên và vẽ nhận diện ảnh bài thi thành công!',
            'annotated_image_url': record.annotated_image.url,
            'original_image_url': record.original_image.url,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Lỗi xử lý file ảnh: {str(e)}'}, status=400)



@manager_required
def api_delete_grading_record(request, record_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không hợp lệ.'}, status=405)
    record = get_object_or_404(GradingRecord, id=record_id)
    student_name = record.student_name
    record.delete()
    return JsonResponse({'status': 'success', 'message': f'Đã xóa bài chấm của thí sinh "{student_name}".'})


@manager_required
def export_grading_results_excel(request):
    """Xuất danh sách điểm thí sinh sang file Excel bằng openpyxl"""
    records = GradingRecord.objects.select_related('key__subject__exam_period').all()

    filter_period = request.GET.get('period_id', '')
    filter_subject = request.GET.get('subject_id', '')
    filter_key = request.GET.get('key_id', '')

    if filter_period:
        records = records.filter(key__subject__exam_period_id=filter_period)
    if filter_subject:
        records = records.filter(key__subject_id=filter_subject)
    if filter_key:
        records = records.filter(key_id=filter_key)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bảng Điểm Trắc Nghiệm"

    period_name = ""
    if filter_period:
        try:
            period_obj = ExamPeriod.objects.get(id=filter_period)
            period_name = f" - KỲ THI: {period_obj.name.upper()}"
        except: pass

    ws.merge_cells('A1:H1')
    ws['A1'] = f"BẢNG ĐIỂM CHẤM THI TRẮC NGHIỆM{period_name}"
    ws['A1'].font = Font(name="Arial", size=16, bold=True, color="1E3A8A")
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 35

    ws.merge_cells('A2:H2')
    ws['A2'] = f"Thời gian xuất: {timezone.now().strftime('%d/%m/%Y %H:%M')} | Tổng số thí sinh: {records.count()}"
    ws['A2'].font = Font(name="Arial", size=10, italic=True, color="4B5563")
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    headers = [
        "STT", "SBD / Mã TS", "Họ và Tên", "Lớp / Phòng", "Môn Thi", "Mã Đề", "Điểm Số / Điểm Tối Đa", "Xếp Loại"
    ]
    ws.row_dimensions[4].height = 25

    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_num, h_text in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_num, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    row_idx = 5
    for idx, r in enumerate(records, start=1):
        percent = (r.total_score / r.max_score * 100) if r.max_score > 0 else 0
        if percent >= 85:
            rank = "Xuất sắc"
        elif percent >= 70:
            rank = "Khá"
        elif percent >= 50:
            rank = "Trung bình"
        else:
            rank = "Chưa đạt"

        row_data = [
            idx,
            r.student_id,
            r.student_name,
            r.student_class or '',
            r.key.subject.name,
            r.exam_code,
            f"{r.total_score} / {r.max_score}",
            rank,
        ]

        for col_num, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_num, value=val)
            cell.font = Font(name="Arial", size=10)
            cell.border = thin_border
            if col_num in [1, 2, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        row_idx += 1

    for col in ws.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        if col_letter == 'A':
            ws.column_dimensions[col_letter].width = 5  # Khoảng 35px
        else:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="Bang_Diem_Cham_Thi_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    wb.save(response)
    return response


# =====================================================================
# 7. TRANG WORKSPACE MÔN THI VÀ XUẤT BÁO CÁO LINH HOẠT (PDF / EXCEL / ZIP)
# =====================================================================

@manager_required
def subject_workspace_view(request, subject_id):
    """
    Giao diện Quản lý Môn Thi Linh Hoạt với 4 Tabs:
    Tab 1: Các bài đã chấm & Nút chấm bài môn này
    Tab 2: Các mã đề ứng với đáp án đã nhập
    Tab 3: Thống kê chi tiết (3 góc nhìn: Theo SBD, Theo Điểm số, Theo Mã đề)
    Tab 4: Xuất kết quả (PDF, Excel, ZIP Ảnh)
    """
    subject = get_object_or_404(Subject.objects.select_related('exam_period'), id=subject_id)
    keys = subject.grading_keys.prefetch_related('questions', 'submissions').order_by('code')
    records = GradingRecord.objects.filter(key__subject=subject).select_related('key', 'graded_by')

    active_tab = request.GET.get('tab', 'results') # results | keys | stats | exports
    stat_mode = request.GET.get('mode', 'sbd')     # sbd | score | code

    # Data cho Tab 3: Thống kê chi tiết
    sbd_records = records.order_by('student_id')
    score_records = records.order_by('-total_score', 'student_id')

    # Thống kê theo mã đề
    code_stats = records.values('exam_code').annotate(
        count=Count('id'),
        avg_score=Avg('total_score'),
        max_score=Max('total_score'),
        min_score=Min('total_score')
    ).order_by('exam_code')

    # Phổ điểm (Xuất sắc >= 8.5, Khá >= 7.0, TB >= 5.0, Chưa đạt < 5.0)
    stats_summary = records.aggregate(
        total_count=Count('id'),
        avg_score=Avg('total_score'),
        max_score=Max('total_score'),
        min_score=Min('total_score')
    )

    rank_counts = {
        'excellent': 0, # >= 85%
        'good': 0,      # >= 70%
        'average': 0,   # >= 50%
        'weak': 0       # < 50%
    }

    # Thống kê câu hỏi theo từng mã đề (chỉ chạy khi đang ở tab stats, mode code để tối ưu)
    code_question_stats = {}
    if active_tab == 'stats' and stat_mode == 'code':
        for r in records:
            code = r.exam_code
            if code not in code_question_stats:
                code_question_stats[code] = {}

            details = r.grading_details
            if isinstance(details, list):
                for q in details:
                    q_num = q.get('number')
                    q_type = q.get('type')
                    if not q_num:
                        continue
                    
                    q_key = f"{q_type}_{q_num}"
                    if q_key not in code_question_stats[code]:
                        code_question_stats[code][q_key] = {'number': q_num, 'correct': 0, 'total': 0, 'type': q_type}
                    
                    code_question_stats[code][q_key]['total'] += 1
                    if q.get('is_correct'):
                        code_question_stats[code][q_key]['correct'] += 1

        # Chuyển đổi thành dictionary of lists (đã sắp xếp theo loại câu và STT câu)
        type_order = {'SINGLE': 1, 'TF': 2, 'NUMERIC': 3}
        for code in code_question_stats:
            sorted_qs = sorted(
                [{**v, 'ratio': round(v['correct'] / v['total'] * 100, 1) if v['total'] > 0 else 0} 
                 for k, v in code_question_stats[code].items()],
                key=lambda x: (type_order.get(x['type'], 99), int(x['number']))
            )
            code_question_stats[code] = sorted_qs

    for r in records:
        pct = (r.total_score / r.max_score * 100) if r.max_score > 0 else 0
        if pct >= 85:
            rank_counts['excellent'] += 1
        elif pct >= 70:
            rank_counts['good'] += 1
        elif pct >= 50:
            rank_counts['average'] += 1
        else:
            rank_counts['weak'] += 1

    context = {
        'subject': subject,
        'keys': keys,
        'records': records,
        'sbd_records': sbd_records,
        'score_records': score_records,
        'code_stats': code_stats,
        'code_question_stats': json.dumps(code_question_stats),
        'stats_summary': stats_summary,
        'rank_counts': rank_counts,
        'active_tab': active_tab,
        'stat_mode': stat_mode,
        'active_tab_nav': 'exams',
    }
    return render(request, 'quiz/grading/subject_workspace.html', context)


@manager_required
def export_grading_results_pdf(request, subject_id):
    """Xuất file PDF báo cáo kết quả bảng điểm môn thi chính thức bằng reportlab"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image, PageBreak
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from django.conf import settings
    import os

    # Đăng ký font Roboto hỗ trợ tiếng Việt
    font_dir = os.path.join(settings.BASE_DIR, 'static', 'fonts')
    try:
        pdfmetrics.registerFont(TTFont('Roboto', os.path.join(font_dir, 'Roboto-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', os.path.join(font_dir, 'Roboto-Bold.ttf')))
        pdfmetrics.registerFont(TTFont('Roboto-Italic', os.path.join(font_dir, 'Roboto-Italic.ttf')))
        font_regular = 'Roboto'
        font_bold = 'Roboto-Bold'
        font_italic = 'Roboto-Italic'
    except Exception as e:
        font_regular = 'Helvetica'
        font_bold = 'Helvetica-Bold'
        font_italic = 'Helvetica-Oblique'

    subject = get_object_or_404(Subject.objects.select_related('exam_period'), id=subject_id)
    records = GradingRecord.objects.filter(key__subject=subject).order_by('student_id')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'PDFTitle',
        parent=styles['Title'],
        fontName=font_bold,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=1, # Center
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'PDFSubTitle',
        parent=styles['Normal'],
        fontName=font_italic,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#4B5563'),
        alignment=1,
        spaceAfter=15
    )

    story = []
    story.append(Paragraph(f"BẢNG ĐIỂM CHẤM THI TRẮC NGHIỆM - MÔN {subject.name.upper()}", title_style))
    story.append(Paragraph(f"Kỳ thi: {subject.exam_period.name} | Mã môn: {subject.code} | Ngày xuất: {timezone.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=15))

    # Table Header & Data
    table_data = [
        ["STT", "SBD", "Họ và Tên", "Lớp", "Mã Đề", "Điểm Số", "Max Điểm", "Xếp Loại"]
    ]

    for idx, r in enumerate(records, start=1):
        pct = (r.total_score / r.max_score * 100) if r.max_score > 0 else 0
        if pct >= 85:
            rank = "Xuất sắc"
        elif pct >= 70:
            rank = "Khá"
        elif pct >= 50:
            rank = "Trung bình"
        else:
            rank = "Chưa đạt"

        table_data.append([
            str(idx),
            str(r.student_id),
            str(r.student_name),
            str(r.student_class or ''),
            str(r.exam_code),
            f"{r.total_score:.2f}",
            f"{r.max_score:.2f}",
            rank
        ])

    pdf_table = Table(table_data, colWidths=[30, 70, 150, 60, 50, 60, 60, 70])
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), font_bold),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'), # Full name left aligned
        ('FONTNAME', (0, 1), (-1, -1), font_regular),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))

    story.append(pdf_table)

    # Thêm ảnh phiếu trả lời của các thí sinh (nếu có) vào các trang sau
    if request.GET.get('include_images') == '1':
        for r in records:
            image_path = None
            if r.annotated_image:
                image_path = r.annotated_image.path
            elif r.original_image:
                image_path = r.original_image.path
                
            if image_path and os.path.exists(image_path):
                try:
                    story.append(PageBreak())
                    story.append(Paragraph(f"Bài làm của thí sinh: {r.student_name} (SBD: {r.student_id})", subtitle_style))
                    img = Image(image_path)
                    # Giới hạn kích thước để vừa trang A4
                    img._restrictSize(500, 700) 
                    story.append(img)
                except Exception as e:
                    # Bỏ qua nếu có lỗi đọc file ảnh
                    pass

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    
    if request.GET.get('include_images') == '1':
        filename = f'Bang_Diem_Va_Anh_{subject.code}_{timezone.now().strftime("%Y%m%d")}.pdf'
    else:
        filename = f'Bang_Diem_{subject.code}_{timezone.now().strftime("%Y%m%d")}.pdf'
        
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@manager_required
def export_grading_images_zip(request, subject_id):
    """Đóng gói và tải xuống file nén ZIP chứa toàn bộ ảnh bài làm của môn thi"""
    import zipfile

    subject = get_object_or_404(Subject, id=subject_id)
    records = GradingRecord.objects.filter(key__subject=subject)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Ghi file README thông tin
        readme_content = f"DANH SACH ANH PHIEU THI MON {subject.name.upper()} ({subject.code})\n"
        readme_content += f"Ky thi: {subject.exam_period.name}\n"
        readme_content += f"Tong so bai cham: {records.count()}\n"
        readme_content += f"Ngay tao zip: {timezone.now().strftime('%d/%m/%Y %H:%M')}\n"
        zip_file.writestr("README.txt", readme_content)

        # Ghi các bài thi mẫu hoặc ảnh đã lưu
        for idx, r in enumerate(records, start=1):
            file_name = f"Phieu_{r.student_class or 'Lop'}_{r.student_id}_{r.exam_code}.txt"
            details_str = json.dumps(r.grading_details, ensure_ascii=False, indent=2)
            zip_file.writestr(file_name, f"Thi sinh: {r.student_name}\nSBD: {r.student_id}\nDiem: {r.total_score}/{r.max_score}\nChi tiet:\n{details_str}")

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Anh_Phieu_Thi_{subject.code}_{timezone.now().strftime("%Y%m%d")}.zip"'
    return response

