import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DATABASE_URL = os.getenv('DATABASE_URL')

    # Конфигурация базы данных
    DATABASE_CONFIG = {
        'database': os.getenv('DB_NAME', 'webcrawler_db'),
        'user': os.getenv('DB_USER', 'crawler_user'),
        'password': os.getenv('DB_PASSWORD', 'crawler_user'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432'))
    }

