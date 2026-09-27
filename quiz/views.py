import io
import json
import random
import cv2
import numpy as np
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count

from .models import (
    Quiz, QuestionBank, BankChoice, QuizQuestion, Subject, Topic, ExamPeriod,
    ExamMatrixEntry, ExamMatrixTopicSpec, UserProfile, ExamResult, generate_unique_exam_code
)
from .avatars import VALID_AVATAR_IDS, get_preset_avatars_with_urls, get_avatar_url
from .docx_parser import parse_docx_bytes
from .docx_generator import generate_sample_docx
from .forms import QuestionBankForm, BankChoiceFormSet, LoginForm, RegisterForm
from .decorators import manager_required, admin_required


# =====================================================================
# XÁC THỰC NGƯỜI DÙNG (AUTHENTICATION)
# =====================================================================

def login_view(request):
    """View đăng nhập tài khoản hệ thống"""
    if request.user.is_authenticated:
        return redirect('home')

    next_url = request.GET.get('next') or request.POST.get('next') or 'home'

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data.get('remember_me')

            # Kiểm tra tài khoản có tồn tại nhưng bị khoá không
            user_check = User.objects.filter(username__iexact=username).first()
            if user_check and not user_check.is_active:
                messages.error(request, "Tài khoản của bạn đã bị khoá. Vui lòng liên hệ Quản trị viên để được mở khoá.")
                return render(request, 'quiz/auth/login.html', {'form': form, 'next': next_url})

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                if remember_me:
                    request.session.set_expiry(1209600)  # 2 tuần
                else:
                    request.session.set_expiry(0)  # Khi đóng trình duyệt

                messages.success(request, f"Đăng nhập thành công! Xin chào, {user.get_full_name() or user.username}.")
                return redirect(next_url)
            else:
                messages.error(request, "Tên đăng nhập hoặc mật khẩu không chính xác.")
    else:
        form = LoginForm()

    return render(request, 'quiz/auth/login.html', {
        'form': form,
        'next': next_url
    })


def logout_view(request):
    """View đăng xuất tài khoản"""
    logout(request)
    messages.info(request, "Bạn đã đăng xuất khỏi hệ thống thành công.")
    return redirect('home')


def register_view(request):
    """View đăng ký tài khoản người dùng thông thường (Học sinh / Thí sinh)"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # Tách họ và tên
            name_parts = full_name.strip().split(' ', 1)
            first_name = name_parts[1] if len(name_parts) > 1 else ''
            last_name = name_parts[0] if len(name_parts) > 1 else full_name

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )

            # Đảm bảo Profile có vai trò là người dùng bình thường ('user')
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = 'user'
            profile.save()

            messages.success(request, "Đăng ký tài khoản thành công! Bạn có thể đăng nhập ngay bây giờ.")
            return redirect('login')
    else:
        form = RegisterForm()

    return render(request, 'quiz/auth/register.html', {'form': form})


@login_required
def profile_view(request):
    """
    Trang quản lý thông tin cá nhân dành cho người dùng đã đăng nhập:
    - Sửa thông tin cá nhân (Họ, Tên, Email)
    - Chọn Avatar có sẵn trong bộ sưu tập (16 avatar)
    - Đổi mật khẩu tài khoản
    - Xem lịch sử các bài thi đã tham gia
    """
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        action = request.POST.get('action')

        # Hành động 1: Cập nhật thông tin cá nhân & Avatar
        if action == 'update_profile':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            avatar = request.POST.get('avatar', '').strip()

            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.save()

            if avatar in VALID_AVATAR_IDS:
                profile.avatar = avatar
                profile.save()

            messages.success(request, "Cập nhật thông tin cá nhân và ảnh đại diện thành công!")
            return redirect('profile')

        # Hành động 2: Đổi mật khẩu
        elif action == 'change_password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not user.check_password(old_password):
                messages.error(request, "Mật khẩu hiện tại không chính xác!")
            elif len(new_password) < 6:
                messages.error(request, "Mật khẩu mới phải có ít nhất 6 ký tự!")
            elif new_password != confirm_password:
                messages.error(request, "Mật khẩu mới và xác nhận mật khẩu không trùng khớp!")
            else:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Thay đổi mật khẩu tài khoản thành công!")
                return redirect('profile')

    my_results = ExamResult.objects.filter(user=user).select_related('quiz', 'quiz__subject').order_by('-completed_at')
    total_exams = my_results.count()
    avg_score = round(sum(r.score for r in my_results) / total_exams, 2) if total_exams > 0 else 0

    context = {
        'profile': profile,
        'preset_avatars': get_preset_avatars_with_urls(),
        'my_results': my_results,
        'total_exams': total_exams,
        'avg_score': avg_score,
    }
    return render(request, 'quiz/auth/profile.html', context)


@login_required
def api_update_avatar(request):
    """API AJAX cập nhật avatar nhanh"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ.'}, status=405)

    avatar = request.POST.get('avatar', '').strip()
    if avatar in VALID_AVATAR_IDS:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.avatar = avatar
        profile.save()
        return JsonResponse({
            'status': 'success',
            'avatar': avatar,
            'avatar_url': profile.avatar_url,
            'message': 'Cập nhật ảnh đại diện thành công!'
        })
    return JsonResponse({'status': 'error', 'message': 'Mã avatar không hợp lệ.'}, status=400)


# =====================================================================
# QUẢN TRỊ NGƯỜI DÙNG (DÀNH CHO ADMIN / QUẢN TRỊ VIÊN)
# =====================================================================

@admin_required
def user_management_view(request):
    """View hiển thị danh sách người dùng, lọc vai trò và tìm kiếm"""
    role_filter = request.GET.get('role', '').strip()
    status_filter = request.GET.get('status', '').strip()
    search_query = request.GET.get('q', '').strip()

    users_qs = User.objects.select_related('profile').all().order_by('-date_joined')

    if role_filter:
        if role_filter == 'admin':
            users_qs = users_qs.filter(Q(is_superuser=True) | Q(profile__role='admin'))
        elif role_filter == 'manager':
            users_qs = users_qs.filter(profile__role='manager', is_superuser=False)
        elif role_filter == 'user':
            users_qs = users_qs.filter(profile__role='user', is_superuser=False)

    if status_filter:
        if status_filter == 'active':
            users_qs = users_qs.filter(is_active=True)
        elif status_filter == 'inactive':
            users_qs = users_qs.filter(is_active=False)

    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    # Thống kê tổng quan
    total_users = User.objects.count()
    total_admins = User.objects.filter(Q(is_superuser=True) | Q(profile__role='admin')).count()
    total_managers = User.objects.filter(profile__role='manager', is_superuser=False).count()
    total_normal_users = User.objects.filter(profile__role='user', is_superuser=False).count()
    total_locked = User.objects.filter(is_active=False).count()

    context = {
        'users': users_qs,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_users': total_users,
        'total_admins': total_admins,
        'total_managers': total_managers,
        'total_normal_users': total_normal_users,
        'total_locked': total_locked,
    }
    return render(request, 'quiz/admin/user_management.html', context)


@admin_required
def update_user_role(request, user_id):
    """API / Action cập nhật vai trò của người dùng (Admin / Manager / User)"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ.'}, status=405)

    target_user = get_object_or_404(User, pk=user_id)
    new_role = request.POST.get('role', '').strip()

    if new_role not in ['admin', 'manager', 'coding_contributor', 'user']:
        return JsonResponse({'status': 'error', 'message': 'Vai trò không hợp lệ.'}, status=400)

    # Bảo vệ an toàn: Admin hiện tại không thể tự hạ quyền của chính mình
    if target_user.id == request.user.id and new_role != 'admin':
        return JsonResponse({
            'status': 'error',
            'message': 'Bạn không thể tự hạ quyền Quản trị viên của chính mình để tránh mất quyền hệ thống!'
        }, status=403)

    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.role = new_role
    profile.save()

    # Đồng bộ hóa với cờ của Django auth
    if new_role == 'admin':
        target_user.is_superuser = True
        target_user.is_staff = True
    elif new_role == 'manager':
        target_user.is_superuser = False
        target_user.is_staff = True
    else:  # user
        target_user.is_superuser = False
        target_user.is_staff = False
    target_user.save()

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    role_name = dict(UserProfile.ROLE_CHOICES).get(new_role, new_role)
    msg = f"Đã chuyển vai trò của người dùng '{target_user.username}' thành '{role_name}'."

    if is_ajax:
        return JsonResponse({
            'status': 'success',
            'message': msg,
            'new_role': new_role,
            'new_role_display': role_name
        })

    messages.success(request, msg)
    return redirect('user_management')


@admin_required
def toggle_user_status(request, user_id):
    """API / Action khoá hoặc mở khoá tài khoản người dùng (is_active)"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ.'}, status=405)

    target_user = get_object_or_404(User, pk=user_id)

    # Bảo vệ an toàn: Admin hiện tại không thể tự khoá chính mình
    if target_user.id == request.user.id:
        return JsonResponse({
            'status': 'error',
            'message': 'Bạn không thể tự khoá tài khoản của chính mình!'
        }, status=403)

    # Đảo trạng thái hoạt động
    target_user.is_active = not target_user.is_active
    target_user.save()

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    status_text = "Mở khoá" if target_user.is_active else "Khoá"
    msg = f"Đã {status_text.lower()} tài khoản '{target_user.username}' thành công."

    if is_ajax:
        return JsonResponse({
            'status': 'success',
            'message': msg,
            'is_active': target_user.is_active,
            'status_text': status_text
        })

    messages.success(request, msg)
    return redirect('user_management')


