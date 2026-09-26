"""
ProEdu Subscription & Licensing Service
Quản lý gói dịch vụ, phân quyền tính năng và bản quyền hệ thống B2B.
"""

from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Plan, UserSubscription, PaymentTransaction, SystemLicense

# Hạn mức mặc định cho tài khoản Miễn phí (Free Tier)
DEFAULT_FREE_LIMITS = {
    'max_exams_created': 3,
    'max_questions_bank': 50,
    'max_math_ocr_per_month': 5,
    'can_view_editorial': False,
    'can_view_hidden_testcases': False,
    'can_export_word': False,
    'can_create_coding_exam': False,
    'priority_judge': False,
}

def get_user_subscription(user):
    """Lấy thông tin gói đang hoạt động của người dùng"""
    if not user or not user.is_authenticated:
        return None
    try:
        sub = user.subscription
        if sub.is_valid:
            return sub
        return None
    except UserSubscription.DoesNotExist:
        return None

def get_user_plan(user):
    """Lấy đối tượng Plan của user (nếu không có thì trả về gói Free mặc định)"""
    # Superuser có toàn quyền
    if user.is_authenticated and user.is_superuser:
        return Plan(
            name="Quản Trị Viên (SuperAdmin)",
            code="SUPERADMIN",
            plan_type="B2B",
            price=0,
            limits={
                'max_exams_created': 999999,
                'max_questions_bank': 999999,
                'max_math_ocr_per_month': 999999,
                'can_view_editorial': True,
                'can_view_hidden_testcases': True,
                'can_export_word': True,
                'can_create_coding_exam': True,
                'priority_judge': True,
            }
        )

    sub = get_user_subscription(user)
    if sub and sub.plan:
        return sub.plan
    
    # Trả về gói Free mặc định
    free_plan = Plan.objects.filter(code='FREE').first()
    if not free_plan:
        free_plan = Plan(
            name="Gói Miễn Phí",
            code="FREE",
            plan_type="B2C",
            price=0,
            limits=DEFAULT_FREE_LIMITS
        )
    return free_plan

def has_feature(user, feature_key: str) -> bool:
    """Kiểm tra xem người dùng có quyền sử dụng tính năng này hay không"""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
        
    plan = get_user_plan(user)
    limits = plan.limits or {}
    return bool(limits.get(feature_key, False))

def can_view_editorial(user, question=None) -> bool:
    """Kiểm tra quyền xem lời giải mẫu bài tập lập trình"""
    return has_feature(user, 'can_view_editorial')

def can_create_coding_exam(user) -> bool:
    """Kiểm tra quyền tạo kỳ thi luyện code riêng"""
    if user.is_staff or user.is_superuser:
        return True
    return has_feature(user, 'can_create_coding_exam')

def get_feature_limit(user, limit_key: str, default=0) -> int:
    """Lấy số lượng tối đa của một tính năng"""
    if user.is_superuser:
        return 999999
    plan = get_user_plan(user)
    limits = plan.limits or {}
    return limits.get(limit_key, default)

def generate_transaction_code(user_id: int) -> str:
    """Sinh mã giao dịch duy nhất"""
    import random
    ts = timezone.now().strftime('%y%m%d%H%M')
    rand = random.randint(1000, 9999)
    return f"PE{ts}{rand}"

def create_payment_transaction(user, plan, payment_method='VIETQR'):
    """Tạo đơn hàng thanh toán mới cho người dùng"""
    tx_code = generate_transaction_code(user.id)
    transfer_content = f"PROEDU {tx_code}"
    
    transaction = PaymentTransaction.objects.create(
        user=user,
        plan=plan,
        transaction_code=tx_code,
        amount=plan.price,
        status='PENDING',
        payment_method=payment_method,
        transfer_content=transfer_content
    )
    return transaction

def activate_subscription_from_transaction(transaction: PaymentTransaction) -> UserSubscription:
    """Kích hoạt gói dịch vụ khi thanh toán thành công"""
    transaction.status = 'SUCCESS'
    transaction.paid_at = timezone.now()
    transaction.save()

    user = transaction.user
    plan = transaction.plan

    # Tính thời gian hiệu lực
    now = timezone.now()
    if plan.billing_cycle == 'MONTH':
        end_date = now + timedelta(days=30)
    elif plan.billing_cycle == 'YEAR':
        end_date = now + timedelta(days=365)
    else: # LIFETIME
        end_date = None

    # Tạo hoặc cập nhật đăng ký
    sub, created = UserSubscription.objects.get_or_create(
        user=user,
        defaults={
            'plan': plan,
            'status': 'ACTIVE',
            'start_date': now,
            'end_date': end_date,
        }
    )
    if not created:
        # Nếu đang có gói còn hạn, cộng dồn ngày
        if sub.end_date and sub.end_date > now and end_date:
            sub.end_date = sub.end_date + (end_date - now)
        else:
            sub.end_date = end_date
        sub.plan = plan
        sub.status = 'ACTIVE'
        sub.start_date = now
        sub.save()

    return sub

def check_system_license(domain: str = None) -> dict:
    """
    Kiểm tra giấy phép bản quyền của hệ thống đối với mô hình B2B Enterprise
    """
    # Nếu chưa kích hoạt license B2B nào thì mặc định là bản Community / Standalone
    license_obj = SystemLicense.objects.filter(is_active=True).first()
    if not license_obj:
        return {
            'licensed': False,
            'message': 'Hệ thống đang hoạt động ở chế độ Community Standalone.',
            'tier': 'COMMUNITY'
        }
    
    if not license_obj.is_valid:
        return {
            'licensed': False,
            'message': f'Bản quyền của đơn vị {license_obj.organization_name} đã hết hạn vào ngày {license_obj.expires_at.strftime("%d/%m/%Y")}. Vui lòng liên hệ quản trị viên để gia hạn.',
            'tier': license_obj.tier
        }

    return {
        'licensed': True,
        'organization': license_obj.organization_name,
        'tier': license_obj.get_tier_display(),
        'expires_at': license_obj.expires_at,
        'max_students': license_obj.max_students,
        'max_teachers': license_obj.max_teachers,
        'brand_title': license_obj.brand_title or license_obj.organization_name
    }
