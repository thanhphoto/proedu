from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.dispatch import receiver
import unicodedata

def sqlite_unaccent(s):
    if not isinstance(s, str): return s
    return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')

@receiver(connection_created)
def extend_sqlite(connection=None, **kwargs):
    if connection.vendor == "sqlite":
        connection.connection.create_function("unaccent", 1, sqlite_unaccent)

class QuizConfig(AppConfig):
    name = 'quiz'
