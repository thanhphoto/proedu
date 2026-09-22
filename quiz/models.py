from django.db import models
from django.contrib.auth.models import User

# 1. KỲ THI
class ExamPeriod(models.Model):
    name = models.CharField(max_length=200, verbose_name="Tên kỳ thi")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# 2. MÔN THI
class Subject(models.Model):
    exam_period = models.ForeignKey(ExamPeriod, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=100, verbose_name="Tên môn thi")
    code = models.CharField(max_length=20, verbose_name="Mã môn")

    # Cấu hình số lượng câu hỏi mặc định theo từng loại
    num_single = models.PositiveIntegerField(default=24, verbose_name="Số câu SingleChoose (Trắc nghiệm 4 lựa chọn)")
    num_tf = models.PositiveIntegerField(default=4, verbose_name="Số câu TrueFalse (Trắc nghiệm Đúng/Sai)")
    num_numeric = models.PositiveIntegerField(default=6, verbose_name="Số câu Numeric (Điền số thực)")

    # Ràng buộc số điểm / 1 câu trong mỗi phần
    score_per_single_val = models.FloatField(default=0.25, verbose_name="Điểm mỗi câu SingleChoose")
    score_per_tf_val = models.FloatField(default=1.0, verbose_name="Điểm tối đa mỗi câu TrueFalse")
    score_per_numeric_val = models.FloatField(default=0.5, verbose_name="Điểm mỗi câu Điền số thực")

    # Điểm tối đa mặc định của từng phần (tính tự động = số câu * điểm/câu)
    max_score_single = models.FloatField(default=6.0, verbose_name="Điểm tối đa phần SingleChoose")
    max_score_numeric = models.FloatField(default=3.0, verbose_name="Điểm tối đa phần Điền số thực")

    # Danh sách lớp áp dụng chấm môn thi này (có thể 1 lớp hoặc nhiều lớp, để trống = áp dụng toàn trường)
    assigned_classes = models.ManyToManyField('StudentClass', blank=True, related_name="subjects", verbose_name="Các lớp áp dụng chấm bài")

    def __str__(self):
        return f"{self.name} ({self.exam_period.name})"

    @property
    def total_questions(self):
        return self.num_single + self.num_tf + self.num_numeric

    @property
    def score_per_single(self):
        if self.score_per_single_val is not None:
            return round(self.score_per_single_val, 3)
        return round(self.max_score_single / self.num_single, 3) if self.num_single > 0 else 0.25

    @property
    def score_per_numeric(self):
        if self.score_per_numeric_val is not None:
            return round(self.score_per_numeric_val, 3)
        return round(self.max_score_numeric / self.num_numeric, 3) if self.num_numeric > 0 else 0.5

    @property
    def score_per_tf(self):
        if self.score_per_tf_val is not None:
            return round(self.score_per_tf_val, 3)
        return 1.0

    @property
    def max_score_tf(self):
        return round(self.num_tf * self.score_per_tf, 2)

    @property
    def total_subject_max_score(self):
        return round(self.max_score_single + self.max_score_tf + self.max_score_numeric, 2)

    def save(self, *args, **kwargs):
        if self.score_per_single_val is not None and self.num_single:
            self.max_score_single = round(self.num_single * self.score_per_single_val, 3)
        if self.score_per_numeric_val is not None and self.num_numeric:
            self.max_score_numeric = round(self.num_numeric * self.score_per_numeric_val, 3)
        super().save(*args, **kwargs)



# =====================================================================
# PHẦN NÂNG CẤP: NGÂN HÀNG CÂU HỎI THUỘC MÔN HỌC (CHƯA VÀO ĐỀ THI)
# =====================================================================

# 3. CHỦ ĐỀ KIẾN THỨC (Ví dụ: Đạo hàm, Tích phân, Di truyền học...)
class Topic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="topics")
    name = models.CharField(max_length=200, verbose_name="Tên chủ đề/Chương")

    def __str__(self):
        return f"{self.name} - {self.subject.name}"

