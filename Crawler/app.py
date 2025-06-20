from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import threading
import asyncio
import traceback
from datetime import datetime
import logging
import json
import tempfile
import os

from database import db_manager
from crawler import WebCrawler
from config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Создание Flask приложения
app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# Глобальный словарь для отслеживания прогресса заданий
job_progress = {}


def get_current_user():
    """Получение текущего пользователя из сессии"""
    if 'user_id' not in session:
        return None

    user = db_manager.get_user_by_id(session['user_id'])
    return user


def login_required(f):
    """Декоратор для проверки авторизации"""

    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходимо войти в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


def admin_required(f):
    """Декоратор для проверки прав администратора"""

    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or user['role'] != 'admin':
            flash('Недостаточно прав доступа', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


# Маршруты приложения

@app.route('/')
def index():
    """Главная страница - перенаправление на dashboard"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа в систему"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        logger.info(f"Попытка входа: {username}")

        if not username or not password:
            flash('Введите имя пользователя и пароль', 'error')
            return render_template('login.html')

        user = db_manager.verify_user(username, password)
        if user:
            session['user_id'] = user['id']
            logger.info(f"Успешный вход: {username} (ID: {user['id']}, роль: {user['role']})")
            flash(f'Добро пожаловать, {user["username"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    if 'user_id' in session:
        logger.info(f"Выход пользователя ID: {session['user_id']}")
    session.clear()
    flash('Вы успешно вышли из системы', 'info')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        logger.info(f"Попытка регистрации пользователя: {username}")

        if not username or not password:
            flash('Заполните все поля', 'error')
            return render_template('register.html')

        if len(username) < 3:
            flash('Имя пользователя должно содержать минимум 3 символа', 'error')
            return render_template('register.html')

        if len(password) < 4:
            flash('Пароль должен содержать минимум 4 символа', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html')

        success, message = db_manager.create_user(username, password)
        if success:
            flash('Регистрация успешна! Теперь вы можете войти в систему.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')

    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Панель управления - список заданий"""
    user = get_current_user()

    if user['role'] == 'admin':
        jobs = db_manager.get_all_jobs()
    else:
        jobs = db_manager.get_user_jobs(user['id'])

    # Добавляем информацию о количестве собранных страниц
    for job in jobs:
        if job.get('pages_crawled') is None:
            pages_count = db_manager.fetch_val(
                "SELECT COUNT(*) FROM crawled_pages WHERE job_id = %s",
                (job['id'],)
            )
            job['pages_crawled'] = pages_count or 0

    return render_template('dashboard.html', jobs=jobs, user=user)


@app.route('/create_job', methods=['GET', 'POST'])
@login_required
def create_job():
    """Создание нового задания на краулинг"""
    user = get_current_user()
    logger.info(f"create_job вызван пользователем: {user}")

    if request.method == 'POST':
        job_name = request.form.get('job_name', '').strip()
        start_url = request.form.get('start_url', '').strip()
        logger.info(f"Получены данные формы: job_name='{job_name}', start_url='{start_url}'")

        try:
            max_pages = int(request.form.get('max_pages', 10))
            max_depth = int(request.form.get('max_depth', 2))
            delay = float(request.form.get('delay', 1.0))
            logger.info(f"Параметры: max_pages={max_pages}, max_depth={max_depth}, delay={delay}")
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка преобразования параметров: {e}")
            flash('Ошибка в параметрах задания', 'error')
            return render_template('create_job.html')

        if not job_name or not start_url:
            flash('Необходимо заполнить все поля', 'error')
            return render_template('create_job.html')

        # Валидация URL
        if not start_url.startswith(('http://', 'https://')):
            flash('URL должен начинаться с http:// или https://', 'error')
            return render_template('create_job.html')

        # Валидация параметров
        if max_pages < 1 or max_pages > 1000:
            flash('Количество страниц должно быть от 1 до 1000', 'error')
            return render_template('create_job.html')

        if max_depth < 1 or max_depth > 10:
            flash('Глубина должна быть от 1 до 10', 'error')
            return render_template('create_job.html')

        if delay < 0 or delay > 10:
            flash('Задержка должна быть от 0 до 10 секунд', 'error')
            return render_template('create_job.html')

        try:
            # Создаем запись в БД
            job_id = db_manager.create_job(
                user['id'], job_name, start_url, max_pages, max_depth, delay
            )
            logger.info(f"Создано задание с ID: {job_id}")

            # Создаем краулер
            logger.info("Создание краулера...")
            crawler = WebCrawler(
                job_name=job_name,
                start_url=start_url,
                user_id=user['id'],
                max_pages=max_pages,
                delay=delay,
                max_depth=max_depth
            )
            crawler.job_id = job_id

            # Устанавливаем db_manager для краулера
            crawler.set_db_manager(db_manager)

            logger.info("Краулер создан успешно")

            # Запускаем краулер в отдельном потоке
            logger.info("Создание потока для краулера...")

            def run_crawler_thread():
                logger.info("Запуск краулера в потоке...")
                logger.info(f"Поток запущен: {threading.current_thread().name}")

                # Устанавливаем callback для отслеживания прогресса
                def progress_callback(**kwargs):
                    job_progress[job_id] = {
                        'active': True,
                        'job_id': job_id,
                        'updated_at': datetime.now().strftime('%H:%M:%S'),
                        **kwargs
                    }

                crawler.progress_callback = progress_callback

                # Создаем новый цикл событий для потока
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Запускаем краулинг
                    result = loop.run_until_complete(crawler.crawl())
                    logger.info(f"Краулер завершен успешно, результат: {result}")

                    # Помечаем задание как неактивное
                    if job_id in job_progress:
                        job_progress[job_id]['active'] = False

                except Exception as e:
                    logger.error(f"Ошибка в краулере: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")

                    # Обновляем статус на failed
                    try:
                        db_manager.update_job_status(job_id, 'failed')
                    except Exception as update_error:
                        logger.error(f"Ошибка обновления статуса: {update_error}")

                    # Помечаем задание как неактивное с ошибкой
                    if job_id in job_progress:
                        job_progress[job_id].update({
                            'active': False,
                            'status': 'failed',
                            'message': f'Ошибка: {str(e)}'
                        })
                finally:
                    logger.info("Закрытие цикла событий")
                    loop.close()

            # Запускаем поток
            thread = threading.Thread(target=run_crawler_thread, name=f"Crawler-{job_id}")
            thread.daemon = True
            thread.start()

            flash(f'Задание "{job_name}" запущено!', 'success')
            return redirect(url_for('job_details', job_id=job_id))

        except Exception as e:
            logger.error(f"Ошибка при создании задания: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            flash('Ошибка при создании задания', 'error')
            return render_template('create_job.html')

    return render_template('create_job.html')


@app.route('/job/<int:job_id>')
@login_required
def job_details(job_id):
    """Детали задания"""
    user = get_current_user()

    # Получаем детали задания
    job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    if not job:
        flash('Задание не найдено', 'error')
        return redirect(url_for('dashboard'))

    # Получаем страницы задания
    pages = db_manager.get_job_pages(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    return render_template('job_details.html', job=job, pages=pages, user=user)


@app.route('/job/<int:job_id>/delete', methods=['POST'])
@login_required
def delete_job(job_id):
    """Удаление задания"""
    user = get_current_user()

    # Проверяем права доступа к заданию
    job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    if not job:
        flash('Задание не найдено', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Удаляем задание
        success = db_manager.delete_job(job_id, user['id'] if user['role'] != 'admin' else None,
                                        user['role'] == 'admin')

        if success:
            flash(f'Задание "{job["job_name"]}" успешно удалено', 'success')
            logger.info(f"Пользователь {user['username']} удалил задание {job_id}")

            # Удаляем информацию о прогрессе, если есть
            if job_id in job_progress:
                del job_progress[job_id]
        else:
            flash('Ошибка при удалении задания', 'error')

    except Exception as e:
        logger.error(f"Ошибка удаления задания {job_id}: {e}")
        flash('Ошибка при удалении задания', 'error')

    return redirect(url_for('dashboard'))


@app.route('/job/<int:job_id>/export')
@login_required
def export_job_data(job_id):
    """Экспорт данных задания в JSON"""
    user = get_current_user()

    # Проверяем права доступа к заданию
    job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    if not job:
        flash('Задание не найдено', 'error')
        return redirect(url_for('dashboard'))

    # Проверяем, что задание завершено
    if job['status'] != 'completed':
        flash('Экспорт доступен только для завершенных заданий', 'warning')
        return redirect(url_for('job_details', job_id=job_id))

    # Получаем все данные для экспорта
    try:
        logger.info(f"Начинаем экспорт данных для задания {job_id}")
        export_data = db_manager.get_job_export_data(job_id, user['id'] if user['role'] != 'admin' else None,
                                                     user['role'] == 'admin')

        if not export_data:
            flash('Нет данных для экспорта', 'warning')
            return redirect(url_for('job_details', job_id=job_id))

        logger.info(f"Получены данные для экспорта: {len(export_data.get('pages', []))} страниц")

        # Конвертируем datetime объекты в строки для job_info
        job_info = {}
        for key, value in export_data['job'].items():
            if key in ['created_at', 'started_at', 'finished_at'] and value:
                if hasattr(value, 'isoformat'):
                    job_info[key] = value.isoformat()
                else:
                    job_info[key] = str(value)
            else:
                job_info[key] = value

        # Формируем JSON структуру
        json_data = {
            "export_info": {
                "exported_at": datetime.now().isoformat(),
                "exported_by": user['username'],
                "crawler_version": "1.0",
                "job_id": job_id
            },
            "job_info": {
                "id": job_info['id'],
                "name": job_info['job_name'],
                "start_url": job_info['start_url'],
                "status": job_info['status'],
                "created_at": job_info.get('created_at'),
                "started_at": job_info.get('started_at'),
                "finished_at": job_info.get('finished_at'),
                "username": job_info.get('username'),
                "parameters": {
                    "max_pages": job_info['max_pages'],
                    "max_depth": job_info['max_depth'],
                    "delay": float(job_info['delay'])
                },
                "statistics": {
                    "total_pages_crawled": len(export_data['pages']),
                    "total_links_found": sum(len(page.get('links', [])) for page in export_data['pages']),
                    "total_words": sum(page.get('content', {}).get('word_count', 0) for page in export_data['pages']),
                    "average_words_per_page": round(
                        sum(page.get('content', {}).get('word_count', 0) for page in export_data['pages']) / len(
                            export_data['pages'])) if export_data['pages'] else 0
                }
            },
            "crawled_data": {
                "pages": export_data['pages'],
                "links": export_data['links']
            }
        }

        # Создаем временный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as temp_file:
            json.dump(json_data, temp_file, ensure_ascii=False, indent=2)
            temp_file_path = temp_file.name

        # Формируем имя файла для скачивания
        safe_job_name = "".join(c for c in job['job_name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_job_name:
            safe_job_name = "crawl_job"

        filename = f"crawl_data_{safe_job_name}_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        logger.info(f"Экспорт завершен, файл: {filename}, размер: {os.path.getsize(temp_file_path)} bytes")

        # Планируем удаление временного файла
        def remove_temp_file():
            try:
                import time
                time.sleep(30)  # Ждем 30 секунд перед удалением
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    logger.info(f"Временный файл {temp_file_path} удален")
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {temp_file_path}: {e}")

        # Запускаем удаление в отдельном потоке
        cleanup_thread = threading.Thread(target=remove_temp_file)
        cleanup_thread.daemon = True
        cleanup_thread.start()

        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )

    except Exception as e:
        logger.error(f"Ошибка экспорта данных для задания {job_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash('Ошибка при экспорте данных. Попробуйте позже.', 'error')
        return redirect(url_for('job_details', job_id=job_id))


@app.route('/job/<int:job_id>/export/preview')
@login_required
def preview_export_data(job_id):
    """Предварительный просмотр данных для экспорта"""
    user = get_current_user()

    # Проверяем права доступа к заданию
    job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    if not job:
        return jsonify({'error': 'Задание не найдено'}), 404

    if job['status'] != 'completed':
        return jsonify({'error': 'Превью доступно только для завершенных заданий'}), 400

    try:
        logger.info(f"Получение превью для задания {job_id}")
        export_data = db_manager.get_job_export_data(job_id, user['id'] if user['role'] != 'admin' else None,
                                                     user['role'] == 'admin')

        if not export_data:
            return jsonify({'error': 'Нет данных для экспорта'}), 404

        # Безопасный расчет размера без сериализации datetime объектов
        sample_data_for_size = {
            "job": export_data['job'],
            "pages_count": len(export_data['pages']),
            "links_count": len(export_data['links']),
            "sample_page": export_data['pages'][0] if export_data['pages'] else {}
        }

        try:
            estimated_size_kb = len(json.dumps(sample_data_for_size, ensure_ascii=False)) / 1024
            # Примерно умножаем на количество страниц для оценки
            if export_data['pages']:
                estimated_size_kb *= len(export_data['pages'])
            data_size_estimate = f"{estimated_size_kb:.1f} KB"
        except Exception as size_error:
            logger.warning(f"Не удалось рассчитать размер файла: {size_error}")
            data_size_estimate = "Не удалось определить"

        # Обрабатываем created_at для отображения
        created_at_str = None
        if export_data['job'].get('created_at'):
            if isinstance(export_data['job']['created_at'], str):
                created_at_str = export_data['job']['created_at']
            elif hasattr(export_data['job']['created_at'], 'isoformat'):
                created_at_str = export_data['job']['created_at'].isoformat()
            else:
                created_at_str = str(export_data['job']['created_at'])

        # Формируем превью (ограниченную версию)
        preview_data = {
            "job_info": {
                "name": export_data['job']['job_name'],
                "status": export_data['job']['status'],
                "total_pages": len(export_data['pages']),
                "total_links": sum(len(page.get('links', [])) for page in export_data['pages']),
                "created_at": created_at_str
            },
            "sample_pages": export_data['pages'][:3] if export_data['pages'] else [],  # Только первые 3 страницы
            "data_size_estimate": data_size_estimate
        }

        logger.info(f"Превью подготовлено для задания {job_id}")
        return jsonify(preview_data)

    except Exception as e:
        logger.error(f"Ошибка предварительного просмотра для задания {job_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'Ошибка получения данных для превью'}), 500


# API для отслеживания прогресса
@app.route('/api/job/<int:job_id>/progress')
@login_required
def get_job_progress(job_id):
    """API для получения прогресса задания"""
    user = get_current_user()

    # Проверяем права доступа к заданию
    job = db_manager.get_job_details(job_id, user['id'] if user['role'] != 'admin' else None, user['role'] == 'admin')

    if not job:
        return jsonify({'error': 'Задание не найдено'}), 404

    # Проверяем, есть ли информация о прогрессе
    if job_id in job_progress:
        progress_data = job_progress[job_id].copy()
        return jsonify(progress_data)

    # Если нет активного прогресса, возвращаем статус из БД
    return jsonify({
        'active': False,
        'job_id': job_id,
        'status': job['status'],
        'progress': 100 if job['status'] == 'completed' else 0,
        'message': f'Задание {job["status"]}'
    })


# Административные маршруты
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    """Административная панель"""
    users = db_manager.get_all_users()
    jobs = db_manager.get_all_jobs()

    return render_template('admin_panel.html', users=users, jobs=jobs)


@app.route('/admin/toggle_role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_toggle_role(user_id):
    """Изменение роли пользователя (user <-> admin)"""
    current_user = get_current_user()

    if user_id == current_user['id']:
        flash('Нельзя изменить свою собственную роль', 'error')
        return redirect(url_for('admin_panel'))

    user_to_change = db_manager.get_user_by_id(user_id)
    if not user_to_change:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('admin_panel'))

    # Определяем новую роль
    new_role = 'admin' if user_to_change['role'] == 'user' else 'user'

    try:
        success = db_manager.update_user_role(user_id, new_role)
        if success:
            action = 'назначен администратором' if new_role == 'admin' else 'снят с должности администратора'
            flash(f'Пользователь {user_to_change["username"]} {action}', 'success')
            logger.info(
                f"Администратор {current_user['username']} изменил роль пользователя {user_to_change['username']} на {new_role}")
        else:
            flash('Ошибка изменения роли пользователя', 'error')
    except Exception as e:
        logger.error(f"Ошибка изменения роли пользователя {user_id}: {e}")
        flash('Ошибка изменения роли пользователя', 'error')

    return redirect(url_for('admin_panel'))
@app.route('/admin/create_user', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    """Создание пользователя администратором"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'user')

    if not username or not password:
        flash('Заполните все поля', 'error')
        return redirect(url_for('admin_panel'))

    if role not in ['user', 'admin']:
        flash('Неверная роль пользователя', 'error')
        return redirect(url_for('admin_panel'))

    success, message = db_manager.create_user(username, password, role)
    if success:
        flash(f'Пользователь {username} создан с ролью {role}', 'success')
    else:
        flash(message, 'error')

    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Удаление пользователя администратором"""
    current_user = get_current_user()

    if user_id == current_user['id']:
        flash('Нельзя удалить самого себя', 'error')
        return redirect(url_for('admin_panel'))

    user_to_delete = db_manager.get_user_by_id(user_id)
    if not user_to_delete:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('admin_panel'))

    if user_to_delete['role'] == 'admin':
        flash('Нельзя удалить администратора', 'error')
        return redirect(url_for('admin_panel'))

    success = db_manager.delete_user(user_id)
    if success:
        flash(f'Пользователь {user_to_delete["username"]} удален', 'success')
    else:
        flash('Ошибка удаления пользователя', 'error')

    return redirect(url_for('admin_panel'))


# Обработчики ошибок
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error_code=404, error_message='Страница не найдена'), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Внутренняя ошибка сервера: {error}")
    return render_template('error.html', error_code=500, error_message='Внутренняя ошибка сервера'), 500


if __name__ == '__main__':
    logger.info("Запуск Flask-приложения...")

    try:
        # Проверяем подключение к базе данных
        test_user = db_manager.get_user_by_id(1)
        logger.info("Подключение к базе данных успешно")
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        exit(1)

    logger.info("Flask-приложение запущено")
    app.run(host='0.0.0.0', port=5000, debug=True)