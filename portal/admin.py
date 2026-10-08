from django.contrib import admin

from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'customer',
        'is_primary',
        'created_at',
    ]

    search_fields = [
        'user__username',
        'customer__legal_name',
    ]

    list_filter = [
        'customer',
    ]