# 4. NGÂN HÀNG CÂU HỎI TỔNG
class QuestionBank(models.Model):
    DIFFICULTY_CHOICES = [('NB', 'Nhận biết'), ('TH', 'Thông hiểu'), ('VD', 'Vận dụng'), ('VDC', 'Vận dụng cao')]
    TYPE_CHOICES = [
        ('SINGLE', 'Trắc nghiệm 1 đáp án đúng (4 lựa chọn)'),
        ('TF', 'Trắc nghiệm Đúng/Sai (Mỗi ý chọn Đúng hoặc Sai)'),
        ('NUMERIC', 'Trả lời ngắn dạng Số Thực'),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="question_bank")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Chủ đề")
    
    # Hỗ trợ lưu mã LaTeX tự do
    question_text = models.TextField(verbose_name="Nội dung câu hỏi (Hỗ trợ mã LaTeX)")
    image = models.ImageField(upload_to='question_images/', blank=True, null=True, verbose_name="Hình ảnh đính kèm câu hỏi")
    
    difficulty = models.CharField(max_length=5, choices=DIFFICULTY_CHOICES, default='NB', verbose_name="Mức độ khó")
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='SINGLE', verbose_name="Loại câu hỏi")
    is_public = models.BooleanField(default=False, verbose_name="Công khai (Học sinh được luyện tập)")

    # ĐƯỢC CHUYỂN VỀ ĐÂY: Dùng riêng cho loại NUMERIC, mỗi câu hỏi chỉ có đúng 1 đáp án là số này
    exact_numeric_answer = models.CharField(max_length=15, blank=True, null=True, verbose_name="Đáp án Số thực (Dành riêng cho câu hỏi Số)")

    @property
    def selected(self):
        """Thuộc tính lưu phương án/lựa chọn mà học sinh đã chọn/tô"""
        return getattr(self, '_selected', None)

    @selected.setter
    def selected(self, value):
        self._selected = value

    @property
    def seleted(self):
        return self.selected

    @seleted.setter
    def seleted(self, value):
        self.selected = value

    def __str__(self):
        return f"[{self.get_question_type_display()}] - {self.question_text[:50]}..."


# --- CẬP NHẬT: ĐÁP ÁN PHƯƠNG ÁN (Chỉ dùng cho loại SINGLE và TF) ---
class BankChoice(models.Model):
    question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name="choices")
    
    # Hỗ trợ lưu mã LaTeX cho từng phương án trả lời (ví dụ biểu thức, phân số)
    choice_text = models.TextField(verbose_name="Nội dung phương án lựa chọn (Hỗ trợ mã LaTeX)")
    is_correct = models.BooleanField(default=False, verbose_name="Là phương án ĐÚNG")

    @property
    def selected(self):
        """Thuộc tính đánh dấu phương án được học sinh chọn"""
        return getattr(self, '_selected', False)

    @selected.setter
    def selected(self, value):
        self._selected = bool(value)

    @property
    def seleted(self):
        return self.selected

    @seleted.setter
    def seleted(self, value):
        self.selected = value

    def __str__(self):
        return self.choice_text[:50]

# =====================================================================
# PHẦN NÂNG CẤP: ĐỀ THI VÀ KẾT QUẢ SAU KHI ĐÃ TRỘN MA TRẬN NẪU NHIÊN
# =====================================================================

import random

def generate_unique_exam_code():
    """Sinh mã bài thi gồm đúng 6 chữ số ngẫu nhiên và không trùng nhau trong CSDL"""
    while True:
        code = str(random.randint(100000, 999999))
        if not Quiz.objects.filter(exam_code=code).exists():
            return code

