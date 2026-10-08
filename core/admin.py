from django.contrib import admin
from .models import (
    Customer, CustomerAlias, Job, Sample, TestType, Test,
    Parameter, Measurement, LimitRule, Result,
    DocumentType, Document, Report, Approval, AuditLog, Notification,
)


class CustomerAliasInline(admin.TabularInline):
    model = CustomerAlias
    extra = 1


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['legal_name', 'contact_person', 'email', 'phone']
    search_fields = ['legal_name', 'aliases__alias']
    inlines = [CustomerAliasInline]


class SampleInline(admin.StackedInline):
    model = Sample
    extra = 0


class TestInline(admin.TabularInline):
    model = Test
    extra = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['test_series_no', 'customer', 'request_type', 'status', 'received_at', 'promised_at']
    list_filter = ['status', 'request_type', 'customer']
    search_fields = ['test_series_no', 'file_no', 'customer__legal_name']
    inlines = [SampleInline, TestInline]


@admin.register(TestType)
class TestTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'section_no', 'form_no']


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['job', 'test_type', 'bay', 'performed_by', 'started_at', 'completed_at']
    list_filter = ['test_type', 'bay']


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'unit', 'data_type', 'test_type']
    list_filter = ['test_type', 'data_type']


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = ['test', 'parameter', 'stage', 'tap_position', 'phase', 'value', 'unit', 'source']
    list_filter = ['stage', 'source', 'parameter']


@admin.register(LimitRule)
class LimitRuleAdmin(admin.ModelAdmin):
    list_display = ['code', 'standard', 'clause', 'parameter', 'comparator', 'limit_value']
    list_filter = ['standard']


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ['job', 'rule', 'measured', 'limit', 'verdict', 'evaluated_at']
    list_filter = ['verdict']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['job', 'version', 'state', 'generated_at', 'generated_by']
    list_filter = ['state']


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ['report', 'step', 'actor', 'at']
    list_filter = ['step']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['at', 'actor', 'entity', 'entity_id', 'action', 'field']
    list_filter = ['action', 'entity']
    search_fields = ['entity', 'field', 'old_value', 'new_value']

    def has_change_permission(self, request, obj=None):
        return False  # Append-only

    def has_delete_permission(self, request, obj=None):
        return False  # Append-only


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['customer', 'job', 'kind', 'message', 'created_at', 'read_at']
    list_filter = ['kind']


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['job', 'doc_type', 'form_no', 'revision', 'uploaded_at']
    list_filter = ['doc_type']
