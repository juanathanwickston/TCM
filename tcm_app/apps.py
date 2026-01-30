from django.apps import AppConfig


class TcmAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tcm_app'
    verbose_name = 'Training Catalogue Manager'
    
    def ready(self):
        """Initialize database schema when Django starts.
        
        Skips initialization if DATABASE_URL is SQLite or missing,
        since db.py requires PostgreSQL (uses psycopg2).
        """
        import os
        db_url = os.environ.get('DATABASE_URL', '')
        
        # Only initialize if we have a PostgreSQL connection
        if db_url.startswith('postgres'):
            from db import init_db
            init_db()