# 6. ĐỀ THI CHÍNH THỨC (Mã đề được sinh ra)
class Quiz(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=200, verbose_name="Mã đề / Tiêu đề đề thi")
    exam_code = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="Mã bài thi (6 chữ số)")
    duration = models.IntegerField(verbose_name="Thời gian làm bài (Phút)")
    start_time = models.DateTimeField(null=True, blank=True, verbose_name="Thời gian bắt đầu mở thi")
    deadline = models.DateTimeField(null=True, blank=True, verbose_name="Ngày hạn nộp bài")

    # Điểm mỗi loại câu hỏi
    score_single = models.FloatField(default=0.25, verbose_name="Điểm mỗi câu Trắc nghiệm")
    score_tf = models.FloatField(default=1.0, verbose_name="Điểm tối đa mỗi câu Đúng/Sai")
    score_numeric = models.FloatField(default=0.5, verbose_name="Điểm mỗi câu Trả lời số")

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.exam_code:
            self.exam_code = generate_unique_exam_code()
        super().save(*args, **kwargs)

    def __str__(self):
        code = self.exam_code or ''
        return f"{self.title} [{code}] - {self.subject.name}"

# 7. CÂU HỎI THỰC TẾ TRONG ĐỀ THI (Bốc ngẫu nhiên từ QuestionBank sang đây)
class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="quiz_questions")
    bank_question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, verbose_name="Gốc từ ngân hàng")
    order = models.IntegerField(verbose_name="Thứ tự câu trong đề thi (Câu 1, Câu 2...)")

    @property
    def selected(self):
        """Thuộc tính lưu phương án/lựa chọn mà học sinh đã chọn/tô"""
        return getattr(self, '_selected', None)

    @selected.setter
    def selected(self, value):
        self._selected = value

    @property
    def seleted(self):
        return self.selected

    @seleted.setter
    def seleted(self, value):
        self.selected = value

    def __str__(self):
        return f"Câu {self.order} trong {self.quiz.title}"

# 8. KẾT QUẢ LÀM BÀI
class ExamResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tài khoản")
    candidate_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Họ tên thí sinh")
    candidate_avatar = models.CharField(max_length=50, default='avatar-1', blank=True, verbose_name="Ảnh đại diện thí sinh")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, verbose_name="Bài thi")
    score = models.FloatField(verbose_name="Điểm số")
    total_questions = models.PositiveIntegerField(default=0, verbose_name="Tổng số câu")
    correct_count = models.PositiveIntegerField(default=0, verbose_name="Số câu đúng")
    time_spent = models.PositiveIntegerField(default=0, verbose_name="Thời gian làm bài (giây)")
    completed_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian nộp bài")

    class Meta:
        verbose_name = "Kết quả làm bài"
        verbose_name_plural = "Kết quả làm bài"

    def __str__(self):
        name = self.candidate_name or (self.user.username if self.user else "Khách")
        return f"{name} - {self.quiz.title} - {self.score}đ"

    @property
    def avatar_url(self):
        from .avatars import get_avatar_url
        if self.user and hasattr(self.user, 'profile') and self.user.profile.avatar:
            return get_avatar_url(self.user.profile.avatar)
        return get_avatar_url(self.candidate_avatar or 'avatar-1')


# 9. MA TRẬN ĐỀ THI (Mỗi dòng = 1 ô: Chủ đề × Mức độ × Loại câu → Số lượng)
class ExamMatrixEntry(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="matrix_entries")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Chủ đề")
    difficulty = models.CharField(max_length=5, choices=QuestionBank.DIFFICULTY_CHOICES, verbose_name="Mức độ khó")
    question_type = models.CharField(max_length=10, choices=QuestionBank.TYPE_CHOICES, verbose_name="Loại câu hỏi")
    quantity = models.PositiveIntegerField(default=0, verbose_name="Số lượng câu")

    class Meta:
        verbose_name = "Ma trận đề thi"
        verbose_name_plural = "Ma trận đề thi"

    def __str__(self):
        topic_name = self.topic.name if self.topic else "Không chủ đề"
        return f"{topic_name} | {self.get_difficulty_display()} | {self.get_question_type_display()} → {self.quantity} câu"


# 10. ĐẶC TẢ CHỦ ĐỀ TRONG MA TRẬN ĐỀ
class ExamMatrixTopicSpec(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="topic_specs")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, verbose_name="Chủ đề")
    description = models.TextField(blank=True, verbose_name="Đặc tả chủ đề kiến thức")

    class Meta:
        verbose_name = "Đặc tả chủ đề"
        verbose_name_plural = "Đặc tả chủ đề"
        unique_together = ('quiz', 'topic')

    def __str__(self):
        return f"{self.topic.name}: {self.description[:50]}"


