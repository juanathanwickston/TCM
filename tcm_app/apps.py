from django.apps import AppConfig


class TcmAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tcm_app'
    verbose_name = 'Training Catalogue Manager'
    
    def ready(self):
        """Initialize database schema when Django starts."""
        from db import init_db
        init_db()
