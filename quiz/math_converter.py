import os
import io
import re
import json
import base64
import requests
from django.conf import settings
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

SYSTEM_PROMPT = """Bạn là một chuyên gia OCR tài liệu Toán học và Khoa học tự nhiên hàng đầu thế giới.
Nhiệm vụ của bạn là đọc và chuyển đổi toàn bộ nội dung từ tệp ảnh/PDF này thành định dạng Markdown chuẩn kết hợp với mã LaTeX.

YÊU CẦU BẮT BUỘC:
1. CÔNG THỨC TOÁN HỌC:
   - Toàn bộ công thức toán học, ký hiệu toán học (kể cả biến đơn như $x$, $y$, $f(x)$, số mũ, phân số, căn bậc, tích phân, đạo hàm, hình học, vecto, ma trận, v.v.) BẮT BUỘC phải đặt trong cặp dấu $...$ (nếu trên cùng dòng) hoặc $$...$$ (nếu là khối công thức riêng biệt).
   - Sử dụng chuẩn LaTeX đầy đủ: ví dụ $\\frac{a}{b}$, $\\sqrt{x^2+1}$, $\\int_{0}^{1} f(x)dx$, $\\vec{u}$, $\\Delta$, $\\alpha$, $\\in$, $\\subset$, $\\lim_{x \\to \\infty}$, $\\begin{cases} ... \\end{cases}$, v.v.

2. BẢNG BIỂU (TABLES):
   - Mọi bảng dữ liệu, bảng biến thiên, bảng giá trị, bảng thống kê BẮT BUỘC chuyển đổi thành định dạng Markdown Table (hoặc mã LaTeX Table \\begin{tabular} ... \\end{tabular}).
   - Các công thức toán hoặc số liệu bên trong từng ô của bảng cũng phải được bọc trong mã LaTeX $...$.
   - Ví dụ bảng Markdown:
     | $x$ | $-\\infty$ | $0$ | $2$ | $+\\infty$ |
     | :--- | :--- | :--- | :--- | :--- |
     | $y'$ | | $+$ | $0$ | $-$ |

3. CẤU TRÚC VĂN BẢN:
   - Giữ nguyên bố cục tiêu đề (#, ##, ###), đề mục (Câu 1, Câu 2, Phần I, Phần II, Bài 1, v.v.), danh sách đáp án (*A.*, *B.*, *C.*, *D.* hoặc A., B., C., D.), gạch đầu dòng (- hoặc *).
   - In đậm (**chữ đậm**) và in nghiêng (*chữ nghiêng*) đúng theo bản gốc.
   - Không được bỏ sót bất kỳ dòng chữ, câu hỏi, chú thích hay bảng biểu nào trong tài liệu.
   - Không thêm lời mở đầu hay kết bài của AI, chỉ trả về nội dung Markdown/LaTeX thuần túy.
"""

def get_gemini_api_key(user_api_key=None):
    """Lấy API Key từ user truyền vào, hoặc từ cấu hình hệ thống (SystemSetting), hoặc biến môi trường / settings."""
    if user_api_key and user_api_key.strip():
        return user_api_key.strip()
    
    # 1. Lấy từ CSDL SystemSetting (được cài đặt tại /quan-tri/cai-dat/)
    try:
        from .models import SystemSetting
        sys_settings = SystemSetting.get_settings()
        if sys_settings and sys_settings.gemini_api_key and sys_settings.gemini_api_key.strip():
            return sys_settings.gemini_api_key.strip()
    except Exception:
        pass

    # 2. Biến môi trường
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
        
    # 3. Cấu hình Django settings
    settings_key = getattr(settings, "GEMINI_API_KEY", "").strip()
    if settings_key:
        return settings_key
        
    return ""

DEFAULT_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp"
]

