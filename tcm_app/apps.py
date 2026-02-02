from django.apps import AppConfig


class TcmAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tcm_app'
    verbose_name = 'Training Catalogue Manager'
    
    def ready(self):
        """Initialize database schema when Django starts.
        
        Skips initialization if:
        - DATABASE_URL is SQLite or missing (CI environment)
        - Running a build-phase command (collectstatic, migrate, etc.)
          where database may not be accessible yet (Railway build phase)
        """
        import os
        import sys
        
        db_url = os.environ.get('DATABASE_URL', '')
        
        # Skip if not PostgreSQL
        if not db_url.startswith('postgres'):
            return
        
        # Skip during build-phase commands (database not accessible on Railway build)
        # These commands don't need database initialization
        build_commands = {'collectstatic', 'migrate', 'makemigrations', 'check', 'compilemessages'}
        if len(sys.argv) > 1 and sys.argv[1] in build_commands:
            return
        
        # Runtime: initialize database
        from db import init_db
        init_db()
