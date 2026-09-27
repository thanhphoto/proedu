import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q, Count, Avg, Max
from django.utils import timezone
from django.contrib.auth.models import User

from .models import (
    CodingClassroom,
    CodingClassroomMember,
    CodingClassroomTopic,
    CodingClassroomAssignment,
    CodingQuestion,
    CodeSubmission,
    CodingTopic,
    Plan,
    UserProfile
)
from .subscription_service import has_feature, get_user_plan

def user_can_manage_coding_classrooms(user) -> bool:
    """Kiểm tra quyền tạo và quản lý Lớp học Luyện Code (Gói Giáo viên & Khảo thí, Admin, Staff)"""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if has_feature(user, 'can_create_coding_exam'):
        return True
    if hasattr(user, 'profile') and user.profile.is_coding_contributor():
        return True
    return False


@login_required
def coding_classroom_list(request):
    """Trang tổng hợp Lớp học Luyện Code: Lớp tôi giảng dạy & Lớp tôi đang theo học"""
    can_manage = user_can_manage_coding_classrooms(request.user)
    
    # 1. Lớp do giáo viên này tạo
    teaching_classrooms = []
    if can_manage:
        teaching_classrooms = CodingClassroom.objects.filter(teacher=request.user).annotate(
            num_students=Count('members', filter=Q(members__status='approved'), distinct=True),
            num_pending=Count('members', filter=Q(members__status='pending'), distinct=True),
            num_assignments=Count('assignments', distinct=True),
            num_topics=Count('custom_topics', distinct=True)
        ).order_by('-created_at')

    # 2. Lớp mà người dùng tham gia (học sinh)
    enrolled_memberships = CodingClassroomMember.objects.filter(
        user=request.user
    ).select_related('classroom', 'classroom__teacher').order_by('-joined_at')

    return render(request, 'quiz/coding/classroom_list.html', {
        'can_manage': can_manage,
        'teaching_classrooms': teaching_classrooms,
        'enrolled_memberships': enrolled_memberships,
    })


@login_required
def coding_classroom_create(request):
    """Tạo lớp học mới (Yêu cầu Gói Giáo Viên & Khảo Thí hoặc Quản trị viên)"""
    if not user_can_manage_coding_classrooms(request.user):
        messages.warning(
            request, 
            "Tính năng tạo Lớp học Luyện Code riêng dành cho Gói Giáo Viên & Khảo Thí. Vui lòng nâng cấp gói để sử dụng."
        )
        return redirect('pricing')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        custom_code = request.POST.get('code', '').strip().upper()
        allow_join = request.POST.get('allow_join') == 'on'
        
        # Nhóm kiến thức khởi tạo mẫu (nếu người dùng nhập)
        initial_topics_str = request.POST.get('initial_topics', '').strip()

        form_data = {'name': name, 'description': description, 'code': custom_code}

        if not name:
            messages.error(request, "Vui lòng nhập tên lớp học.")
            return render(request, 'quiz/coding/classroom_form.html', {'classroom': form_data, 'is_create': True})

        if custom_code:
            if len(custom_code) > 20:
                messages.error(request, "Mã lớp không được vượt quá 20 ký tự.")
                return render(request, 'quiz/coding/classroom_form.html', {'classroom': form_data, 'is_create': True})
            if CodingClassroom.objects.filter(code=custom_code).exists():
                messages.error(request, f"Mã lớp '{custom_code}' đã tồn tại. Vui lòng chọn mã khác.")
                return render(request, 'quiz/coding/classroom_form.html', {'classroom': form_data, 'is_create': True})

        classroom = CodingClassroom(
            name=name,
            description=description,
            teacher=request.user,
            allow_join=allow_join
        )
        if custom_code:
            classroom.code = custom_code
        classroom.save()

        # Tạo các nhóm kiến thức mặc định nếu có
        if initial_topics_str:
            lines = [line.strip() for line in initial_topics_str.split('\n') if line.strip()]
            for idx, line in enumerate(lines):
                CodingClassroomTopic.objects.create(
                    classroom=classroom,
                    name=line,
                    order=idx + 1
                )
        else:
            # Tạo nhóm mặc định để giáo viên dễ hình dung
            CodingClassroomTopic.objects.create(
                classroom=classroom,
                name="Chuyên đề 1: Nhập xuất & Cấu trúc cơ bản",
                order=1
            )
            CodingClassroomTopic.objects.create(
                classroom=classroom,
                name="Chuyên đề 2: Cấu trúc lặp & Mảng dữ liệu",
                order=2
            )

        messages.success(request, f"Đã tạo thành công lớp học '{classroom.name}' (Mã lớp: {classroom.code})!")
        return redirect('coding_classroom_manage', classroom_id=classroom.id)

    return render(request, 'quiz/coding/classroom_form.html', {
        'is_create': True
    })


