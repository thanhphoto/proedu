import re
import base64
from docx import Document

def parse_docx_bytes(file_bytes_io):
    """
    Phân tích file Word (.docx) từ bytes buffer và trả về danh sách dict câu hỏi.
    Mỗi dict câu hỏi gồm:
    {
        'order': int,
        'question_text': str,
        'difficulty': 'NB' | 'TH' | 'VD' | 'VDC',
        'question_type': 'SINGLE' | 'TF' | 'NUMERIC',
        'choices': [{'choice_text': str, 'is_correct': bool}],
        'exact_numeric_answer': str,
        'image_base64': str or None,
        'image_ext': str or None,
        'lines': list[str]
    }
    """
    doc = Document(file_bytes_io)
    
    raw_blocks = []
    for p in doc.paragraphs:
        text = p.text.strip()
        
        # Trích xuất danh sách ảnh đính kèm trong paragraph này (nếu có)
        images = extract_images_from_paragraph(p, doc)

        if not text and not images:
            continue
        
        has_bold = any(run.bold for run in p.runs)
        has_underline = any(run.underline for run in p.runs)
        
        raw_blocks.append({
            'text': text,
            'has_bold': has_bold,
            'has_underline': has_underline,
            'runs': p.runs,
            'images': images
        })
        
    questions = []
    current_q = None

    q_pattern = re.compile(r'^(?:Câu\s*\d+(?:\.\d+)?|\[Câu\s*\d+(?:\.\d+)?\])(?:[\:\.\s]|$)', re.IGNORECASE)

    for block in raw_blocks:
        text = block['text']
        
        if q_pattern.match(text):
            if current_q:
                finalize_question(current_q)
                questions.append(current_q)
            
            current_q = {
                'order': len(questions) + 1,
                'question_text': '',
                'difficulty': 'NB',
                'question_type': None,
                'choices': [],
                'exact_numeric_answer': '',
                'image_base64': None,
                'image_ext': 'png',
                'lines': [text] if text else [],
                'block_list': [block]
            }
        else:
            if current_q:
                if text:
                    current_q['lines'].append(text)
                current_q['block_list'].append(block)

    if current_q:
        finalize_question(current_q)
        questions.append(current_q)

    # Gộp câu hỏi con vào câu hỏi nhóm nhưng giữ dạng phẳng (flat list)
    final_questions = []
    current_group_idx = None

    for idx, q in enumerate(questions):
        is_sub_question = False
        m = re.match(r'^(?:Câu\s*(\d+\.\d+)|\[Câu\s*(\d+\.\d+)\])', q['lines'][0] if q.get('lines') else '', re.IGNORECASE)
        if m:
            is_sub_question = True

        if q.get('question_type') == 'GROUP':
            current_group_idx = idx
            q['is_group_parent'] = True
        elif is_sub_question and current_group_idx is not None:
            q['parent_group_idx'] = current_group_idx
        else:
            current_group_idx = None # Thoát khỏi nhóm
            
        final_questions.append(q)

    return final_questions


def extract_images_from_paragraph(p, doc):
    """
    Trích xuất danh sách ảnh đính kèm trong 1 paragraph của python-docx.
    """
    images = []
    xml_str = p._element.xml
    
    # Tìm tất cả rId hình ảnh từ XML thẻ <a:blip r:embed="rIdX"/> hoặc <v:imagedata r:id="rIdX"/>
    r_ids = re.findall(r'(?:blip|imagedata)[^>]+(?:r:embed|r:id|embed)="([^"]+)"', xml_str, re.IGNORECASE)
    if not r_ids:
        r_ids = re.findall(r'(?:r:embed|r:id)="([^"]+)"', xml_str, re.IGNORECASE)

    for r_id in set(r_ids):
        if r_id in doc.part.rels:
            rel = doc.part.rels[r_id]
            if hasattr(rel, 'target_part') and rel.target_part:
                target = rel.target_part
                content_type = getattr(target, 'content_type', '')
                if 'image' in content_type or 'image' in rel.target_ref:
                    try:
                        blob = target.blob
                        ext = content_type.split('/')[-1] if '/' in content_type else 'png'
                        if ext == 'jpeg': ext = 'jpg'
                        b64_str = base64.b64encode(blob).decode('utf-8')
                        data_url = f"data:image/{ext};base64,{b64_str}"
                        images.append({
                            'data_url': data_url,
                            'base64': b64_str,
                            'ext': ext
                        })
                    except Exception:
                        pass
    return images


