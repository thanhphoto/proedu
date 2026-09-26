"""
Admin Dashboard Views for ProEdu
Trung tâm điều hành và quản trị tổng thể hệ thống:
- Báo cáo thống kê toàn diện (Người dùng, Khảo thí, Luyện code, Doanh thu, AI LaTeX)
- Liên kết nhanh tới tất cả các phân hệ quản lý
- Cấu hình website, thông tin thanh toán VietQR và thông tin bản quyền B2B
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User

from .decorators import admin_required
from .models import (
    UserProfile, QuestionBank, Quiz, ExamResult,
    CodingQuestion, CodingExam, CodeSubmission,
    MathDocConversion, Plan, UserSubscription,
    PaymentTransaction, SystemLicense, SystemSetting
)
from .subscription_service import check_system_license

@login_required
@admin_required
def admin_dashboard_view(request):
    """Trang Bảng Điều Khiển Quản Trị Hệ Thống (Admin Dashboard)"""
    settings = SystemSetting.get_settings()
    
    # Xử lý cập nhật cấu hình hệ thống & thanh toán
    if request.method == 'POST' and 'update_settings' in request.POST:
        settings.site_title = request.POST.get('site_title', settings.site_title).strip()
        settings.site_slogan = request.POST.get('site_slogan', settings.site_slogan).strip()
        settings.hotline = request.POST.get('hotline', settings.hotline).strip()
        settings.contact_email = request.POST.get('contact_email', settings.contact_email).strip()
        
        # Cấu hình VietQR
        settings.bank_id = request.POST.get('bank_id', settings.bank_id).strip().upper()
        settings.bank_account_number = request.POST.get('bank_account_number', settings.bank_account_number).strip()
        settings.bank_account_name = request.POST.get('bank_account_name', settings.bank_account_name).strip().upper()
        settings.payment_prefix = request.POST.get('payment_prefix', settings.payment_prefix).strip().upper()
        
        settings.enable_registration = 'enable_registration' in request.POST
        settings.enable_vietqr = 'enable_vietqr' in request.POST
        settings.maintenance_mode = 'maintenance_mode' in request.POST
        settings.save()
        
        messages.success(request, "Đã cập nhật thành công cấu hình hệ thống & thông tin thanh toán!")
        return redirect('admin_dashboard')

    # ==========================
    # 1. THỐNG KÊ NGƯỜI DÙNG
    # ==========================
    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)
    
    total_users = User.objects.count()
    new_users_week = User.objects.filter(date_joined__gte=seven_days_ago).count()
    student_count = UserProfile.objects.filter(role='STUDENT').count()
    manager_count = UserProfile.objects.filter(role='MANAGER').count()
    admin_count = User.objects.filter(is_superuser=True).count()
    locked_count = User.objects.filter(is_active=False).count()

    # ==========================
    # 2. THỐNG KÊ KHẢO THÍ & ĐỀ THI
    # ==========================
    total_questions = QuestionBank.objects.count()
    total_quizzes = Quiz.objects.count()
    total_exam_results = ExamResult.objects.count()

    # ==========================
    # 3. THỐNG KÊ PHÂN HỆ LUYỆN CODE
    # ==========================
    total_coding_questions = CodingQuestion.objects.count()
    total_coding_exams = CodingExam.objects.count()
    total_submissions = CodeSubmission.objects.count()
    accepted_submissions = CodeSubmission.objects.filter(status='Accepted').count()
    ac_rate = round((accepted_submissions / total_submissions * 100), 1) if total_submissions > 0 else 0

    # ==========================
    # 4. THỐNG KÊ THƯƠNG MẠI HOÁ & TÀI CHÍNH
    # ==========================
    total_plans = Plan.objects.count()
    active_subscriptions = UserSubscription.objects.filter(status='ACTIVE').count()
    
    revenue_agg = PaymentTransaction.objects.filter(status='SUCCESS').aggregate(total=Sum('amount'))
    total_revenue = revenue_agg['total'] or 0

    recent_transactions = PaymentTransaction.objects.select_related('user', 'plan').order_by('-created_at')[:8]
    recent_users = User.objects.select_related('profile').order_by('-date_joined')[:6]

    # ==========================
    # 5. THỐNG KÊ CÔNG CỤ AI LATEX
    # ==========================
    total_math_conversions = MathDocConversion.objects.count()
    completed_math_conversions = MathDocConversion.objects.filter(status='Completed').count()

    # ==========================
    # 6. THÔNG TIN BẢN QUYỀN B2B
    # ==========================
    license_info = check_system_license()

    context = {
        'settings': settings,
        'license_info': license_info,
        
        # User metrics
        'total_users': total_users,
        'new_users_week': new_users_week,
        'student_count': student_count,
        'manager_count': manager_count,
        'admin_count': admin_count,
        'locked_count': locked_count,
        'recent_users': recent_users,

        # Exam metrics
        'total_questions': total_questions,
        'total_quizzes': total_quizzes,
        'total_exam_results': total_exam_results,

        # Coding metrics
        'total_coding_questions': total_coding_questions,
        'total_coding_exams': total_coding_exams,
        'total_submissions': total_submissions,
        'accepted_submissions': accepted_submissions,
        'ac_rate': ac_rate,

        # Commercial metrics
        'total_plans': total_plans,
        'active_subscriptions': active_subscriptions,
        'total_revenue': total_revenue,
        'recent_transactions': recent_transactions,

        # AI tool metrics
        'total_math_conversions': total_math_conversions,
        'completed_math_conversions': completed_math_conversions,
    }
    return render(request, 'quiz/admin/dashboard.html', context)


# =====================================================================
# 1. QUẢN LÝ GÓI DỊCH VỤ (PLANS) & THUÊ BAO (SUBSCRIPTIONS)
# =====================================================================

@login_required
@admin_required
def admin_plans_view(request):
    """Giao diện quản lý danh sách Gói dịch vụ và Đăng ký của người dùng"""
    plans = Plan.objects.all().order_by('sort_order', 'price')
    subscriptions = UserSubscription.objects.select_related('user', 'plan').order_by('-updated_at')

    # Xử lý cập nhật / thêm gói dịch vụ
    if request.method == 'POST' and 'save_plan' in request.POST:
        plan_id = request.POST.get('plan_id')
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        price = int(request.POST.get('price', 0))
        original_price = int(request.POST.get('original_price', 0))
        billing_cycle = request.POST.get('billing_cycle', 'YEAR')
        plan_type = request.POST.get('plan_type', 'B2C')
        badge_text = request.POST.get('badge_text', '').strip()
        short_description = request.POST.get('short_description', '').strip()
        features_raw = request.POST.get('features_list', '').strip()

        # Parse danh sách tính năng theo từng dòng
        features_list = [f.strip() for f in features_raw.split('\n') if f.strip()]

        if plan_id:
            plan = get_object_or_404(Plan, id=plan_id)
            plan.name = name
            plan.price = price
            plan.original_price = original_price
            plan.billing_cycle = billing_cycle
            plan.plan_type = plan_type
            plan.badge_text = badge_text
            plan.short_description = short_description
            plan.features_list = features_list
            plan.is_active = 'is_active' in request.POST
            plan.is_featured = 'is_featured' in request.POST
            plan.save()
            messages.success(request, f"Đã cập nhật gói '{plan.name}' thành công!")
        else:
            plan = Plan.objects.create(
                name=name,
                code=code,
                price=price,
                original_price=original_price,
                billing_cycle=billing_cycle,
                plan_type=plan_type,
                badge_text=badge_text,
                short_description=short_description,
                features_list=features_list,
                is_active='is_active' in request.POST,
                is_featured='is_featured' in request.POST
            )
            messages.success(request, f"Đã tạo gói mới '{plan.name}' thành công!")
        return redirect('admin_plans')

    context = {
        'plans': plans,
        'subscriptions': subscriptions,
    }
    return render(request, 'quiz/admin/plans_management.html', context)


@login_required
@admin_required
def admin_toggle_plan(request, plan_id):
    """Bật / tắt mở bán gói dịch vụ"""
    from django.shortcuts import get_object_or_404
    plan = get_object_or_404(Plan, id=plan_id)
    plan.is_active = not plan.is_active
    plan.save()
    status_str = "Mở bán" if plan.is_active else "Tạm dừng"
    messages.success(request, f"Đã chuyển trạng thái gói '{plan.name}' sang: {status_str}")
    return redirect('admin_plans')


@login_required
@admin_required
def admin_extend_subscription(request, sub_id):
    """Gia hạn thuê bao của người dùng thêm 1 năm"""
    sub = get_object_or_404(UserSubscription, id=sub_id)
    now = timezone.now()
    if sub.end_date and sub.end_date > now:
        sub.end_date = sub.end_date + timedelta(days=365)
    else:
        sub.end_date = now + timedelta(days=365)
    sub.status = 'ACTIVE'
    sub.save()
    messages.success(request, f"Đã gia hạn gói {sub.plan.name} cho tài khoản {sub.user.username} thêm 1 năm (đến {sub.end_date.strftime('%d/%m/%Y')})!")
    return redirect('admin_plans')


# =====================================================================
# 2. QUẢN LÝ GIAO DỊCH & SỔ ĐƠN HÀNG (PAYMENT TRANSACTIONS)
# =====================================================================

@login_required
@admin_required
def admin_transactions_view(request):
    """Giao diện quản lý danh sách đơn hàng thanh toán"""
    status_filter = request.GET.get('status', '')
    query = request.GET.get('q', '').strip()

    transactions = PaymentTransaction.objects.select_related('user', 'plan').all()

    if status_filter:
        transactions = transactions.filter(status=status_filter)
    if query:
        transactions = transactions.filter(
            Q(transaction_code__icontains=query) |
            Q(user__username__icontains=query) |
            Q(transfer_content__icontains=query)
        )

    context = {
        'transactions': transactions,
        'status_filter': status_filter,
        'query': query,
    }
    return render(request, 'quiz/admin/transactions_management.html', context)


@login_required
@admin_required
def admin_approve_transaction(request, tx_id):
    """Duyệt đơn hàng và kích hoạt gói thủ công"""
    from .subscription_service import activate_subscription_from_transaction
    tx = get_object_or_404(PaymentTransaction, id=tx_id)
    if tx.status == 'SUCCESS':
        messages.warning(request, "Đơn hàng này đã được kích hoạt trước đó!")
        return redirect('admin_transactions')

    activate_subscription_from_transaction(tx)
    messages.success(request, f"Đã duyệt đơn #{tx.transaction_code} và kích hoạt gói {tx.plan.name} cho tài khoản {tx.user.username} thành công!")
    return redirect('admin_transactions')


@login_required
@admin_required
def admin_cancel_transaction(request, tx_id):
    """Huỷ đơn hàng"""
    tx = get_object_or_404(PaymentTransaction, id=tx_id)
    tx.status = 'CANCELLED'
    tx.save()
    messages.info(request, f"Đã huỷ đơn hàng #{tx.transaction_code}.")
    return redirect('admin_transactions')


# =====================================================================
# 3. QUẢN LÝ BẢN QUYỀN ĐƠN VỊ B2B (SYSTEM LICENSES)
# =====================================================================

@login_required
@admin_required
def admin_licenses_view(request):
    """Giao diện quản lý bản quyền trường học / trung tâm B2B"""
    import secrets
    licenses = SystemLicense.objects.all().order_by('-created_at')

    # Xử lý thêm / sửa bản quyền
    if request.method == 'POST' and 'save_license' in request.POST:
        lic_id = request.POST.get('license_id')
        org_name = request.POST.get('organization_name', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        contact_email = request.POST.get('contact_email', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        domain = request.POST.get('domain', '').strip().lower()
        tier = request.POST.get('tier', 'CAMPUS')
        max_students = int(request.POST.get('max_students', 500))
        max_teachers = int(request.POST.get('max_teachers', 20))
        duration_years = int(request.POST.get('duration_years', 1))

        brand_title = request.POST.get('brand_title', '').strip()
        brand_logo_url = request.POST.get('brand_logo_url', '').strip()
        brand_banner_url = request.POST.get('brand_banner_url', '').strip()
        brand_slogan = request.POST.get('brand_slogan', '').strip()

        now = timezone.now()
        expires_at = now + timedelta(days=365 * duration_years)

        if lic_id:
            lic = get_object_or_404(SystemLicense, id=lic_id)
            lic.organization_name = org_name
            lic.contact_person = contact_person
            lic.contact_email = contact_email
            lic.contact_phone = contact_phone
            lic.domain = domain
            lic.tier = tier
            lic.max_students = max_students
            lic.max_teachers = max_teachers
            lic.brand_title = brand_title
            lic.brand_logo_url = brand_logo_url
            lic.brand_banner_url = brand_banner_url
            lic.brand_slogan = brand_slogan
            lic.is_active = 'is_active' in request.POST
            lic.save()
            messages.success(request, f"Đã cập nhật bản quyền của đơn vị '{lic.organization_name}'!")
        else:
            # Sinh License Key an toàn dạng RSA/Token
            token = secrets.token_hex(24).upper()
            license_key = f"PROEDU-B2B-{domain.upper()}-{token}"
            
            lic = SystemLicense.objects.create(
                organization_name=org_name,
                contact_person=contact_person,
                contact_email=contact_email,
                contact_phone=contact_phone,
                domain=domain,
                tier=tier,
                max_students=max_students,
                max_teachers=max_teachers,
                brand_title=brand_title,
                brand_logo_url=brand_logo_url,
                brand_banner_url=brand_banner_url,
                brand_slogan=brand_slogan,
                license_key=license_key,
                issued_at=now,
                expires_at=expires_at,
                is_active=True
            )
            messages.success(request, f"Đã tạo bản quyền thành công cho '{lic.organization_name}' (Hiệu lực đến {expires_at.strftime('%d/%m/%Y')})!")
        return redirect('admin_licenses')

    context = {
        'licenses': licenses,
    }
    return render(request, 'quiz/admin/licenses_management.html', context)


@login_required
@admin_required
def admin_extend_license(request, license_id):
    """Gia hạn bản quyền đơn vị B2B thêm 1 năm"""
    lic = get_object_or_404(SystemLicense, id=license_id)
    now = timezone.now()
    if lic.expires_at and lic.expires_at > now:
        lic.expires_at = lic.expires_at + timedelta(days=365)
    else:
        lic.expires_at = now + timedelta(days=365)
    lic.is_active = True
    lic.save()
    messages.success(request, f"Đã gia hạn bản quyền cho đơn vị '{lic.organization_name}' thêm 1 năm (Hiệu lực đến {lic.expires_at.strftime('%d/%m/%Y')})!")
    return redirect('admin_licenses')


# =====================================================================
# 4. TRANG CÀI ĐẶT HỆ THỐNG & THANH TOÁN (SETTINGS PORTAL)
# =====================================================================

@login_required
@admin_required
def admin_settings_view(request):
    """Trang Cấu hình Website & Cài đặt nhận diện thương hiệu White-label, VietQR"""
    settings = SystemSetting.get_settings()

    if request.method == 'POST':
        # Thông tin website & Nhận diện thương hiệu
        settings.site_title = request.POST.get('site_title', settings.site_title).strip()
        settings.site_slogan = request.POST.get('site_slogan', settings.site_slogan).strip()
        settings.hotline = request.POST.get('hotline', settings.hotline).strip()
        settings.contact_email = request.POST.get('contact_email', settings.contact_email).strip()
        settings.footer_text = request.POST.get('footer_text', settings.footer_text).strip()

        # Banner & Tiêu đề phía khách
        settings.hero_title = request.POST.get('hero_title', settings.hero_title).strip()
        settings.hero_subtitle = request.POST.get('hero_subtitle', settings.hero_subtitle).strip()

        # Logo upload / URL
        if 'brand_logo' in request.FILES:
            settings.brand_logo = request.FILES['brand_logo']
        elif request.POST.get('clear_brand_logo'):
            settings.brand_logo = None
        settings.brand_logo_url = request.POST.get('brand_logo_url', '').strip()

        # Favicon upload / URL
        if 'brand_favicon' in request.FILES:
            settings.brand_favicon = request.FILES['brand_favicon']
        elif request.POST.get('clear_brand_favicon'):
            settings.brand_favicon = None
        settings.brand_favicon_url = request.POST.get('brand_favicon_url', '').strip()

        # Banner upload / URL
        if 'hero_banner' in request.FILES:
            settings.hero_banner = request.FILES['hero_banner']
        elif request.POST.get('clear_hero_banner'):
            settings.hero_banner = None
        settings.hero_banner_url = request.POST.get('hero_banner_url', '').strip()
        
        # Cấu hình VietQR
        settings.bank_id = request.POST.get('bank_id', settings.bank_id).strip().upper()
        settings.bank_account_number = request.POST.get('bank_account_number', settings.bank_account_number).strip()
        settings.bank_account_name = request.POST.get('bank_account_name', settings.bank_account_name).strip().upper()
        settings.payment_prefix = request.POST.get('payment_prefix', settings.payment_prefix).strip().upper()
        
        settings.enable_registration = 'enable_registration' in request.POST
        settings.enable_vietqr = 'enable_vietqr' in request.POST
        settings.maintenance_mode = 'maintenance_mode' in request.POST
        settings.gemini_api_key = request.POST.get('gemini_api_key', settings.gemini_api_key).strip()
        settings.save()
        
        messages.success(request, "Đã lưu cài đặt nhận diện thương hiệu và hệ thống thành công!")
        return redirect('admin_settings')

    context = {
        'settings': settings,
    }
    return render(request, 'quiz/admin/settings_management.html', context)