@login_required
def coding_classroom_edit(request, classroom_id):
    """Chỉnh sửa thông tin lớp học (không cho phép sửa mã lớp)"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        messages.error(request, "Bạn không có quyền chỉnh sửa lớp học này.")
        return redirect('coding_classroom_join_or_view', code=classroom.code)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        allow_join = request.POST.get('allow_join') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        if not name:
            messages.error(request, "Tên lớp không được để trống.")
            return render(request, 'quiz/coding/classroom_form.html', {'classroom': classroom, 'is_create': False})

        # Lưu ý: Không cho phép sửa classroom.code để bảo toàn link tham gia của học sinh
        classroom.name = name
        classroom.description = description
        classroom.allow_join = allow_join
        classroom.is_active = is_active
        classroom.save()

        messages.success(request, "Đã cập nhật thông tin lớp học thành công.")
        return redirect('coding_classroom_manage', classroom_id=classroom.id)

    return render(request, 'quiz/coding/classroom_form.html', {
        'classroom': classroom,
        'is_create': False
    })


@login_required
@require_POST
def coding_classroom_delete(request, classroom_id):
    """Xóa lớp học"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return HttpResponseForbidden("Bạn không có quyền xóa lớp học này.")
    name = classroom.name
    classroom.delete()
    messages.success(request, f"Đã xóa lớp học '{name}'.")
    return redirect('coding_classroom_list')