@admin_required
def admin_reset_user_password(request, user_id):
    """API / Action cho phép Quản trị viên đổi / reset mật khẩu mới cho người dùng"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ.'}, status=405)

    target_user = get_object_or_404(User, pk=user_id)

    # Lấy mật khẩu mới từ POST form hoặc JSON body
    new_password = request.POST.get('new_password', '').strip()
    if not new_password and request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            new_password = data.get('new_password', '').strip()
        except Exception:
            pass

    if not new_password:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập mật khẩu mới!'}, status=400)

    if len(new_password) < 6:
        return JsonResponse({'status': 'error', 'message': 'Mật khẩu mới phải có ít nhất 6 ký tự!'}, status=400)

    target_user.set_password(new_password)
    target_user.save()

    # Nếu tự đổi mật khẩu cho chính mình, duy trì session không bị out
    if target_user.id == request.user.id:
        update_session_auth_hash(request, target_user)

    msg = f"Đã đặt lại mật khẩu mới cho tài khoản '{target_user.username}' thành công!"

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'
    if not is_ajax and not request.POST.get('is_ajax'):
        messages.success(request, msg)
        return redirect('user_management')

    return JsonResponse({
        'status': 'success',
        'message': msg
    })


# =====================================================================
# QUẢN LÝ NGÂN HÀNG ĐỀ & THÊM CÂU HỎI THỦ CÔNG (DÀNH CHO QUẢN LÝ & ADMIN)
# =====================================================================

@manager_required
def manage_question_bank(request):
    """
    Trang Quản lý Ngân hàng đề:
    Cho phép Quản lý/Admin xem và tạo nhanh Kỳ thi (ExamPeriod), Môn thi (Subject), Chủ đề (Topic)
    trực tiếp trên giao diện mà không cần vào Django admin.
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_period':
            name = request.POST.get('period_name', '').strip()
            desc = request.POST.get('period_desc', '').strip()
            if name:
                ExamPeriod.objects.create(name=name, description=desc)
                messages.success(request, f"Đã thêm kỳ thi: {name}")
            else:
                messages.error(request, "Vui lòng nhập tên kỳ thi.")

        elif action == 'add_subject':
            period_id = request.POST.get('subject_period_id')
            name = request.POST.get('subject_name', '').strip()
            code = request.POST.get('subject_code', '').strip()
            if period_id and name and code:
                period = get_object_or_404(ExamPeriod, pk=period_id)
                Subject.objects.create(exam_period=period, name=name, code=code)
                messages.success(request, f"Đã thêm môn thi: {name} ({code})")
            else:
                messages.error(request, "Vui lòng nhập đầy đủ thông tin môn thi.")

        elif action == 'add_topic':
            subject_id = request.POST.get('topic_subject_id')
            name = request.POST.get('topic_name', '').strip()
            if subject_id and name:
                subj = get_object_or_404(Subject, pk=subject_id)
                Topic.objects.create(subject=subj, name=name)
                messages.success(request, f"Đã thêm chủ đề: {name}")
            else:
                messages.error(request, "Vui lòng nhập đầy đủ thông tin chủ đề.")

        return redirect('manage_question_bank')

    periods = ExamPeriod.objects.prefetch_related('subjects__topics').all().order_by('-id')
    subjects = Subject.objects.select_related('exam_period').annotate(q_count=Count('question_bank')).order_by('name')
    total_questions = QuestionBank.objects.count()

    context = {
        'periods': periods,
        'subjects': subjects,
        'total_questions': total_questions,
    }
    return render(request, 'quiz/manage_question_bank.html', context)


@manager_required
def add_question(request):
    """
    Thêm từng câu hỏi vào ngân hàng câu hỏi bằng Form thủ công.
    Hỗ trợ 3 loại:
      - SINGLE: Trắc nghiệm 1 đáp án đúng (4 lựa chọn A, B, C, D)
      - TF: Đúng/Sai (4 ý a, b, c, d với lựa chọn Đúng hoặc Sai cho mỗi ý)
      - NUMERIC: Trả lời ngắn dạng Số thực
    """
    exam_periods = ExamPeriod.objects.all().order_by('name')
    subjects = Subject.objects.select_related('exam_period').all().order_by('name')
    topics = Topic.objects.select_related('subject').all().order_by('name')

    if request.method == 'POST':
        subject_id = request.POST.get('subject_id')
        topic_id = request.POST.get('topic_id')
        difficulty = request.POST.get('difficulty', 'NB')
        question_type = request.POST.get('question_type', 'SINGLE')
        question_text = request.POST.get('question_text', '').strip()
        exact_numeric_answer = request.POST.get('exact_numeric_answer', '').strip()
        image_file = request.FILES.get('image')

        if not subject_id or not question_text:
            messages.error(request, "Vui lòng chọn môn thi và nhập nội dung câu hỏi.")
        else:
            subject = get_object_or_404(Subject, pk=subject_id)
            topic = Topic.objects.filter(pk=topic_id).first() if topic_id else None

            # Tạo câu hỏi
            q_obj = QuestionBank.objects.create(
                subject=subject,
                topic=topic,
                difficulty=difficulty,
                question_type=question_type,
                question_text=question_text,
                exact_numeric_answer=exact_numeric_answer if question_type == 'NUMERIC' else None,
                image=image_file
            )

            # Lưu các phương án đáp án tùy theo loại câu hỏi
            if question_type == 'SINGLE':
                # Nhận 4 phương án choice_text_0 -> 3 và correct_choice
                correct_idx = request.POST.get('correct_choice', '0')
                for i in range(4):
                    c_text = request.POST.get(f'single_choice_{i}', '').strip()
                    if c_text:
                        is_corr = (str(i) == str(correct_idx))
                        BankChoice.objects.create(
                            question=q_obj,
                            choice_text=c_text,
                            is_correct=is_corr
                        )
            elif question_type == 'TF':
                # Nhận 4 ý tf_choice_text_0 -> 3 và tf_correct_0 -> 3 ('true'/'false')
                for i in range(4):
                    c_text = request.POST.get(f'tf_choice_{i}', '').strip()
                    if c_text:
                        is_corr = (request.POST.get(f'tf_correct_{i}') == 'true')
                        BankChoice.objects.create(
                            question=q_obj,
                            choice_text=c_text,
                            is_correct=is_corr
                        )

            messages.success(request, f"Đã thêm thành công câu hỏi mới [ID #{q_obj.id}] vào môn {subject.name}!")
            if 'save_and_add_another' in request.POST:
                return redirect(f"/them-cau-hoi/?subject_id={subject.id}&topic_id={topic_id or ''}")
            return redirect('import_word')

    context = {
        'exam_periods': exam_periods,
        'subjects': subjects,
        'topics': topics,
        'selected_subject_id': request.GET.get('subject_id', ''),
        'selected_topic_id': request.GET.get('topic_id', ''),
    }
    return render(request, 'quiz/add_question.html', context)


# =====================================================================
# CÁC VIEW HỆ THỐNG CƠ BẢN
# =====================================================================

def home_page(request):
    context = {
        'title': 'Hệ thống thi trực tuyến & chấm phiếu bài làm trắc nghiệm',
        'teacher_name':'Trịnh Văn Thành'
    }
    return render(request,'quiz/home.html',context)


def online_exam(request):
    """Trang danh sách các bài thi trực tuyến đang mở cho thí sinh."""
    quizzes = Quiz.objects.select_related('subject', 'subject__exam_period').prefetch_related('matrix_entries', 'quiz_questions').all().order_by('-id')
    quizzes_data = []
    for q in quizzes:
        q_count = q.quiz_questions.count()
        if q_count == 0:
            q_count = sum(e.quantity for e in q.matrix_entries.all())
        quizzes_data.append({
            'quiz': q,
            'question_count': q_count,
        })
    return render(request, 'quiz/online_exam.html', {'quizzes_data': quizzes_data})


