from django import forms
from django.forms import inlineformset_factory
from django.contrib.auth.models import User
from .models import QuestionBank, BankChoice, Topic, Subject, ExamPeriod, UserProfile


# =====================================================================
# BIỂU MẪU XÁC THỰC NGƯỜI DÙNG (AUTHENTICATION)
# =====================================================================

class LoginForm(forms.Form):
    username = forms.CharField(
        label="Tên đăng nhập",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg rounded-3',
            'placeholder': 'Nhập tên đăng nhập...',
            'autocomplete': 'username',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label="Mật khẩu",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg rounded-3',
            'placeholder': 'Nhập mật khẩu...',
            'autocomplete': 'current-password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Ghi nhớ đăng nhập",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class RegisterForm(forms.ModelForm):
    full_name = forms.CharField(
        max_length=150,
        required=True,
        label="Họ và tên",
        widget=forms.TextInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Ví dụ: Nguyễn Văn A'
        })
    )
    email = forms.EmailField(
        required=True,
        label="Địa chỉ Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'email@example.com'
        })
    )
    password = forms.CharField(
        min_length=6,
        required=True,
        label="Mật khẩu",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Ít nhất 6 ký tự...'
        })
    )
    confirm_password = forms.CharField(
        required=True,
        label="Xác nhận mật khẩu",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Nhập lại mật khẩu...'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'password']
        labels = {
            'username': 'Tên đăng nhập',
        }
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control rounded-3',
                'placeholder': 'Tên đăng nhập không dấu, không khoảng trắng'
            })
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Tên đăng nhập này đã được sử dụng. Vui lòng chọn tên khác.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email này đã được đăng ký tài khoản.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Mật khẩu xác nhận không khớp.")
        return cleaned_data


# =====================================================================
# BIỂU MẪU CÂU HỎI & NGÂN HÀNG ĐỀ
# =====================================================================

class QuestionBankForm(forms.ModelForm):
    class Meta:
        model = QuestionBank
        fields = ['question_text', 'difficulty', 'topic', 'question_type', 'exact_numeric_answer']
        widgets = {
            'question_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'exact_numeric_answer': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'question_text': 'Nội dung câu hỏi',
            'difficulty': 'Độ khó',
            'topic': 'Chủ đề / Chương',
            'question_type': 'Loại câu hỏi',
            'exact_numeric_answer': 'Đáp án số thực (nếu áp dụng)'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict topic choices to topics of the related subject (if instance exists)
        if self.instance and self.instance.subject_id:
            self.fields['topic'].queryset = Topic.objects.filter(subject_id=self.instance.subject_id)
        else:
            self.fields['topic'].queryset = Topic.objects.none()

# Inline formset for answer choices
BankChoiceFormSet = inlineformset_factory(
    QuestionBank,
    BankChoice,
    fields=('choice_text', 'is_correct'),
    extra=0,
    can_delete=True,
    widgets={
        'choice_text': forms.TextInput(attrs={'class': 'form-control'}),
        'is_correct': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    },
    labels={
        'choice_text': 'Nội dung phương án',
        'is_correct': 'Đúng'
    }
)

