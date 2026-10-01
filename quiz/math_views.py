import os
import mimetypes
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.core.files.base import ContentFile
from django.utils import timezone
from django.contrib import messages

from .models import MathDocConversion
from .math_converter import call_gemini_vision_ocr, convert_markdown_latex_to_docx, get_gemini_api_key
from .subscription_service import get_user_subscription, get_user_plan

def math_converter_view(request):
    """Trang giao diện chính chuyển đổi ảnh/PDF chứa công thức Toán sang Word."""
    conversions = []
    has_active_package = False
    quota_limit = 1
    quota_used = 0
    quota_remaining = 1
    user_plan = None

    if request.user.is_authenticated:
        conversions = MathDocConversion.objects.filter(user=request.user).order_by('-created_at')
        sub = get_user_subscription(request.user)
        user_plan = get_user_plan(request.user)
        has_active_package = (sub is not None and sub.is_valid) or request.user.is_superuser

        if not has_active_package:
            # Tài khoản chưa mua gói: Miễn phí 1 trang duy nhất
            quota_limit = 1
            quota_used = MathDocConversion.objects.filter(user=request.user, status='Completed').count()
            quota_remaining = max(0, quota_limit - quota_used)
        else:
            now = timezone.now()
            quota_used = MathDocConversion.objects.filter(
                user=request.user,
                status='Completed',
                created_at__year=now.year,
                created_at__month=now.month
            ).count()
            quota_limit = user_plan.limits.get('max_math_ocr_per_month', 999999 if request.user.is_superuser else 30) if user_plan.limits else 30
            quota_remaining = max(0, quota_limit - quota_used)

    # Kiểm tra xem hệ thống đã có sẵn GEMINI_API_KEY chưa
    has_system_api_key = bool(get_gemini_api_key())
    
    return render(request, 'quiz/math_converter.html', {
        'conversions': conversions,
        'has_system_api_key': has_system_api_key,
        'has_active_package': has_active_package,
        'quota_limit': quota_limit,
        'quota_used': quota_used,
        'quota_remaining': quota_remaining,
        'user_plan': user_plan,
        'can_convert': quota_remaining > 0 or request.user.is_superuser,
        'title': 'Chuyển Đổi Ảnh / PDF Sang Word (Toán & Bảng Biểu LaTeX)'
    })