def enter_exam_code(request):
    """
    Trang/Endpoint tiếp nhận mã bài thi 6 số từ thí sinh.
    - Tìm kiếm bài thi theo exam_code (hoặc ID nếu nhập số cũ).
    - Nếu tìm thấy -> chuyển hướng vào /thi/<exam_code>/.
    - Nếu không tìm thấy -> thông báo lỗi trực quan.
    """
    code = (request.GET.get('code') or request.POST.get('exam_code') or request.POST.get('code') or '').strip()
    error_msg = None

    if code:
        quiz = Quiz.objects.filter(exam_code=code).first()
        if not quiz and code.isdigit():
            quiz = Quiz.objects.filter(pk=int(code)).first()

        if quiz:
            return redirect('take_exam', exam_code=quiz.exam_code)
        else:
            error_msg = f"Mã bài thi [{code}] không tồn tại trong hệ thống. Vui lòng kiểm tra lại!"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({'valid': False, 'message': error_msg})

    if request.method == 'POST' and error_msg:
        messages.error(request, error_msg)

    return render(request, 'quiz/enter_code.html', {'error_msg': error_msg, 'code': code})


def take_exam(request, exam_code):
    """
    Trang làm bài thi trực tuyến dành cho thí sinh (qua mã đề thi 6 số hoặc quét mã QR).
    - Tra cứu Quiz theo exam_code (hỗ trợ dự phòng ID số).
    - Kiểm tra thời gian bắt đầu làm bài (start_time do người tạo quy định).
    - Kiểm tra hạn nộp bài (deadline).
    - Nếu thí sinh đã đăng nhập: lấy tên từ User.
    - Nếu thí sinh chưa đăng nhập: yêu cầu nhập đầy đủ Họ và tên trước khi cho phép làm bài.
    """
    quiz = Quiz.objects.select_related('subject', 'subject__exam_period').filter(exam_code=exam_code).first()
    if not quiz and exam_code.isdigit():
        quiz = Quiz.objects.select_related('subject', 'subject__exam_period').filter(pk=int(exam_code)).first()
        if quiz:
            return redirect('take_exam', exam_code=quiz.exam_code)

    if not quiz:
        messages.error(request, f"Không tìm thấy bài thi với mã: {exam_code}. Vui lòng nhập mã đề thi hợp lệ!")
        return redirect('enter_exam_code')

    now = timezone.now()
    is_before_start = False
    is_expired = False
    seconds_until_start = 0

    if quiz.start_time and now < quiz.start_time:
        is_before_start = True
        seconds_until_start = max(0, int((quiz.start_time - now).total_seconds()))

    if quiz.deadline and now > quiz.deadline:
        is_expired = True

    # Đảm bảo bài thi có câu hỏi trong QuizQuestion
    quiz_questions = quiz.quiz_questions.select_related('bank_question', 'bank_question__topic').prefetch_related('bank_question__choices').order_by('order')

    if not quiz_questions.exists():
        # Bốc câu hỏi tự động theo ma trận đề thi
        entries = quiz.matrix_entries.filter(quantity__gt=0)
        questions_pool = []
        for entry in entries:
            qs = QuestionBank.objects.filter(
                subject=quiz.subject,
                difficulty=entry.difficulty,
                question_type=entry.question_type,
                parent_group__isnull=True
            )
            if entry.topic:
                qs = qs.filter(topic=entry.topic)
            available = list(qs)
            if len(available) >= entry.quantity:
                questions_pool.extend(random.sample(available, entry.quantity))
            else:
                questions_pool.extend(available)

        # Fallback nếu ma trận rỗng hoặc chưa đủ câu
        if not questions_pool:
            questions_pool = list(QuestionBank.objects.filter(subject=quiz.subject).order_by('?')[:20])

        random.shuffle(questions_pool)
        for idx, q_bank in enumerate(questions_pool, start=1):
            QuizQuestion.objects.create(quiz=quiz, bank_question=q_bank, order=idx)

        quiz_questions = quiz.quiz_questions.select_related('bank_question', 'bank_question__topic').prefetch_related('bank_question__choices').order_by('order')

    user_full_name = ""
    if request.user.is_authenticated:
        user_full_name = request.user.get_full_name() or request.user.username

    context = {
        'quiz': quiz,
        'quiz_questions': quiz_questions,
        'total_questions': quiz_questions.count(),
        'user_full_name': user_full_name,
        'is_logged_in': request.user.is_authenticated,
        'is_before_start': is_before_start,
        'is_expired': is_expired,
        'seconds_until_start': seconds_until_start,
        'start_time_iso': quiz.start_time.isoformat() if quiz.start_time else '',
        'deadline_iso': quiz.deadline.isoformat() if quiz.deadline else '',
    }
    return render(request, 'quiz/take_exam.html', context)


def submit_exam(request, exam_code):
    """
    Xử lý nộp bài thi, chấm điểm tự động và lưu kết quả (ExamResult).
    Nếu chưa đăng nhập: BẮT BUỘC phải có Họ và tên thí sinh mới cho nộp/chấm điểm.
    """
    quiz = Quiz.objects.filter(exam_code=exam_code).first()
    if not quiz and exam_code.isdigit():
        quiz = Quiz.objects.filter(pk=int(exam_code)).first()

    if not quiz:
        messages.error(request, f"Không tìm thấy bài thi với mã: {exam_code}")
        return redirect('home')

    if request.method != 'POST':
        return redirect('take_exam', exam_code=quiz.exam_code)

    # 1. Xác thực thông tin thí sinh
    if request.user.is_authenticated:
        candidate_name = request.user.get_full_name() or request.user.username
        user = request.user
    else:
        candidate_name = request.POST.get('candidate_name', '').strip()
        user = None
        if not candidate_name:
            messages.error(request, "Vui lòng nhập đầy đủ Họ và tên thí sinh để hoàn thành bài thi!")
            return redirect('take_exam', exam_code=quiz.exam_code)

    time_spent = 0
    try:
        time_spent = int(request.POST.get('time_spent', 0))
    except (ValueError, TypeError):
        time_spent = 0

    # 2. Lấy danh sách câu hỏi và chấm điểm
    quiz_questions = quiz.quiz_questions.select_related('bank_question').prefetch_related('bank_question__choices').order_by('order')
    
    total_score = 0.0
    correct_count = 0
    total_questions = quiz_questions.count()
    detailed_results = []

    for qq in quiz_questions:
        q = qq.bank_question
        q_type = q.question_type
        is_correct_q = False
        q_score = 0.0

        if q_type == 'SINGLE':
            selected_choice_id = request.POST.get(f'q_{qq.id}_single')
            user_choice = None
            correct_choice = None
            for c in q.choices.all():
                if c.is_correct:
                    correct_choice = c
                if selected_choice_id and str(c.id) == str(selected_choice_id):
                    user_choice = c

            if user_choice and user_choice.is_correct:
                is_correct_q = True
                q_score = quiz.score_single
                correct_count += 1
            total_score += q_score

            detailed_results.append({
                'order': qq.order,
                'question': q,
                'type': 'SINGLE',
                'user_choice': user_choice,
                'correct_choice': correct_choice,
                'is_correct': is_correct_q,
                'score_earned': q_score
            })

        elif q_type == 'TF':
            tf_correct_sub = 0
            choices_detail = []
            for c in q.choices.all():
                user_tf = request.POST.get(f'q_{qq.id}_choice_{c.id}')
                expected_tf = 'true' if c.is_correct else 'false'
                is_sub_correct = (user_tf == expected_tf)
                if is_sub_correct:
                    tf_correct_sub += 1
                choices_detail.append({
                    'choice': c,
                    'user_ans': user_tf,
                    'expected_ans': expected_tf,
                    'is_correct': is_sub_correct
                })

            if tf_correct_sub == 4:
                q_score = quiz.score_tf
                is_correct_q = True
                correct_count += 1
            elif tf_correct_sub == 3:
                q_score = quiz.score_tf * 0.5
            elif tf_correct_sub == 2:
                q_score = quiz.score_tf * 0.25
            elif tf_correct_sub == 1:
                q_score = quiz.score_tf * 0.1
            else:
                q_score = 0.0

            total_score += q_score
            detailed_results.append({
                'order': qq.order,
                'question': q,
                'type': 'TF',
                'choices_detail': choices_detail,
                'sub_correct': tf_correct_sub,
                'is_correct': is_correct_q,
                'score_earned': q_score
            })

        elif q_type == 'NUMERIC':
            user_num = request.POST.get(f'q_{qq.id}_numeric', '').strip()
            exact_num = (q.exact_numeric_answer or '').strip()

            def normalize_num(val):
                try:
                    return float(val.replace(',', '.'))
                except (ValueError, AttributeError):
                    return None

            u_float = normalize_num(user_num)
            e_float = normalize_num(exact_num)

            if u_float is not None and e_float is not None and abs(u_float - e_float) <= 0.001:
                is_correct_q = True
                q_score = quiz.score_numeric
                correct_count += 1
            total_score += q_score

            detailed_results.append({
                'order': qq.order,
                'question': q,
                'type': 'NUMERIC',
                'user_num': user_num,
                'exact_num': exact_num,
                'is_correct': is_correct_q,
                'score_earned': q_score
            })

    final_score = round(min(total_score, 10.0), 2)

    # Lấy avatar của thí sinh (nếu đã đăng nhập lấy từ profile, nếu là khách lấy từ form hoặc mặc định)
    candidate_avatar = 'avatar-1'
    if user and hasattr(user, 'profile') and user.profile.avatar:
        candidate_avatar = user.profile.avatar
    else:
        candidate_avatar = request.POST.get('candidate_avatar', 'avatar-1')
        if candidate_avatar not in VALID_AVATAR_IDS:
            candidate_avatar = 'avatar-1'

    # 3. Lưu kết quả vào CSDL
    result = ExamResult.objects.create(
        user=user,
        candidate_name=candidate_name,
        candidate_avatar=candidate_avatar,
        quiz=quiz,
        score=final_score,
        total_questions=total_questions,
        correct_count=correct_count,
        time_spent=time_spent
    )

    minutes_spent = time_spent // 60
    seconds_spent = time_spent % 60

    context = {
        'quiz': quiz,
        'result': result,
        'candidate_name': candidate_name,
        'final_score': final_score,
        'correct_count': correct_count,
        'total_questions': total_questions,
        'minutes_spent': minutes_spent,
        'seconds_spent': seconds_spent,
        'detailed_results': detailed_results,
    }
    return render(request, 'quiz/exam_result.html', context)


