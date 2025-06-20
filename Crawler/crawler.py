# Импорты для асинхронной работы и HTTP-запросов
import asyncio
import traceback

import aiohttp
import logging
import json
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from urllib.parse import urljoin, urlparse, unquote
from urllib.robotparser import RobotFileParser
from datetime import datetime
import os
from typing import Set, Dict, Optional, Tuple, List, Callable
import re
import sys
import time

from config import Config

# Настройка для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WebCrawler:
    """
    Веб-краулер для сбора данных с веб-страниц.
    Поддерживает асинхронный обход, проверку robots.txt,
    ограничение глубины и сохранение в PostgreSQL.
    """

    def __init__(
            self,
            job_name: str,
            start_url: str,
            user_id: int = 1,
            max_pages: int = 100,
            delay: float = 1.0,
            max_depth: int = 3,
            max_retries: int = 3,
            user_agent: str = "MyCrawler/1.0"
    ):
        """
        Инициализация краулера

        Args:
            job_name: Название задания
            start_url: Начальный URL для краулинга
            user_id: ID пользователя
            max_pages: Максимальное количество страниц
            delay: Задержка между запросами в секундах
            max_depth: Максимальная глубина обхода
            max_retries: Количество попыток при ошибках
            user_agent: User-Agent для запросов
        """
        self.job_name = job_name
        self.start_url = start_url
        self.user_id = user_id
        self.max_pages = max_pages
        self.delay = delay
        self.max_depth = max_depth
        self.max_retries = max_retries
        self.user_agent = user_agent

        # Инициализация базовых параметров
        self.visited_urls: Set[str] = set()
        self.ua = UserAgent()
        self.domain = urlparse(start_url).netloc
        self.robots_parser = RobotFileParser()
        self.session: Optional[aiohttp.ClientSession] = None
        self.job_id: Optional[int] = None
        self.progress_callback: Optional[Callable] = None
        self.db_manager = None  # Будет установлен извне

        # Статистика
        self.stats = {
            'pages_processed': 0,
            'pages_successful': 0,
            'pages_failed': 0,
            'links_found': 0,
            'start_time': None,
            'end_time': None
        }

        # Загрузка и парсинг robots.txt
        self._init_robots_parser()

    def set_db_manager(self, db_manager):
        """Установка менеджера базы данных"""
        self.db_manager = db_manager

    def _init_robots_parser(self):
        """Инициализация парсера robots.txt"""
        try:
            self.robots_parser.set_url(urljoin(self.start_url, "/robots.txt"))
            self.robots_parser.read()
            logger.info(f"Robots.txt загружен для {self.domain}")
        except Exception as e:
            logger.warning(f"Не удалось прочитать robots.txt для {self.domain}: {str(e)}")

    async def init_db_pool(self):
        """Заглушка для совместимости - база данных уже инициализирована"""
        logger.info("База данных уже инициализирована")

    async def close(self):
        """Закрытие всех соединений"""
        if self.session:
            await self.session.close()
            logger.info("HTTP сессия закрыта")

    def get_headers(self) -> Dict:
        """Генерация HTTP-заголовков для запроса"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def allowed_by_robots(self, url: str) -> bool:
        """Проверка разрешения на обход URL согласно robots.txt"""
        try:
            return self.robots_parser.can_fetch(self.user_agent, url)
        except Exception as e:
            logger.error(f"Ошибка проверки robots.txt для {url}: {str(e)}")
            return True  # Разрешаем в случае ошибки

    async def fetch_page(self, url: str) -> Tuple[Optional[str], int]:
        """
        Получение содержимого страницы с поддержкой повторных попыток
        и обработкой ошибок
        """
        for attempt in range(self.max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with self.session.get(
                        url,
                        headers=self.get_headers(),
                        timeout=timeout,
                        allow_redirects=True
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.debug(f"Успешно получена страница {url} (размер: {len(content)} символов)")
                        return content, response.status
                    elif response.status == 429:  # Too Many Requests
                        delay = min(60, 2 ** (attempt + 1))  # Максимум 60 секунд
                        logger.warning(f"Превышен лимит запросов для {url}. Повтор через {delay} сек...")
                        await asyncio.sleep(delay)
                    elif response.status in [301, 302, 303, 307, 308]:
                        # Редиректы уже обрабатываются автоматически с allow_redirects=True
                        logger.warning(f"Редирект {response.status} для {url}")
                        return None, response.status
                    else:
                        logger.warning(f"HTTP {response.status} для {url}")
                        return None, response.status

            except asyncio.TimeoutError:
                logger.warning(f"Таймаут при запросе {url} (попытка {attempt + 1})")
                if attempt == self.max_retries - 1:
                    return None, 0
                await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                logger.warning(f"Ошибка клиента при запросе {url}: {str(e)} (попытка {attempt + 1})")
                if attempt == self.max_retries - 1:
                    return None, 0
                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Неожиданная ошибка при запросе {url}: {str(e)} (попытка {attempt + 1})")
                if attempt == self.max_retries - 1:
                    return None, 0
                await asyncio.sleep(2 ** attempt)

        return None, 0

    async def create_job(self) -> int:
        """Создание нового задания на краулинг в БД"""
        try:
            if self.job_id:
                # Задание уже создано
                return self.job_id

            if not self.db_manager:
                raise Exception("DatabaseManager не установлен")

            job_id = self.db_manager.create_job(
                self.user_id,
                self.job_name,
                self.start_url,
                self.max_pages,
                self.max_depth,
                self.delay
            )
            logger.info(f"Создано новое задание с ID: {job_id}")
            return job_id
        except Exception as e:
            logger.error(f"Ошибка создания задания: {str(e)}")
            raise

    async def update_job_status(self, status: str):
        """Обновление статуса задания"""
        try:
            if self.job_id and self.db_manager:
                self.db_manager.update_job_status(self.job_id, status)
                logger.info(f"Обновлен статус задания {self.job_id} на {status}")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса задания: {str(e)}")

    async def save_page(self, url: str, title: str, depth: int, status_code: int,
                        metadata: dict, content: dict, headings: dict) -> int:
        """Сохранение данных страницы в БД"""
        # Объединяем мета-теги и заголовки в один JSON для метаданных
        metadata_json = {
            **metadata,
            'headings': headings
        }

        try:
            if not self.db_manager:
                raise Exception("DatabaseManager не установлен")

            page_id = self.db_manager.save_page(
                self.job_id,
                url,
                title,
                depth,
                status_code,
                metadata_json,
                content
            )
            logger.debug(f"Сохранена страница с ID: {page_id}")
            return page_id
        except Exception as e:
            logger.error(f"Ошибка сохранения страницы {url}: {str(e)}")
            raise

    async def save_links(self, page_id: int, links: List[str], link_texts: Dict[str, str] = None):
        """Сохранение ссылок со страницы в БД"""
        if not links:
            return

        try:
            if not self.db_manager:
                raise Exception("DatabaseManager не установлен")

            self.db_manager.save_links(self.job_id, page_id, links, link_texts)
            logger.debug(f"Сохранено {len(links)} ссылок для страницы {page_id}")
            self.stats['links_found'] += len(links)
        except Exception as e:
            logger.error(f"Ошибка сохранения ссылок: {str(e)}")

    def parse_metadata(self, soup: BeautifulSoup) -> Dict:
        """Извлечение мета-данных страницы"""
        meta = {
            'description': '',
            'keywords': '',
            'og_title': '',
            'og_description': '',
            'og_image': '',
            'og_url': '',
            'viewport': '',
            'charset': '',
            'author': '',
            'robots': ''
        }

        try:
            # Основные мета-теги
            description_tag = soup.find('meta', attrs={'name': 'description'})
            if description_tag and description_tag.get('content'):
                meta['description'] = description_tag.get('content', '')[:500]

            keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
            if keywords_tag and keywords_tag.get('content'):
                meta['keywords'] = keywords_tag.get('content', '')[:200]

            author_tag = soup.find('meta', attrs={'name': 'author'})
            if author_tag and author_tag.get('content'):
                meta['author'] = author_tag.get('content', '')[:100]

            robots_tag = soup.find('meta', attrs={'name': 'robots'})
            if robots_tag and robots_tag.get('content'):
                meta['robots'] = robots_tag.get('content', '')[:100]

            # Open Graph теги
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                meta['og_title'] = og_title.get('content', '')[:200]

            og_desc = soup.find('meta', property='og:description')
            if og_desc and og_desc.get('content'):
                meta['og_description'] = og_desc.get('content', '')[:500]

            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                meta['og_image'] = og_image.get('content', '')[:200]

            og_url = soup.find('meta', property='og:url')
            if og_url and og_url.get('content'):
                meta['og_url'] = og_url.get('content', '')[:200]

            # Viewport
            viewport = soup.find('meta', attrs={'name': 'viewport'})
            if viewport and viewport.get('content'):
                meta['viewport'] = viewport.get('content', '')[:200]

            # Charset
            charset = soup.find('meta', attrs={'charset': True})
            if charset:
                meta['charset'] = charset.get('charset', '')[:50]

        except Exception as e:
            logger.error(f"Ошибка парсинга метаданных: {str(e)}")

        return meta

    def parse_headings(self, soup: BeautifulSoup) -> Dict:
        """Извлечение всех заголовков страницы (h1-h6)"""
        headings = {f'h{i}': [] for i in range(1, 7)}

        try:
            for i in range(1, 7):
                for heading in soup.find_all(f'h{i}'):
                    text = heading.get_text().strip()
                    if text and len(text) <= 500:  # Ограничиваем длину заголовка
                        headings[f'h{i}'].append(text)

                # Ограничиваем количество заголовков каждого уровня
                headings[f'h{i}'] = headings[f'h{i}'][:20]

        except Exception as e:
            logger.error(f"Ошибка парсинга заголовков: {str(e)}")

        return headings

    def parse_content(self, soup: BeautifulSoup) -> Dict:
        """Извлечение основного текста страницы"""
        try:
            # Удаляем скрипты и стили
            for script in soup(["script", "style", "noscript"]):
                script.decompose()

            # Извлекаем текст из параграфов
            paragraphs = soup.find_all('p')
            text_parts = []

            for p in paragraphs:
                text = p.get_text().strip()
                if text and len(text) > 10:  # Исключаем очень короткие параграфы
                    text_parts.append(text)

            full_text = ' '.join(text_parts)
            full_text = re.sub(r'\s+', ' ', full_text)  # Удаление лишних пробелов

            # Подсчитываем различные элементы
            links_count = len(soup.find_all('a', href=True))
            images_count = len(soup.find_all('img'))
            forms_count = len(soup.find_all('form'))

            return {
                'content_text': full_text[:10000],  # Ограничение длины текста
                'word_count': len(full_text.split()) if full_text else 0,
                'char_count': len(full_text),
                'links_count': links_count,
                'images_count': images_count,
                'forms_count': forms_count,
                'paragraphs_count': len(text_parts)
            }

        except Exception as e:
            logger.error(f"Ошибка парсинга контента: {str(e)}")
            return {
                'content_text': '',
                'word_count': 0,
                'char_count': 0,
                'links_count': 0,
                'images_count': 0,
                'forms_count': 0,
                'paragraphs_count': 0
            }

    def extract_links(self, soup: BeautifulSoup, base_url: str) -> Tuple[List[str], Dict[str, str]]:
        """Извлечение ссылок со страницы"""
        links = []
        link_texts = {}

        try:
            for link in soup.find_all('a', href=True):
                try:
                    href = link['href']
                    if not href or href.startswith('#'):  # Пропускаем якоря
                        continue

                    # Преобразуем в абсолютный URL
                    absolute_url = urljoin(base_url, href)
                    decoded_url = unquote(absolute_url)
                    parsed_url = urlparse(decoded_url)

                    # Проверяем валидность URL
                    if not parsed_url.scheme or not parsed_url.netloc:
                        continue

                    # Очистка URL от якоря и некоторых параметров
                    clean_url = parsed_url._replace(
                        fragment="",
                        query=""
                    ).geturl()

                    # Проверка принадлежности к тому же домену
                    if (parsed_url.netloc == self.domain or
                            parsed_url.netloc.endswith('.' + self.domain)):

                        if clean_url not in links:  # Избегаем дубликатов
                            links.append(clean_url)

                            # Сохраняем текст ссылки
                            link_text = link.get_text().strip()
                            if link_text:
                                link_texts[clean_url] = link_text[:200]  # Ограничиваем длину
                            else:
                                # Если нет текста, пробуем title или alt
                                title_text = link.get('title', '').strip()
                                if title_text:
                                    link_texts[clean_url] = title_text[:200]

                except Exception as e:
                    logger.debug(f"Ошибка обработки ссылки {link.get('href', 'N/A')}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Ошибка извлечения ссылок: {str(e)}")

        return links, link_texts

    def parse_page(self, html: str, url: str) -> Optional[Tuple[Dict, Dict, Dict, Dict, List[str], Dict[str, str]]]:
        """
        Основной метод парсинга страницы.
        Возвращает кортеж из основных данных, метаданных, заголовков, контента, ссылок и текстов ссылок.
        """
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Основная информация
            title = ''
            if soup.title and soup.title.string:
                title = soup.title.string.strip()[:500]  # Ограничиваем длину заголовка

            # Сбор всех данных
            metadata = self.parse_metadata(soup)
            headings = self.parse_headings(soup)
            content = self.parse_content(soup)
            links, link_texts = self.extract_links(soup, url)

            # Основные данные для страницы
            page_data = {
                'url': unquote(url),
                'title': title,
            }

            return page_data, metadata, headings, content, links, link_texts

        except Exception as e:
            logger.error(f"Ошибка парсинга страницы {url}: {str(e)}")
            return None

    def update_progress(self, **kwargs):
        """Обновление прогресса через callback"""
        if self.progress_callback:
            try:
                self.progress_callback(**kwargs)
            except Exception as e:
                logger.error(f"Ошибка в callback прогресса: {e}")

    async def process_url(self, url: str, depth: int, queue: asyncio.Queue):
        """Обработка одной URL с учетом глубины и очереди"""
        try:
            # Обновляем прогресс - начинаем обработку URL
            self.update_progress(
                status='processing',
                current_url=url,
                pages_processed=self.stats['pages_processed'],
                progress=min(90, int((self.stats['pages_processed'] / self.max_pages) * 100)),
                message=f'Обработка: {url[:50]}...'
            )

            if not self.allowed_by_robots(url):
                logger.info(f"Пропуск {url} - запрещено robots.txt")
                return

            # Получаем содержимое страницы и статус ответа
            html, status_code = await self.fetch_page(url)

            if not html:
                logger.warning(f"Не удалось получить содержимое страницы: {url}")
                self.stats['pages_failed'] += 1
                return

            # Парсим страницу
            parsed_data = self.parse_page(html, url)
            if not parsed_data:
                logger.warning(f"Не удалось парсить страницу: {url}")
                self.stats['pages_failed'] += 1
                return

            page_data, metadata, headings, content, links, link_texts = parsed_data

            # Сохраняем данные страницы в БД
            page_id = await self.save_page(
                page_data['url'],
                page_data['title'],
                depth,
                status_code,
                metadata,
                content,
                headings
            )

            # Сохраняем найденные ссылки
            if links:
                await self.save_links(page_id, links, link_texts)

            # Обновляем статистику
            self.stats['pages_processed'] += 1
            self.stats['pages_successful'] += 1

            logger.info(
                f"Обработано: {url} (Глубина {depth}, Ссылок: {len(links)}, Слов: {content.get('word_count', 0)})")

            # Обновляем прогресс после обработки
            self.update_progress(
                pages_processed=self.stats['pages_processed'],
                progress=min(95, int((self.stats['pages_processed'] / self.max_pages) * 100)),
                message=f'Обработано {self.stats["pages_processed"]} из {self.max_pages} страниц'
            )

            # Добавление новых ссылок в очередь
            if depth < self.max_depth and len(self.visited_urls) < self.max_pages:
                new_links_added = 0
                for link in links:
                    if (link not in self.visited_urls and
                            len(self.visited_urls) < self.max_pages):
                        self.visited_urls.add(link)
                        await queue.put((link, depth + 1))
                        new_links_added += 1

                if new_links_added > 0:
                    logger.debug(f"Добавлено {new_links_added} новых ссылок в очередь")

        except Exception as e:
            logger.error(f"Ошибка обработки URL {url}: {str(e)}")
            self.stats['pages_failed'] += 1
            self.update_progress(
                message=f'Ошибка при обработке {url}: {str(e)}'
            )

    async def crawl(self):
        """
        Основной метод краулинга.
        Асинхронно обходит страницы с учетом ограничений.
        """
        try:
            self.stats['start_time'] = datetime.now()

            # Инициализируем соединение с базой данных (заглушка)
            await self.init_db_pool()

            # Создаем запись о задании (если не создана)
            if not self.job_id:
                self.job_id = await self.create_job()

            # Обновляем статус на 'running'
            await self.update_job_status('running')

            # Обновляем прогресс - начинаем краулинг
            self.update_progress(
                status='running',
                progress=0,
                message='Запуск краулера...',
                current_url=self.start_url
            )

            # Устанавливаем HTTP-сессию
            connector = aiohttp.TCPConnector(
                limit=10,  # Максимум 10 одновременных соединений
                limit_per_host=5,  # Максимум 5 соединений на хост
                ttl_dns_cache=300,  # Кеш DNS на 5 минут
                use_dns_cache=True
            )

            async with aiohttp.ClientSession(connector=connector) as session:
                self.session = session
                queue = asyncio.Queue()

                # Начинаем с заданного URL
                await queue.put((self.start_url, 0))
                self.visited_urls.add(self.start_url)

                # Счетчик активных задач
                active_tasks = 0
                max_concurrent_tasks = 3  # Максимум одновременных задач

                # Обрабатываем очередь URL
                while (not queue.empty() or active_tasks > 0) and len(self.visited_urls) <= self.max_pages:
                    # Запускаем новые задачи, если есть место и URL в очереди
                    while active_tasks < max_concurrent_tasks and not queue.empty() and len(
                            self.visited_urls) <= self.max_pages:
                        try:
                            url, depth = await asyncio.wait_for(queue.get(), timeout=0.1)
                            task = asyncio.create_task(self.process_url(url, depth, queue))
                            active_tasks += 1

                            # Ждем завершения задачи
                            try:
                                await task
                            except Exception as e:
                                logger.error(f"Ошибка в задаче обработки URL: {e}")
                            finally:
                                active_tasks -= 1

                            # Добавляем задержку между запросами
                            if self.delay > 0:
                                await asyncio.sleep(self.delay)

                        except asyncio.TimeoutError:
                            # Очередь пуста, выходим из внутреннего цикла
                            break

                    # Небольшая пауза, чтобы не загружать CPU
                    await asyncio.sleep(0.1)

                # Обновляем статус задания на 'completed'
                await self.update_job_status('completed')

                self.stats['end_time'] = datetime.now()
                duration = self.stats['end_time'] - self.stats['start_time']

                logger.info(f"Краулинг завершен успешно:")
                logger.info(f"  - Время выполнения: {duration}")
                logger.info(f"  - Страниц обработано: {self.stats['pages_processed']}")
                logger.info(f"  - Успешно: {self.stats['pages_successful']}")
                logger.info(f"  - Ошибок: {self.stats['pages_failed']}")
                logger.info(f"  - Ссылок найдено: {self.stats['links_found']}")

                # Финальное обновление прогресса
                self.update_progress(
                    status='completed',
                    progress=100,
                    message=f'Краулинг завершен! Обработано {self.stats["pages_processed"]} страниц'
                )

        except Exception as e:
            logger.error(f"Ошибка при выполнении краулинга: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")

            if self.job_id:
                await self.update_job_status('failed')

            self.update_progress(
                status='failed',
                message=f'Ошибка краулинга: {str(e)}'
            )
            raise

        finally:
            # Закрываем все соединения
            await self.close()

        # Возвращаем ID выполненного задания
        return self.job_id


# Функция для тестирования краулера
async def main():
    """Точка входа в программу для тестирования"""
    try:
        # Импортируем db_manager здесь, чтобы избежать циклического импорта
        from database import db_manager

        # Создаем краулер с параметрами
        crawler = WebCrawler(
            job_name="Тест краулера - Википедия",
            start_url="https://ru.wikipedia.org/wiki/Программирование",
            user_id=1,  # ID пользователя 'admin'
            max_pages=10,  # Ограничение количества страниц для теста
            delay=1.0,  # Задержка между запросами
            max_depth=2,  # Ограичение глубины обхода
            max_retries=3  # Количество попыток при ошибках
        )

        # Устанавливаем менеджер базы данных
        crawler.set_db_manager(db_manager)

        # Callback для отслеживания прогресса
        def progress_callback(**kwargs):
            print(f"Прогресс: {kwargs}")

        crawler.progress_callback = progress_callback

        # Запускаем процесс краулинга
        job_id = await crawler.crawl()
        print(f"Задание с ID {job_id} выполнено. Результаты сохранены в базе данных.")

    except Exception as e:
        logger.error(f"Ошибка в main(): {str(e)}")
        print(f"Произошла ошибка: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())