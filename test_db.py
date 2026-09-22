import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proedu.settings")
django.setup()
from quiz.models import GradingRecord
try:
    GradingRecord.objects.create(
        key=None,
        student_id="123",
        student_name="Test",
        exam_code="",
        total_score=0.0,
        max_score=10.0,
        correct_count=0
    )
    print("SUCCESS")
except Exception as e:
    print("ERROR:", str(e))