def scan_sheet(request):
    context = {}
    if request.method == 'POST' and request.FILES.get('exam_image'):
        file_uploaded = request.FILES['exam_image']
        file_bytes = np.frombuffer(file_uploaded.read(), np.uint8)
        img_original = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        # Xử lý OpenCV cơ bản
        img_gray = cv2.cvtColor(img_original, cv2.COLOR_BGR2GRAY)
        img_blur = cv2.GaussianBlur(img_gray, (5, 5), 0)
        _, img_thresh = cv2.threshold(img_blur, 150, 255, cv2.THRESH_BINARY_INV)

        # Mã hóa Base64 để hiển thị
        _, buffer_orig = cv2.imencode('.jpg', img_original)
        string_orig = base64.b64encode(buffer_orig).decode('utf-8')
        
        _, buffer_thresh = cv2.imencode('.jpg', img_thresh)
        string_thresh = base64.b64encode(buffer_thresh).decode('utf-8')
        
        context['original_image'] = string_orig
        context['processed_image'] = string_thresh

    return render(request, 'quiz/scan_sheet.html', context)


@manager_required
def import_word_questions(request):
    # Existing import_word view remains unchanged
    """
    View xử lý tải lên file Word, xem trước (Preview) danh sách câu hỏi trích xuất,
    xác nhận lưu vào Ngân hàng câu hỏi (QuestionBank), và hiển thị/lọc danh sách câu hỏi đã lưu.
    """
    exam_periods = ExamPeriod.objects.all().order_by('name')
    subjects = Subject.objects.select_related('exam_period').all().order_by('name')
    topics = Topic.objects.select_related('subject').all().order_by('name')

    # Dữ liệu JSON hỗ trợ liên kết động 3 cấp trên JavaScript (ExamPeriod -> Subject -> Topic)
    subjects_data = [
        {'id': s.id, 'name': s.name, 'code': s.code, 'exam_period_id': s.exam_period_id, 'exam_period_name': s.exam_period.name}
        for s in subjects
    ]
    topics_data = [
        {'id': t.id, 'name': t.name, 'subject_id': t.subject_id}
        for t in topics
    ]

    # Nhận tham số lọc danh sách câu hỏi đã có trong CSDL
    filter_period_id = request.GET.get('filter_period_id') or request.POST.get('filter_period_id') or ''
    filter_subject_id = request.GET.get('filter_subject_id') or request.POST.get('filter_subject_id') or ''
    filter_topic_id = request.GET.get('filter_topic_id') or request.POST.get('filter_topic_id') or ''
    filter_difficulty = request.GET.get('filter_difficulty') or request.POST.get('filter_difficulty') or ''
    filter_question_type = request.GET.get('filter_question_type') or request.POST.get('filter_question_type') or ''

    # Lọc danh sách câu hỏi trong Ngân hàng
    saved_questions_qs = QuestionBank.objects.select_related('subject', 'subject__exam_period', 'topic').prefetch_related('choices').order_by('-id')

    if filter_period_id and filter_period_id.isdigit():
        saved_questions_qs = saved_questions_qs.filter(subject__exam_period_id=int(filter_period_id))
    if filter_subject_id and filter_subject_id.isdigit():
        saved_questions_qs = saved_questions_qs.filter(subject_id=int(filter_subject_id))
    if filter_topic_id and filter_topic_id.isdigit():
        saved_questions_qs = saved_questions_qs.filter(topic_id=int(filter_topic_id))
    if filter_difficulty:
        saved_questions_qs = saved_questions_qs.filter(difficulty=filter_difficulty)
    if filter_question_type:
        saved_questions_qs = saved_questions_qs.filter(question_type=filter_question_type)

    selected_period_id = None
    selected_subject_id = None
    selected_topic_id = None

    context = {
        'exam_periods': exam_periods,
        'subjects': subjects,
        'topics': topics,
        'subjects_json': json.dumps(subjects_data, ensure_ascii=False),
        'topics_json': json.dumps(topics_data, ensure_ascii=False),
        'parsed_questions': None,
        'selected_period_id': selected_period_id,
        'selected_subject_id': selected_subject_id,
        'selected_topic_id': selected_topic_id,
        'saved_questions': saved_questions_qs[:100],  # Hiển thị tối đa 100 câu mới nhất
        'total_saved_count': saved_questions_qs.count(),
        'filter_period_id': filter_period_id,
        'filter_subject_id': filter_subject_id,
        'filter_topic_id': filter_topic_id,
        'filter_difficulty': filter_difficulty,
        'filter_question_type': filter_question_type,
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'parse':
            period_id = request.POST.get('exam_period_id')
            subject_id = request.POST.get('subject_id')
            topic_id = request.POST.get('topic_id')
            word_file = request.FILES.get('word_file')

            context['selected_period_id'] = int(period_id) if period_id and period_id.isdigit() else None
            context['selected_subject_id'] = int(subject_id) if subject_id and subject_id.isdigit() else None
            context['selected_topic_id'] = int(topic_id) if topic_id and topic_id.isdigit() else None

            if not subject_id:
                messages.error(request, 'Vui lòng chọn Môn học trước khi tải file!')
                return render(request, 'quiz/import_word.html', context)

            if not word_file or not word_file.name.endswith('.docx'):
                messages.error(request, 'File không đúng định dạng. Vui lòng tải lên file Word có đuôi .docx!')
                return render(request, 'quiz/import_word.html', context)

            try:
                file_buffer = io.BytesIO(word_file.read())
                questions = parse_docx_bytes(file_buffer)
                
                if not questions:
                    messages.warning(request, 'Không tìm thấy câu hỏi nào hợp lệ trong file Word.')
                else:
                    messages.success(request, f'Đã phân tích thành công {len(questions)} câu hỏi từ file Word. Vui lòng kiểm tra lại trước khi lưu.')

                context['parsed_questions'] = questions
                context['parsed_questions_json'] = json.dumps(questions, ensure_ascii=False)
                context['count_single'] = sum(1 for q in questions if q.get('question_type') == 'SINGLE')
                context['count_tf'] = sum(1 for q in questions if q.get('question_type') == 'TF')
                context['count_numeric'] = sum(1 for q in questions if q.get('question_type') == 'NUMERIC')

            except Exception as e:
                messages.error(request, f'Lỗi khi xử lý file Word: {str(e)}')

        elif action == 'confirm_save':
            period_id = request.POST.get('exam_period_id')
            subject_id = request.POST.get('subject_id')
            topic_id = request.POST.get('topic_id')
            questions_json = request.POST.get('questions_json')

            context['selected_period_id'] = int(period_id) if period_id and period_id.isdigit() else None
            context['selected_subject_id'] = int(subject_id) if subject_id and subject_id.isdigit() else None
            context['selected_topic_id'] = int(topic_id) if topic_id and topic_id.isdigit() else None

            if not subject_id or not questions_json:
                messages.error(request, 'Dữ liệu môn học hoặc câu hỏi không hợp lệ để lưu!')
                return render(request, 'quiz/import_word.html', context)

            try:
                from django.core.files.base import ContentFile
                subject = Subject.objects.get(id=subject_id)
                topic = Topic.objects.filter(id=topic_id).first() if topic_id else None
                questions_data = json.loads(questions_json)

                count = 0
                with transaction.atomic():
                    # Lưu tạm các object đã tạo để map parent
                    saved_objs = {}
                    
                    for idx, q in enumerate(questions_data):
                        # Lấy parent object nếu có
                        parent_obj = None
                        if 'parent_group_idx' in q and q['parent_group_idx'] in saved_objs:
                            parent_obj = saved_objs[q['parent_group_idx']]
                            
                        q_obj = QuestionBank.objects.create(
                            subject=subject,
                            topic=topic,
                            question_text=q.get('question_text', ''),
                            difficulty=q.get('difficulty', 'NB'),
                            question_type=q.get('question_type', 'SINGLE'),
                            is_public=True,
                            exact_numeric_answer=q.get('exact_numeric_answer', ''),
                            parent_group=parent_obj
                        )
                        saved_objs[idx] = q_obj

                        # Lưu file ảnh nếu có
                        img_b64 = q.get('image_raw') or q.get('image_base64')
                        if img_b64:
                            if ',' in img_b64:
                                img_b64 = img_b64.split(',', 1)[1]
                            try:
                                img_bytes = base64.b64decode(img_b64)
                                ext = q.get('image_ext', 'png')
                                filename = f"q_{q_obj.id}.{ext}"
                                q_obj.image.save(filename, ContentFile(img_bytes), save=True)
                            except Exception as img_err:
                                print(f"Error saving question image: {img_err}")

                        for c in q.get('choices', []):
                            BankChoice.objects.create(
                                question=q_obj,
                                choice_text=c.get('choice_text', ''),
                                is_correct=c.get('is_correct', False)
                            )
                        count += 1

                messages.success(request, f'🎉 Nhập thành công {count} câu hỏi vào Ngân hàng câu hỏi cho môn "{subject.name}"!')
                return redirect(f"{request.path}?filter_subject_id={subject.id}")

            except Exception as e:
                messages.error(request, f'Lỗi khi lưu câu hỏi vào CSDL: {str(e)}')
                if questions_json:
                    try:
                        context['parsed_questions'] = json.loads(questions_json)
                        context['parsed_questions_json'] = questions_json
                    except Exception:
                        pass

    return render(request, 'quiz/import_word.html', context)


@manager_required
def edit_question(request, question_id):
    """Edit an existing QuestionBank entry and its choices."""
    question = get_object_or_404(QuestionBank, pk=question_id)

    if request.method == "POST":
        form = QuestionBankForm(request.POST, request.FILES, instance=question)
        formset = BankChoiceFormSet(request.POST, instance=question)

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'Cập nhật câu hỏi thành công!'})
            messages.success(request, "Cập nhật câu hỏi thành công.")
            return redirect('import_word')
        else:
            # Collect errors
            errors = []
            for field, errs in form.errors.items():
                for e in errs:
                    errors.append(f"{form.fields[field].label if field in form.fields else field}: {e}")
            for i, f_errors in enumerate(formset.errors):
                for field, errs in f_errors.items():
                    for e in errs:
                        errors.append(f"Phương án {i+1}: {e}")
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': 'Dữ liệu không hợp lệ.', 'errors': errors}, status=400)
    else:
        form = QuestionBankForm(instance=question)
        formset = BankChoiceFormSet(instance=question)

    return render(request, 'quiz/edit_question.html', {
        'form': form,
        'formset': formset,
        'question': question,
    })


