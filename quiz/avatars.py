from django.templatetags.static import static

PRESET_AVATARS = [
    {
        'id': 'avatar-1',
        'name': 'Cử nhân Nam',
        'desc': 'Trang phục cử nhân, kính tri thức',
        'category': 'student'
    },
    {
        'id': 'avatar-2',
        'name': 'Cử nhân Nữ',
        'desc': 'Nữ cử nhân xuất sắc, tươi tắn',
        'category': 'student'
    },
    {
        'id': 'avatar-3',
        'name': 'Nhà khoa học',
        'desc': 'Giáo sư thông thái, kính bảo hộ',
        'category': 'science'
    },
    {
        'id': 'avatar-4',
        'name': 'IT Boy',
        'desc': 'Chàng trai lập trình viên, tai nghe',
        'category': 'tech'
    },
    {
        'id': 'avatar-5',
        'name': 'IT Girl',
        'desc': 'Nữ lập trình viên công nghệ, tóc tím',
        'category': 'tech'
    },
    {
        'id': 'avatar-6',
        'name': 'Phù thủy Toán',
        'desc': 'Phù thủy toán học, râu dài uyên bác',
        'category': 'magic'
    },
    {
        'id': 'avatar-7',
        'name': 'Phi hành gia',
        'desc': 'Nhà thám hiểm không gian vũ trụ',
        'category': 'space'
    },
    {
        'id': 'avatar-8',
        'name': 'Học sinh Năng động',
        'desc': 'Chàng trai thể thao, mũ lưỡi trai',
        'category': 'student'
    },
    {
        'id': 'avatar-9',
        'name': 'Nghệ sĩ Trẻ',
        'desc': 'Phong cách sáng tạo, mũ beret đỏ',
        'category': 'art'
    },
    {
        'id': 'avatar-10',
        'name': 'Mèo Trí Thức',
        'desc': 'Mèo mướp thông thái đeo kính cận',
        'category': 'animal'
    },
    {
        'id': 'avatar-11',
        'name': 'Cú Mèo Tri Thức',
        'desc': 'Cú mèo biểu tượng sự thông tuệ',
        'category': 'animal'
    },
    {
        'id': 'avatar-12',
        'name': 'Cáo Nhanh Trí',
        'desc': 'Chú cáo vàng thông minh lanh lợi',
        'category': 'animal'
    },
    {
        'id': 'avatar-13',
        'name': 'Robot AI',
        'desc': 'Trợ lý trí tuệ nhân tạo tương lai',
        'category': 'tech'
    },
    {
        'id': 'avatar-14',
        'name': 'Thầy giáo Mẫu mực',
        'desc': 'Thầy giáo lịch thiệp, kinh nghiệm',
        'category': 'teacher'
    },
    {
        'id': 'avatar-15',
        'name': 'Cô giáo Tận tụy',
        'desc': 'Cô giáo duyên dáng, truyền cảm hứng',
        'category': 'teacher'
    },
    {
        'id': 'avatar-16',
        'name': 'Quán quân Vàng',
        'desc': 'Thí sinh đạt giải nhất vòng nguyệt quế',
        'category': 'champion'
    },
]

VALID_AVATAR_IDS = {a['id'] for a in PRESET_AVATARS}


def get_avatar_url(avatar_id):
    """Trả về đường dẫn URL của avatar theo mã ID."""
    if not avatar_id or avatar_id not in VALID_AVATAR_IDS:
        avatar_id = 'avatar-1'
    return static(f'quiz/avatars/{avatar_id}.svg')


def get_preset_avatars_with_urls():
    """Trả về danh sách các avatar có sẵn kèm đường dẫn tĩnh URL."""
    res = []
    for item in PRESET_AVATARS:
        item_copy = item.copy()
        item_copy['url'] = get_avatar_url(item['id'])
        res.append(item_copy)
    return res
