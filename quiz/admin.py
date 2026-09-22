from django.contrib import admin
from .models import ExamPeriod, Subject, Topic, QuestionBank, BankChoice, Quiz, QuizQuestion, ExamResult, ExamMatrixEntry, ExamMatrixTopicSpec

# --- CẤU HÌNH INLINE: Nhập đáp án ngay trong giao diện tạo câu hỏi ---
class BankChoiceInline(admin.TabularInline):
    model = BankChoice
    extra = 4
    # Bỏ trường exact_numeric_answer cũ trong inline
    fields = ('choice_text', 'is_correct')

# --- CẤU HÌNH GIAO DIỆN QUẢN LÝ NGÂN HÀNG CÂU HỎI ---
@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    # Các cột hiển thị ngoài danh sách
    list_display = ('short_question_text', 'subject', 'topic', 'difficulty', 'question_type', 'is_public')
    
    # Bộ lọc nhanh ở thanh bên phải
    list_filter = ('subject', 'difficulty', 'question_type', 'is_public')
    
    # Ô tìm kiếm theo nội dung câu hỏi
    search_fields = ('question_text',)
    
    # Nhúng Inline chọn đáp án vào giao diện chi tiết câu hỏi
    inlines = [BankChoiceInline]

    # Hàm bổ trợ để rút ngắn nội dung câu hỏi hiển thị ngoài danh sách
    def short_question_text(self, obj):
        return obj.question_text[:60] + "..." if len(obj.question_text) > 60 else obj.question_text
    short_question_text.short_description = "Nội dung câu hỏi"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_word_url'] = '/nhap-cau-hoi-word/'
        return super().changelist_view(request, extra_context=extra_context)



# --- CẤU HÌNH INLINE: Xem danh sách câu hỏi nằm trong đề thi ---
class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 0  # Không tự sinh dòng trống, chỉ hiển thị các câu đã bốc ngẫu nhiên
    readonly_fields = ('bank_question', 'order')

class ExamMatrixEntryInline(admin.TabularInline):
    model = ExamMatrixEntry
    extra = 0
    readonly_fields = ('topic', 'difficulty', 'question_type', 'quantity')

class ExamMatrixTopicSpecInline(admin.TabularInline):
    model = ExamMatrixTopicSpec
    extra = 0


# --- CẤU HÌNH GIAO DIỆN QUẢN LÝ ĐỀ THI ---
@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'exam_code', 'subject', 'duration', 'deadline', 'created_at')
    list_filter = ('subject',)
    search_fields = ('title', 'exam_code')
    inlines = [ExamMatrixEntryInline, ExamMatrixTopicSpecInline, QuizQuestionInline]


# --- ĐĂNG KÝ CÁC BẢNG CÒN LẠI VÀO DIỆN MẶC ĐỊNH ---
admin.site.register(ExamPeriod)
admin.site.register(Subject)
admin.site.register(Topic)
admin.site.register(ExamResult)
