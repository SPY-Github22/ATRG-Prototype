from django.urls import path

from . import views

app_name = 'ingest'

urlpatterns = [
    # CSV import
    path('', views.import_batch_list, name='import_list'),
    path('start/', views.import_start, name='import_start'),
    path('<int:batch_id>/mapping/', views.import_mapping, name='import_mapping'),
    path('<int:batch_id>/preview/', views.import_preview, name='import_preview'),
    path('<int:batch_id>/commit/', views.import_commit, name='import_commit'),

    # OCR queue
    path('ocr/', views.ocr_list, name='ocr_list'),
    path('ocr/upload/', views.ocr_upload, name='ocr_upload'),
    path('ocr/<int:item_id>/review/', views.ocr_review, name='ocr_review'),
]
