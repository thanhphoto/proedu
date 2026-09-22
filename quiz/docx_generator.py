import io
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image, ImageDraw

def create_dummy_chart_image():
    """Tạo một hình ảnh đồ thị minh họa đơn giản bằng PIL"""
    img = Image.new('RGB', (300, 150), color='#f8fafc')
    draw = ImageDraw.Draw(img)
    
    # Vẽ trục tọa độ
    draw.line([(30, 120), (270, 120)], fill='#475569', width=2)
    draw.line([(30, 20), (30, 130)], fill='#475569', width=2)
    
    # Vẽ đường cong minh họa hàm số
    points = [(30, 110), (80, 40), (140, 100), (200, 30), (260, 115)]
    draw.line(points, fill='#4f46e5', width=3)
    
    img_buf = io.BytesIO()
    img.save(img_buf, format='PNG')
    img_buf.seek(0)
    return img_buf


def generate_sample_docx():
    """
    Tạo file Word (.docx) mẫu chuẩn ứng với định dạng tiêu đề:
    Câu x: [Loại câu hỏi/Độ khó] kèm hình ảnh minh họa mẫu.
    """
    doc = Document()
    
    # Tiêu đề tài liệu
    title = doc.add_heading('NGÂN HÀNG CÂU HỎI MẪU - SMARTQUIZ PRO', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    subtitle = doc.add_paragraph('Định dạng tiêu đề chuẩn: Câu x: [Loại câu hỏi/Độ khó]. Hỗ trợ trích xuất hình ảnh đính kèm.')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.italic = True
    subtitle.runs[0].font.size = Pt(10)
    subtitle.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    
    doc.add_paragraph() # Dòng trống
    
    # --- CÂU 1: SINGLE (Có hình ảnh đồ thị) ---
    p1 = doc.add_paragraph()
    r1 = p1.add_run('Câu 1: [Trắc nghiệm/Nhận biết] ')
    r1.bold = True
    p1.add_run('Cho hàm số $y = f(x)$ có đồ thị như hình vẽ bên dưới. Số điểm cực trị của hàm số đã cho là:')
    
    # Nhúng hình ảnh đồ thị mẫu vào câu 1
    try:
        sample_img_buf = create_dummy_chart_image()
        doc.add_picture(sample_img_buf, width=Inches(3))
    except Exception:
        pass

    p1_a = doc.add_paragraph('*A. $2$')
    p1_b = doc.add_paragraph('B. $1$')
    p1_c = doc.add_paragraph('C. $0$')
    p1_d = doc.add_paragraph('D. $3$')
    
    doc.add_paragraph()
    
    # --- CÂU 2: TF ---
    p2 = doc.add_paragraph()
    r2 = p2.add_run('Câu 2: [Đúng Sai/Thông hiểu] ')
    r2.bold = True
    p2.add_run('Trong không gian $Oxyz$, cho hai điểm $A(1, 0, 2)$ và $B(2, -1, 3)$. Xét tính đúng sai của các mệnh đề sau:')
    
    p2_a = doc.add_paragraph('a) Tọa độ vectơ $\\vec{AB} = (1, -1, 1)$ [Đúng]')
    p2_b = doc.add_paragraph('b) Trung điểm $I$ của đoạn $AB$ là $I\\left(\\frac{3}{2}, -\\frac{1}{2}, \\frac{5}{2}\\right)$ [Đúng]')
    p2_c = doc.add_paragraph('c) Độ dài đoạn thẳng $AB = \\sqrt{5}$ [Sai]')
    p2_d = doc.add_paragraph('d) Phương trình mặt phẳng trung trực của $AB$ đi qua điểm $O(0,0,0)$ [Sai]')
    
    doc.add_paragraph()
    
    # --- CÂU 3: NUMERIC ---
    p3 = doc.add_paragraph()
    r3 = p3.add_run('Câu 3: [Trả lời ngắn/Vận dụng] ')
    r3.bold = True
    p3.add_run('Cho hàm số $y = x^3 - 3x + 2$. Tìm giá trị lớn nhất của hàm số trên đoạn $[0, 2]$.')
    
    p3_ans = doc.add_paragraph('Đáp án: 4')
    p3_ans.runs[0].bold = True
    
    doc.add_paragraph()
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
