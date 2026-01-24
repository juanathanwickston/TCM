from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Pages
    path('', views.dashboard_view, name='home'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('inventory/', views.inventory_view, name='inventory'),
    path('inventory/update-audience/', views.update_audience_view, name='update_audience'),
    path('scrubbing/', views.scrubbing_view, name='scrubbing'),
    path('investment/', views.investment_view, name='investment'),
    path('tools/', views.tools_view, name='tools'),
]
