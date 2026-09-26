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

@login_required
def math_converter_view(request):
    """Trang giao diện chính chuyển đổi ảnh/PDF chứa công thức Toán sang Word."""
    conversions = MathDocConversion.objects.filter(user=request.user).order_by('-created_at')
    
    # Kiểm tra xem hệ thống đã có sẵn GEMINI_API_KEY chưa
    has_system_api_key = bool(get_gemini_api_key())
    
    return render(request, 'quiz/math_converter.html', {
        'conversions': conversions,
        'has_system_api_key': has_system_api_key,
        'title': 'Chuyển Đổi Ảnh / PDF Sang Word (Toán & Bảng Biểu LaTeX)'
    })

@login_required
@require_POST
def api_convert_math_doc(request):
    """API tiếp nhận file ảnh hoặc PDF, thực hiện nhận diện và tạo file Word."""
    uploaded_file = request.FILES.get('doc_file')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'Vui lòng chọn tệp ảnh hoặc PDF cần chuyển đổi.'})

    user_api_key = request.POST.get('api_key', '').strip()
    
    # Lưu vào session nếu người dùng nhập key mới
    if user_api_key:
        request.session['user_gemini_api_key'] = user_api_key
    elif 'user_gemini_api_key' in request.session:
        user_api_key = request.session['user_gemini_api_key']
        
    api_key_to_use = get_gemini_api_key(user_api_key)
    if not api_key_to_use:
        return JsonResponse({
            'success': False, 
            'error': 'Chưa cấu hình Google Gemini API Key. Vui lòng nhập API Key của bạn để bắt đầu chuyển đổi.'
        })

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
            'created_at': conversion.created_at.strftime('%H:%M %d/%m/%Y'),
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
        'created_at': conversion.created_at.strftime('%H:%M %d/%m/%Y'),
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