def coding_classroom_join_or_view(request, code):
    """
    URL: /lop-hoc/<str:code>/
    Xử lý học sinh join vào lớp hoặc xem lớp học sau khi được duyệt.
    """
    clean_code = code.strip().upper()
    classroom = get_object_or_404(CodingClassroom, code__iexact=clean_code)

    # Nếu là giáo viên phụ trách lớp học: chuyển ngay sang trang quản lý lớp
    if request.user.is_authenticated and classroom.teacher == request.user:
        return redirect('coding_classroom_manage', classroom_id=classroom.id)

    # Kiểm tra trạng thái thành viên nếu học sinh đã đăng nhập
    member = None
    if request.user.is_authenticated:
        member = CodingClassroomMember.objects.filter(classroom=classroom, user=request.user).first()

    # Xử lý khi học sinh bấm "Tham gia lớp học"
    if request.method == 'POST' and request.POST.get('action') == 'join':
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.get_full_path()}")

        if not classroom.is_active or not classroom.allow_join:
            messages.error(request, "Lớp học này hiện không nhận thêm học sinh mới.")
            return redirect('coding_classroom_join_or_view', code=clean_code)

        if not member:
            CodingClassroomMember.objects.create(
                classroom=classroom,
                user=request.user,
                status='pending'
            )
            messages.success(request, "Đã gửi yêu cầu tham gia! Vui lòng chờ giáo viên xác nhận để chính thức vào lớp.")
        elif member.status == 'rejected':
            member.status = 'pending'
            member.joined_at = timezone.now()
            member.save()
            messages.info(request, "Đã gửi lại yêu cầu tham gia lớp học. Vui lòng chờ giáo viên xác nhận.")
        return redirect('coding_classroom_join_or_view', code=clean_code)

    # Lấy danh sách chuyên đề và bài tập
    assignments = classroom.assignments.select_related('question', 'topic').order_by('topic__order', 'order', 'id')
    topics = classroom.custom_topics.all().order_by('order', 'id')

    # 1. Chưa gửi yêu cầu hoặc đang ở trạng thái Pending / Rejected hoặc Khách chưa đăng nhập
    if not member or member.status != 'approved':
        topic_dict = {t.id: {'topic': t, 'assignments': []} for t in topics}
        uncategorized_assignments = []
        for a in assignments:
            if a.topic_id and a.topic_id in topic_dict:
                topic_dict[a.topic_id]['assignments'].append(a)
            else:
                uncategorized_assignments.append(a)

        topic_groups = [topic_dict[t.id] for t in topics]

        return render(request, 'quiz/coding/classroom_join_preview.html', {
            'classroom': classroom,
            'member': member,
            'topic_groups': topic_groups,
            'uncategorized_assignments': uncategorized_assignments,
            'assignments_count': len(assignments),
            'topics_count': len(topics),
            'approved_students_count': classroom.approved_students_count,
        })

    # 2. Đã được duyệt CHÍNH THỨC (Approved) -> Hiển thị Giao diện học tập trong lớp
    assignments = classroom.assignments.select_related('question', 'topic').order_by('topic__order', 'order', 'id')
    topics = classroom.custom_topics.all().order_by('order', 'id')

    # Lấy kết quả làm bài của học sinh (Nếu học sinh đã làm trước đó thì lấy đó là kết quả trong lớp)
    assigned_question_ids = [a.question_id for a in assignments]
    
    # Lấy toàn bộ submission của học sinh này đối với các bài trong lớp
    all_user_subs = CodeSubmission.objects.filter(
        student=request.user,
        question_id__in=assigned_question_ids
    ).order_by('question_id', '-score', '-created_at')

    # Map best submission per question
    best_sub_by_q = {}
    for sub in all_user_subs:
        qid = sub.question_id
        if qid not in best_sub_by_q:
            best_sub_by_q[qid] = sub

    # Gom bài tập theo từng Nhóm kiến thức
    # Nhóm có ID -> danh sách bài, và nhóm Chưa phân loại (topic=None)
    topic_groups = []
    uncategorized_assignments = []

    total_score = 0.0
    total_max_score = 0.0
    passed_count = 0
    attempted_count = 0

    # Build topic lookup
    topic_dict = {t.id: {'topic': t, 'assignments': []} for t in topics}

    for assign in assignments:
        q = assign.question
        sub = best_sub_by_q.get(q.id)
        
        assign.user_submission = sub
        if sub:
            assign.user_status = sub.status
            assign.user_score = round(sub.score, 2)
            total_score += sub.score
            attempted_count += 1
            if sub.status == 'Accepted':
                passed_count += 1
        else:
            assign.user_status = 'Chưa làm'
            assign.user_score = 0.0

        total_max_score += q.max_score

        if assign.topic_id and assign.topic_id in topic_dict:
            topic_dict[assign.topic_id]['assignments'].append(assign)
        else:
            uncategorized_assignments.append(assign)

    for t in topics:
        topic_groups.append(topic_dict[t.id])

    total_questions = len(assignments)
    progress_percent = int((passed_count / total_questions * 100)) if total_questions > 0 else 0

    return render(request, 'quiz/coding/classroom_student_view.html', {
        'classroom': classroom,
        'member': member,
        'topic_groups': topic_groups,
        'uncategorized_assignments': uncategorized_assignments,
        'total_questions': total_questions,
        'passed_count': passed_count,
        'attempted_count': attempted_count,
        'unattempted_count': max(0, total_questions - attempted_count),
        'total_score': round(total_score, 2),
        'total_max_score': round(total_max_score, 2),
        'progress_percent': progress_percent,
    })