def get_available_gemini_models(api_key):
    """
    Tự động truy vấn danh sách model được cấp quyền thực tế của API Key từ Google AI.
    """
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            models = data.get('models', [])
            valid_models = []
            for m in models:
                name = m.get('name', '')
                methods = m.get('supportedGenerationMethods', [])
                if 'generateContent' in methods:
                    clean_name = name.replace('models/', '')
                    valid_models.append(clean_name)
            if valid_models:
                def sort_key(m):
                    if '2.0-flash' in m: return 0
                    if '1.5-flash' in m: return 1
                    if '1.5-pro' in m: return 2
                    if 'flash' in m: return 3
                    return 4
                valid_models.sort(key=sort_key)
                return valid_models
    except Exception:
        pass
        
    return DEFAULT_MODELS

def call_gemini_vision_ocr(file_bytes, mime_type, api_key=None):
    """
    Gửi tệp ảnh hoặc PDF sang Google Gemini Vision API để trích xuất văn bản + LaTeX + bảng biểu.
    Tự động truy vấn và chọn model hoạt động tốt nhất cho API Key của người dùng.
    """
    key = get_gemini_api_key(api_key)
    if not key:
        raise ValueError("Chưa cấu hình Google Gemini API Key. Vui lòng nhập API Key để tiếp tục.")

    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    },
                    {
                        "text": SYSTEM_PROMPT
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    # Lấy danh sách các model khả dụng cho API Key này
    models_to_try = get_available_gemini_models(key)
    last_err_msg = ""

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=180)
            if response.status_code == 200:
                res_data = response.json()
                candidates = res_data.get("candidates", [])
                if candidates:
                    content_parts = candidates[0].get("content", {}).get("parts", [])
                    if content_parts:
                        extracted_text = content_parts[0].get("text", "").strip()
                        if extracted_text.startswith("```markdown"):
                            extracted_text = extracted_text[len("```markdown"):].strip()
                        elif extracted_text.startswith("```latex"):
                            extracted_text = extracted_text[len("```latex"):].strip()
                        elif extracted_text.startswith("```"):
                            extracted_text = extracted_text[3:].strip()
                        if extracted_text.endswith("```"):
                            extracted_text = extracted_text[:-3].strip()
                        return extracted_text
            
            # Lưu lại lỗi
            err_msg = response.text
            try:
                err_json = response.json()
                err_msg = err_json.get("error", {}).get("message", response.text)
            except Exception:
                pass
            last_err_msg = f"{model_name} ({response.status_code}): {err_msg}"
            
            # Nếu sai API key (400/403) thì báo ngay
            if response.status_code in [400, 403] and ("API_KEY_INVALID" in err_msg or "API key not valid" in err_msg):
                raise RuntimeError(f"API Key không hợp lệ: {err_msg}")
                
        except requests.exceptions.RequestException as e:
            last_err_msg = f"Lỗi kết nối model {model_name}: {str(e)}"
            continue

    raise RuntimeError(f"Lỗi từ Gemini API: {last_err_msg}")


