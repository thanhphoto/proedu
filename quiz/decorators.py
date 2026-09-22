from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden

def manager_required(view_func):
    """
    Decorator yêu cầu người dùng phải đăng nhập và có quyền Quản lý hoặc Quản trị viên.
    Áp dụng cho: Tạo ngân hàng đề, nhập Word, thêm câu hỏi, tạo bài thi, sửa đề thi...
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Vui lòng đăng nhập để thực hiện thao tác này.'}, status=401)
            messages.warning(request, "Vui lòng đăng nhập bằng tài khoản Quản lý để truy cập tính năng này.")
            return redirect(f"/dang-nhap/?next={request.path}")

        # Kiểm tra tài khoản có hoạt động không
        if not request.user.is_active:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Tài khoản của bạn đã bị khoá.'}, status=403)
            messages.error(request, "Tài khoản của bạn đã bị khoá. Vui lòng liên hệ Quản trị viên.")
            return redirect("home")

        is_mgr = False
        if request.user.is_superuser or request.user.is_staff:
            is_mgr = True
        elif hasattr(request.user, 'profile') and request.user.profile.is_manager():
            is_mgr = True

        if not is_mgr:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền thực hiện tính năng này (Yêu cầu quyền Quản lý).'}, status=403)
            messages.error(request, "Bạn không có quyền truy cập tính năng này (Yêu cầu quyền Quản lý).")
            return redirect("home")

        return view_func(request, *args, **kwargs)
    return _wrapped_view


def admin_required(view_func):
    """
    Decorator yêu cầu người dùng phải đăng nhập và có quyền Quản trị viên (Admin - cao nhất).
    Áp dụng cho: Quản lý người dùng, đổi vai trò, khoá/mở khoá tài khoản.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Vui lòng đăng nhập bằng tài khoản Quản trị viên.'}, status=401)
            messages.warning(request, "Vui lòng đăng nhập bằng tài khoản Quản trị viên để truy cập trang này.")
            return redirect(f"/dang-nhap/?next={request.path}")

        if not request.user.is_active:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Tài khoản của bạn đã bị khoá.'}, status=403)
            messages.error(request, "Tài khoản của bạn đã bị khoá. Vui lòng liên hệ Quản trị viên.")
            return redirect("home")

        is_adm = False
        if request.user.is_superuser:
            is_adm = True
        elif hasattr(request.user, 'profile') and request.user.profile.is_admin():
            is_adm = True

        if not is_adm:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền truy cập trang quản trị này.'}, status=403)
            messages.error(request, "Bạn không có quyền truy cập tính năng này (Yêu cầu quyền Quản trị viên).")
            return redirect("home")

        return view_func(request, *args, **kwargs)
    return _wrapped_view
