# Веб-краулер на Python

Асинхронный веб-краулер для сбора данных с веб-страниц. Поддерживает ограничение глубины обхода, проверку robots.txt и сохранение данных в различных форматах.

## Возможности

- 🔄 Асинхронный обход страниц
- 📊 Сбор метаданных и контента
- 🔍 Парсинг заголовков и текста
- 🔗 Извлечение и обработка ссылок
- 📝 Сохранение в JSON и CSV форматах
- ⏱️ Настраиваемая задержка между запросами
- 🛡️ Поддержка robots.txt
- 🔄 Автоматические повторные попытки при ошибках
- 📈 Ограничение глубины обхода
- 🎯 Ограничение количества страниц

## Требования

- Python 3.7+
- Установленные зависимости из requirements.txt

## Установка

1. Клонируйте репозиторий:
```bash
git clone <url-репозитория>
cd <директория-проекта>
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
```

3. Активируйте виртуальное окружение:
- Windows:
```bash
venv\Scripts\activate
```
- Linux/Mac:
```bash
source venv/bin/activate
```

4. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Использование

Базовый пример использования:

```python
from crawler import WebCrawler
import asyncio

async def main():
    crawler = WebCrawler(
        start_url="https://example.com",
        max_pages=100,      # Максимальное количество страниц
        delay=0.5,         # Задержка между запросами
        max_depth=3,       # Максимальная глубина обхода
        max_retries=3,     # Количество попыток при ошибках
        user_agent="MyCrawler/1.0"  # Идентификатор краулера
    )
    await crawler.crawl()

if __name__ == "__main__":
    asyncio.run(main())
```

## Параметры конфигурации

- `start_url` (str): Начальный URL для обхода
- `max_pages` (int): Максимальное количество страниц для обхода (по умолчанию: 100)
- `delay` (float): Задержка между запросами в секундах (по умолчанию: 1.0)
- `max_depth` (int): Максимальная глубина обхода (по умолчанию: 3)
- `max_retries` (int): Количество попыток при ошибках (по умолчанию: 3)
- `user_agent` (str): User-Agent для запросов (по умолчанию: "*")

## Собранные данные

Краулер собирает следующие данные с каждой страницы:

- URL страницы
- Заголовок страницы
- Мета-описание
- Ключевые слова
- Open Graph теги
- Заголовки (h1-h6)
- Основной текст
- Количество слов
- Количество ссылок
- Список ссылок
- Временная метка

## Сохранение данных

Данные сохраняются в директории `crawled_data` в двух форматах:
- JSON файл с полными данными
- CSV файл с табличным представлением

Имена файлов включают временную метку для удобства отслеживания.

## Логирование

Краулер ведет подробный лог своей работы в файле `crawler.log`. Лог включает:
- Информацию о посещенных страницах
- Ошибки и предупреждения
- Статус обработки страниц
- Информацию о сохранении данных

## Ограничения

- Краулер работает только в рамках одного домена
- Соблюдает правила robots.txt
- Имеет встроенные механизмы защиты от перегрузки серверов