def _set_cell_background(cell, color_hex="F1F5F9"):
    """Đặt màu nền cho cell trong bảng Word."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _set_table_borders(table, border_color="CBD5E1"):
    """Thiết lập viền mỏng thanh lịch cho bảng Word."""
    tblPr = table._tbl.tblPr
    tblBorders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:bottom w:val="single" w:sz="6" w:space="0" w:color="{border_color}"/>'
        f'  <w:left w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:right w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:insideV w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(tblBorders)


def _clean_xml_text(text):
    """Loại bỏ control characters không hợp lệ trong XML 1.0."""
    if not text:
        return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

def _format_runs_in_paragraph(paragraph, text, default_font_size=11, is_heading=False):
    """
    Phân tích Markdown inline (Bold **, Italic *, LaTeX $...$, Code `...`) 
    và thêm các run vào paragraph với định dạng in đậm/nghiêng/toán học tương ứng,
    triệt tiêu hoàn toàn các ký tự ** và * thừa, chuyển thành in đậm và in nghiêng.
    """
    if not text:
        return

    # Tách theo cặp ** để xử lý in đậm
    bold_parts = text.split('**')
    
    for b_idx, b_part in enumerate(bold_parts):
        if not b_part:
            continue
            
        # Vị trí lẻ (1, 3, 5,...) là nằm trong cặp **...** -> In đậm
        is_bold_segment = (b_idx % 2 == 1) or is_heading
        
        # Tách tiếp theo cặp * để xử lý in nghiêng
        italic_parts = b_part.split('*')
        for i_idx, i_part in enumerate(italic_parts):
            if not i_part:
                continue
                
            is_italic_segment = (i_idx % 2 == 1)
            
            # Bên trong i_part, phân tích tiếp: Math $$...$$, $...$, Code `...`
            inner_pattern = re.compile(r'(\$\$[\s\S]*?\$\$|\$[^\$]+?\$|`[^`]+?`)')
            sub_parts = inner_pattern.split(i_part)
            
            for sub in sub_parts:
                if not sub:
                    continue
                    
                run = paragraph.add_run()
                run.font.name = 'Times New Roman'
                run.font.size = Pt(default_font_size)
                
                # Khối công thức $$...$$
                if sub.startswith("$$") and sub.endswith("$$") and len(sub) >= 4:
                    run.text = _clean_xml_text(f" {sub} ")
                    run.font.name = 'Cambria Math'
                    run.font.color.rgb = RGBColor(30, 64, 175) # Blue
                    run.bold = True
                    if is_italic_segment:
                        run.italic = True
                    
                # Công thức inline $...$
                elif sub.startswith("$") and sub.endswith("$") and len(sub) >= 2:
                    run.text = _clean_xml_text(sub)
                    run.font.name = 'Cambria Math'
                    run.font.color.rgb = RGBColor(30, 64, 175) # Dark Blue
                    if is_bold_segment:
                        run.bold = True
                    if is_italic_segment:
                        run.italic = True
                        
                # Khối mã inline `...`
                elif sub.startswith("`") and sub.endswith("`") and len(sub) >= 2:
                    run.text = _clean_xml_text(sub[1:-1])
                    run.font.name = 'Courier New'
                    run.font.color.rgb = RGBColor(185, 28, 28)
                    if is_bold_segment:
                        run.bold = True
                    if is_italic_segment:
                        run.italic = True
                        
                # Văn bản thường
                else:
                    run.text = _clean_xml_text(sub)
                    if is_bold_segment:
                        run.bold = True
                        if is_heading:
                            run.font.color.rgb = RGBColor(15, 23, 42)
                    if is_italic_segment:
                        run.italic = True


def convert_markdown_latex_to_docx(markdown_text, title="TÀI LIỆU TOÁN HỌC"):
    """
    Chuyển đổi toàn bộ văn bản Markdown/LaTeX sang tệp Word (.docx) chuyên nghiệp.
    """
    doc = Document()
    
    # Thiết lập lề trang chuẩn A4 (1 inch = 2.54 cm)
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.0)
        section.page_width = Inches(8.27)  # A4
        section.page_height = Inches(11.69)
        
    lines = markdown_text.splitlines()
    i = 0
    total_lines = len(lines)
    
    while i < total_lines:
        line = lines[i].strip()
        
        # Dòng trống
        if not line:
            i += 1
            continue
            
        # 1. BẢNG BIỂU MARKDOWN (| col1 | col2 |)
        if line.startswith("|") and line.endswith("|"):
            table_lines = []
            while i < total_lines and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
                
            # Xử lý các dòng bảng
            parsed_rows = []
            for t_line in table_lines:
                # Bỏ qua dòng phân cách |---|---|
                if re.match(r'^\|[\s\-:|]+\|$', t_line):
                    continue
                # Tách cells
                raw_cells = t_line.strip("|").split("|")
                cells = [c.strip() for c in raw_cells]
                if cells:
                    parsed_rows.append(cells)
                    
            if parsed_rows:
                num_cols = max(len(r) for r in parsed_rows)
                # Đảm bảo mỗi dòng đủ số cột
                for r in parsed_rows:
                    while len(r) < num_cols:
                        r.append("")
                        
                table = doc.add_table(rows=len(parsed_rows), cols=num_cols)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                _set_table_borders(table)
                
                for r_idx, row_data in enumerate(parsed_rows):
                    row = table.rows[r_idx]
                    is_header = (r_idx == 0)
                    for c_idx, cell_text in enumerate(row_data):
                        cell = row.cells[c_idx]
                        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                        
                        # Set header background
                        if is_header:
                            _set_cell_background(cell, "E2E8F0")
                        else:
                            if r_idx % 2 == 1:
                                _set_cell_background(cell, "F8FAFC")
                                
                        p = cell.paragraphs[0]
                        p.paragraph_format.space_before = Pt(3)
                        p.paragraph_format.space_after = Pt(3)
                        p.paragraph_format.line_spacing = 1.15
                        
                        _format_runs_in_paragraph(p, cell_text, default_font_size=10, is_heading=is_header)
                        
                # Thêm khoảng cách sau bảng
                doc.add_paragraph().paragraph_format.space_after = Pt(4)
            continue
            
        # 2. TIÊU ĐỀ HEADINGS (#, ##, ###)
        if line.startswith("#"):
            heading_level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip()
            
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            
            font_size = 14
            if heading_level == 1:
                font_size = 16
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif heading_level == 2:
                font_size = 13.5
            elif heading_level >= 3:
                font_size = 12
                
            _format_runs_in_paragraph(p, heading_text, default_font_size=font_size, is_heading=True)
            i += 1
            continue
            
        # 3. DANH SÁCH BULLETS / LISTS (- item, * item, 1. item)
        bullet_match = re.match(r'^(\*|-|\+)\s+(.*)$', line)
        num_match = re.match(r'^(\d+)\.\s+(.*)$', line)
        
        if bullet_match:
            item_text = bullet_match.group(2)
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            _format_runs_in_paragraph(p, item_text, default_font_size=11)
            i += 1
            continue
            
        if num_match:
            item_num = num_match.group(1)
            item_text = num_match.group(2)
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            
            r_num = p.add_run(f"{item_num}. ")
            r_num.font.name = 'Times New Roman'
            r_num.font.size = Pt(11)
            r_num.bold = True
            
            _format_runs_in_paragraph(p, item_text, default_font_size=11)
            i += 1
            continue
            
        # 4. ĐÁP ÁN TRẮC NGHIỆM TRÊN CÙNG DÒNG HOẶC DÒNG RIÊNG (A. ... B. ...)
        if re.match(r'^(\*|\*\*)?[A-D][\.\)](\*|\*\*)?\s+', line):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            _format_runs_in_paragraph(p, line, default_font_size=11)
            i += 1
            continue
            
        # 5. KHỐI CÔNG THỨC TOÁN RIÊNG BIỆT ($$...$$)
        if line.startswith("$$") and line.endswith("$$"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            
            r = p.add_run(line)
            r.font.name = 'Cambria Math'
            r.font.size = Pt(12)
            r.font.color.rgb = RGBColor(30, 64, 175)
            r.bold = True
            i += 1
            continue
            
        # 6. ĐOẠN VĂN THƯỜNG (PARAGRAPH)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.2
        
        # Nếu là câu hỏi (Câu 1:, Bài 1:,...) thì in đậm phần đầu
        is_question = bool(re.match(r'^(Câu|Bài|Ví dụ|Dạng|Phần)\s+\d+[:.]?', line, re.IGNORECASE))
        _format_runs_in_paragraph(p, line, default_font_size=11, is_heading=is_question)
        
        i += 1
        
    doc_buffer = io.BytesIO()
    doc.save(doc_buffer)
    doc_buffer.seek(0)
    return doc_buffer