# =====================================================================
# PHÂN QUYỀN VÀ THÔNG TIN NGƯỜI DÙNG (RBAC)
# =====================================================================

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Quản trị viên'),
        ('manager', 'Quản lý'),
        ('coding_contributor', 'Cộng tác viên lập trình'),
        ('user', 'Người dùng bình thường'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name="Tài khoản")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user', verbose_name="Vai trò")
    avatar = models.CharField(max_length=50, default='avatar-1', verbose_name="Ảnh đại diện")
    student_code = models.CharField(max_length=6, unique=True, null=True, blank=True, verbose_name="Mã số")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Ngày cập nhật")

    def save(self, *args, **kwargs):
        if not self.student_code:
            import random
            while True:
                code = str(random.randint(100000, 999999))
                if not UserProfile.objects.filter(student_code=code).exists():
                    self.student_code = code
                    break
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Hồ sơ người dùng"
        verbose_name_plural = "Hồ sơ người dùng"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def avatar_url(self):
        from .avatars import get_avatar_url
        return get_avatar_url(self.avatar)

    def is_admin(self):
        return self.role == 'admin' or self.user.is_superuser

    def is_manager(self):
        return self.role in ['admin', 'manager'] or self.user.is_superuser or self.user.is_staff

    def is_coding_contributor(self):
        return self.role in ['admin', 'manager', 'coding_contributor'] or self.user.is_superuser or self.user.is_staff


# Tự động tạo hoặc cập nhật UserProfile khi User được tạo
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        initial_role = 'admin' if instance.is_superuser else ('manager' if instance.is_staff else 'user')
        UserProfile.objects.create(user=instance, role=initial_role)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
        else:
            initial_role = 'admin' if instance.is_superuser else ('manager' if instance.is_staff else 'user')
            UserProfile.objects.create(user=instance, role=initial_role)


# =====================================================================
# QUẢN LÝ HỌC SINH VÀ LỚP HỌC DÙNG CHUNG (MASTER STUDENT ROSTER)
# =====================================================================

