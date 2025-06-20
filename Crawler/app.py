from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import threading
import asyncio
import traceback
from datetime import datetime
import logging

from config import Config
from database import db_manager
from auth import login_required, get_current_user
from crawler import WebCrawler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Глобальный словарь для отслеживания активных заданий
active_jobs = {}


def run_async_crawler(crawler, job_id):
    """Запуск краулера в отдельном потоке с отслеживанием прогресса"""
    logger.info(f"Запуск краулера в потоке: {threading.current_thread().name}")

    # Добавляем задание в список активных
    active_jobs[job_id] = {
        'status': 'starting',
        'progress': 0,
        'current_url': crawler.start_url,
        'pages_processed': 0,
        'total_pages': crawler.max_pages,
        'started_at': datetime.now(),
        'message': 'Инициализация краулера...'
    }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info(f"Запуск crawl() для задания: {crawler.job_name}")

        # Передаем callback для обновления прогресса
        crawler.progress_callback = lambda **kwargs: update_job_progress(job_id, **kwargs)

        result = loop.run_until_complete(crawler.crawl())
        logger.info(f"Краулер завершен успешно, результат: {result}")

        # Финальное обновление
        active_jobs[job_id].update({
            'status': 'completed',
            'progress': 100,
            'message': 'Краулинг завершен успешно!'
        })

    except Exception as e:
        logger.error(f"Ошибка при выполнении краулинга: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        # Обновляем статус на ошибку
        if job_id in active_jobs:
            active_jobs[job_id].update({
                'status': 'failed',
                'message': f'Ошибка: {str(e)}'
            })

    finally:
        logger.info("Закрытие цикла событий")
        loop.close()

        # Удаляем из активных заданий через 5 минут
        def cleanup_job():
            import time
            time.sleep(300)  # 5 минут
            if job_id in active_jobs:
                del active_jobs[job_id]

        cleanup_thread = threading.Thread(target=cleanup_job)
        cleanup_thread.daemon = True
        cleanup_thread.start()


def update_job_progress(job_id, **kwargs):
    """Обновление прогресса задания"""
    if job_id in active_jobs:
        active_jobs[job_id].update(kwargs)
        active_jobs[job_id]['updated_at'] = datetime.now()


@app.route('/')
def index():
    """Главная страница - редирект на dashboard или login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Введите имя пользователя и пароль', 'error')
            return render_template('login.html')

        logger.info(f"Попытка входа: {username}")
        user = db_manager.verify_user(username, password)

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Вход выполнен успешно!', 'success')
            logger.info(f"Успешный вход: {username} (ID: {user['id']}, роль: {user['role']})")
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Страница регистрации"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password:
            flash('Введите имя пользователя и пароль', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return render_template('register.html')

        logger.info(f"Попытка регистрации пользователя: {username}")
        success, message = db_manager.create_user(username, password)

        if success:
            flash('Регистрация успешна! Теперь вы можете войти в систему.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')

    return render_template('register.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Панель управления пользователя"""
    user = get_current_user()

    if user['role'] == 'admin':
        jobs = db_manager.get_all_jobs()
    else:
        jobs = db_manager.get_user_jobs(user['id'])

    return render_template('dashboard.html', jobs=jobs, user=user)


@app.route('/admin')
@login_required
def admin_panel():
    """Панель администратора"""
    user = get_current_user()
    if not user or user['role'] != 'admin':
        flash('Недостаточно прав доступа', 'error')
        return redirect(url_for('dashboard'))

    users = db_manager.get_all_users()
    jobs = db_manager.get_all_jobs()

    return render_template('admin_panel.html', users=users, jobs=jobs)


@app.route('/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    """Удаление пользователя (только для админа)"""
    user = get_current_user()
    if not user or user['role'] != 'admin':
        flash('Недостаточно прав доступа', 'error')
        return redirect(url_for('dashboard'))

    success = db_manager.delete_user(user_id)
    if success:
        flash('Пользователь удален', 'success')
    else:
        flash('Ошибка удаления пользователя', 'error')

    return redirect(url_for('admin_panel'))


@app.route('/create_job', methods=['GET', 'POST'])
@login_required
def create_job():
    """Создание нового задания краулера"""
    user = get_current_user()
    logger.info(f"create_job вызван пользователем: {user}")

    if request.method == 'POST':
        job_name = request.form.get('job_name', '').strip()
        start_url = request.form.get('start_url', '').strip()

        logger.info(f"Получены данные формы: job_name='{job_name}', start_url='{start_url}'")

        if not job_name or not start_url:
            flash('Введите название задания и URL', 'error')
            limits = Config.USER_LIMITS if user['role'] != 'admin' else None
            return render_template('create_job.html', user=user, limits=limits)

        try:
            max_pages = int(request.form.get('max_pages', 20))
            max_depth = int(request.form.get('max_depth', 2))
            delay = float(request.form.get('delay', 0.5))
            logger.info(f"Параметры: max_pages={max_pages}, max_depth={max_depth}, delay={delay}")
        except ValueError as e:
            logger.error(f"Ошибка в параметрах: {e}")
            flash('Некорректные числовые значения', 'error')
            limits = Config.USER_LIMITS if user['role'] != 'admin' else None
            return render_template('create_job.html', user=user, limits=limits)

        # Проверка ограничений для обычных пользователей
        if user['role'] != 'admin':
            limits = Config.USER_LIMITS
            if max_pages > limits['max_pages_per_job']:
                flash(f'Максимальное количество страниц: {limits["max_pages_per_job"]}', 'error')
                return render_template('create_job.html', user=user, limits=limits)

            if max_depth > limits['max_depth']:
                flash(f'Максимальная глубина: {limits["max_depth"]}', 'error')
                return render_template('create_job.html', user=user, limits=limits)

            if delay < limits['min_delay']:
                flash(f'Минимальная задержка: {limits["min_delay"]} сек', 'error')
                return render_template('create_job.html', user=user, limits=limits)

        # Сначала создаем запись в БД, чтобы получить ID
        try:
            job_id = db_manager.create_job(
                user['id'], job_name, start_url, max_pages, max_depth, delay, 'running'
            )
            logger.info(f"Создано задание с ID: {job_id}")
        except Exception as e:
            logger.error(f"Ошибка создания задания в БД: {e}")
            flash('Ошибка создания задания в базе данных', 'error')
            limits = Config.USER_LIMITS if user['role'] != 'admin' else None
            return render_template('create_job.html', user=user, limits=limits)

        # Создание краулера
        try:
            logger.info("Создание краулера...")
            crawler = WebCrawler(
                job_name=job_name,
                start_url=start_url,
                user_id=user['id'],
                max_pages=max_pages,
                delay=delay,
                max_depth=max_depth
            )
            crawler.job_id = job_id  # Устанавливаем ID задания
            logger.info("Краулер создан успешно")
        except Exception as e:
            logger.error(f"Ошибка создания краулера: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            flash('Ошибка создания краулера', 'error')
            limits = Config.USER_LIMITS if user['role'] != 'admin' else None
            return render_template('create_job.html', user=user, limits=limits)

        # Запуск краулера в отдельном потоке
        def run_crawler():
            try:
                logger.info("Запуск краулера в потоке...")
                run_async_crawler(crawler, job_id)
            except Exception as e:
                logger.error(f"Ошибка при создании/запуске краулера: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")

        logger.info("Создание потока для краулера...")
        thread = threading.Thread(target=run_crawler)
        thread.daemon = True
        thread.start()
        logger.info(f"Поток запущен: {thread.name}")

        flash('Задание создано и запущено!', 'success')
        return redirect(url_for('job_details', job_id=job_id))  # Сразу переходим к деталям

    limits = Config.USER_LIMITS if user['role'] != 'admin' else None
    return render_template('create_job.html', user=user, limits=limits)


@app.route('/job/<int:job_id>')
@login_required
def job_details(job_id):
    """Детали задания"""
    user = get_current_user()

    job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    if not job:
        flash('Задание не найдено', 'error')
        return redirect(url_for('dashboard'))

    pages = db_manager.get_job_pages(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    return render_template('job_details.html', job=job, pages=pages, user=user)


@app.route('/api/job/<int:job_id>/progress')
@login_required
def get_job_progress(job_id):
    """API для получения прогресса задания"""
    user = get_current_user()

    # Проверяем права доступа
    if user['role'] != 'admin':
        job = db_manager.get_job_details(job_id, user['id'], False)
        if not job:
            return jsonify({'error': 'Задание не найдено'}), 404

    # Получаем информацию о прогрессе
    progress_info = active_jobs.get(job_id)

    if progress_info:
        # Задание активно
        return jsonify({
            'active': True,
            'status': progress_info['status'],
            'progress': progress_info['progress'],
            'current_url': progress_info.get('current_url', ''),
            'pages_processed': progress_info.get('pages_processed', 0),
            'total_pages': progress_info.get('total_pages', 0),
            'message': progress_info.get('message', ''),
            'started_at': progress_info['started_at'].strftime('%H:%M:%S') if progress_info.get('started_at') else '',
            'updated_at': progress_info.get('updated_at', datetime.now()).strftime('%H:%M:%S')
        })
    else:
        # Задание не активно, получаем статус из БД
        job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None,
                                         user['role'] == 'admin')
        if job:
            return jsonify({
                'active': False,
                'status': job['status'],
                'progress': 100 if job['status'] == 'completed' else 0,
                'message': f"Статус: {job['status']}"
            })
        else:
            return jsonify({'error': 'Задание не найдено'}), 404


@app.route('/api/jobs/active')
@login_required
def get_active_jobs():
    """API для получения списка активных заданий"""
    user = get_current_user()

    # Фильтруем активные задания по пользователю (если не админ)
    filtered_jobs = {}

    for job_id, job_info in active_jobs.items():
        # Проверяем права доступа к заданию
        if user['role'] == 'admin':
            filtered_jobs[job_id] = job_info
        else:
            # Проверяем, принадлежит ли задание пользователю
            job_details = db_manager.get_job_details(job_id, user['id'], False)
            if job_details:
                filtered_jobs[job_id] = job_info

    return jsonify(filtered_jobs)


@app.errorhandler(404)
def not_found_error(error):
    """Обработчик ошибки 404"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Обработчик ошибки 500"""
    logger.error(f"Внутренняя ошибка сервера: {error}")
    return render_template('500.html'), 500


if __name__ == '__main__':
    print("Запуск Flask-приложения...")
    logger.info("Flask-приложение запущено")
    app.run(debug=True, host='0.0.0.0', port=5000)