@manager_required
def download_sample_word(request):
    """
    View tạo và tải về file Word mẫu cho giáo viên
    """
    buffer = generate_sample_docx()
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = 'attachment; filename="Mau_Cau_Hoi_SmartQuiz.docx"'
    return response


def generate_random_quiz_by_matrix(subject_id, title, duration, num_single, num_tf, num_numeric):
    """
    Hàm tạo tự động 1 Đề thi từ Ngân hàng câu hỏi dựa trên ma trận số lượng
    num_single: Số câu Chọn 1 đáp án (Loại 1)
    num_tf: Số câu Đúng/Sai (Loại 2)
    num_numeric: Số câu Trả lời số thực (Loại 3)
    """
    subject = Subject.objects.get(id=subject_id)
    
    # 1. Khởi tạo một vỏ đề thi mới (Mã đề)
    new_quiz = Quiz.objects.create(
        subject=subject,
        title=title,
        duration=duration
    )
    
    # 2. Bốc ngẫu nhiên câu hỏi từ ngân hàng theo từng loại câu hỏi
    # Lệnh .order_by('?') trong Django tương đương với bốc RANDOM ngẫu nhiên các dòng
    questions_type_1 = QuestionBank.objects.filter(subject=subject, question_type='SINGLE', parent_group__isnull=True).order_by('?')[:num_single]
    questions_type_2 = QuestionBank.objects.filter(subject=subject, question_type='TF', parent_group__isnull=True).order_by('?')[:num_tf]
    questions_type_3 = QuestionBank.objects.filter(subject=subject, question_type='NUMERIC', parent_group__isnull=True).order_by('?')[:num_numeric]
    
    # 3. Gộp toàn bộ danh sách câu hỏi đã bốc được
    all_selected_questions = list(questions_type_1) + list(questions_type_2) + list(questions_type_3)
    
    # Xáo trộn thứ tự các câu hỏi này một lần nữa để tránh việc các câu cùng loại nằm liền nhau
    random.shuffle(all_selected_questions)
    
    # 4. Lưu danh sách câu hỏi này vào Đề thi chính thức với số thứ tự (Câu 1, Câu 2, Câu 3...)
    for index, q_bank in enumerate(all_selected_questions, start=1):
        QuizQuestion.objects.create(
            quiz=new_quiz,
            bank_question=q_bank,
            order=index
        )
        
    return new_quiz


from .models import ExamMatrixEntry, ExamMatrixTopicSpec
from django.db.models import Count


@manager_required
def get_matrix_data(request):
    """API trả JSON: danh sách chủ đề + số câu có sẵn theo subject_id."""
    subject_id = request.GET.get('subject_id')
    if not subject_id:
        return JsonResponse({'topics': [], 'counts': {}})

    topics = list(Topic.objects.filter(subject_id=subject_id).values('id', 'name').order_by('name'))

    # Đếm số câu hỏi có sẵn theo topic × difficulty × question_type
    counts_qs = (
        QuestionBank.objects
        .filter(subject_id=subject_id)
        .values('topic_id', 'difficulty', 'question_type')
        .annotate(count=Count('id'))
    )
    counts = {}
    for row in counts_qs:
        key = f"{row['topic_id'] or 'none'}_{row['difficulty']}_{row['question_type']}"
        counts[key] = row['count']

    return JsonResponse({'topics': topics, 'counts': counts})