@login_required
def coding_classroom_manage(request, classroom_id):
    """
    Giao diện Quản Lý Lớp Học Toàn Diện dành cho Giáo Viên:
    - Quản lý Nhóm kiến thức & Phân chia bài tập
    - Danh sách học sinh, duyệt yêu cầu, thêm học sinh trực tiếp không cần xác nhận
    - Xem bài làm của học sinh (Theo danh sách học sinh)
    - Xem thống kê danh sách bài tập (mỗi bài có bao nhiêu học sinh làm)
    """
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        messages.error(request, "Bạn không có quyền quản lý lớp học này.")
        return redirect('coding_classroom_join_or_view', code=classroom.code)

    # 1. Danh sách học sinh chính thức và yêu cầu chờ duyệt
    all_members = classroom.members.select_related('user', 'user__profile').order_by('-joined_at')
    approved_members = [m for m in all_members if m.status == 'approved']
    pending_members = [m for m in all_members if m.status == 'pending']

    # 2. Danh sách nhóm kiến thức và bài tập trong lớp
    topics = classroom.custom_topics.all().order_by('order', 'id')
    assignments = classroom.assignments.select_related('question', 'topic').order_by('topic__order', 'order', 'id')
    
    assigned_q_ids = [a.question_id for a in assignments]
    total_class_max_score = sum(a.question.max_score for a in assignments)

    # 3. Tính toán thống kê theo Học sinh:
    # Lấy toàn bộ submission của các học sinh chính thức đối với các câu hỏi trong lớp
    approved_user_ids = [m.user_id for m in approved_members]
    
    all_submissions = CodeSubmission.objects.filter(
        student_id__in=approved_user_ids,
        question_id__in=assigned_q_ids
    ).values('student_id', 'question_id', 'status', 'score', 'id', 'created_at')

    # Mapping: (student_id, question_id) -> best submission
    student_q_sub = {}
    for s in all_submissions:
        key = (s['student_id'], s['question_id'])
        if key not in student_q_sub or s['score'] > student_q_sub[key]['score']:
            student_q_sub[key] = s

    # Tính tổng quan cho từng học sinh
    student_stats = []
    total_questions_count = len(assignments)

    for m in approved_members:
        u_id = m.user_id
        done_count = 0
        accepted_count = 0
        u_total_score = 0.0

        for a in assignments:
            sub = student_q_sub.get((u_id, a.question_id))
            if sub:
                done_count += 1
                u_total_score += sub['score']
                if sub['status'] == 'Accepted':
                    accepted_count += 1

        percent = int((accepted_count / total_questions_count * 100)) if total_questions_count > 0 else 0
        student_stats.append({
            'member': m,
            'user': m.user,
            'done_count': done_count,
            'accepted_count': accepted_count,
            'total_score': round(u_total_score, 2),
            'percent': percent,
        })

    # 4. Tính toán thống kê theo Bài tập:
    # "Xem được danh sách bài tập mỗi bài tập có bao nhiêu học sinh làm"
    question_stats = []
    total_students_count = len(approved_members)

    for a in assignments:
        q = a.question
        q_attempted_users = set()
        q_accepted_users = set()
        scores_list = []

        for m in approved_members:
            sub = student_q_sub.get((m.user_id, q.id))
            if sub:
                q_attempted_users.add(m.user_id)
                scores_list.append(sub['score'])
                if sub['status'] == 'Accepted':
                    q_accepted_users.add(m.user_id)

        attempted_num = len(q_attempted_users)
        accepted_num = len(q_accepted_users)
        avg_score = round(sum(scores_list) / len(scores_list), 2) if scores_list else 0.0
        attempt_rate = int((attempted_num / total_students_count * 100)) if total_students_count > 0 else 0

        question_stats.append({
            'assignment': a,
            'question': q,
            'topic': a.topic,
            'attempted_num': attempted_num,
            'accepted_num': accepted_num,
            'attempt_rate': attempt_rate,
            'avg_score': avg_score,
            'total_students': total_students_count,
        })

    # Gom bài tập theo từng Nhóm kiến thức cho Tab 1
    topic_dict = {t.id: {'topic': t, 'assignments': []} for t in topics}
    uncategorized_assignments = []
    for a in assignments:
        if a.topic_id and a.topic_id in topic_dict:
            topic_dict[a.topic_id]['assignments'].append(a)
        else:
            uncategorized_assignments.append(a)

    topic_groups = [topic_dict[t.id] for t in topics]

    # Danh sách chủ đề hệ thống phục vụ bộ lọc tìm bài tập
    system_topics = CodingTopic.objects.all().order_by('name')

    return render(request, 'quiz/coding/classroom_manage.html', {
        'classroom': classroom,
        'topics': topics,
        'topic_groups': topic_groups,
        'uncategorized_assignments': uncategorized_assignments,
        'pending_members': pending_members,
        'approved_members': approved_members,
        'student_stats': student_stats,
        'question_stats': question_stats,
        'total_questions_count': total_questions_count,
        'total_students_count': total_students_count,
        'total_class_max_score': total_class_max_score,
        'system_topics': system_topics,
    })


