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

    return {
        'is_admin': is_admin,
        'is_manager': is_manager,
        'current_user_role': role,
        'current_user_role_display': role_display,
        'user_profile': profile,
    }
