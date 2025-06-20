import psycopg2
import psycopg2.extras
import bcrypt
import json
from typing import List, Dict, Optional, Tuple
from config import Config
import threading
from contextlib import contextmanager
import logging

# Создаем собственный логгер для database.py
logger = logging.getLogger(__name__)


class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            self.config = {
                'dbname': Config.DATABASE_CONFIG['database'],
                'user': Config.DATABASE_CONFIG['user'],
                'password': Config.DATABASE_CONFIG['password'],
                'host': Config.DATABASE_CONFIG['host'],
                'port': Config.DATABASE_CONFIG['port']
            }
            self._initialized = True
            self._create_default_admin()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения с базой данных"""
        conn = None
        try:
            conn = psycopg2.connect(**self.config)
            conn.autocommit = True
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def _create_default_admin(self):
        """Создание администратора по умолчанию"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем, есть ли уже администратор
                cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
                admin_exists = cursor.fetchone()

                if not admin_exists:
                    # Создаем администратора с паролем 'admin'
                    password_hash = bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        ('admin', password_hash, 'admin')
                    )
                    print("Создан администратор по умолчанию: admin/admin")

        except Exception as e:
            print(f"Ошибка создания администратора по умолчанию: {e}")

    def execute_query(self, query: str, params: tuple = None) -> str:
        """Выполнение запроса"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.statusmessage

    def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Получение одной записи"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            return dict(result) if result else None

    def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Получение всех записей"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            return [dict(row) for row in results]

    def fetch_val(self, query: str, params: tuple = None):
        """Получение одного значения"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            return result[0] if result else None

    # Методы для работы с пользователями
    def create_user(self, username: str, password: str, role: str = 'user') -> Tuple[bool, str]:
        """Создание нового пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем, существует ли пользователь
                cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
                existing_user = cursor.fetchone()

                if existing_user:
                    return False, "Пользователь с таким именем уже существует"

                # Создаем хеш пароля
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                # Вставляем пользователя
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username.lower(), password_hash, role)
                )

                logger.info(f"Создан пользователь: {username} с ролью {role}")
                return True, "Пользователь успешно создан"

        except psycopg2.IntegrityError as e:
            logger.error(f"Ошибка целостности при создании пользователя: {e}")
            return False, "Пользователь с таким именем уже существует"
        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            return False, f"Ошибка создания пользователя: {str(e)}"

    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Проверка пользователя при входе"""
        try:
            user = self.fetch_one(
                "SELECT id, username, password_hash, role FROM users WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )

            if not user:
                logger.warning(f"Пользователь {username} не найден")
                return None

            # Проверяем пароль
            if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                logger.info(f"Успешный вход пользователя: {username}")
                return {
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role']
                }
            else:
                logger.warning(f"Неверный пароль для пользователя: {username}")
                return None

        except Exception as e:
            logger.error(f"Ошибка проверки пользователя: {e}")
            return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Получение пользователя по ID"""
        try:
            return self.fetch_one(
                "SELECT id, username, role, created_at FROM users WHERE id = %s",
                (user_id,)
            )
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None

    def get_all_users(self) -> List[Dict]:
        """Получение всех пользователей (для админа)"""
        try:
            return self.fetch_all(
                "SELECT id, username, role, created_at FROM users ORDER BY created_at DESC"
            )
        except Exception as e:
            logger.error(f"Ошибка получения пользователей: {e}")
            return []

    def delete_user(self, user_id: int) -> bool:
        """Удаление пользователя"""
        try:
            # Проверяем, что это не администратор
            user = self.fetch_one("SELECT role FROM users WHERE id = %s", (user_id,))
            if user and user['role'] == 'admin':
                logger.warning("Попытка удалить администратора")
                return False

            result = self.execute_query("DELETE FROM users WHERE id = %s", (user_id,))
            return "DELETE 1" in result
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя: {e}")
            return False

    # Методы для работы с заданиями краулера
    def create_job(self, user_id: int, job_name: str, start_url: str, max_pages: int,
                   max_depth: int, delay: float, status: str = 'running') -> int:
        """Создание нового задания на краулинг"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO crawl_jobs 
                    (user_id, job_name, start_url, max_pages, max_depth, delay, status, started_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) 
                    RETURNING id
                """, (user_id, job_name, start_url, max_pages, max_depth, delay, status))

                job_id = cursor.fetchone()[0]
                logger.info(f"Создано новое задание с ID: {job_id}")
                return job_id
        except Exception as e:
            logger.error(f"Ошибка создания задания: {e}")
            raise

    def update_job_status(self, job_id: int, status: str):
        """Обновление статуса задания"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE crawl_jobs SET status = %s, 
                    finished_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE finished_at END
                    WHERE id = %s
                """, (status, status, job_id))
                logger.info(f"Обновлен статус задания {job_id} на {status}")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса задания: {e}")

    def save_page(self, job_id: int, url: str, title: str, depth: int, status_code: int,
                  metadata: dict, content: dict) -> int:
        """Сохранение данных страницы в БД"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO crawled_pages 
                    (job_id, url, title, depth, status_code, metadata, content) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s) 
                    RETURNING id
                """, (job_id, url, title, depth, status_code,
                      json.dumps(metadata, ensure_ascii=False),
                      json.dumps(content, ensure_ascii=False)))

                page_id = cursor.fetchone()[0]
                return page_id
        except Exception as e:
            logger.error(f"Ошибка сохранения страницы {url}: {e}")
            raise

    def save_links(self, job_id: int, page_id: int, links: list, link_texts: dict = None):
        """Сохранение ссылок со страницы в БД"""
        if not links:
            return

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Подготавливаем данные для вставки
                insert_data = []
                for link in links:
                    link_text = link_texts.get(link, "") if link_texts else ""
                    insert_data.append((job_id, page_id, link, link_text))

                # Выполняем массовую вставку
                cursor.executemany("""
                    INSERT INTO links (job_id, from_page_id, to_url, link_text)
                    VALUES (%s, %s, %s, %s)
                """, insert_data)

        except Exception as e:
            logger.error(f"Ошибка сохранения ссылок: {e}")

    def get_user_jobs(self, user_id: int) -> List[Dict]:
        """Получение заданий пользователя"""
        try:
            return self.fetch_all("""
                SELECT id, job_name, start_url, max_pages, max_depth, delay, 
                       status, created_at, started_at, finished_at
                FROM crawl_jobs 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            """, (user_id,))
        except Exception as e:
            logger.error(f"Ошибка получения заданий пользователя: {e}")
            return []

    def get_all_jobs(self) -> List[Dict]:
        """Получение всех заданий (для админа)"""
        try:
            return self.fetch_all("""
                SELECT cj.id, cj.job_name, cj.start_url, cj.max_pages, cj.max_depth, 
                       cj.delay, cj.status, cj.created_at, cj.started_at, cj.finished_at,
                       u.username
                FROM crawl_jobs cj
                JOIN users u ON cj.user_id = u.id
                ORDER BY cj.created_at DESC
            """)
        except Exception as e:
            logger.error(f"Ошибка получения всех заданий: {e}")
            return []

    def get_job_details(self, job_id: int, user_id: int = None, is_admin: bool = False) -> Optional[Dict]:
        """Получение деталей задания"""
        try:
            if is_admin:
                return self.fetch_one("""
                    SELECT cj.*, u.username,
                           COUNT(cp.id) as pages_crawled
                    FROM crawl_jobs cj
                    JOIN users u ON cj.user_id = u.id
                    LEFT JOIN crawled_pages cp ON cj.id = cp.job_id
                    WHERE cj.id = %s
                    GROUP BY cj.id, u.username
                """, (job_id,))
            else:
                return self.fetch_one("""
                    SELECT cj.*,
                           COUNT(cp.id) as pages_crawled
                    FROM crawl_jobs cj
                    LEFT JOIN crawled_pages cp ON cj.id = cp.job_id
                    WHERE cj.id = %s AND cj.user_id = %s
                    GROUP BY cj.id
                """, (job_id, user_id))
        except Exception as e:
            logger.error(f"Ошибка получения деталей задания: {e}")
            return None

    def get_job_pages(self, job_id: int, user_id: int = None, is_admin: bool = False) -> List[Dict]:
        """Получение страниц задания"""
        try:
            if not is_admin:
                # Проверяем, что задание принадлежит пользователю
                if not self.fetch_val("SELECT id FROM crawl_jobs WHERE id = %s AND user_id = %s", (job_id, user_id)):
                    return []

            pages = self.fetch_all("""
                SELECT id, url, title, depth, status_code, crawled_at, metadata, content
                FROM crawled_pages 
                WHERE job_id = %s 
                ORDER BY crawled_at DESC
                LIMIT 100
            """, (job_id,))

            # Обрабатываем данные для отображения
            processed_pages = []
            for page in pages:
                try:
                    # Извлекаем word_count и links_count из content
                    if isinstance(page['content'], str):
                        content = json.loads(page['content']) if page['content'] else {}
                    elif isinstance(page['content'], dict):
                        content = page['content']
                    else:
                        content = {}

                    # Подсчитываем количество ссылок для этой страницы
                    links_count = self.fetch_val("""
                        SELECT COUNT(*) FROM links WHERE job_id = %s AND from_page_id = %s
                    """, (job_id, page['id'])) or 0

                    processed_page = dict(page)
                    processed_page['word_count'] = content.get('word_count', 0)
                    processed_page['links_count'] = links_count
                    processed_pages.append(processed_page)

                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Ошибка обработки данных страницы {page['id']}: {e}")
                    # Добавляем страницу с базовыми данными
                    processed_page = dict(page)
                    processed_page['word_count'] = 0
                    processed_page['links_count'] = 0
                    processed_pages.append(processed_page)

            return processed_pages

        except Exception as e:
            logger.error(f"Ошибка получения страниц задания: {e}")
            return []

    def get_job_export_data(self, job_id: int, user_id: int = None, is_admin: bool = False) -> Optional[Dict]:
        """Получение полных данных задания для экспорта"""
        try:
            # Проверяем права доступа
            if not is_admin and user_id:
                job_check = self.fetch_val("SELECT id FROM crawl_jobs WHERE id = %s AND user_id = %s",
                                           (job_id, user_id))
                if not job_check:
                    return None

            # Получаем информацию о задании
            if is_admin:
                job = self.fetch_one("""
                    SELECT cj.*, u.username
                    FROM crawl_jobs cj
                    JOIN users u ON cj.user_id = u.id
                    WHERE cj.id = %s
                """, (job_id,))
            else:
                job = self.fetch_one("""
                    SELECT cj.*, u.username
                    FROM crawl_jobs cj
                    JOIN users u ON cj.user_id = u.id
                    WHERE cj.id = %s AND cj.user_id = %s
                """, (job_id, user_id))

            if not job:
                return None

            # Конвертируем datetime объекты в строки для job
            job_data = dict(job)
            for field in ['created_at', 'started_at', 'finished_at']:
                if job_data.get(field) and hasattr(job_data[field], 'isoformat'):
                    job_data[field] = job_data[field].isoformat()

            # Получаем все страницы с их данными
            pages = self.fetch_all("""
                SELECT 
                    id,
                    url,
                    title,
                    depth,
                    status_code,
                    metadata,
                    content,
                    crawled_at
                FROM crawled_pages 
                WHERE job_id = %s 
                ORDER BY crawled_at ASC
            """, (job_id,))

            # Обрабатываем данные страниц
            processed_pages = []
            for page in pages:
                try:
                    # Обрабатываем JSON поля - проверяем тип данных
                    if isinstance(page['metadata'], str):
                        metadata = json.loads(page['metadata']) if page['metadata'] else {}
                    elif isinstance(page['metadata'], dict):
                        metadata = page['metadata']
                    else:
                        metadata = {}

                    if isinstance(page['content'], str):
                        content = json.loads(page['content']) if page['content'] else {}
                    elif isinstance(page['content'], dict):
                        content = page['content']
                    else:
                        content = {}

                    # Получаем ссылки для этой страницы
                    page_links = self.fetch_all("""
                        SELECT to_url, link_text
                        FROM links 
                        WHERE job_id = %s AND from_page_id = %s
                        ORDER BY id
                    """, (job_id, page['id']))

                    # Конвертируем datetime в строку
                    crawled_at_str = None
                    if page['crawled_at'] and hasattr(page['crawled_at'], 'isoformat'):
                        crawled_at_str = page['crawled_at'].isoformat()
                    elif page['crawled_at']:
                        crawled_at_str = str(page['crawled_at'])

                    processed_page = {
                        "id": page['id'],
                        "url": page['url'],
                        "title": page['title'] or "",
                        "depth": page['depth'],
                        "status_code": page['status_code'],
                        "crawled_at": crawled_at_str,
                        "metadata": metadata,
                        "content": content,
                        "links": [
                            {
                                "url": link['to_url'],
                                "text": link['link_text'] or ""
                            }
                            for link in page_links
                        ]
                    }
                    processed_pages.append(processed_page)

                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Ошибка обработки данных для страницы {page['id']}: {e}")
                    # Добавляем страницу с базовыми данными
                    crawled_at_str = None
                    if page['crawled_at'] and hasattr(page['crawled_at'], 'isoformat'):
                        crawled_at_str = page['crawled_at'].isoformat()
                    elif page['crawled_at']:
                        crawled_at_str = str(page['crawled_at'])

                    processed_pages.append({
                        "id": page['id'],
                        "url": page['url'],
                        "title": page['title'] or "",
                        "depth": page['depth'],
                        "status_code": page['status_code'],
                        "crawled_at": crawled_at_str,
                        "metadata": {},
                        "content": {
                            "content_text": "",
                            "word_count": 0,
                            "char_count": 0,
                            "links_count": 0,
                            "images_count": 0,
                            "forms_count": 0,
                            "paragraphs_count": 0
                        },
                        "links": [],
                        "error": f"Ошибка обработки данных: {str(e)}"
                    })

            # Получаем все ссылки задания (общий граф)
            all_links = self.fetch_all("""
                SELECT 
                    cp.url as from_url,
                    l.to_url,
                    l.link_text,
                    cp.depth as from_depth
                FROM links l
                JOIN crawled_pages cp ON l.from_page_id = cp.id
                WHERE l.job_id = %s
                ORDER BY cp.depth, cp.url, l.to_url
            """, (job_id,))

            return {
                "job": job_data,  # Используем обработанные данные с конвертированными datetime
                "pages": processed_pages,
                "links": [dict(link) for link in all_links]
            }

        except Exception as e:
            logger.error(f"Ошибка получения данных для экспорта задания {job_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def update_user_role(self, user_id: int, new_role: str) -> bool:
        """Изменение роли пользователя"""
        try:
            if new_role not in ['user', 'admin']:
                logger.error(f"Недопустимая роль: {new_role}")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET role = %s WHERE id = %s",
                    (new_role, user_id)
                )

                if cursor.rowcount > 0:
                    logger.info(f"Роль пользователя {user_id} изменена на {new_role}")
                    return True
                else:
                    logger.warning(f"Пользователь {user_id} не найден для изменения роли")
                    return False

        except Exception as e:
            logger.error(f"Ошибка изменения роли пользователя {user_id}: {e}")
            return False

    def delete_job(self, job_id: int, user_id: int = None, is_admin: bool = False) -> bool:
        """Удаление задания и всех связанных данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем права доступа
                if not is_admin and user_id:
                    cursor.execute("SELECT user_id FROM crawl_jobs WHERE id = %s", (job_id,))
                    job_owner = cursor.fetchone()
                    if not job_owner or job_owner[0] != user_id:
                        logger.warning(f"Попытка удаления чужого задания {job_id} пользователем {user_id}")
                        return False

                # Удаляем связанные данные в правильном порядке (из-за внешних ключей)

                # 1. Удаляем ссылки
                cursor.execute("DELETE FROM links WHERE job_id = %s", (job_id,))
                links_deleted = cursor.rowcount

                # 2. Удаляем страницы
                cursor.execute("DELETE FROM crawled_pages WHERE job_id = %s", (job_id,))
                pages_deleted = cursor.rowcount

                # 3. Удаляем само задание
                cursor.execute("DELETE FROM crawl_jobs WHERE id = %s", (job_id,))
                job_deleted = cursor.rowcount

                if job_deleted > 0:
                    logger.info(f"Удалено задание {job_id}: {pages_deleted} страниц, {links_deleted} ссылок")
                    return True
                else:
                    logger.warning(f"Задание {job_id} не найдено для удаления")
                    return False

        except Exception as e:
            logger.error(f"Ошибка удаления задания {job_id}: {e}")
            return False

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()