# =====================================================================
# CÁC API THAO TÁC QUẢN LÝ LỚP HỌC (AJAX / POST)
# =====================================================================

@login_required
@require_POST
def api_coding_classroom_approve_member(request, classroom_id):
    """Giáo viên duyệt hoặc từ chối yêu cầu tham gia lớp học"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thực hiện thao tác này.'}, status=403)

    try:
        data = json.loads(request.body)
        member_id = data.get('member_id')
        action = data.get('action') # 'approve', 'reject', 'approve_all'

        if action == 'approve_all':
            CodingClassroomMember.objects.filter(classroom=classroom, status='pending').update(
                status='approved',
                approved_at=timezone.now()
            )
            return JsonResponse({'success': True, 'message': 'Đã duyệt toàn bộ học sinh chờ.'})

        member = get_object_or_404(CodingClassroomMember, id=member_id, classroom=classroom)
        if action == 'approve':
            member.status = 'approved'
            member.approved_at = timezone.now()
            member.save()
            return JsonResponse({'success': True, 'status': 'approved'})
        elif action == 'reject':
            member.status = 'rejected'
            member.save()
            return JsonResponse({'success': True, 'status': 'rejected'})
        else:
            return JsonResponse({'error': 'Hành động không hợp lệ'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_coding_classroom_add_student(request, classroom_id):
    """
    Giáo viên thêm trực tiếp học sinh vào lớp (KHÔNG CẦN XÁC NHẬN).
    Nhập username hoặc email của học sinh.
    """
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thêm học sinh vào lớp này.'}, status=403)

    try:
        data = json.loads(request.body)
        identifier = data.get('identifier', '').strip() # username or email or comma separated

        if not identifier:
            return JsonResponse({'error': 'Vui lòng nhập tên đăng nhập hoặc email học sinh.'}, status=400)

        added_users = []
        already_members = []
        not_found = []

        tokens = [t.strip() for t in identifier.replace(';', ',').split(',') if t.strip()]

        for tok in tokens:
            target_user = User.objects.filter(Q(username__iexact=tok) | Q(email__iexact=tok)).first()
            if not target_user:
                not_found.append(tok)
                continue

            member, created = CodingClassroomMember.objects.get_or_create(
                classroom=classroom,
                user=target_user,
                defaults={'status': 'approved', 'approved_at': timezone.now()}
            )
            if not created:
                if member.status != 'approved':
                    member.status = 'approved'
                    member.approved_at = timezone.now()
                    member.save()
                    added_users.append(target_user.username)
                else:
                    already_members.append(target_user.username)
            else:
                added_users.append(target_user.username)

        msg_parts = []
        if added_users:
            msg_parts.append(f"Đã thêm thành công: {', '.join(added_users)}")
        if already_members:
            msg_parts.append(f"Đã có trong lớp từ trước: {', '.join(already_members)}")
        if not_found:
            msg_parts.append(f"Không tìm thấy tài khoản: {', '.join(not_found)}")

        return JsonResponse({
            'success': True,
            'message': ' | '.join(msg_parts),
            'added_count': len(added_users)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_coding_classroom_remove_member(request, classroom_id, member_id):
    """Xóa học sinh khỏi lớp học"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thực hiện thao tác này.'}, status=403)

    member = get_object_or_404(CodingClassroomMember, id=member_id, classroom=classroom)
    username = member.user.username
    member.delete()
    return JsonResponse({'success': True, 'message': f"Đã xóa học sinh {username} khỏi lớp."})