@manager_required
def create_exam(request):
    """View lưu ma trận đề thi (không bốc câu hỏi — hệ thống tự bốc khi thí sinh làm bài)."""
    exam_periods = ExamPeriod.objects.all().order_by('name')
    subjects = Subject.objects.select_related('exam_period').all().order_by('name')

    subjects_data = [
        {'id': s.id, 'name': s.name, 'code': s.code, 'exam_period_id': s.exam_period_id}
        for s in subjects
    ]

    auto_exam_code = generate_unique_exam_code()

    context = {
        'exam_periods': exam_periods,
        'subjects': subjects,
        'subjects_json': json.dumps(subjects_data, ensure_ascii=False),
        'auto_exam_code': auto_exam_code,
    }

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        subject_id = request.POST.get('subject_id')
        title = request.POST.get('title', '').strip()
        exam_code = request.POST.get('exam_code', '').strip() or auto_exam_code
        duration = request.POST.get('duration', '45')
        start_time = request.POST.get('start_time', '').strip()
        deadline = request.POST.get('deadline', '').strip()
        score_single = request.POST.get('score_single', '0.25')
        score_tf = request.POST.get('score_tf', '1.0')
        score_numeric = request.POST.get('score_numeric', '0.5')
        matrix_json = request.POST.get('matrix_json', '[]')
        topic_specs_json = request.POST.get('topic_specs_json', '[]')

        # Validate
        errors = []
        if not subject_id:
            errors.append('Vui lòng chọn môn thi.')
        if not title:
            errors.append('Vui lòng nhập tiêu đề đề thi.')
        if not exam_code:
            exam_code = auto_exam_code
        elif Quiz.objects.filter(exam_code=exam_code).exists():
            errors.append(f'Mã bài thi "{exam_code}" đã tồn tại. Vui lòng chọn mã khác.')

        try:
            duration_val = int(duration)
        except ValueError:
            errors.append('Thời gian làm bài phải là số nguyên.')
            duration_val = 45

        try:
            matrix_data = json.loads(matrix_json)
        except json.JSONDecodeError:
            errors.append('Dữ liệu ma trận không hợp lệ.')
            matrix_data = []

        try:
            topic_specs_data = json.loads(topic_specs_json)
        except json.JSONDecodeError:
            topic_specs_data = []

        # Lọc chỉ giữ entry có quantity > 0
        matrix_data = [e for e in matrix_data if e.get('quantity', 0) > 0]

        if not matrix_data:
            errors.append('Ma trận đề trống. Vui lòng nhập ít nhất 1 ô có số câu > 0.')

        # Kiểm tra ngân hàng có đủ câu không
        shortage_errors = []
        for entry in matrix_data:
            qty = entry.get('quantity', 0)
            topic_id = entry.get('topic_id')
            diff = entry.get('difficulty')
            qtype = entry.get('question_type')

            qs = QuestionBank.objects.filter(
                subject_id=subject_id,
                difficulty=diff,
                question_type=qtype
            )
            if topic_id:
                qs = qs.filter(topic_id=topic_id)
            available = qs.count()
            if available < qty:
                topic_name = Topic.objects.filter(id=topic_id).values_list('name', flat=True).first() or 'Không chủ đề'
                diff_display = dict(QuestionBank.DIFFICULTY_CHOICES).get(diff, diff)
                type_display = dict(QuestionBank.TYPE_CHOICES).get(qtype, qtype)
                shortage_errors.append(
                    f"{topic_name} | {diff_display} | {type_display}: cần {qty}, có {available}"
                )

        if shortage_errors:
            errors.append('Ngân hàng không đủ câu hỏi:')
            errors.extend(shortage_errors)

        if errors:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': errors}, status=400)
            for e in errors:
                messages.error(request, e)
            return render(request, 'quiz/create_exam.html', context)

        # Lưu ma trận đề (KHÔNG bốc câu hỏi)
        try:
            from datetime import datetime as dt
            start_time_dt = None
            if start_time:
                try:
                    start_time_dt = dt.fromisoformat(start_time)
                except ValueError:
                    pass

            deadline_dt = None
            if deadline:
                try:
                    deadline_dt = dt.fromisoformat(deadline)
                except ValueError:
                    pass

            with transaction.atomic():
                quiz = Quiz.objects.create(
                    subject_id=subject_id,
                    title=title,
                    exam_code=exam_code,
                    duration=duration_val,
                    start_time=start_time_dt,
                    deadline=deadline_dt,
                    score_single=float(score_single),
                    score_tf=float(score_tf),
                    score_numeric=float(score_numeric),
                )

                # Lưu ma trận
                total_questions = 0
                for entry in matrix_data:
                    ExamMatrixEntry.objects.create(
                        quiz=quiz,
                        topic_id=entry.get('topic_id') or None,
                        difficulty=entry['difficulty'],
                        question_type=entry['question_type'],
                        quantity=entry['quantity'],
                    )
                    total_questions += entry['quantity']

                # Lưu đặc tả chủ đề
                for spec in topic_specs_data:
                    topic_id = spec.get('topic_id')
                    desc = spec.get('description', '').strip()
                    if topic_id and desc:
                        ExamMatrixTopicSpec.objects.create(
                            quiz=quiz,
                            topic_id=topic_id,
                            description=desc,
                        )

            result = {
                'status': 'success',
                'message': f'Lưu ma trận đề "{title}" thành công! ({total_questions} câu hỏi sẽ được bốc ngẫu nhiên khi thí sinh làm bài)',
                'quiz_id': quiz.id,
                'exam_code': quiz.exam_code,
                'total_questions': total_questions,
                'export_word_url': f'/xuat-ma-tran-word/{quiz.id}/',
                'export_excel_url': f'/xuat-ma-tran-excel/{quiz.id}/',
            }

            if is_ajax:
                return JsonResponse(result)
            messages.success(request, result['message'])
            return render(request, 'quiz/create_exam.html', context)

        except Exception as e:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': [str(e)]}, status=500)
            messages.error(request, f'Lỗi khi lưu ma trận: {str(e)}')

    return render(request, 'quiz/create_exam.html', context)


@manager_required
def export_matrix_word(request, quiz_id):
    """Xuất ma trận đề ra file Word."""
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    quiz = get_object_or_404(Quiz, pk=quiz_id)
    entries = quiz.matrix_entries.select_related('topic').all()

    # Lấy danh sách topics và difficulties
    topics = list(set(e.topic for e in entries))
    topics.sort(key=lambda t: (t.name if t else ''))
    difficulties = ['NB', 'TH', 'VD', 'VDC']
    diff_labels = dict(QuestionBank.DIFFICULTY_CHOICES)
    type_labels = dict(QuestionBank.TYPE_CHOICES)
    q_types = ['SINGLE', 'TF', 'NUMERIC']

    # Build lookup
    matrix = {}
    for e in entries:
        key = (e.topic_id, e.difficulty, e.question_type)
        matrix[key] = e.quantity

    doc = Document()

    # Title
    title_p = doc.add_heading(f'MA TRẬN ĐỀ THI', level=1)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Info
    doc.add_paragraph(f'Tiêu đề: {quiz.title}')
    doc.add_paragraph(f'Mã bài thi: {quiz.exam_code or "—"}')
    doc.add_paragraph(f'Môn thi: {quiz.subject.name}')
    doc.add_paragraph(f'Thời gian: {quiz.duration} phút')
    if quiz.deadline:
        doc.add_paragraph(f'Hạn nộp: {quiz.deadline.strftime("%d/%m/%Y %H:%M")}')
    doc.add_paragraph(f'Điểm: TN={quiz.score_single} | Đ/S={quiz.score_tf} | Số={quiz.score_numeric}')
    doc.add_paragraph()

    # Tạo bảng
    num_cols = 1 + len(difficulties) * len(q_types) + 1  # Topic + cells + Tổng
    num_rows = 2 + len(topics) + 2  # Header (2 rows) + topics + Tổng SL + Tổng Điểm

    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row 1: Chủ đề | NB | TH | VD | VDC | Tổng
    cell = table.cell(0, 0)
    cell.text = 'Chủ đề'
    table.cell(0, 0).merge(table.cell(1, 0))
    col_idx = 1
    for diff in difficulties:
        start_col = col_idx
        end_col = col_idx + len(q_types) - 1
        table.cell(0, start_col).merge(table.cell(0, end_col))
        table.cell(0, start_col).text = diff_labels.get(diff, diff)
        col_idx += len(q_types)
    table.cell(0, num_cols - 1).merge(table.cell(1, num_cols - 1))
    table.cell(0, num_cols - 1).text = 'Tổng'

    # Header row 2: sub-columns for each question type
    col_idx = 1
    short_type_labels = {'SINGLE': 'TN', 'TF': 'Đ/S', 'NUMERIC': 'Số'}
    for diff in difficulties:
        for qtype in q_types:
            table.cell(1, col_idx).text = short_type_labels.get(qtype, qtype)
            col_idx += 1

    # Data rows
    score_map = {'SINGLE': quiz.score_single, 'TF': quiz.score_tf, 'NUMERIC': quiz.score_numeric}
    for row_idx, topic in enumerate(topics, start=2):
        topic_id = topic.id if topic else None
        table.cell(row_idx, 0).text = topic.name if topic else 'Không chủ đề'
        row_total = 0
        col_idx = 1
        for diff in difficulties:
            for qtype in q_types:
                qty = matrix.get((topic_id, diff, qtype), 0)
                table.cell(row_idx, col_idx).text = str(qty) if qty > 0 else ''
                row_total += qty
                col_idx += 1
        table.cell(row_idx, num_cols - 1).text = str(row_total)

    # Tổng SL row
    total_row = 2 + len(topics)
    table.cell(total_row, 0).text = 'Tổng SL'
    grand_total = 0
    col_idx = 1
    for diff in difficulties:
        for qtype in q_types:
            col_sum = sum(matrix.get((t.id if t else None, diff, qtype), 0) for t in topics)
            table.cell(total_row, col_idx).text = str(col_sum) if col_sum > 0 else ''
            grand_total += col_sum
            col_idx += 1
    table.cell(total_row, num_cols - 1).text = str(grand_total)

    # Tổng Điểm row
    score_row = total_row + 1
    table.cell(score_row, 0).text = 'Tổng Điểm'
    grand_score = 0.0
    col_idx = 1
    for diff in difficulties:
        for qtype in q_types:
            col_sum = sum(matrix.get((t.id if t else None, diff, qtype), 0) for t in topics)
            score = col_sum * score_map.get(qtype, 0)
            table.cell(score_row, col_idx).text = f'{score:.2f}' if score > 0 else ''
            grand_score += score
            col_idx += 1
    table.cell(score_row, num_cols - 1).text = f'{grand_score:.2f}'

    # Bold headers
    for row in table.rows[:2]:
        for cell in row.cells:
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.size = Pt(9)

    # Đặc tả chủ đề kiến thức
    topic_specs = quiz.topic_specs.select_related('topic').all()
    if topic_specs.exists():
        doc.add_paragraph()
        doc.add_heading('ĐẶC TẢ CHỦ ĐỀ KIẾN THỨC', level=2)
        for spec in topic_specs:
            p = doc.add_paragraph()
            run_title = p.add_run(f'📌 {spec.topic.name}: ')
            run_title.bold = True
            run_title.font.size = Pt(11)
            run_title.font.color.rgb = RGBColor(79, 70, 229)
            p.add_run(spec.description).font.size = Pt(10)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = f'attachment; filename="MaTranDe_{quiz.exam_code or quiz.id}.docx"'
    return response


