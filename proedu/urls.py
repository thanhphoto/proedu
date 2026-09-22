from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.get_view_urls() if hasattr(admin.site, 'get_view_urls') else admin.site.urls),
    path('', include('quiz.urls')) # Trỏ toàn bộ request từ trang chủ đến app quiz
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

