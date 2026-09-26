def user_roles(request):
    """
    Context processor cung cấp thông tin phân quyền cho toàn bộ templates trong hệ thống.
    Cho phép dùng cú pháp thuận tiện:
      {% if is_admin %}...{% endif %}
      {% if is_manager %}...{% endif %}
      {{ current_user_role_display }}
    """
    if not request.user.is_authenticated:
        return {
            'is_admin': False,
            'is_manager': False,
            'current_user_role': None,
            'current_user_role_display': '',
            'user_profile': None,
        }

    user = request.user
    profile = getattr(user, 'profile', None)

    is_admin = False
    is_manager = False
    role = 'user'
    role_display = 'Người dùng'

    if user.is_superuser:
        is_admin = True
        is_manager = True
        role = 'admin'
        role_display = 'Quản trị viên'
    elif profile:
        role = profile.role
        role_display = profile.get_role_display()
        if profile.is_admin():
            is_admin = True
            is_manager = True
        elif profile.is_manager():
            is_manager = True
    elif user.is_staff:
        is_manager = True
        role = 'manager'
        role_display = 'Quản lý'

    from .subscription_service import get_user_subscription, get_user_plan
    from django.utils import timezone

    subscription = get_user_subscription(user)
    plan = get_user_plan(user)
    days_left = None
    if subscription and subscription.end_date:
        delta = subscription.end_date - timezone.now()
        days_left = max(0, delta.days)

    return {
        'is_admin': is_admin,
        'is_manager': is_manager,
        'current_user_role': role,
        'current_user_role_display': role_display,
        'user_profile': profile,
        'user_subscription': subscription,
        'user_plan': plan,
        'user_days_left': days_left,
    }


def system_branding(request):
    """
    Context processor cung cấp thông tin nhận diện thương hiệu (White-label) cho toàn bộ templates.
    Tự động hỗ trợ:
    1. Cấu hình thương hiệu toàn hệ thống (Logo, Favicon, Banner, Tiêu đề, Slogan, Footer).
    2. Nhận diện thương hiệu theo Tên miền trường học (B2B Multi-tenant) nếu truy cập từ Domain riêng.
    """
    from .models import SystemSetting, SystemLicense

    setting = SystemSetting.get_settings()
    
    # Mặc định lấy cấu hình toàn hệ thống
    site_title = setting.site_title
    site_slogan = setting.site_slogan
    logo_url = setting.logo_url
    favicon_url = setting.favicon_url
    banner_url = setting.banner_url
    hero_title = setting.hero_title or "Hệ Thống Khảo Thí Thông Minh"
    hero_subtitle = setting.hero_subtitle or setting.site_slogan
    footer_text = setting.footer_text or f"© 2026 {site_title}. All rights reserved."
    is_b2b_brand = False
    license_obj = None

    try:
        host = request.get_host().split(':')[0].lower()
        license_obj = SystemLicense.objects.filter(domain__iexact=host, is_active=True).first()
        if license_obj and license_obj.is_valid:
            is_b2b_brand = True
            if license_obj.brand_title:
                site_title = license_obj.brand_title
            elif license_obj.organization_name:
                site_title = license_obj.organization_name

            if license_obj.brand_logo_url:
                logo_url = license_obj.brand_logo_url
            if license_obj.brand_banner_url:
                banner_url = license_obj.brand_banner_url
            if license_obj.brand_slogan:
                site_slogan = license_obj.brand_slogan
                hero_subtitle = license_obj.brand_slogan
            footer_text = f"© 2026 {site_title}. Triển khai trên nền tảng ProEdu."
    except Exception:
        pass

    return {
        'system_settings': setting,
        'site_title': site_title,
        'site_slogan': site_slogan,
        'site_logo_url': logo_url,
        'site_favicon_url': favicon_url,
        'site_banner_url': banner_url,
        'site_hero_title': hero_title,
        'site_hero_subtitle': hero_subtitle,
        'site_footer_text': footer_text,
        'is_b2b_brand': is_b2b_brand,
        'b2b_license': license_obj,
    }