@require_POST
def api_convert_math_doc(request):
    """API tiếp nhận file ảnh hoặc PDF, thực hiện nhận diện và tạo file Word."""
    # 1. BẮT BUỘC ĐĂNG NHẬP TRƯỚC KHI CHUYỂN ĐỔI
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'require_login': True,
            'error': 'Bạn cần đăng nhập tài khoản trước khi thực hiện chuyển đổi tài liệu.'
        }, status=401)

    uploaded_file = request.FILES.get('doc_file')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'Vui lòng chọn tệp ảnh hoặc PDF cần chuyển đổi.'})

    orig_name = uploaded_file.name
    ext = os.path.splitext(orig_name)[1].lower()
    
    if ext in ['.pdf']:
        file_type = 'PDF'
        mime_type = 'application/pdf'
    elif ext in ['.jpg', '.jpeg']:
        file_type = 'Image'
        mime_type = 'image/jpeg'
    elif ext in ['.png']:
        file_type = 'Image'
        mime_type = 'image/png'
    elif ext in ['.webp']:
        file_type = 'Image'
        mime_type = 'image/webp'
    else:
        return JsonResponse({
            'success': False, 
            'error': 'Định dạng tệp không được hỗ trợ. Vui lòng chọn tệp PDF hoặc ảnh (PNG, JPG, JPEG, WEBP).'
        })

    # Giới hạn kích thước tệp 25MB
    if uploaded_file.size > 25 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'Kích thước tệp vượt quá giới hạn cho phép (tối đa 25MB).'})

    # 2. KIỂM TRA SỐ TRANG CỦA TỆP
    page_count = 1
    if ext == '.pdf':
        try:
            from pypdf import PdfReader
            uploaded_file.seek(0)
            reader = PdfReader(uploaded_file)
            page_count = len(reader.pages)
            uploaded_file.seek(0)
        except Exception:
            page_count = 1

    # 3. KIỂM TRA QUYỀN HẠN & HẠN MỨC GÓI CỦA NGƯỜI DÙNG
    sub = get_user_subscription(request.user)
    plan = get_user_plan(request.user)
    has_active_package = (sub is not None and sub.is_valid) or request.user.is_superuser

    if not has_active_package:
        # TÀI KHOẢN CHƯA MUA GÓI: MIỄN PHÍ 1 TRANG ĐẦU TIÊN
        total_completed = MathDocConversion.objects.filter(user=request.user, status='Completed').count()
        if total_completed >= 1:
            return JsonResponse({
                'success': False,
                'require_upgrade': True,
                'error': 'Bạn đã sử dụng hết 01 trang chuyển đổi miễn phí dành cho tài khoản dùng thử. Vui lòng nâng cấp gói để tiếp tục sử dụng!'
            }, status=403)
        
        if page_count > 1:
            return JsonResponse({
                'success': False,
                'require_upgrade': True,
                'error': f'Tài khoản dùng thử miễn phí chỉ được chuyển đổi tài liệu 01 trang (Tệp của bạn có {page_count} trang). Vui lòng nâng cấp gói để chuyển đổi tài liệu nhiều trang!'
            }, status=403)
    else:
        # TÀI KHOẢN ĐÃ MUA GÓI: KIỂM TRA HẠN MỨC TRONG THÁNG
        if not request.user.is_superuser:
            now = timezone.now()
            monthly_used = MathDocConversion.objects.filter(
                user=request.user,
                status='Completed',
                created_at__year=now.year,
                created_at__month=now.month
            ).count()
            max_limit = plan.limits.get('max_math_ocr_per_month', 30) if plan.limits else 30
            if monthly_used + page_count > max_limit:
                return JsonResponse({
                    'success': False,
                    'require_upgrade': True,
                    'error': f'Bạn đã sử dụng {monthly_used}/{max_limit} trang trong tháng này. Tệp có {page_count} trang vượt quá hạn mức còn lại. Vui lòng nâng cấp gói cao hơn!'
                }, status=403)

    user_api_key = request.POST.get('api_key', '').strip()
    if user_api_key:
        request.session['user_gemini_api_key'] = user_api_key
    elif 'user_gemini_api_key' in request.session:
        user_api_key = request.session['user_gemini_api_key']
        
    api_key_to_use = get_gemini_api_key(user_api_key)
    if not api_key_to_use:
        return JsonResponse({
            'success': False, 
            'error': 'Chưa cấu hình Google Gemini API Key. Vui lòng cấu hình API Key để bắt đầu chuyển đổi.'
        })

    # Tạo bản ghi lịch sử ban đầu
    conversion = MathDocConversion.objects.create(
        user=request.user,
        original_filename=orig_name,
        file_type=file_type,
        file_size=uploaded_file.size,
        status='Processing'
    )
    
    # Lưu tệp đầu vào
    conversion.input_file.save(orig_name, uploaded_file, save=True)

    try:
        # 1. Đọc nội dung tệp
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        
        # 2. Gọi AI Gemini Vision OCR
        extracted_latex = call_gemini_vision_ocr(file_bytes, mime_type, api_key=api_key_to_use)
        
        if not extracted_latex or not extracted_latex.strip():
            raise RuntimeError("Không trích xuất được nội dung nào từ tài liệu.")
            
        conversion.extracted_latex = extracted_latex
        
        # 3. Tạo file Word (.docx)
        docx_buffer = convert_markdown_latex_to_docx(extracted_latex, title=orig_name)
        
        # Tên file kết quả
        base_name = os.path.splitext(orig_name)[0]
        output_filename = f"{base_name}_converted.docx"
        
        # Lưu file docx vào Model
        conversion.output_docx.save(output_filename, ContentFile(docx_buffer.getvalue()), save=False)
        conversion.status = 'Completed'
        conversion.completed_at = timezone.now()
        conversion.save()
        
        return JsonResponse({
            'success': True,
            'id': conversion.id,
            'filename': orig_name,
            'file_type': file_type,
            'created_at': timezone.localtime(conversion.created_at).strftime('%H:%M %d/%m/%Y'),
            'docx_url': f"/chuyen-doi-tai-lieu/tai-ve/{conversion.id}/",
            'extracted_latex': extracted_latex,
            'message': 'Chuyển đổi thành công sang file Word!'
        })
        
    except Exception as e:
        conversion.status = 'Failed'
        conversion.error_message = str(e)
        conversion.save()
        return JsonResponse({'success': False, 'error': str(e), 'id': conversion.id})


@login_required
def download_converted_docx(request, conversion_id):
    """Tải xuống tệp Word đã chuyển đổi."""
    conversion = get_object_or_404(MathDocConversion, id=conversion_id, user=request.user)
    
    if not conversion.output_docx or not os.path.exists(conversion.output_docx.path):
        raise Http404("Tệp Word không tồn tại hoặc đã bị xóa.")
        
    response = FileResponse(open(conversion.output_docx.path, 'rb'), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(conversion.output_docx.name)}"'
    return response


@login_required
def get_conversion_detail(request, conversion_id):
    """Lấy chi tiết nội dung văn bản và mã LaTeX đã trích xuất."""
    conversion = get_object_or_404(MathDocConversion, id=conversion_id, user=request.user)
    return JsonResponse({
        'success': True,
        'id': conversion.id,
        'filename': conversion.original_filename,
        'file_type': conversion.file_type,
        'status': conversion.status,
        'created_at': timezone.localtime(conversion.created_at).strftime('%H:%M %d/%m/%Y'),
        'extracted_latex': conversion.extracted_latex,
        'error_message': conversion.error_message,
        'has_docx': bool(conversion.output_docx)
    })


@login_required
@require_POST
def delete_conversion_history(request, conversion_id):
    """Xóa một bản ghi lịch sử chuyển đổi."""
    conversion = get_object_or_404(MathDocConversion, id=conversion_id, user=request.user)
    
    try:
        # Xoá các tệp đính kèm vật lý nếu có
        if conversion.input_file:
            conversion.input_file.delete(save=False)
        if conversion.output_docx:
            conversion.output_docx.delete(save=False)
            
        conversion.delete()
        return JsonResponse({'success': True, 'message': 'Đã xóa bản ghi thành công.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