def finalize_question(q):
    lines = q['lines']
    blocks = q['block_list']
    
    # Trích xuất hình ảnh đầu tiên trong các block của câu hỏi này (nếu có)
    for block in blocks:
        if block.get('images'):
            first_img = block['images'][0]
            q['image_base64'] = first_img['data_url']
            q['image_raw'] = first_img['base64']
            q['image_ext'] = first_img['ext']
            break

    full_text = " ".join(lines)
    header_line = lines[0] if lines else ""

    # --- 1. PHÂN TÍCH TIÊU ĐỀ DẠNG: Câu x: [Loại câu hỏi/Độ khó] ---
    bracket_matches = re.findall(r'\[([^\]]+)\]', full_text)
    
    parsed_type = None
    parsed_diff = None

    for tag in bracket_matches:
        parts = [p.strip() for p in re.split(r'[\/\-\,]', tag)]
        for part in parts:
            p_lower = part.lower()
            if p_lower in ['vdc', 'vận dụng cao', 'van dung cao']:
                parsed_diff = 'VDC'
            elif p_lower in ['vd', 'vận dụng', 'van dung']:
                parsed_diff = 'VD'
            elif p_lower in ['th', 'thông hiểu', 'thong hieu']:
                parsed_diff = 'TH'
            elif p_lower in ['nb', 'nhận biết', 'nhan biet']:
                parsed_diff = 'NB'

            if any(k in p_lower for k in ['single', 'trắc nghiệm', 'trac nghiem', 'tn', '1 đáp án']):
                parsed_type = 'SINGLE'
            elif any(k in p_lower for k in ['tf', 'đúng sai', 'đúng/sai', 'dung sai', 'đs']):
                parsed_type = 'TF'
            elif any(k in p_lower for k in ['numeric', 'trả lời ngắn', 'tra loi ngan', 'tln', 'số', 'so']):
                parsed_type = 'NUMERIC'
            elif any(k in p_lower for k in ['nhóm', 'group']):
                parsed_type = 'GROUP'

    if parsed_diff:
        q['difficulty'] = parsed_diff
    if parsed_type:
        q['question_type'] = parsed_type

    choice_single_pattern = re.compile(r'^\*?\s*([A-D])[\.\/\)]\s*(.*)')
    choice_tf_pattern = re.compile(r'^\*?\s*([a-d])[\.\/\)]\s*(.*)')
    answer_key_pattern = re.compile(r'^(?:Đáp án|Đáp số|KQ|Kết quả)\s*[:\=]\s*(.*)', re.IGNORECASE)

    q_text_lines = []
    choices = []
    explicit_answer_key = None

    for idx, block in enumerate(blocks):
        line = block['text']
        if not line:
            continue
        
        if idx == 0 and lines and line == lines[0]:
            clean_header = re.sub(r'^(?:Câu\s*\d+(?:\.\d+)?|\[Câu\s*\d+(?:\.\d+)?\])', '', line, flags=re.IGNORECASE).strip()
            clean_header = re.sub(r'\[([^\]]+)\]', '', clean_header).strip()
            clean_header = re.sub(r'^[\:\.\s\-]+', '', clean_header).strip()
            if clean_header:
                q_text_lines.append(clean_header)
            continue

        ans_match = answer_key_pattern.match(line)
        if ans_match:
            explicit_answer_key = ans_match.group(1).strip()
            continue

        match_single = choice_single_pattern.match(line)
        if match_single:
            letter = match_single.group(1)
            content = match_single.group(2).strip()
            
            is_correct = False
            if line.startswith('*') or '*' in line[:4]:
                is_correct = True
            elif block['has_bold'] or block['has_underline']:
                is_correct = True
                
            choices.append({
                'label': letter,
                'text': content,
                'is_correct': is_correct,
                'type': 'SINGLE'
            })
            continue

        match_tf = choice_tf_pattern.match(line)
        if match_tf:
            letter = match_tf.group(1)
            content = match_tf.group(2).strip()
            
            is_correct = False
            if re.search(r'\[Đúng\]|\(Đ\)|\[Dung\]|\[Đ\]|\*a|\*b|\*c|\*d', line, re.IGNORECASE):
                is_correct = True
            elif re.search(r'\[Sai\]|\(S\)', line, re.IGNORECASE):
                is_correct = False
            elif block['has_bold'] or block['has_underline']:
                is_correct = True
            
            clean_content = re.sub(r'\[(Đúng|Sai|Dung|Đ|S)\]|\((Đ|S)\)', '', content, flags=re.IGNORECASE).strip()

            choices.append({
                'label': letter,
                'text': clean_content if clean_content else content,
                'is_correct': is_correct,
                'type': 'TF'
            })
            continue

        q_text_lines.append(line)

    q['question_text'] = "\n".join(q_text_lines).strip()

    if not q['question_type']:
        if any(c['type'] == 'SINGLE' for c in choices):
            q['question_type'] = 'SINGLE'
        elif any(c['type'] == 'TF' for c in choices):
            q['question_type'] = 'TF'
        elif explicit_answer_key:
            q['question_type'] = 'NUMERIC'
        else:
            q['question_type'] = 'SINGLE'

    if explicit_answer_key:
        if q['question_type'] == 'SINGLE':
            correct_letter = explicit_answer_key.strip().upper()[:1]
            for c in choices:
                if c['label'] == correct_letter:
                    c['is_correct'] = True
        elif q['question_type'] == 'TF':
            for c in choices:
                pattern = rf"{c['label']}\s*[\-\:\=]\s*(Đúng|Đ|Dung|True|1)"
                if re.search(pattern, explicit_answer_key, re.IGNORECASE):
                    c['is_correct'] = True
        elif q['question_type'] == 'NUMERIC':
            q['exact_numeric_answer'] = explicit_answer_key.strip()

    if q['question_type'] == 'NUMERIC' and not q['exact_numeric_answer'] and explicit_answer_key:
        q['exact_numeric_answer'] = explicit_answer_key.strip()

    q['choices'] = [{'choice_text': c['text'], 'is_correct': c['is_correct']} for c in choices]

    # Xóa các trường tạm chứa đối tượng python-docx không thể serialize JSON
    q.pop('block_list', None)
    q.pop('lines', None)
    q.pop('blocks', None)

