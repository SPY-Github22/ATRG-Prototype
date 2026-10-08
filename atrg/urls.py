from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    # Main portal UI
    path('', include('portal.urls')),

    # Module URL namespaces
    path('core/', include('core.urls')),
    path('ingest/', include('ingest.urls')),
    path('testing/', include('testing.urls')),
    path('review/', include('review.urls')),
    path('reports/', include('reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
