from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import threading
import asyncio
import traceback
from datetime import datetime
import logging
import json
import tempfile
import os

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
        import tempfile
        import os

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
        else:
            flash('Ошибка при удалении задания', 'error')

    except Exception as e:
        logger.error(f"Ошибка удаления задания {job_id}: {e}")
        flash('Ошибка при удалении задания', 'error')

    return redirect(url_for('dashboard'))

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