class StudentClass(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Tên lớp học (VD: 12A1)")
    grade = models.CharField(max_length=20, blank=True, verbose_name="Khối lớp (VD: 12)")
    description = models.TextField(blank=True, verbose_name="Ghi chú / Mô tả")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")

    class Meta:
        verbose_name = "Lớp học"
        verbose_name_plural = "Danh sách Lớp học"
        ordering = ['grade', 'name']

    def __str__(self):
        return self.name

    @property
    def total_students(self):
        return self.students.count()


class Student(models.Model):
    student_id = models.CharField(max_length=50, unique=True, verbose_name="Số Báo Danh (SBD)")
    full_name = models.CharField(max_length=150, verbose_name="Họ và tên học sinh")
    student_class = models.ForeignKey(StudentClass, on_delete=models.SET_NULL, null=True, blank=True, related_name="students", verbose_name="Lớp học")
    dob = models.DateField(null=True, blank=True, verbose_name="Ngày sinh")
    gender = models.CharField(max_length=10, choices=[('Nam', 'Nam'), ('Nữ', 'Nữ')], blank=True, verbose_name="Giới tính")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")

    class Meta:
        verbose_name = "Học sinh"
        verbose_name_plural = "Danh sách Học sinh (Master)"
        ordering = ['student_class__name', 'student_id']

    def __str__(self):
        cls_name = self.student_class.name if self.student_class else 'Chưa phân lớp'
        return f"{self.full_name} (SBD: {self.student_id}) - Lớp {cls_name}"


# =====================================================================
# PHÂN HỆ CHẤM TRẮC NGHIỆM (GRADING SYSTEM)
# =====================================================================

class GradingExamKey(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="grading_keys", verbose_name="Môn thi")
    code = models.CharField(max_length=20, default='101', verbose_name="Mã đề thi (VD: 101, 102...)")
    title = models.CharField(max_length=200, blank=True, verbose_name="Tên bộ đề / Tiêu đề đáp án")
    description = models.TextField(blank=True, verbose_name="Ghi chú")
    
    # Điểm đồng nhất theo loại câu hỏi trong mã đề
    score_single = models.FloatField(default=0.25, verbose_name="Điểm mỗi câu SingleChoose")
    score_numeric = models.FloatField(default=0.5, verbose_name="Điểm mỗi câu Điền số thực")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Người tạo")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Bộ đáp án chấm thi"
        verbose_name_plural = "Bộ đáp án chấm thi"
        unique_together = ('subject', 'code')


    def __str__(self):
        return f"{self.subject.name} - Đề {self.code}"

    @property
    def total_questions(self):
        return self.questions.count()

    @property
    def max_possible_score(self):
        total = 0.0
        for q in self.questions.all():
            if q.question_type == 'TF':
                total += 1.0  # Chuẩn Đúng/Sai 4 ý tối đa 1.0 điểm
            else:
                total += q.score_weight
        return round(total, 3)


class GradingKeyQuestion(models.Model):
    TYPE_CHOICES = [
        ('SINGLE', 'Trắc nghiệm 1 đáp án đúng (SingleChoose)'),
        ('TF', 'Trắc nghiệm Đúng/Sai (TrueFalse)'),
        ('NUMERIC', 'Điền số thực (Numeric - Tối đa 4 ký tự)'),
    ]

    key = models.ForeignKey(GradingExamKey, on_delete=models.CASCADE, related_name="questions", verbose_name="Bộ đáp án")
    question_number = models.PositiveIntegerField(verbose_name="Số thứ tự câu")
    question_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='SINGLE', verbose_name="Loại câu hỏi")
    score_weight = models.FloatField(default=0.25, verbose_name="Điểm cho câu hỏi này")
    
    # Đáp án chuẩn cho SingleChoose: 'A', 'B', 'C', 'D'
    correct_single = models.CharField(max_length=5, blank=True, null=True, verbose_name="Đáp án SingleChoose (A/B/C/D)")
    
    # Đáp án chuẩn cho TrueFalse: dict {'a': True, 'b': False, 'c': True, 'd': True}
    correct_tf = models.JSONField(default=dict, blank=True, verbose_name="Đáp án Đúng/Sai 4 ý (a,b,c,d)")
    
    # Đáp án chuẩn cho Numeric: tối đa 4 ký tự tính cả dấu thập phân/âm
    correct_numeric = models.CharField(max_length=4, blank=True, null=True, verbose_name="Đáp án Số thực (Tối đa 4 ký tự)")

    @property
    def selected(self):
        """Thuộc tính lưu phương án/lựa chọn mà học sinh đã chọn/tô"""
        return getattr(self, '_selected', None)

    @selected.setter
    def selected(self, value):
        self._selected = value

    @property
    def seleted(self):
        return self.selected

    @seleted.setter
    def seleted(self, value):
        self.selected = value

    class Meta:
        verbose_name = "Đáp án câu hỏi chấm"
        verbose_name_plural = "Đáp án câu hỏi chấm"
        ordering = ['question_number']
        unique_together = ('key', 'question_number')

    def __str__(self):
        return f"Đề {self.key.code} - Câu {self.question_number} [{self.get_question_type_display()}]"


