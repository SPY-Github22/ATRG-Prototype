from django.contrib import admin

from .models import ImportBatch, OCRQueueItem


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = [
        'filename',
        'job',
        'test',
        'status',
        'total_rows',
        'valid_rows',
        'error_rows',
        'uploaded_by',
        'uploaded_at',
    ]

    list_filter = [
        'status',
        'job',
    ]

    search_fields = [
        'filename',
        'job__test_series_no',
    ]

    readonly_fields = [
        'header_json',
        'mapping_json',
        'preview_json',
        'total_rows',
        'valid_rows',
        'error_rows',
    ]


@admin.register(OCRQueueItem)
class OCRQueueItemAdmin(admin.ModelAdmin):
    list_display = [
        'job',
        'test',
        'status',
        'confidence',
        'uploaded_by',
        'reviewed_by',
        'created_at',
    ]

    list_filter = [
        'status',
        'job',
    ]

    readonly_fields = [
        'proposal_json',
        'confidence',
        'created_at',
    ]
