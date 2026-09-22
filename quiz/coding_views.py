import json
import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import CodingQuestion, TestCase, CodeSubmission, CodingComment, CodingExam, CodingExamAttempt, CodingExamRegistration
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django import forms
from django.core.exceptions import PermissionDenied

import sys
import subprocess
import tempfile
import os
import uuid

PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"

def execute_code_locally(language, code, stdin, run_timeout_sec):
    import time
    if language not in ('python', 'cpp'):
        return {'status': 'System Error', 'output': 'Ngôn ngữ này chưa được hỗ trợ chạy nội bộ'}
        
    if language == 'python':
        python_bin = sys.executable
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
            
        try:
            start_time = time.perf_counter()
            process = subprocess.run(
                [python_bin, temp_file],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=run_timeout_sec
            )
            exec_time = time.perf_counter() - start_time
            if process.returncode == 0:
                return {'status': 'Accepted', 'output': process.stdout, 'time': exec_time}
            else:
                return {'status': 'Runtime Error', 'output': process.stderr, 'time': exec_time}
        except subprocess.TimeoutExpired:
            return {'status': 'Time Limit Exceeded', 'output': ''}
        except Exception as e:
            return {'status': 'System Error', 'output': str(e)}
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
    elif language == 'cpp':
        from django.conf import settings
        includes_dir = os.path.join(settings.BASE_DIR, 'quiz', 'cpp_includes')
        
        with tempfile.TemporaryDirectory() as tmpdirname:
            source_file = os.path.join(tmpdirname, 'solution.cpp')
            executable = os.path.join(tmpdirname, 'solution')
            
            with open(source_file, 'w') as f:
                f.write(code)
            
            try:
                compile_process = subprocess.run(
                    ['g++', '-O2', source_file, '-o', executable, '-I', includes_dir],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if compile_process.returncode != 0:
                    return {'status': 'Compilation Error', 'output': compile_process.stderr}
            except subprocess.TimeoutExpired:
                return {'status': 'Compilation Error', 'output': 'Quá thời gian biên dịch (10s)'}
            except Exception as e:
                return {'status': 'System Error', 'output': f'Lỗi gọi trình biên dịch (Vui lòng cài đặt gcc/g++): {str(e)}'}
                
            try:
                start_time = time.perf_counter()
                run_process = subprocess.run(
                    [executable],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=run_timeout_sec
                )
                exec_time = time.perf_counter() - start_time
                if run_process.returncode == 0:
                    return {'status': 'Accepted', 'output': run_process.stdout, 'time': exec_time}
                else:
                    return {'status': 'Runtime Error', 'output': run_process.stderr, 'time': exec_time}
            except subprocess.TimeoutExpired:
                return {'status': 'Time Limit Exceeded', 'output': ''}
            except Exception as e:
                return {'status': 'System Error', 'output': str(e)}

class CodingQuestionForm(forms.ModelForm):
    class Meta:
        model = CodingQuestion
        fields = ['title', 'description', 'time_limit', 'memory_limit', 'initial_code_cpp', 'initial_code_python', 'difficulty', 'max_score', 'topics', 'past_exam']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'past_exam': forms.Select(attrs={'class': 'form-select select2-exam', 'data-placeholder': 'VD: HSG Tỉnh 2023...'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'time_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'memory_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'initial_code_cpp': forms.Textarea(attrs={'class': 'form-control text-monospace', 'rows': 5}),
            'initial_code_python': forms.Textarea(attrs={'class': 'form-control text-monospace', 'rows': 5}),
            'difficulty': forms.Select(attrs={'class': 'form-select'}),
            'max_score': forms.NumberInput(attrs={'class': 'form-control'}),
            'topics': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing_exams = CodingQuestion.objects.exclude(past_exam='').values_list('past_exam', flat=True).distinct()
        choices = [('', '--- Chọn hoặc gõ thêm mới ---')]
        for exam in existing_exams:
            choices.append((exam, exam))
        
        if self.instance and self.instance.past_exam and self.instance.past_exam not in [c[0] for c in choices]:
            choices.append((self.instance.past_exam, self.instance.past_exam))
            
        self.fields['past_exam'].widget.choices = choices

class CodingExamForm(forms.ModelForm):
    class Meta:
        model = CodingExam
        fields = ['title', 'description', 'start_time', 'end_time', 'duration', 'exam_type', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control'}),
            'exam_type': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

from django.utils import timezone

@login_required
def coding_exam_list(request):
    exams = CodingExam.objects.all().order_by('-created_at')
    
    now = timezone.now()
    ongoing_exams = []
    upcoming_exams = []
    ended_exams = []
    
    for exam in exams:
        if exam.end_time and exam.end_time < now:
            ended_exams.append(exam)
        elif exam.start_time and exam.start_time > now:
            upcoming_exams.append(exam)
        else:
            ongoing_exams.append(exam)
            
    exam_groups = [
        {'title': 'Đang diễn ra', 'icon': 'fas fa-play-circle text-success', 'exams': ongoing_exams},
        {'title': 'Sắp diễn ra', 'icon': 'fas fa-calendar-alt text-primary', 'exams': upcoming_exams},
        {'title': 'Đã kết thúc', 'icon': 'fas fa-stop-circle text-secondary', 'exams': ended_exams},
    ]
            
    return render(request, 'quiz/coding/exam_list.html', {
        'exam_groups': exam_groups
    })

@login_required
def coding_exam_create(request):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền tạo kỳ thi lập trình.")
        
    if request.method == 'POST':
        form = CodingExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.created_by = request.user
            exam.save()
            return redirect('coding_exam_list')
    else:
        form = CodingExamForm()
        
    return render(request, 'quiz/coding/exam_form.html', {'form': form, 'title': 'Tạo kỳ thi lập trình'})

@login_required
def coding_exam_edit(request, exam_id):
    exam = get_object_or_404(CodingExam, id=exam_id)
    if exam.created_by != request.user:
        raise PermissionDenied("Bạn không có quyền sửa kỳ thi này.")
        
    if request.method == 'POST':
        form = CodingExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            return redirect('coding_exam_list')
    else:
        form = CodingExamForm(instance=exam)
        
    return render(request, 'quiz/coding/exam_form.html', {'form': form, 'title': 'Sửa kỳ thi lập trình', 'exam': exam})

@login_required
@require_POST
def coding_exam_delete(request, exam_id):
    exam = get_object_or_404(CodingExam, id=exam_id)
    if exam.created_by != request.user:
        raise PermissionDenied("Bạn không có quyền xóa kỳ thi này.")
        
    exam.delete()
    return redirect('coding_exam_list')

@login_required
def coding_exam_detail(request, exam_id):
    exam = get_object_or_404(CodingExam, id=exam_id)
    questions = exam.questions.all().order_by('created_at')
    
    can_manage = request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.is_coding_contributor() and (request.user.profile.is_admin() or exam.created_by == request.user)
    
    if not can_manage:
        questions = questions.filter(is_active=True)
    
    attempt = None
    registration = None
    if request.user.is_authenticated:
        try:
            attempt = CodingExamAttempt.objects.get(user=request.user, exam=exam)
        except CodingExamAttempt.DoesNotExist:
            attempt = None
            
        if exam.exam_type == 'registered':
            try:
                registration = CodingExamRegistration.objects.get(user=request.user, exam=exam)
            except CodingExamRegistration.DoesNotExist:
                registration = None

        if request.method == 'POST' and 'start_exam' in request.POST:
            if exam.exam_type == 'registered':
                if not registration or registration.status != 'approved':
                    return redirect('coding_exam_detail', exam_id=exam.id)
                    
            if not attempt:
                attempt = CodingExamAttempt.objects.create(user=request.user, exam=exam)
            return redirect('coding_exam_detail', exam_id=exam.id)
            
    solved_questions = set()
    attempted_questions = set()
    max_score_dict = {}
    
    if request.user.is_authenticated:
        submissions = CodeSubmission.objects.filter(student=request.user, question__in=questions)
        solved_questions = set(submissions.filter(status='Accepted').values_list('question_id', flat=True))
        attempted_questions = set(submissions.values_list('question_id', flat=True))
        
        from django.db.models import Max
        max_scores = submissions.values('question_id').annotate(max_score=Max('score'))
        max_score_dict = {item['question_id']: item['max_score'] for item in max_scores}
    
    for q in questions:
        q.user_score = max_score_dict.get(q.id, 0.0)
        if q.id in solved_questions:
            q.status = 'solved'
        elif q.id in attempted_questions:
            q.status = 'attempted'
        else:
            q.status = 'unattempted'
            
    leaderboard = CodingExamAttempt.objects.filter(exam=exam).order_by('-total_score', 'start_time')
    user_rank = None
    for i, a in enumerate(leaderboard):
        if a.user == request.user:
            user_rank = i + 1
            break
            
    return render(request, 'quiz/coding/exam_detail.html', {
        'exam': exam,
        'questions': questions,
        'attempt': attempt,
        'registration': registration,
        'user_rank': user_rank,
        'total_participants': leaderboard.count(),
        'can_manage': can_manage
    })

@login_required
def coding_exam_register(request, exam_id):
    from django.contrib import messages
    exam = get_object_or_404(CodingExam, id=exam_id)
    
    if exam.exam_type != 'registered':
        return redirect('coding_exam_detail', exam_id=exam.id)
        
    if request.method == 'POST':
        registration, created = CodingExamRegistration.objects.get_or_create(
            user=request.user,
            exam=exam,
            defaults={'status': 'pending'}
        )
        if created:
            messages.success(request, "Đăng ký thành công! Đang chờ duyệt.")
        else:
            messages.info(request, "Bạn đã đăng ký kỳ thi này rồi.")
            
    return redirect('coding_exam_detail', exam_id=exam.id)

@login_required
def coding_manage_registrations(request, exam_id):
    exam = get_object_or_404(CodingExam, id=exam_id)
    
    can_manage = request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.is_coding_contributor() and (request.user.profile.is_admin() or exam.created_by == request.user)
    if not (can_manage or request.user.is_superuser):
        raise PermissionDenied("Bạn không có quyền quản lý kỳ thi này.")
        
    registrations = CodingExamRegistration.objects.filter(exam=exam).select_related('user').order_by('-created_at')
    
    return render(request, 'quiz/coding/exam_registrations.html', {
        'exam': exam,
        'registrations': registrations
    })

@login_required
def api_coding_approve_registration(request):
    from django.http import JsonResponse
    import json
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
        
    try:
        data = json.loads(request.body)
        reg_id = data.get('registration_id')
        status = data.get('status')
        
        if status not in ['approved', 'rejected']:
            return JsonResponse({'error': 'Trạng thái không hợp lệ'}, status=400)
            
        registration = get_object_or_404(CodingExamRegistration, id=reg_id)
        exam = registration.exam
        
        can_manage = request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.is_coding_contributor() and (request.user.profile.is_admin() or exam.created_by == request.user)
        if not (can_manage or request.user.is_superuser):
            return JsonResponse({'error': 'Bạn không có quyền'}, status=403)
            
        registration.status = status
        registration.save()
        
        return JsonResponse({'success': True, 'status': status})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def api_get_submission_code(request, submission_id):
    from django.http import JsonResponse
    from django.utils import timezone
    submission = get_object_or_404(CodeSubmission, id=submission_id)
    
    # Check if this submission belongs to an exam attempt
    exams = submission.question.codingexam_set.all()
    can_view = False
    if request.user.is_superuser or request.user == submission.student:
        can_view = True
    else:
        for exam in exams:
            if exam.created_by == request.user:
                can_view = True
                break
            
    # For students viewing other's code in exam, exam must be ended.
    if not can_view:
        now = timezone.now()
        for exam in exams:
            if exam.end_time and now > exam.end_time:
                has_attempted = CodingExamAttempt.objects.filter(exam=exam, user=request.user).exists()
                if has_attempted:
                    can_view = True
                    break
                    
    if not can_view:
        return JsonResponse({'error': 'Bạn không có quyền xem code này hoặc kỳ thi chưa kết thúc.'}, status=403)
        
    return JsonResponse({
        'code': submission.code,
        'language': submission.language
    })

@login_required
def coding_exam_results(request, exam_id):
    from django.db.models import Q, Max
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.utils import timezone
    from django.http import HttpResponse

    exam = get_object_or_404(CodingExam, id=exam_id)
    now = timezone.now()
    exam_ended = bool(exam.end_time and now > exam.end_time)
    
    # Check permissions
    has_attempted = CodingExamAttempt.objects.filter(exam=exam, user=request.user).exists()
    can_manage = request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.is_coding_contributor() and (request.user.profile.is_admin() or exam.created_by == request.user)
    if not (can_manage or request.user.is_superuser or has_attempted):
        raise PermissionDenied("Bạn không có quyền xem kết quả kỳ thi này.")

    questions = exam.questions.all().order_by('created_at')
    
    # Search
    search_query = request.GET.get('q', '').strip()
    attempts_query = CodingExamAttempt.objects.filter(exam=exam).select_related('user')
    
    if search_query:
        attempts_query = attempts_query.filter(
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )

    # Ranking
    attempts_list = list(attempts_query)
    
    # Populate detailed scores and time taken
    for attempt in attempts_list:
        attempt.question_scores = []
        submissions = CodeSubmission.objects.filter(student=attempt.user, question__in=questions)
        last_submission_time = None
        
        for q in questions:
            q_subs = submissions.filter(question=q)
            if q_subs.exists():
                max_score_sub = q_subs.order_by('-score', '-created_at').first()
                attempt.question_scores.append({
                    'score': max_score_sub.score,
                    'submission_id': max_score_sub.id
                })
                latest_sub = q_subs.order_by('-created_at').first()
                if not last_submission_time or latest_sub.created_at > last_submission_time:
                    last_submission_time = latest_sub.created_at
            else:
                attempt.question_scores.append({'score': 0, 'submission_id': None})
                
        if last_submission_time and last_submission_time > attempt.start_time:
            delta = last_submission_time - attempt.start_time
            attempt.time_taken_seconds = delta.total_seconds()
        else:
            attempt.time_taken_seconds = 0
            
        minutes = int(attempt.time_taken_seconds // 60)
        seconds = int(attempt.time_taken_seconds % 60)
        attempt.time_taken_str = f"{minutes}p {seconds}s"
        
    # Sort by total_score descending, time_taken_seconds ascending, start_time ascending
    attempts_list.sort(key=lambda a: (-a.total_score, a.time_taken_seconds, a.start_time))
            
    # Export
    export_type = request.GET.get('export')
    if export_type == 'excel':
        import openpyxl
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=Ket_qua_ky_thi_{exam.id}.xlsx'
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Kết quả"
        
        # Headers
        headers = ['Hạng', 'Mã Số', 'Họ và Tên / Username']
        for i, q in enumerate(questions, 1):
            headers.append(f'Câu {i}')
        headers.extend(['Tổng Điểm', 'Thời Gian Làm Bài', 'Thời Gian Bắt Đầu'])
        ws.append(headers)
        
        for idx, attempt in enumerate(attempts_list, start=1):
            start_time_str = attempt.start_time.strftime("%d/%m/%Y %H:%M:%S") if attempt.start_time else ""
            full_name = attempt.user.get_full_name() or attempt.user.username
            student_code = attempt.user.profile.student_code if hasattr(attempt.user, 'profile') else ''
            row = [
                idx,
                student_code,
                full_name,
            ]
            for qs in attempt.question_scores:
                row.append(qs['score'])
            row.extend([attempt.total_score, attempt.time_taken_str, start_time_str])
            ws.append(row)
            
        wb.save(response)
        return response
        
    elif export_type == 'pdf':
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet
            import unicodedata
        except ImportError:
            return HttpResponse("ReportLab is not installed.", status=500)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=Ket_qua_ky_thi_{exam.id}.pdf'
        
        doc = SimpleDocTemplate(response, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = styles['Heading1']
        title_style.alignment = 1 # Center
        
        def strip_accents(s):
            return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')
            
        title_text = strip_accents(exam.title)
        elements.append(Paragraph(f"Ket Qua Ky Thi: {title_text}", title_style))
        elements.append(Spacer(1, 20))
        
        headers = ['Hang', 'Ma So', 'Ho Ten / Username']
        col_widths = [40, 60, 150]
        for i, q in enumerate(questions, 1):
            headers.append(f'C{i}')
            col_widths.append(40)
        headers.extend(['Tong Diem', 'TG Lam Bai', 'TG Bat Dau'])
        col_widths.extend([60, 80, 100])
            
        data = [headers]
        for idx, attempt in enumerate(attempts_list, start=1):
            full_name = strip_accents(attempt.user.get_full_name() or attempt.user.username)
            start_time_str = attempt.start_time.strftime("%d/%m/%Y %H:%M") if attempt.start_time else ""
            student_code = str(attempt.user.profile.student_code) if hasattr(attempt.user, 'profile') else ''
            row = [
                str(idx),
                student_code,
                full_name,
            ]
            for qs in attempt.question_scores:
                row.append(str(qs['score']))
            row.extend([str(attempt.total_score), str(attempt.time_taken_str), start_time_str])
            data.append(row)
            
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('FONTSIZE', (0,1), (-1,-1), 9),
        ]))
        
        elements.append(table)
        doc.build(elements)
        return response

    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(attempts_list, 20)
    try:
        attempts_page = paginator.page(page)
    except PageNotAnInteger:
        attempts_page = paginator.page(1)
    except EmptyPage:
        attempts_page = paginator.page(paginator.num_pages)
        
    status_text = "Kết quả cuối cùng" if exam_ended else "Kết quả hiện tại"

    context = {
        'exam': exam,
        'questions': questions,
        'search_query': search_query,
        'attempts': attempts_page,
        'status_text': status_text,
        'exam_ended': exam_ended
    }
    return render(request, 'quiz/coding/exam_results.html', context)

@login_required
def coding_manage_list(request):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền quản lý bài tập lập trình.")
        
    from django.db.models import Q
    if request.user.profile.is_admin():
        questions = CodingQuestion.objects.filter(Q(created_by=request.user) | Q(created_by__isnull=True)).order_by('-created_at')
    else:
        questions = CodingQuestion.objects.filter(created_by=request.user).order_by('-created_at')
        
    # Filter
    q_search = request.GET.get('q', '').strip()
    difficulty = request.GET.get('difficulty', '')
    topic_id = request.GET.get('topic', '')
    author_q = request.GET.get('author', '').strip()
    
    if q_search:
        import unicodedata
        from django.db.models import Func, CharField
        q_unaccent = unicodedata.normalize('NFKD', q_search).encode('ASCII', 'ignore').decode('utf-8')
        questions = questions.annotate(
            title_unaccent=Func('title', function='unaccent', output_field=CharField())
        ).filter(
            Q(title__icontains=q_search) | Q(title_unaccent__icontains=q_unaccent)
        )
    if difficulty:
        questions = questions.filter(difficulty=difficulty)
    if topic_id and topic_id.isdigit():
        questions = questions.filter(topics__id=topic_id)
    if author_q:
        import unicodedata
        from django.db.models import Func, CharField
        a_unaccent = unicodedata.normalize('NFKD', author_q).encode('ASCII', 'ignore').decode('utf-8')
        questions = questions.annotate(
            u_un=Func('created_by__username', function='unaccent', output_field=CharField()),
            u_fn=Func('created_by__first_name', function='unaccent', output_field=CharField()),
            u_ln=Func('created_by__last_name', function='unaccent', output_field=CharField())
        ).filter(
            Q(created_by__username__icontains=author_q) |
            Q(created_by__first_name__icontains=author_q) |
            Q(created_by__last_name__icontains=author_q) |
            Q(u_un__icontains=a_unaccent) |
            Q(u_fn__icontains=a_unaccent) |
            Q(u_ln__icontains=a_unaccent)
        )
        
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(questions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    all_topics = CodingTopic.objects.all().order_by('name')
        
    return render(request, 'quiz/coding/manage_list.html', {
        'page_obj': page_obj,
        'all_topics': all_topics,
        'q_search': q_search,
        'difficulty': difficulty,
        'topic_id': topic_id,
        'author_q': author_q
    })

from .models import CodingTopic

def _process_topics_in_post(post_data):
    data = post_data.copy()
    topics = data.getlist('topics')
    new_topic_ids = []
    for t in topics:
        if not t.isdigit() and t.strip():
            topic, created = CodingTopic.objects.get_or_create(name=t.strip())
            new_topic_ids.append(str(topic.id))
        else:
            new_topic_ids.append(t)
    data.setlist('topics', new_topic_ids)
    return data

@login_required
def coding_export_json(request):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền quản lý bài tập lập trình.")
        
    from django.db.models import Q
    import json
    from django.http import HttpResponse

    if request.user.profile.is_admin():
        questions = CodingQuestion.objects.filter(Q(created_by=request.user) | Q(created_by__isnull=True)).order_by('-created_at')
    else:
        questions = CodingQuestion.objects.filter(created_by=request.user).order_by('-created_at')
        
    # Lọc tương tự như trong coding_manage_list
    q_search = request.GET.get('q', '').strip()
    difficulty = request.GET.get('difficulty', '')
    topic_id = request.GET.get('topic', '')
    author_q = request.GET.get('author', '').strip()
    ids = request.GET.get('ids', '')
    
    if ids:
        id_list = [int(x) for x in ids.split(',') if x.isdigit()]
        if id_list:
            questions = questions.filter(id__in=id_list)
            
    if q_search:
        import unicodedata
        from django.db.models import Func, CharField
        q_unaccent = unicodedata.normalize('NFKD', q_search).encode('ASCII', 'ignore').decode('utf-8')
        questions = questions.annotate(
            title_unaccent=Func('title', function='unaccent', output_field=CharField())
        ).filter(
            Q(title__icontains=q_search) | Q(title_unaccent__icontains=q_unaccent)
        )
    if difficulty:
        questions = questions.filter(difficulty=difficulty)
    if topic_id and topic_id.isdigit():
        questions = questions.filter(topics__id=topic_id)
    if author_q:
        import unicodedata
        from django.db.models import Func, CharField
        a_unaccent = unicodedata.normalize('NFKD', author_q).encode('ASCII', 'ignore').decode('utf-8')
        questions = questions.annotate(
            u_un=Func('created_by__username', function='unaccent', output_field=CharField()),
            u_fn=Func('created_by__first_name', function='unaccent', output_field=CharField()),
            u_ln=Func('created_by__last_name', function='unaccent', output_field=CharField())
        ).filter(
            Q(created_by__username__icontains=author_q) |
            Q(created_by__first_name__icontains=author_q) |
            Q(created_by__last_name__icontains=author_q) |
            Q(u_un__icontains=a_unaccent) |
            Q(u_fn__icontains=a_unaccent) |
            Q(u_ln__icontains=a_unaccent)
        )
        
    data = []
    for q in questions:
        q_data = {
            "title": q.title,
            "description": q.description,
            "time_limit": q.time_limit,
            "memory_limit": q.memory_limit,
            "difficulty": q.difficulty,
            "max_score": q.max_score,
            "is_public": q.is_public,
            "is_active": q.is_active,
            "past_exam": q.past_exam,
            "topics": [t.name for t in q.topics.all()],
            "initial_code_cpp": q.initial_code_cpp,
            "initial_code_python": q.initial_code_python,
            "solution_code_cpp": q.solution_code_cpp,
            "solution_code_python": q.solution_code_python,
            "testcases": [
                {
                    "input_data": tc.input_data,
                    "expected_output": tc.expected_output,
                    "is_hidden": tc.is_hidden,
                    "points": tc.points
                } for tc in q.testcases.all()
            ]
        }
        data.append(q_data)
        
    response = HttpResponse(json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json")
    response['Content-Disposition'] = 'attachment; filename="coding_questions.json"'
    return response

@login_required
@require_POST
def coding_import_json(request):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        return JsonResponse({'success': False, 'error': 'Bạn không có quyền quản lý bài tập lập trình.'})
        
    file = request.FILES.get('json_file')
    if not file:
        return JsonResponse({'success': False, 'error': 'Vui lòng chọn tệp JSON.'})
        
    try:
        import json
        from django.db import transaction
        data = json.loads(file.read().decode('utf-8'))
        
        if not isinstance(data, list):
            return JsonResponse({'success': False, 'error': 'Định dạng JSON không hợp lệ (phải là một mảng).'})
            
        with transaction.atomic():
            for item in data:
                question = CodingQuestion.objects.create(
                    title=item.get('title', 'Untitled'),
                    description=item.get('description', ''),
                    time_limit=item.get('time_limit', 1.0),
                    memory_limit=item.get('memory_limit', 128),
                    difficulty=item.get('difficulty', 'Dễ'),
                    max_score=item.get('max_score', 10),
                    is_public=item.get('is_public', True),
                    is_active=item.get('is_active', True),
                    past_exam=item.get('past_exam', ''),
                    initial_code_cpp=item.get('initial_code_cpp', ''),
                    initial_code_python=item.get('initial_code_python', ''),
                    solution_code_cpp=item.get('solution_code_cpp', ''),
                    solution_code_python=item.get('solution_code_python', ''),
                    created_by=request.user
                )
                
                # Handle topics
                topics = item.get('topics', [])
                for topic_name in topics:
                    topic, _ = CodingTopic.objects.get_or_create(name=topic_name)
                    question.topics.add(topic)
                    
                # Handle testcases
                testcases = item.get('testcases', [])
                for tc in testcases:
                    TestCase.objects.create(
                        question=question,
                        input_data=tc.get('input_data', ''),
                        expected_output=tc.get('expected_output', ''),
                        is_hidden=tc.get('is_hidden', False),
                        points=tc.get('points', 0.1)
                    )
                    
        return JsonResponse({'success': True, 'message': f'Nhập thành công {len(data)} bài toán.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def coding_create(request):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền thêm bài tập lập trình.")
        
    if request.method == 'POST':
        data = _process_topics_in_post(request.POST)
        form = CodingQuestionForm(data)
        if form.is_valid():
            question = form.save(commit=False)
            question.created_by = request.user
            exam_id = request.GET.get('exam_id')
            if exam_id and exam_id.isdigit():
                exam = get_object_or_404(CodingExam, id=int(exam_id))
                if exam.created_by != request.user:
                    raise PermissionDenied("Bạn không có quyền thêm bài tập vào kỳ thi này.")
                question.exam_id = exam.id
            question.save()
            form.save_m2m()
            if question.exam_id:
                return redirect('coding_exam_detail', exam_id=question.exam_id)
            return redirect('coding_manage_list')
    else:
        form = CodingQuestionForm()
        
    return render(request, 'quiz/coding/form.html', {
        'form': form, 
        'title': 'Thêm bài tập lập trình',
        'exam_id': request.GET.get('exam_id')
    })

@login_required
def coding_edit(request, question_id):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền sửa bài tập lập trình.")
        
    question = get_object_or_404(CodingQuestion, id=question_id)
    
    # Only admin, creator, or exam creator can edit
    is_exam_creator = question.exam and question.exam.created_by == request.user
    if question.created_by != request.user and not is_exam_creator:
        raise PermissionDenied("Bạn chỉ có thể sửa bài do chính mình tạo.")
        
    if request.method == 'POST':
        data = _process_topics_in_post(request.POST)
        form = CodingQuestionForm(data, instance=question)
        if form.is_valid():
            form.save()
            if question.exam_id:
                return redirect('coding_exam_detail', exam_id=question.exam_id)
            return redirect('coding_manage_list')
    else:
        form = CodingQuestionForm(instance=question)
        
    return render(request, 'quiz/coding/form.html', {
        'form': form, 
        'title': 'Sửa bài tập lập trình',
        'exam_id': question.exam_id
    })

# Map language choices to Piston language identifiers
LANGUAGE_MAP = {
    'python': {'language': 'python', 'version': '3.10.0'},
    'cpp': {'language': 'c++', 'version': '10.2.0'}
}

from django.core.paginator import Paginator
from django.db.models import Q

def coding_list_view(request):
    questions = CodingQuestion.objects.filter(is_public=True, is_active=True).order_by('-created_at')
    
    # Filter
    q_search = request.GET.get('q', '').strip()
    difficulty = request.GET.get('difficulty', '')
    topic_id = request.GET.get('topic', '')
    author_q = request.GET.get('author', '').strip()
    
    if q_search:
        import unicodedata
        from django.db.models import Func, CharField
        q_unaccent = unicodedata.normalize('NFKD', q_search).encode('ASCII', 'ignore').decode('utf-8')
        questions = questions.annotate(
            title_unaccent=Func('title', function='unaccent', output_field=CharField())
        ).filter(
            Q(title__icontains=q_search) | Q(title_unaccent__icontains=q_unaccent)
        )
    if difficulty:
        questions = questions.filter(difficulty=difficulty)
    if topic_id and topic_id.isdigit():
        questions = questions.filter(topics__id=topic_id)
    if author_q:
        import unicodedata
        from django.db.models import Func, CharField
        a_unaccent = unicodedata.normalize('NFKD', author_q).encode('ASCII', 'ignore').decode('utf-8')
        questions = questions.annotate(
            u_un=Func('created_by__username', function='unaccent', output_field=CharField()),
            u_fn=Func('created_by__first_name', function='unaccent', output_field=CharField()),
            u_ln=Func('created_by__last_name', function='unaccent', output_field=CharField())
        ).filter(
            Q(created_by__username__icontains=author_q) |
            Q(created_by__first_name__icontains=author_q) |
            Q(created_by__last_name__icontains=author_q) |
            Q(u_un__icontains=a_unaccent) |
            Q(u_fn__icontains=a_unaccent) |
            Q(u_ln__icontains=a_unaccent)
        )
        
    # Pagination
    paginator = Paginator(questions, 10) # 10 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all topics for filter dropdown
    all_topics = CodingTopic.objects.all().order_by('name')

    solved_questions = set()
    attempted_questions = set()
    
    if request.user.is_authenticated:
        # Get user submissions to show solved status
        submissions = CodeSubmission.objects.filter(student=request.user)
        solved_questions = set(submissions.filter(status='Accepted').values_list('question_id', flat=True))
        attempted_questions = set(submissions.values_list('question_id', flat=True))
    
    for q in page_obj:
        if q.id in solved_questions:
            q.status = 'solved'
        elif q.id in attempted_questions:
            q.status = 'attempted'
        else:
            q.status = 'unattempted'
            
    return render(request, 'quiz/coding/list.html', {
        'page_obj': page_obj,
        'all_topics': all_topics,
        'q_search': q_search,
        'difficulty': difficulty,
        'topic_id': topic_id,
        'author_q': author_q
    })

def coding_detail_view(request, question_id):
    question = get_object_or_404(CodingQuestion, id=question_id)
    latest_submission = None
    attempt = None
    remaining_time = None

    latest_submission_passed_count = 0
    details_json = "null"

    if request.user.is_authenticated:
        # Get latest submission if any
        latest_submission = CodeSubmission.objects.filter(student=request.user, question=question).first()
        if latest_submission and latest_submission.details:
            latest_submission_passed_count = sum(1 for tc in latest_submission.details if tc.get('status') == 'Accepted')
            import json
            details_json = json.dumps(latest_submission.details)
        
        if question.exam_id:
            try:
                attempt = CodingExamAttempt.objects.get(user=request.user, exam=question.exam)
                if question.exam.duration > 0:
                    from django.utils import timezone
                    elapsed = (timezone.now() - attempt.start_time).total_seconds()
                    remaining_time = max(0, int(question.exam.duration * 60 - elapsed))
            except CodingExamAttempt.DoesNotExist:
                return redirect('coding_exam_detail', exam_id=question.exam_id)
    
    comments = question.comments.all()
    
    return render(request, 'quiz/coding/detail.html', {
        'question': question,
        'latest_submission': latest_submission,
        'latest_submission_passed_count': latest_submission_passed_count,
        'details_json': details_json,
        'comments': comments,
        'attempt': attempt,
        'remaining_time': remaining_time
    })

@login_required
@require_POST
def add_coding_comment(request, question_id):
    question = get_object_or_404(CodingQuestion, id=question_id)
    content = request.POST.get('content', '').strip()
    if content:
        CodingComment.objects.create(
            user=request.user,
            question=question,
            content=content
        )
    return redirect('coding_detail', question_id=question.id)

@login_required
@require_POST
def submit_code_api(request, question_id):
    question = get_object_or_404(CodingQuestion, id=question_id)
    
    if question.exam_id:
        try:
            attempt = CodingExamAttempt.objects.get(user=request.user, exam=question.exam)
            if question.exam.duration > 0:
                from django.utils import timezone
                elapsed = (timezone.now() - attempt.start_time).total_seconds()
                # Thêm 5 giây buffer
                if elapsed > (question.exam.duration * 60 + 5):
                    return JsonResponse({'error': 'Đã hết thời gian làm bài'}, status=403)
        except CodingExamAttempt.DoesNotExist:
            return JsonResponse({'error': 'Bạn chưa bắt đầu kỳ thi này'}, status=403)
    
    try:
        data = json.loads(request.body)
        code = data.get('code', '')
        language = data.get('language', 'python')
    except Exception:
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    if not code:
        return JsonResponse({'error': 'Code is required'}, status=400)
        
    if language not in LANGUAGE_MAP:
        return JsonResponse({'error': 'Unsupported language'}, status=400)

    testcases = question.testcases.all()
    if not testcases:
        return JsonResponse({'error': 'No testcases found for this question'}, status=400)

    total_score = 0
    passed_count = 0
    results = []
    
    overall_status = 'Accepted'

    for tc in testcases:
        try:
            # Chạy nội bộ thay vì gọi Piston API
            res_data = execute_code_locally(language, code, tc.input_data, question.time_limit)
            
            status = res_data['status']
            if status == 'Accepted':
                output = res_data.get('output', '').strip()
                expected = tc.expected_output.strip()
                
                # Normalize line endings
                output = output.replace('\r\n', '\n')
                expected = expected.replace('\r\n', '\n')
                
                if output == expected:
                    passed_count += 1
                    total_score += tc.points
                else:
                    status = 'Wrong Answer'
            else:
                output = res_data.get('output', '')
                
            # Update overall status if not Accepted
            if status != 'Accepted' and overall_status == 'Accepted':
                overall_status = status
                
            results.append({
                'testcase_id': tc.id,
                'status': status,
                'output': output if not tc.is_hidden else 'Hidden',
                'expected': tc.expected_output if not tc.is_hidden else 'Hidden',
                'is_hidden': tc.is_hidden,
                'time': res_data.get('time', 0)
            })
            
        except Exception as e:
            overall_status = 'System Error'
            results.append({
                'testcase_id': tc.id,
                'status': 'System Error',
                'output': str(e),
                'expected': tc.expected_output if not tc.is_hidden else 'Hidden',
                'is_hidden': tc.is_hidden,
                'time': 0
            })
            break # Stop executing if system error

    # Save submission
    submission = CodeSubmission.objects.create(
        student=request.user,
        question=question,
        language=language,
        code=code,
        status=overall_status,
        score=total_score,
        details=results
    )

    if question.exam_id:
        from django.db.models import Max
        try:
            attempt = CodingExamAttempt.objects.get(user=request.user, exam_id=question.exam_id)
            exam_scores = CodeSubmission.objects.filter(
                student=request.user, 
                question__exam_id=question.exam_id
            ).values('question').annotate(max_score=Max('score'))
            attempt.total_score = sum(item['max_score'] for item in exam_scores)
            attempt.save()
        except CodingExamAttempt.DoesNotExist:
            pass

    return JsonResponse({
        'submission_id': submission.id,
        'status': overall_status,
        'score': total_score,
        'passed_count': passed_count,
        'total_testcases': len(testcases),
        'results': results
    })

@login_required
@require_POST
def coding_delete_testcase(request, testcase_id):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền quản lý bài tập lập trình.")
        
    tc = get_object_or_404(TestCase, id=testcase_id)
    question = tc.question
    
    is_exam_creator = question.exam and question.exam.created_by == request.user
    if question.created_by != request.user and not is_exam_creator:
        raise PermissionDenied("Bạn chỉ có thể sửa bài do chính mình tạo.")
        
    tc.delete()
    return JsonResponse({'success': True})

@login_required
@require_POST
def coding_update_testcase_points(request, question_id):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền quản lý bài tập lập trình.")
        
    question = get_object_or_404(CodingQuestion, id=question_id)
    is_exam_creator = question.exam and question.exam.created_by == request.user
    if question.created_by != request.user and not is_exam_creator:
        raise PermissionDenied("Bạn chỉ có thể sửa bài do chính mình tạo.")
        
    try:
        new_points = float(request.POST.get('points', 0))
        if new_points < 0:
            return JsonResponse({'error': 'Điểm không được âm'}, status=400)
            
        question.testcases.all().update(points=new_points)
        return JsonResponse({'success': True})
    except ValueError:
        return JsonResponse({'error': 'Điểm không hợp lệ'}, status=400)

@login_required
@require_POST
def coding_update_single_tc_points(request, testcase_id):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền quản lý bài tập lập trình.")
        
    tc = get_object_or_404(TestCase, id=testcase_id)
    question = tc.question
    
    is_exam_creator = question.exam and question.exam.created_by == request.user
    if question.created_by != request.user and not is_exam_creator:
        raise PermissionDenied("Bạn chỉ có thể sửa bài do chính mình tạo.")
        
    try:
        new_points = float(request.POST.get('points', 0))
        if new_points < 0:
            return JsonResponse({'error': 'Điểm không được âm'}, status=400)
            
        tc.points = new_points
        tc.save()
        return JsonResponse({'success': True})
    except ValueError:
        return JsonResponse({'error': 'Điểm không hợp lệ'}, status=400)

@login_required
def coding_toggle_attr(request, question_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    question = get_object_or_404(CodingQuestion, id=question_id)
    is_exam_creator = question.exam and question.exam.created_by == request.user
    if question.created_by != request.user and not is_exam_creator:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    attr = request.POST.get('attr')
    if attr in ['is_public', 'is_active']:
        current_val = getattr(question, attr)
        setattr(question, attr, not current_val)
        question.save()
        return JsonResponse({'success': True, 'state': getattr(question, attr)})
    return JsonResponse({'error': 'Invalid attribute'}, status=400)

def coding_auto_testcase(request, question_id):
    if not hasattr(request.user, 'profile') or not request.user.profile.is_coding_contributor():
        raise PermissionDenied("Bạn không có quyền quản lý bài tập lập trình.")
        
    question = get_object_or_404(CodingQuestion, id=question_id)
    is_exam_creator = question.exam and question.exam.created_by == request.user
    if question.created_by != request.user and not is_exam_creator:
        raise PermissionDenied("Bạn chỉ có thể sửa bài do chính mình tạo.")

    if request.method == 'POST':
        if request.POST.get('action') == 'save_solution':
            language = request.POST.get('language')
            solution_code = request.POST.get('solution_code')
            if not language or not solution_code:
                return JsonResponse({'error': 'Thiếu tham số'}, status=400)
            if language == 'python':
                question.solution_code_python = solution_code
            elif language == 'cpp':
                question.solution_code_cpp = solution_code
            question.save()
            return JsonResponse({'success': True, 'message': 'Đã lưu đáp án chuẩn thành công!'})

        language = request.POST.get('language')
        solution_code = request.POST.get('solution_code')
        inputs_raw = request.POST.get('inputs_raw')
        
        if not language or not solution_code or not inputs_raw:
            return JsonResponse({'error': 'Thiếu tham số'}, status=400)
            
        if language not in LANGUAGE_MAP:
            return JsonResponse({'error': 'Ngôn ngữ không được hỗ trợ'}, status=400)

        # Tự động lưu đáp án chuẩn
        if language == 'python':
            question.solution_code_python = solution_code
        elif language == 'cpp':
            question.solution_code_cpp = solution_code
        question.save()

        # Parse inputs
        inputs = [i.strip() for i in inputs_raw.split('---') if i.strip()]
        if not inputs:
            return JsonResponse({'error': 'Không có dữ liệu đầu vào hợp lệ. Hãy ngăn cách các testcase bằng "---"'}, status=400)
            
        generated_count = 0
        points_per_tc = round(question.max_score / len(inputs), 2) if len(inputs) > 0 else 0

        # Run solution to get outputs
        for inp in inputs:
            try:
                res_data = execute_code_locally(language, solution_code, inp, 5)
                
                if res_data['status'] == 'Accepted':
                    output = res_data.get('output', '').strip()
                    # Create testcase
                    TestCase.objects.create(
                        question=question,
                        input_data=inp,
                        expected_output=output,
                        is_hidden=False,
                        points=points_per_tc
                    )
                    generated_count += 1
                else:
                    error_msg = res_data.get('output', 'Lỗi khi chạy code (Runtime/Compile Error)')
                    return JsonResponse({'error': f'Code đáp án bị lỗi ở input "{inp}": {error_msg}'}, status=400)
                    
            except Exception as e:
                print("Error generating testcase:", e)
                return JsonResponse({'error': f'Lỗi kết nối tới máy chủ biên dịch: {str(e)}'}, status=500)
                
        return JsonResponse({'success': True, 'generated': generated_count})

    return render(request, 'quiz/coding/auto_testcase.html', {'question': question})