class GradingRecord(models.Model):
    key = models.ForeignKey(GradingExamKey, on_delete=models.CASCADE, related_name="submissions", verbose_name="Mã đề chấm", null=True, blank=True)
    student_id = models.CharField(max_length=50, verbose_name="Số báo danh / Mã thí sinh")
    student_name = models.CharField(max_length=150, verbose_name="Họ và tên thí sinh")
    student_class = models.CharField(max_length=50, blank=True, default='', verbose_name="Lớp / Phòng thi")
    exam_code = models.CharField(max_length=20, blank=True, default='', verbose_name="Mã đề thí sinh làm")
    total_score = models.FloatField(default=0.0, verbose_name="Tổng điểm đạt được")
    max_score = models.FloatField(default=10.0, verbose_name="Điểm tối đa")
    correct_count = models.PositiveIntegerField(default=0, verbose_name="Số câu đúng tuyệt đối")
    
    # Dữ liệu trả lời của thí sinh
    student_answers = models.JSONField(default=dict, blank=True, verbose_name="Đáp án thí sinh điền")
    
    # Kết quả chấm chi tiết
    grading_details = models.JSONField(default=list, blank=True, verbose_name="Chi tiết chấm từng câu")
    
    # File ảnh bài làm
    annotated_image = models.ImageField(upload_to='grading_sheets/annotated/', blank=True, null=True, verbose_name="Ảnh phiếu đã chấm (vẽ nhận diện)")
    original_image = models.ImageField(upload_to='grading_sheets/original/', blank=True, null=True, verbose_name="Ảnh phiếu gốc")
    
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Người chấm")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian chấm")

    class Meta:
        verbose_name = "Kết quả bài chấm"
        verbose_name_plural = "Kết quả bài chấm"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student_name} ({self.student_id}) - Đề {self.key.code} - {self.total_score}đ"

class CodingTopic(models.Model):
    name = models.CharField(max_length=100, verbose_name="Tên chủ đề")
    description = models.TextField(blank=True, default="", verbose_name="Mô tả")

    class Meta:
        verbose_name = "Chủ đề lập trình"
        verbose_name_plural = "Chủ đề lập trình"
        ordering = ['name']

    def __str__(self):
        return self.name

class CodingExam(models.Model):
    EXAM_TYPE_CHOICES = (
        ('free', 'Tự do'),
        ('registered', 'Có đăng ký & kiểm duyệt'),
    )
    title = models.CharField(max_length=255, verbose_name="Tên kỳ thi")
    description = models.TextField(blank=True, default="", verbose_name="Mô tả")
    start_time = models.DateTimeField(null=True, blank=True, verbose_name="Thời gian bắt đầu")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Thời gian kết thúc")
    duration = models.IntegerField(default=0, verbose_name="Thời gian làm bài (phút)", help_text="Nhập 0 nếu không giới hạn")
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES, default='free', verbose_name="Loại kỳ thi")
    is_active = models.BooleanField(default=True, verbose_name="Kích hoạt")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coding_exams', verbose_name="Người tạo")

    class Meta:
        verbose_name = "Kỳ thi lập trình"
        verbose_name_plural = "Kỳ thi lập trình"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class CodingExamRegistration(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coding_registrations', verbose_name="Thí sinh")
    exam = models.ForeignKey(CodingExam, on_delete=models.CASCADE, related_name='registrations', verbose_name="Kỳ thi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Trạng thái")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày đăng ký")

    class Meta:
        verbose_name = "Đăng ký kỳ thi lập trình"
        verbose_name_plural = "Đăng ký kỳ thi lập trình"
        ordering = ['-created_at']
        unique_together = ('user', 'exam')

    def __str__(self):
        return f"{self.user.username} - {self.exam.title} - {self.status}"



class CodingQuestion(models.Model):
    DIFFICULTY_CHOICES = (
        ('Dễ', 'Dễ'),
        ('Trung bình', 'Trung bình'),
        ('Khó', 'Khó'),
        ('Rất khó', 'Rất khó'),
    )

    exam = models.ForeignKey(CodingExam, on_delete=models.CASCADE, related_name='questions', null=True, blank=True, verbose_name="Kỳ thi")

    title = models.CharField(max_length=255, verbose_name="Tên bài toán")
    description = models.TextField(verbose_name="Mô tả chi tiết")
    time_limit = models.FloatField(default=1.0, verbose_name="Giới hạn thời gian (giây)")
    memory_limit = models.IntegerField(default=128, verbose_name="Giới hạn bộ nhớ (MB)")
    initial_code_cpp = models.TextField(blank=True, default="", verbose_name="Code mẫu C++")
    initial_code_python = models.TextField(blank=True, default="", verbose_name="Code mẫu Python")
    solution_code_cpp = models.TextField(blank=True, default="", verbose_name="Code đáp án chuẩn C++")
    solution_code_python = models.TextField(blank=True, default="", verbose_name="Code đáp án chuẩn Python")
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default='Dễ', verbose_name="Mức độ khó")
    max_score = models.IntegerField(default=10, verbose_name="Điểm tối đa (100% testcase)")
    is_public = models.BooleanField(default=True, verbose_name="Công khai ở Luyện Code")
    is_active = models.BooleanField(default=True, verbose_name="Hiển thị với người dùng")
    past_exam = models.CharField(max_length=255, blank=True, default="", verbose_name="Thuộc đề thi (đã thi trực tiếp)")
    topics = models.ManyToManyField(CodingTopic, blank=True, related_name='questions', verbose_name="Chủ đề")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coding_questions', verbose_name="Người tạo")

    class Meta:
        verbose_name = "Bài toán lập trình"
        verbose_name_plural = "Bài toán lập trình"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class TestCase(models.Model):
    question = models.ForeignKey(CodingQuestion, on_delete=models.CASCADE, related_name="testcases")
    input_data = models.TextField(verbose_name="Dữ liệu đầu vào", blank=True, default="")
    expected_output = models.TextField(verbose_name="Kết quả đầu ra mong đợi", blank=True, default="")
    is_hidden = models.BooleanField(default=False, verbose_name="Testcase ẩn")
    points = models.FloatField(default=0.1, verbose_name="Điểm số")

    class Meta:
        verbose_name = "Test case"
        verbose_name_plural = "Test cases"

    def __str__(self):
        return f"Testcase for {self.question.title}"

