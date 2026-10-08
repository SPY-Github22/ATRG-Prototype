from django.urls import path

from . import views

app_name = 'portal'

urlpatterns = [
    # Internal dashboard
    path('', views.dashboard, name='dashboard'),

    # Supports older LOGIN_REDIRECT_URL='/dashboard/'
    path('dashboard/', views.dashboard),

    # Internal job views
    path('jobs/<int:job_id>/', views.job_detail, name='job_detail'),

    path(
        'tests/<int:test_id>/enter/',
        views.test_enter,
        name='test_enter',
    ),

    path(
        'tests/<int:test_id>/complete/',
        views.test_complete,
        name='test_complete',
    ),

    path(
        'jobs/<int:job_id>/generate-report/',
        views.generate_report,
        name='generate_report',
    ),

    path(
        'jobs/<int:job_id>/report/preview/',
        views.report_preview,
        name='report_preview',
    ),

    path(
        'jobs/<int:job_id>/transition/<str:action>/',
        views.transition_view,
        name='transition',
    ),

    path(
        'reports/<int:report_id>/download/',
        views.report_download,
        name='report_download',
    ),

    path(
        'reports/<int:report_id>/verify/',
        views.verify_report,
        name='verify_report',
    ),

    path('audit/', views.audit_log, name='audit_log'),

    # Customer portal
    path('customer/', views.customer_home, name='customer_home'),

    path(
        'customer/request/new/',
        views.customer_request_new,
        name='customer_request_new',
    ),

    path(
        'customer/jobs/<int:job_id>/',
        views.customer_job_detail,
        name='customer_job_detail',
    ),

    path(
        'customer/notifications/',
        views.customer_notifications,
        name='customer_notifications',
    ),

    path(
        'notifications/<int:notification_id>/read/',
        views.notification_mark_read,
        name='notification_mark_read',
    ),

    path(
        'notifications/mark-all-read/',
        views.notifications_mark_all_read,
        name='notifications_mark_all_read',
    ),
]
