import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proedu.settings")
django.setup()

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.conf import settings

font_dir = os.path.join(settings.BASE_DIR, 'static', 'fonts')
try:
    pdfmetrics.registerFont(TTFont('Roboto', os.path.join(font_dir, 'Roboto-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('Roboto-Bold', os.path.join(font_dir, 'Roboto-Bold.ttf')))
    pdfmetrics.registerFont(TTFont('Roboto-Italic', os.path.join(font_dir, 'Roboto-Italic.ttf')))
    print("Fonts registered successfully!")
except Exception as e:
    print("Error registering fonts:", e)
