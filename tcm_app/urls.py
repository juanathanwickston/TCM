from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password_view, name='change_password'),
    
    # Pages
    path('', views.dashboard_view, name='home'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('inventory/', views.inventory_view, name='inventory'),
    path('inventory/update-audience/', views.update_audience_view, name='update_audience'),
    path('scrubbing/', views.scrubbing_view, name='scrubbing'),
    path('scrubbing/save/', views.save_scrub_view, name='save_scrub'),
    path('scrubbing/batch/', views.save_scrub_batch_view, name='save_scrub_batch'),
    path('investment/', views.investment_view, name='investment'),
    path('investment/save/', views.save_investment_view, name='save_investment'),
    path('investment/batch/', views.save_investment_batch_view, name='save_investment_batch'),
    path('investment/save-item/', views.save_investment_single_view, name='save_investment_single'),
    path('inventory/batch/', views.save_audience_batch_view, name='save_audience_batch'),
    
    # Tools
    path('tools/', views.tools_view, name='tools'),
    path('tools/import/zip/', views.import_zip_view, name='import_zip'),
    path('tools/sync/sharepoint/', views.sync_sharepoint_view, name='sync_sharepoint'),
    path('tools/danger/clear/', views.clear_all_data_view, name='clear_all_data'),
    
    # User Management (AJAX)
    path('tools/users/list/', views.list_users_view, name='list_users'),
    path('tools/users/create/', views.create_user_view, name='create_user'),
    path('tools/users/update/<int:user_id>/', views.update_user_view, name='update_user'),
    path('tools/users/delete/<int:user_id>/', views.delete_user_view, name='delete_user'),
    path('tools/users/reset-password/<int:user_id>/', views.reset_password_view, name='reset_password'),
]