@login_required
@require_POST
def api_coding_classroom_topic_create(request, classroom_id):
    """Tạo nhóm kiến thức riêng trong lớp học"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thực hiện thao tác này.'}, status=403)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        order = int(data.get('order', 0))

        if not name:
            return JsonResponse({'error': 'Tên nhóm kiến thức không được để trống.'}, status=400)

        topic = CodingClassroomTopic.objects.create(
            classroom=classroom,
            name=name,
            description=description,
            order=order or (classroom.custom_topics.count() + 1)
        )
        return JsonResponse({
            'success': True,
            'topic': {
                'id': topic.id,
                'name': topic.name,
                'description': topic.description,
                'order': topic.order
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_coding_classroom_topic_edit(request, classroom_id, topic_id):
    """Chỉnh sửa nhóm kiến thức"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thực hiện thao tác này.'}, status=403)

    topic = get_object_or_404(CodingClassroomTopic, id=topic_id, classroom=classroom)
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        order = int(data.get('order', topic.order))

        if not name:
            return JsonResponse({'error': 'Tên nhóm kiến thức không được để trống.'}, status=400)

        topic.name = name
        topic.description = description
        topic.order = order
        topic.save()

        return JsonResponse({'success': True, 'topic': {'id': topic.id, 'name': topic.name, 'order': topic.order}})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_coding_classroom_topic_delete(request, classroom_id, topic_id):
    """Xóa nhóm kiến thức (các bài tập thuộc nhóm sẽ chuyển sang trạng thái chưa phân nhóm)"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thực hiện thao tác này.'}, status=403)

    topic = get_object_or_404(CodingClassroomTopic, id=topic_id, classroom=classroom)
    topic.delete()
    return JsonResponse({'success': True, 'message': 'Đã xóa nhóm kiến thức.'})


@login_required
def api_coding_classroom_search_questions(request, classroom_id):
    """
    Tìm kiếm câu hỏi trên hệ thống hoặc do giáo viên tạo để thêm vào lớp.
    """
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền.'}, status=403)

    q_search = request.GET.get('q', '').strip()
    source = request.GET.get('source', 'all') # 'all', 'mine', 'public'
    difficulty = request.GET.get('difficulty', '').strip()
    topic_id = request.GET.get('topic_id', '').strip()

    # Các câu hỏi đã có trong lớp
    existing_q_ids = classroom.assignments.values_list('question_id', flat=True)

    questions_qs = CodingQuestion.objects.exclude(id__in=existing_q_ids)

    if source == 'mine':
        questions_qs = questions_qs.filter(created_by=request.user)
    elif source == 'public':
        questions_qs = questions_qs.filter(is_public=True)
    else: # all accessible
        questions_qs = questions_qs.filter(Q(is_public=True) | Q(created_by=request.user))

    if q_search:
        questions_qs = questions_qs.filter(Q(title__icontains=q_search) | Q(code__icontains=q_search))

    if difficulty:
        questions_qs = questions_qs.filter(difficulty=difficulty)

    if topic_id and topic_id.isdigit():
        questions_qs = questions_qs.filter(topics__id=int(topic_id))

    questions_qs = questions_qs.order_by('-created_at')[:40]

    results = []
    for q in questions_qs:
        results.append({
            'id': q.id,
            'code': q.code,
            'title': q.title,
            'difficulty': q.difficulty,
            'max_score': q.max_score,
            'is_mine': q.created_by == request.user,
            'testcases_count': q.testcases.count(),
        })

    return JsonResponse({'questions': results})


@login_required
@require_POST
def api_coding_classroom_add_questions(request, classroom_id):
    """Thêm một hoặc nhiều bài tập vào lớp học (gán vào nhóm kiến thức cụ thể)"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền thêm bài tập.'}, status=403)

    try:
        data = json.loads(request.body)
        question_ids = data.get('question_ids', [])
        topic_id = data.get('topic_id') # Có thể None nếu chưa phân nhóm

        if not question_ids:
            return JsonResponse({'error': 'Vui lòng chọn ít nhất 1 bài tập.'}, status=400)

        target_topic = None
        if topic_id:
            target_topic = get_object_or_404(CodingClassroomTopic, id=topic_id, classroom=classroom)

        added_count = 0
        for q_id in question_ids:
            q = get_object_or_404(CodingQuestion, id=q_id)
            # Chỉ cho phép bài công khai hoặc do chính giáo viên tạo
            if not q.is_public and q.created_by != request.user:
                continue

            assignment, created = CodingClassroomAssignment.objects.get_or_create(
                classroom=classroom,
                question=q,
                defaults={
                    'topic': target_topic,
                    'order': classroom.assignments.count() + 1
                }
            )
            if not created and target_topic:
                assignment.topic = target_topic
                assignment.save()
            if created:
                added_count += 1

        return JsonResponse({
            'success': True,
            'message': f"Đã thêm {added_count} bài tập vào lớp thành công!",
            'added_count': added_count
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_coding_classroom_remove_question(request, classroom_id, assignment_id):
    """Xóa bài tập khỏi lớp học"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền.'}, status=403)

    assignment = get_object_or_404(CodingClassroomAssignment, id=assignment_id, classroom=classroom)
    title = assignment.question.title
    assignment.delete()
    return JsonResponse({'success': True, 'message': f"Đã xóa bài '{title}' khỏi lớp học."})


@login_required
@require_POST
def api_coding_classroom_move_question(request, classroom_id, assignment_id):
    """Di chuyển bài tập sang nhóm kiến thức khác"""
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền.'}, status=403)

    assignment = get_object_or_404(CodingClassroomAssignment, id=assignment_id, classroom=classroom)
    try:
        data = json.loads(request.body)
        target_topic_id = data.get('topic_id')

        if target_topic_id:
            target_topic = get_object_or_404(CodingClassroomTopic, id=target_topic_id, classroom=classroom)
            assignment.topic = target_topic
        else:
            assignment.topic = None

        assignment.save()
        return JsonResponse({'success': True, 'topic_name': assignment.topic.name if assignment.topic else 'Chưa phân nhóm'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_coding_classroom_student_detail(request, classroom_id, user_id):
    """
    API xem chi tiết toàn bộ bài làm của 1 học sinh trong lớp (theo danh sách bài tập của lớp).
    Giáo viên có thể xem điểm, trạng thái, và nút xem code đã nộp của học sinh.
    """
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user and request.user.id != user_id:
        return JsonResponse({'error': 'Bạn không có quyền xem thông tin này.'}, status=403)

    target_student = get_object_or_404(User, id=user_id)
    assignments = classroom.assignments.select_related('question', 'topic').order_by('topic__order', 'order', 'id')

    assigned_q_ids = [a.question_id for a in assignments]

    # Lấy các bài nộp tốt nhất của học sinh cho các câu hỏi này
    submissions = CodeSubmission.objects.filter(
        student=target_student,
        question_id__in=assigned_q_ids
    ).order_by('question_id', '-score', '-created_at')

    best_subs = {}
    for sub in submissions:
        if sub.question_id not in best_subs:
            best_subs[sub.question_id] = sub

    results = []
    for a in assignments:
        q = a.question
        sub = best_subs.get(q.id)
        results.append({
            'assignment_id': a.id,
            'question_id': q.id,
            'question_code': q.code,
            'question_title': q.title,
            'topic_name': a.topic.name if a.topic else 'Chưa phân nhóm',
            'max_score': q.max_score,
            'status': sub.status if sub else 'Chưa làm',
            'score': round(sub.score, 2) if sub else 0.0,
            'submission_id': sub.id if sub else None,
            'submitted_at': sub.created_at.strftime('%d/%m/%Y %H:%M') if sub else None,
            'language': sub.language if sub else None,
        })

    return JsonResponse({
        'student': {
            'id': target_student.id,
            'username': target_student.username,
            'full_name': target_student.get_full_name() or target_student.username,
            'email': target_student.email
        },
        'submissions': results
    })


@login_required
def api_coding_classroom_question_detail(request, classroom_id, question_id):
    """
    API xem chi tiết 1 bài tập trong lớp: xem mỗi học sinh trong lớp làm bài này như thế nào.
    Hiển thị học sinh nào đã làm, điểm mấy, trạng thái, và học sinh nào chưa làm.
    """
    classroom = get_object_or_404(CodingClassroom, id=classroom_id)
    if classroom.teacher != request.user:
        return JsonResponse({'error': 'Bạn không có quyền xem thông tin này.'}, status=403)

    assignment = get_object_or_404(CodingClassroomAssignment, classroom=classroom, question_id=question_id)
    question = assignment.question

    approved_members = classroom.members.filter(status='approved').select_related('user', 'user__profile')
    member_user_ids = [m.user_id for m in approved_members]

    # Tìm các bài nộp của các học sinh này cho câu hỏi này
    submissions = CodeSubmission.objects.filter(
        student_id__in=member_user_ids,
        question=question
    ).order_by('student_id', '-score', '-created_at')

    best_subs = {}
    for sub in submissions:
        if sub.student_id not in best_subs:
            best_subs[sub.student_id] = sub

    results = []
    attempted_count = 0
    accepted_count = 0

    for m in approved_members:
        u = m.user
        sub = best_subs.get(u.id)
        if sub:
            attempted_count += 1
            if sub.status == 'Accepted':
                accepted_count += 1

        results.append({
            'student_id': u.id,
            'username': u.username,
            'full_name': u.get_full_name() or u.username,
            'avatar_url': u.profile.avatar_url if hasattr(u, 'profile') else '/static/quiz/avatars/avatar-1.svg',
            'status': sub.status if sub else 'Chưa làm',
            'score': round(sub.score, 2) if sub else 0.0,
            'submission_id': sub.id if sub else None,
            'submitted_at': sub.created_at.strftime('%d/%m/%Y %H:%M') if sub else None,
            'language': sub.language if sub else None
        })

    # Sắp xếp: Đã làm lên trước, điểm cao lên trước
    results.sort(key=lambda x: (x['status'] != 'Chưa làm', x['score']), reverse=True)

    return JsonResponse({
        'question': {
            'id': question.id,
            'code': question.code,
            'title': question.title,
            'difficulty': question.difficulty,
            'max_score': question.max_score,
            'topic_name': assignment.topic.name if assignment.topic else 'Chưa phân nhóm'
        },
        'stats': {
            'total_students': len(approved_members),
            'attempted_count': attempted_count,
            'accepted_count': accepted_count,
        },
        'students': results
    })
