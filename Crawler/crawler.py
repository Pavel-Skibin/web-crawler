# Импорты для асинхронной работы и HTTP-запросов
import asyncio
import aiohttp
import logging
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from urllib.parse import urljoin, urlparse, unquote
from urllib.robotparser import RobotFileParser
from datetime import datetime
import os
from typing import Set, List, Dict, Optional
import json
import csv
import re

# Настройка для Windows
import sys
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
    Поддерживает асинхронный обход, проверку robots.txt и ограничение глубины.
    """
    def __init__(
            self,
            start_url: str,          # Начальный URL для обхода
            max_pages: int = 100,    # Максимальное количество страниц для обхода
            delay: float = 1.0,      # Задержка между запросами в секундах
            max_depth: int = 3,      # Максимальная глубина обхода
            max_retries: int = 3,    # Количество попыток при ошибках
            user_agent: str = "*"    # User-Agent для запросов
    ):
        self.start_url = start_url
        self.max_pages = max_pages
        self.delay = delay
        self.max_depth = max_depth
        self.max_retries = max_retries
        self.user_agent = user_agent

        # Инициализация базовых параметров
        self.visited_urls: Set[str] = set()
        self.data: List[Dict] = []
        self.ua = UserAgent()
        self.domain = urlparse(start_url).netloc
        self.robots_parser = RobotFileParser()
        self.output_dir = 'crawled_data'
        self.session: Optional[aiohttp.ClientSession] = None

        # Загрузка и парсинг robots.txt
        self.robots_parser.set_url(urljoin(start_url, "/robots.txt"))
        try:
            self.robots_parser.read()
        except Exception as e:
            logger.warning(f"Не удалось прочитать robots.txt: {str(e)}")

        os.makedirs(self.output_dir, exist_ok=True)

    async def close_session(self):
        """Закрытие HTTP-сессии"""
        if self.session:
            await self.session.close()

    def get_headers(self) -> Dict:
        """Генерация HTTP-заголовков для запроса"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }

    def allowed_by_robots(self, url: str) -> bool:
        """Проверка разрешения на обход URL согласно robots.txt"""
        try:
            return self.robots_parser.can_fetch(self.user_agent, url)
        except Exception as e:
            logger.error(f"Ошибка проверки robots.txt: {str(e)}")
            return True

    async def fetch_page(self, url: str) -> Optional[str]:
        """
        Получение содержимого страницы с поддержкой повторных попыток
        и обработкой ошибок
        """
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(
                        url,
                        headers=self.get_headers(),
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:  # Too Many Requests
                        delay = 2 ** (attempt + 1)
                        logger.warning(f"Превышен лимит запросов. Повтор через {delay} сек...")
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(f"HTTP {response.status} для {url}")
                        return None
            except Exception as e:
                logger.error(f"Попытка {attempt + 1} не удалась: {str(e)}")
                if attempt == self.max_retries - 1:
                    return None
                await asyncio.sleep(2 ** attempt)
        return None

    def parse_metadata(self, soup: BeautifulSoup) -> Dict:
        """Извлечение мета-данных страницы"""
        meta = {
            'description': '',
            'keywords': '',
            'og_title': '',
            'og_description': '',
            'viewport': '',
        }

        # Парсинг основных мета-тегов
        description_tag = soup.find('meta', attrs={'name': 'description'})
        if description_tag:
            meta['description'] = description_tag.get('content', '')

        keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_tag:
            meta['keywords'] = keywords_tag.get('content', '')

        # Парсинг Open Graph тегов
        og_title = soup.find('meta', property='og:title')
        if og_title:
            meta['og_title'] = og_title.get('content', '')

        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            meta['og_description'] = og_desc.get('content', '')

        # Парсинг viewport
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport:
            meta['viewport'] = viewport.get('content', '')

        return meta

    def parse_headings(self, soup: BeautifulSoup) -> Dict:
        """Извлечение всех заголовков страницы (h1-h6)"""
        headings = {f'h{i}': [] for i in range(1, 7)}
        for i in range(1, 7):
            for heading in soup.find_all(f'h{i}'):
                headings[f'h{i}'].append(heading.get_text().strip())
        return headings

    def parse_content(self, soup: BeautifulSoup) -> Dict:
        """Извлечение основного текста страницы"""
        text = ' '.join([p.get_text().strip() for p in soup.find_all('p')])
        text = re.sub(r'\s+', ' ', text)  # Удаление лишних пробелов
        return {
            'content_text': text[:5000],  # Ограничение длины текста
            'word_count': len(text.split()),
            'links_count': len(soup.find_all('a'))
        }

    def parse_page(self, html: str, url: str) -> Optional[Dict]:
        """
        Основной метод парсинга страницы.
        Извлекает заголовок, мета-данные, контент и ссылки.
        """
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Основная информация
            title = soup.title.string.strip() if soup.title else ''

            # Сбор всех данных
            meta = self.parse_metadata(soup)
            headings = self.parse_headings(soup)
            content = self.parse_content(soup)

            # Обработка ссылок
            links = []
            for link in soup.find_all('a', href=True):
                try:
                    absolute_url = urljoin(url, link['href'])
                    decoded_url = unquote(absolute_url)
                    parsed_url = urlparse(decoded_url)
                    
                    # Очистка URL от якоря и параметров
                    clean_url = parsed_url._replace(
                        fragment="",
                        query=""
                    ).geturl()

                    # Проверка принадлежности к тому же домену
                    if parsed_url.netloc.endswith(self.domain):
                        links.append(clean_url)

                except Exception as e:
                    logger.error(f"Ошибка обработки ссылки {link['href']}: {str(e)}")

            return {
                'url': unquote(url),
                'title': title,
                **meta,
                **headings,
                **content,
                'links': links,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга {url}: {str(e)}")
            return None

    async def process_url(self, url: str, depth: int, queue: asyncio.Queue):
        """Обработка одной URL с учетом глубины и очереди"""
        if not self.allowed_by_robots(url):
            logger.info(f"Пропуск {url} - запрещено robots.txt")
            return

        html = await self.fetch_page(url)
        if not html:
            return

        page_data = self.parse_page(html, url)
        if page_data:
            self.data.append(page_data)
            logger.info(f"Обработано: {url} (Глубина {depth})")

            # Добавление новых ссылок в очередь
            if depth < self.max_depth:
                for link in page_data['links']:
                    if link not in self.visited_urls and len(self.visited_urls) < self.max_pages:
                        self.visited_urls.add(link)
                        await queue.put((link, depth + 1))

    async def crawl(self):
        """
        Основной метод краулинга.
        Асинхронно обходит страницы с учетом ограничений.
        """
        try:
            async with aiohttp.ClientSession() as session:
                self.session = session
                queue = asyncio.Queue()
                await queue.put((self.start_url, 0))
                self.visited_urls.add(self.start_url)
                tasks = []

                while not queue.empty() and len(self.visited_urls) <= self.max_pages:
                    url, depth = await queue.get()
                    task = asyncio.create_task(self.process_url(url, depth, queue))
                    tasks.append(task)
                    await asyncio.sleep(self.delay)

                await asyncio.gather(*tasks)
        finally:
            await self.close_session()
            self.save_data()

    def save_data(self):
        """
        Сохранение собранных данных в JSON и CSV форматах.
        Файлы сохраняются с временной меткой в имени.
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Сохранение в JSON
        json_path = os.path.join(self.output_dir, f'data_{timestamp}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

        # Сохранение в CSV
        if self.data:
            csv_path = os.path.join(self.output_dir, f'data_{timestamp}.csv')
            fieldnames = set(self.data[0].keys())

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(fieldnames))
                writer.writeheader()
                for row in self.data:
                    # Конвертация списков в строки для CSV
                    row_copy = row.copy()
                    for key, value in row_copy.items():
                        if isinstance(value, list):
                            row_copy[key] = '; '.join(value)
                    writer.writerow(row_copy)

        logger.info(f"Сохранено {len(self.data)} страниц в {json_path} и {csv_path}")


async def main():
    """Точка входа в программу"""
    crawler = WebCrawler(
        start_url="https://ru.wikipedia.org/wiki/Западная_Европа",
        max_pages=20,      # Ограничение количества страниц
        delay=0.5,         # Задержка между запросами
        max_depth=2,       # Ограничение глубины обхода
        max_retries=3,     # Количество попыток при ошибках
        user_agent="MyCrawler/1.0"  # Идентификатор краулера
    )
    await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())