class CodeSubmission(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Đang chờ chấm'),
        ('Accepted', 'Đúng (Accepted)'),
        ('Wrong Answer', 'Sai (Wrong Answer)'),
        ('Time Limit Exceeded', 'Quá thời gian (TLE)'),
        ('Compilation Error', 'Lỗi biên dịch (CE)'),
        ('Runtime Error', 'Lỗi thực thi (RE)'),
    )
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="code_submissions", verbose_name="Học sinh nộp")
    question = models.ForeignKey(CodingQuestion, on_delete=models.CASCADE, related_name="submissions", verbose_name="Bài toán")
    language = models.CharField(max_length=50, choices=[('cpp', 'C++'), ('python', 'Python')], verbose_name="Ngôn ngữ")
    code = models.TextField(verbose_name="Nội dung code")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending', verbose_name="Trạng thái")
    score = models.FloatField(default=0.0, verbose_name="Điểm")
    details = models.JSONField(null=True, blank=True, verbose_name="Chi tiết testcases")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian nộp")

    class Meta:
        verbose_name = "Bài nộp lập trình"
        verbose_name_plural = "Bài nộp lập trình"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} - {self.question.title} - {self.status}"

class CodingComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coding_comments", verbose_name="Người dùng")
    question = models.ForeignKey(CodingQuestion, on_delete=models.CASCADE, related_name="comments", verbose_name="Bài toán")
    content = models.TextField(verbose_name="Nội dung bình luận")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian bình luận")

    class Meta:
        verbose_name = "Bình luận Luyện Code"
        verbose_name_plural = "Bình luận Luyện Code"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} on {self.question.title} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class CodingExamAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coding_exam_attempts', verbose_name="Thí sinh")
    exam = models.ForeignKey(CodingExam, on_delete=models.CASCADE, related_name='attempts', verbose_name="Kỳ thi")
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian bắt đầu")
    is_completed = models.BooleanField(default=False, verbose_name="Đã hoàn thành")
    total_score = models.FloatField(default=0.0, verbose_name="Tổng điểm")

    class Meta:
        verbose_name = "Lượt làm bài thi lập trình"
        verbose_name_plural = "Lượt làm bài thi lập trình"
        ordering = ['-total_score', 'start_time']
        unique_together = ('user', 'exam') # Each user attempts exam once.

    def __str__(self):
        return f"{self.user.username} - {self.exam.title} - {self.total_score}đ"
