"""
Subscription & Commercial Views for ProEdu
Xử lý hiển thị bảng giá, đăng ký gói, thanh toán QR và đối soát giao dịch.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from .models import Plan, UserSubscription, PaymentTransaction, SystemLicense, SystemSetting
from .subscription_service import (
    get_user_subscription, get_user_plan, create_payment_transaction,
    activate_subscription_from_transaction, check_system_license
)

def pricing_view(request):
    """Trang Bảng giá dịch vụ và các gói đăng ký"""
    b2c_plans = Plan.objects.filter(is_active=True, plan_type='B2C').order_by('sort_order')
    b2b_plans = Plan.objects.filter(is_active=True, plan_type='B2B').order_by('sort_order')
    
    current_sub = None
    current_plan = None
    if request.user.is_authenticated:
        current_sub = get_user_subscription(request.user)
        current_plan = get_user_plan(request.user)

    system_license = check_system_license()

    context = {
        'b2c_plans': b2c_plans,
        'b2b_plans': b2b_plans,
        'current_sub': current_sub,
        'current_plan': current_plan,
        'system_license': system_license,
    }
    return render(request, 'quiz/pricing.html', context)


@login_required
def checkout_view(request, plan_code):
    """Trang thanh toán gói dịch vụ bằng mã QR ngân hàng tự động"""
    plan = get_object_or_404(Plan, code=plan_code, is_active=True)
    
    # Nếu gói miễn phí, kích hoạt ngay lập tức
    if plan.price == 0:
        sub, _ = UserSubscription.objects.get_or_create(user=request.user, defaults={
            'plan': plan,
            'status': 'ACTIVE',
            'start_date': timezone.now(),
        })
        sub.plan = plan
        sub.status = 'ACTIVE'
        sub.save()
        messages.success(request, f"Bạn đã đăng ký thành công {plan.name}!")
        return redirect('pricing')

    # Tìm giao dịch PENDING gần nhất trong 30 phút qua hoặc tạo mới
    existing_tx = PaymentTransaction.objects.filter(
        user=request.user,
        plan=plan,
        status='PENDING'
    ).first()

    if not existing_tx:
        existing_tx = create_payment_transaction(request.user, plan, payment_method='VIETQR')

    settings = SystemSetting.get_settings()
    BANK_ID = settings.bank_id or "MB"
    ACCOUNT_NO = settings.bank_account_number or "0987654321"
    ACCOUNT_NAME = settings.bank_account_name or "PROEDU VIETNAM"
    
    # Chuỗi VietQR API URL QuickLink chuẩn
    vietqr_url = f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png?amount={existing_tx.amount}&addInfo={existing_tx.transfer_content}&accountName={ACCOUNT_NAME}"

    context = {
        'plan': plan,
        'transaction': existing_tx,
        'vietqr_url': vietqr_url,
        'bank_id': BANK_ID,
        'account_no': ACCOUNT_NO,
        'account_name': ACCOUNT_NAME,
        'site_settings': settings,
    }
    return render(request, 'quiz/checkout.html', context)


@login_required
def api_check_payment_status(request, tx_code):
    """API kiểm tra trạng thái thanh toán từ client (Ajax polling)"""
    tx = get_object_or_404(PaymentTransaction, transaction_code=tx_code, user=request.user)
    return JsonResponse({
        'status': tx.status,
        'paid': tx.status == 'SUCCESS'
    })


@login_required
def simulate_payment_success(request, tx_code):
    """
    Hàm mô phỏng thanh toán thành công (Dành cho Demo / Thử nghiệm trước khi đấu nối Webhook thật)
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Tính năng mô phỏng chỉ dành cho Quản trị viên thử nghiệm.")
        return redirect('pricing')

    tx = get_object_or_404(PaymentTransaction, transaction_code=tx_code)
    activate_subscription_from_transaction(tx)
    messages.success(request, f"Đã mô phỏng thanh toán thành công! Gói {tx.plan.name} đã được kích hoạt cho tài khoản {tx.user.username}.")
    return redirect('pricing')