@manager_required
def export_matrix_excel(request, quiz_id):
    """Xuất ma trận đề ra file Excel."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

    quiz = get_object_or_404(Quiz, pk=quiz_id)
    entries = quiz.matrix_entries.select_related('topic').all()

    topics = list(set(e.topic for e in entries))
    topics.sort(key=lambda t: (t.name if t else ''))
    difficulties = ['NB', 'TH', 'VD', 'VDC']
    diff_labels = dict(QuestionBank.DIFFICULTY_CHOICES)
    q_types = ['SINGLE', 'TF', 'NUMERIC']
    short_type_labels = {'SINGLE': 'TN', 'TF': 'Đ/S', 'NUMERIC': 'Số'}

    matrix = {}
    for e in entries:
        key = (e.topic_id, e.difficulty, e.question_type)
        matrix[key] = e.quantity

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ma trận đề"

    # Styles
    header_font = Font(bold=True, size=14, color="FFFFFF")
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    sub_header_font = Font(bold=True, size=10)
    sub_header_fill = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    total_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    score_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")

    # Title rows
    ws.merge_cells('A1:M1')
    ws['A1'] = f'MA TRẬN ĐỀ THI - {quiz.title}'
    ws['A1'].font = Font(bold=True, size=16, color="4F46E5")
    ws['A1'].alignment = Alignment(horizontal='center')

    ws['A2'] = f'Mã bài thi: {quiz.exam_code or "—"}'
    ws['A3'] = f'Môn thi: {quiz.subject.name}'
    ws['A4'] = f'Thời gian: {quiz.duration} phút'
    ws['A5'] = f'Điểm: TN={quiz.score_single} | Đ/S={quiz.score_tf} | Số={quiz.score_numeric}'
    if quiz.deadline:
        ws['A6'] = f'Hạn nộp: {quiz.deadline.strftime("%d/%m/%Y %H:%M")}'

    start_row = 8

    # Header row 1: merge cells for difficulty groups
    ws.cell(row=start_row, column=1, value='Chủ đề').font = sub_header_font
    ws.cell(row=start_row, column=1).fill = header_fill
    ws.cell(row=start_row, column=1).font = Font(bold=True, color="FFFFFF")
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row + 1, end_column=1)

    col = 2
    for diff in difficulties:
        start_col = col
        end_col = col + len(q_types) - 1
        ws.merge_cells(start_row=start_row, start_column=start_col, end_row=start_row, end_column=end_col)
        cell = ws.cell(row=start_row, column=start_col, value=diff_labels.get(diff, diff))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        # Fill merged cells
        for c in range(start_col, end_col + 1):
            ws.cell(row=start_row, column=c).fill = header_fill
            ws.cell(row=start_row, column=c).border = thin_border
        col += len(q_types)

    total_col = col
    ws.cell(row=start_row, column=total_col, value='Tổng').font = Font(bold=True, color="FFFFFF")
    ws.cell(row=start_row, column=total_col).fill = header_fill
    ws.merge_cells(start_row=start_row, start_column=total_col, end_row=start_row + 1, end_column=total_col)

    # Header row 2: question type sub-headers
    col = 2
    for diff in difficulties:
        for qtype in q_types:
            cell = ws.cell(row=start_row + 1, column=col, value=short_type_labels.get(qtype, qtype))
            cell.font = sub_header_font
            cell.fill = sub_header_fill
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border
            col += 1

    # Data rows
    score_map = {'SINGLE': quiz.score_single, 'TF': quiz.score_tf, 'NUMERIC': quiz.score_numeric}
    data_start = start_row + 2
    for row_idx, topic in enumerate(topics):
        row = data_start + row_idx
        topic_id = topic.id if topic else None
        ws.cell(row=row, column=1, value=topic.name if topic else 'Không chủ đề').border = thin_border
        row_total = 0
        col = 2
        for diff in difficulties:
            for qtype in q_types:
                qty = matrix.get((topic_id, diff, qtype), 0)
                cell = ws.cell(row=row, column=col, value=qty if qty > 0 else None)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center')
                row_total += qty
                col += 1
        total_cell = ws.cell(row=row, column=total_col, value=row_total)
        total_cell.border = thin_border
        total_cell.font = Font(bold=True)
        total_cell.alignment = Alignment(horizontal='center')

    # Tổng SL row
    total_row = data_start + len(topics)
    ws.cell(row=total_row, column=1, value='Tổng SL').font = Font(bold=True)
    ws.cell(row=total_row, column=1).fill = total_fill
    ws.cell(row=total_row, column=1).border = thin_border
    grand_total = 0
    col = 2
    for diff in difficulties:
        for qtype in q_types:
            col_sum = sum(matrix.get((t.id if t else None, diff, qtype), 0) for t in topics)
            cell = ws.cell(row=total_row, column=col, value=col_sum if col_sum > 0 else None)
            cell.border = thin_border
            cell.fill = total_fill
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
            grand_total += col_sum
            col += 1
    cell = ws.cell(row=total_row, column=total_col, value=grand_total)
    cell.border = thin_border
    cell.fill = total_fill
    cell.font = Font(bold=True, size=12)
    cell.alignment = Alignment(horizontal='center')

    # Tổng Điểm row
    score_row = total_row + 1
    ws.cell(row=score_row, column=1, value='Tổng Điểm').font = Font(bold=True)
    ws.cell(row=score_row, column=1).fill = score_fill
    ws.cell(row=score_row, column=1).border = thin_border
    grand_score = 0.0
    col = 2
    for diff in difficulties:
        for qtype in q_types:
            col_sum = sum(matrix.get((t.id if t else None, diff, qtype), 0) for t in topics)
            score = col_sum * score_map.get(qtype, 0)
            cell = ws.cell(row=score_row, column=col, value=round(score, 2) if score > 0 else None)
            cell.border = thin_border
            cell.fill = score_fill
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
            grand_score += score
            col += 1
    cell = ws.cell(row=score_row, column=total_col, value=round(grand_score, 2))
    cell.border = thin_border
    cell.fill = score_fill
    cell.font = Font(bold=True, size=12, color="16A34A")
    cell.alignment = Alignment(horizontal='center')

    # Column widths
    ws.column_dimensions['A'].width = 25
    for c in range(2, total_col + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 8

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="MaTranDe_{quiz.exam_code or quiz.id}.xlsx"'
    return response


@manager_required
def exam_list(request):
    """Danh sách các bài thi đã tạo."""
    q = request.GET.get('q', '').strip()
    selected_period = request.GET.get('period', '').strip()
    selected_subject = request.GET.get('subject', '').strip()

    quizzes_qs = Quiz.objects.select_related('subject', 'subject__exam_period').prefetch_related('matrix_entries', 'topic_specs').order_by('-created_at')

    if q:
        quizzes_qs = quizzes_qs.filter(
            Q(title__icontains=q) | Q(exam_code__icontains=q)
        )
    if selected_period:
        quizzes_qs = quizzes_qs.filter(subject__exam_period_id=selected_period)
    if selected_subject:
        quizzes_qs = quizzes_qs.filter(subject_id=selected_subject)

    quizzes_data = []
    total_matrix_questions_all = 0

    for quiz in quizzes_qs:
        entries = quiz.matrix_entries.all()
        total_questions = sum(e.quantity for e in entries)
        total_matrix_questions_all += total_questions

        score_map = {
            'SINGLE': quiz.score_single,
            'TF': quiz.score_tf,
            'NUMERIC': quiz.score_numeric
        }
        total_score = sum(e.quantity * score_map.get(e.question_type, 0) for e in entries)
        is_score_10 = abs(total_score - 10.0) <= 0.001

        quizzes_data.append({
            'quiz': quiz,
            'total_questions': total_questions,
            'total_score': round(total_score, 2),
            'is_score_10': is_score_10,
            'topic_specs_count': quiz.topic_specs.count(),
        })

    exam_periods = ExamPeriod.objects.all().order_by('name')
    subjects = Subject.objects.select_related('exam_period').all().order_by('name')

    # Count subjects with exams
    subjects_with_exams_count = Quiz.objects.values('subject_id').distinct().count()

    context = {
        'quizzes_data': quizzes_data,
        'total_quizzes': len(quizzes_data),
        'total_matrix_questions_all': total_matrix_questions_all,
        'subjects_with_exams_count': subjects_with_exams_count,
        'exam_periods': exam_periods,
        'subjects': subjects,
        'q': q,
        'selected_period': selected_period,
        'selected_subject': selected_subject,
    }
    return render(request, 'quiz/exam_list.html', context)


@manager_required
def exam_detail(request, quiz_id):
    """Xem chi tiết và sửa cấu trúc ma trận đề thi."""
    quiz = get_object_or_404(Quiz.objects.select_related('subject', 'subject__exam_period'), pk=quiz_id)

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        title = request.POST.get('title', '').strip()
        exam_code = request.POST.get('exam_code', '').strip()
        duration = request.POST.get('duration', '45')
        start_time = request.POST.get('start_time', '').strip()
        deadline = request.POST.get('deadline', '').strip()
        score_single = request.POST.get('score_single', '0.25')
        score_tf = request.POST.get('score_tf', '1.0')
        score_numeric = request.POST.get('score_numeric', '0.5')
        matrix_json = request.POST.get('matrix_json', '[]')
        topic_specs_json = request.POST.get('topic_specs_json', '[]')

        errors = []
        if not title:
            errors.append('Vui lòng nhập tiêu đề đề thi.')
        if not exam_code:
            errors.append('Vui lòng nhập mã bài thi.')
        elif Quiz.objects.filter(exam_code=exam_code).exclude(pk=quiz.id).exists():
            errors.append(f'Mã bài thi "{exam_code}" đã tồn tại cho một bài thi khác. Vui lòng chọn mã khác.')

        try:
            duration_val = int(duration)
        except ValueError:
            errors.append('Thời gian làm bài phải là số nguyên.')
            duration_val = quiz.duration

        try:
            matrix_data = json.loads(matrix_json)
        except json.JSONDecodeError:
            errors.append('Dữ liệu ma trận không hợp lệ.')
            matrix_data = []

        try:
            topic_specs_data = json.loads(topic_specs_json)
        except json.JSONDecodeError:
            topic_specs_data = []

        # Lọc chỉ giữ entry có quantity > 0
        matrix_data = [e for e in matrix_data if e.get('quantity', 0) > 0]

        if not matrix_data:
            errors.append('Ma trận đề trống. Vui lòng nhập ít nhất 1 ô có số câu > 0.')

        # Kiểm tra ngân hàng có đủ câu không
        shortage_errors = []
        for entry in matrix_data:
            qty = entry.get('quantity', 0)
            topic_id = entry.get('topic_id')
            diff = entry.get('difficulty')
            qtype = entry.get('question_type')

            qs = QuestionBank.objects.filter(
                subject_id=quiz.subject_id,
                difficulty=diff,
                question_type=qtype
            )
            if topic_id:
                qs = qs.filter(topic_id=topic_id)
            available = qs.count()
            if available < qty:
                topic_name = Topic.objects.filter(id=topic_id).values_list('name', flat=True).first() or 'Không chủ đề'
                diff_display = dict(QuestionBank.DIFFICULTY_CHOICES).get(diff, diff)
                type_display = dict(QuestionBank.TYPE_CHOICES).get(qtype, qtype)
                shortage_errors.append(
                    f"{topic_name} | {diff_display} | {type_display}: cần {qty}, có {available}"
                )

        if shortage_errors:
            errors.append('Ngân hàng không đủ câu hỏi:')
            errors.extend(shortage_errors)

        if errors:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': errors}, status=400)
            for e in errors:
                messages.error(request, e)
            return redirect('exam_detail', quiz_id=quiz.id)

        try:
            from datetime import datetime as dt
            start_time_dt = None
            if start_time:
                try:
                    start_time_dt = dt.fromisoformat(start_time)
                except ValueError:
                    pass

            deadline_dt = None
            if deadline:
                try:
                    deadline_dt = dt.fromisoformat(deadline)
                except ValueError:
                    pass

            with transaction.atomic():
                quiz.title = title
                quiz.exam_code = exam_code
                quiz.duration = duration_val
                quiz.start_time = start_time_dt
                quiz.deadline = deadline_dt
                quiz.score_single = float(score_single)
                quiz.score_tf = float(score_tf)
                quiz.score_numeric = float(score_numeric)
                quiz.save()

                # Xóa ma trận cũ và tạo ma trận mới
                quiz.matrix_entries.all().delete()
                total_questions = 0
                for entry in matrix_data:
                    ExamMatrixEntry.objects.create(
                        quiz=quiz,
                        topic_id=entry.get('topic_id') or None,
                        difficulty=entry['difficulty'],
                        question_type=entry['question_type'],
                        quantity=entry['quantity'],
                    )
                    total_questions += entry['quantity']

                # Cập nhật đặc tả chủ đề
                quiz.topic_specs.all().delete()
                for spec in topic_specs_data:
                    topic_id = spec.get('topic_id')
                    desc = spec.get('description', '').strip()
                    if topic_id and desc:
                        ExamMatrixTopicSpec.objects.create(
                            quiz=quiz,
                            topic_id=topic_id,
                            description=desc,
                        )

            if is_ajax:
                return JsonResponse({
                    'status': 'success',
                    'message': f'Cập nhật bài thi "{title}" thành công!',
                    'quiz_id': quiz.id,
                })
            messages.success(request, f'Cập nhật bài thi "{title}" thành công!')
            return redirect('exam_detail', quiz_id=quiz.id)

        except Exception as e:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': [str(e)]}, status=500)
            return redirect('exam_detail', quiz_id=quiz.id)

    # GET: Dữ liệu môn thi, chủ đề và số câu khả dụng trong ngân hàng
    topics = Topic.objects.filter(subject=quiz.subject).order_by('name')
    topics_list = [{'id': t.id, 'name': t.name} for t in topics]

    # Số lượng câu hỏi có sẵn trong ngân hàng
    avail_counts_qs = QuestionBank.objects.filter(
        subject=quiz.subject
    ).values('topic_id', 'difficulty', 'question_type').annotate(total=Count('id'))

    avail_counts = {}
    for item in avail_counts_qs:
        key = f"{item['topic_id']}_{item['difficulty']}_{item['question_type']}"
        avail_counts[key] = item['total']

    # Ma trận hiện tại của bài thi
    current_matrix = {}
    for entry in quiz.matrix_entries.all():
        key = f"{entry.topic_id}_{entry.difficulty}_{entry.question_type}"
        current_matrix[key] = entry.quantity

    # Đặc tả chủ đề hiện tại
    current_specs = {}
    for spec in quiz.topic_specs.all():
        current_specs[str(spec.topic_id)] = spec.description

    # Danh sách kết quả thí sinh tham gia làm bài thi
    exam_results = ExamResult.objects.filter(quiz=quiz).select_related('user', 'user__profile').order_by('-score', 'time_spent')

    context = {
        'quiz': quiz,
        'topics': topics,
        'topics_json': json.dumps(topics_list, ensure_ascii=False),
        'avail_counts_json': json.dumps(avail_counts, ensure_ascii=False),
        'current_matrix_json': json.dumps(current_matrix, ensure_ascii=False),
        'current_specs_json': json.dumps(current_specs, ensure_ascii=False),
        'start_time_formatted': quiz.start_time.strftime('%Y-%m-%dT%H:%M') if quiz.start_time else '',
        'deadline_formatted': quiz.deadline.strftime('%Y-%m-%dT%H:%M') if quiz.deadline else '',
        'exam_results': exam_results,
        'total_results': exam_results.count(),
    }
    return render(request, 'quiz/exam_detail.html', context)


@manager_required
def exam_results_view(request, quiz_id):
    """Trang xem bảng điểm và danh sách chi tiết các thí sinh tham gia bài thi."""
    quiz = get_object_or_404(Quiz.objects.select_related('subject', 'subject__exam_period'), pk=quiz_id)
    results = ExamResult.objects.filter(quiz=quiz).select_related('user', 'user__profile').order_by('-score', 'time_spent')

    total_participants = results.count()
    avg_score = round(sum(r.score for r in results) / total_participants, 2) if total_participants > 0 else 0
    scores = [r.score for r in results]
    highest_score = max(scores, default=0)
    lowest_score = min(scores, default=0)

    context = {
        'quiz': quiz,
        'results': results,
        'total_participants': total_participants,
        'avg_score': avg_score,
        'highest_score': highest_score,
        'lowest_score': lowest_score,
    }
    return render(request, 'quiz/exam_results_list.html', context)


@manager_required
def delete_exam(request, quiz_id):
    """Xóa bài thi và ma trận."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ.'}, status=405)

    quiz = get_object_or_404(Quiz, pk=quiz_id)
    title = quiz.title
    code = quiz.exam_code or str(quiz.id)
    quiz.delete()

    return JsonResponse({
        'status': 'success',
        'message': f'Đã xóa bài thi "{title}" [{code}] thành công!'
    })