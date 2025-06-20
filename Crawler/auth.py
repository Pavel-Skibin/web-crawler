from functools import wraps
from flask import session, redirect, url_for, flash
from database import db_manager


def login_required(f):
    """Декоратор для проверки авторизации"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходимо войти в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Декоратор для проверки прав администратора"""

    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходимо войти в систему', 'error')
            return redirect(url_for('login'))

        user = await db_manager.get_user_by_id(session['user_id'])
        if not user or user['role'] != 'admin':
            flash('Недостаточно прав доступа', 'error')
            return redirect(url_for('dashboard'))

        return await f(*args, **kwargs)

    return decorated_function


def get_current_user():
    """Получение текущего пользователя"""
    if 'user_id' in session:
        return {
            'id': session['user_id'],
            'username': session['username'],
            'role': session['role']
        }
    return None


def is_admin():
    """Проверка, является ли текущий пользователь администратором"""
    user = get_current_user()
    return user and user['role'] == 'admin'