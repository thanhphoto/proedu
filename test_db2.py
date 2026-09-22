import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proedu.settings")
django.setup()
from quiz.grading_views import api_grade_submission
from django.test import RequestFactory
import json

factory = RequestFactory()
request = factory.post('/cham-trac-nghiem/api/cham-bai/',
    data=json.dumps({"key_id": "", "student_id": "999", "student_name": "Test", "student_class": "", "answers": {}, "force_zero": True}),
    content_type='application/json')
request.user = None # simulate anonymous or we can fetch a user
from django.contrib.auth.models import User
request.user = User.objects.first()

response = api_grade_submission(request)
print("Response status:", response.status_code)
print("Response content:", response.content.decode('utf-8'))
