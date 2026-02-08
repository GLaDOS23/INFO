import feedparser
import requests
from datetime import datetime, timezone
from typing import List, Dict, Set, Optional
import re
import time
import logging
import sqlite3
import json
from pathlib import Path
from bs4 import BeautifulSoup
import uuid

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NewsFetcher:
    """Агрегатор новостей из RSS-источников с сохранением в БД и JSON"""

    # Словарь всех доступных источников
    ALL_FEEDS = {
        # Российские источники
        "lenta": "https://lenta.ru/rss",
        "ria": "https://ria.ru/export/rss2/index.xml",
        "rt": "https://russian.rt.com/rss",
        "tass": "https://tass.ru/rss/v2.xml",
        "kommersant": "https://www.kommersant.ru/RSS/news.xml",
        "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        "vedomosti": "https://www.vedomosti.ru/rss/news",
        "mk": "https://www.mk.ru/rss/index.xml",
        "gazeta": "https://www.gazeta.ru/export/rss/lenta.xml",
        "meduza": "https://meduza.io/rss2/all",
        "fontanka": "https://www.fontanka.ru/fontanka.rss",
        "sport_express": "https://www.sport-express.ru/services/materials/news/se/",
        "interfax": "http://www.interfax.ru/rss.asp",
        "rg": "https://rg.ru/xml/index.xml",
        "kp": "https://www.kp.ru/rss/allsections.xml",
        "ai": "https://www.aftershock.news/rss.xml",
        "vz": "https://vz.ru/rss.xml",
        # Международные источники
        "bbc": "https://feeds.bbci.co.uk/news/rss.xml",
        "nytimes": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "reuters": "http://feeds.reuters.com/reuters/topNews",
        "cnn": "http://rss.cnn.com/rss/edition.rss",
        "npr": "https://feeds.npr.org/1001/rss.xml",
        "ap": "https://apnews.com/apf-topnews",
        "dw": "https://rss.dw.com/rdf/rss-en-top",
        "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
        "bloomberg": "https://www.bloomberg.com/feeds/podcasts/etf_report.xml",
        "ft": "https://www.ft.com/rss/home",
        "wsj": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "guardian": "https://www.theguardian.com/world/rss",
        "euronews": "https://www.euronews.com/rss",
        # Белорусские
        "belta": "https://www.belta.by/rss/main",
        "tut": "https://news.tut.by/rss/index.rss",
        # Казахстанские
        "kazinform": "https://www.inform.kz/rss/ru",
        "tengrinews": "https://tengrinews.kz/rss/",
        # Технологии и программирование (русские)
        "habr": "https://habr.com/ru/rss/articles/all/?fl=ru",
        "vc": "https://vc.ru/feed",
        "tproger": "https://tproger.ru/feed/",
        "xakep": "https://xakep.ru/feed/",
        "devby": "https://dev.by/rss",
        # Технологии и программирование (международные)
        "wired": "https://www.wired.com/feed/rss",
        "hackernews": "https://news.ycombinator.com/rss",
        "mittech": "https://www.technologyreview.com/feed/",
        "github": "https://github.blog/feed/",
        "stackoverflow": "https://stackoverflow.blog/feed/",
        "devto": "https://dev.to/feed",
        # Нейросети и машинное обучение
        "towardsds": "https://towardsdatascience.com/feed",
        "kdnuggets": "https://www.kdnuggets.com/feed",
        "tensorflow": "https://blog.tensorflow.org/feeds/posts/default",
        "pytorch": "https://pytorch.org/blog/rss.xml",
        "ai_news": "https://www.artificialintelligence-news.com/feed/",
    }

    # Маппинг идентификаторов в отображаемые названия
    SOURCE_NAMES = {
        "lenta": "Лента.ру",
        "ria": "РИА Новости",
        "rt": "RT",
        "tass": "ТАСС",
        "kommersant": "Коммерсантъ",
        "rbc": "РБК",
        "vedomosti": "Ведомости",
        "mk": "Московский комсомолец",
        "gazeta": "Газета.Ru",
        "meduza": "Meduza",
        "fontanka": "Фонтанка.ру",
        "sport_express": "Спорт-Экспресс",
        "interfax": "Интерфакс",
        "rg": "Российская газета",
        "kp": "Комсомольская правда",
        "ai": "Афтершок",
        "vz": "Взгляд",
        "bbc": "BBC News",
        "nytimes": "New York Times",
        "reuters": "Reuters",
        "cnn": "CNN",
        "npr": "NPR",
        "ap": "Associated Press",
        "dw": "Deutsche Welle",
        "aljazeera": "Al Jazeera",
        "bloomberg": "Bloomberg",
        "ft": "Financial Times",
        "wsj": "Wall Street Journal",
        "guardian": "The Guardian",
        "euronews": "Euronews",
        "belta": "БЕЛТА",
        "tut": "TUT.BY",
        "kazinform": "Казинформ",
        "tengrinews": "Tengrinews",
        "habr": "Хабр",
        "vc": "VC.ru",
        "tproger": "Tproger",
        "xakep": "Хакер",
        "devby": "Dev.by",
        "wired": "Wired",
        "hackernews": "Hacker News",
        "mittech": "MIT Tech Review",
        "github": "GitHub Blog",
        "stackoverflow": "Stack Overflow",
        "devto": "Dev.to",
        "towardsds": "Towards Data Science",
        "kdnuggets": "KDnuggets",
        "tensorflow": "TensorFlow Blog",
        "pytorch": "PyTorch Blog",
        "ai_news": "AI News",
    }

    def __init__(self, db_path: str = "newshub.db", max_items: int = 500, timeout: int = 10):
        """
        Инициализация агрегатора

        Args:
            db_path: Путь к SQLite базе данных
            max_items: Максимальное количество сохраняемых новостей
            timeout: Таймаут для запросов в секундах
        """
        self.db_path = db_path
        self.max_items = max_items
        self.timeout = timeout
        self.news: List[Dict] = []
        self.seen_guids: Set[str] = set()
        self.seen_links: Set[str] = set()
        self.saved_links: Set[str] = set()
        self.seen_news_ids: Set[str] = set()  # Для отслеживания просмотренных новостей
        self.last_fetch_time: Optional[float] = None
        self.selected_feeds: Set[str] = set()

        # Инициализация БД
        self.init_database()
        self.load_selected_feeds_from_db()
        self.load_saved_links()

    def init_database(self):
        """Инициализация SQLite базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Таблица для избранных источников
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS favorite_sources (
                    source_id TEXT PRIMARY KEY
                )
            """)

            conn.commit()
            conn.close()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")

    def load_selected_feeds_from_db(self):
        """Загрузка выбранных источников из базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT source_id FROM favorite_sources")
            rows = cursor.fetchall()

            self.selected_feeds.clear()
            for row in rows:
                self.selected_feeds.add(row[0])

            conn.close()

            # Если БД пустая — устанавливаем дефолтные источники
            if not self.selected_feeds:
                self.selected_feeds.update(["habr", "pytorch", "ai_news"])
                self.save_selected_feeds_to_db()
                logger.info("Установлены дефолтные источники: lenta, ria, bbc")

            logger.info(f"Загружено {len(self.selected_feeds)} выбранных источников из БД")
        except Exception as e:
            logger.error(f"Ошибка загрузки выбранных источников: {e}")
            # Дефолтные источники при ошибке
            self.selected_feeds.update(["lenta", "ria", "bbc"])

    def save_selected_feeds_to_db(self):
        """Сохранение выбранных источников в базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Очистка таблицы
            cursor.execute("DELETE FROM favorite_sources")

            # Вставка выбранных источников
            for source_id in self.selected_feeds:
                cursor.execute("INSERT INTO favorite_sources (source_id) VALUES (?)", (source_id,))

            conn.commit()
            conn.close()
            logger.info(f"Сохранено {len(self.selected_feeds)} выбранных источников в БД")
        except Exception as e:
            logger.error(f"Ошибка сохранения выбранных источников: {e}")

    def get_source_name(self, source_id: str) -> str:
        """Получение отображаемого названия источника"""
        # Поддержка кастомных источников (как в оригинале с суффиксом _name)
        custom_name = getattr(self, f"{source_id}_name", None)
        if custom_name:
            return custom_name
        return self.SOURCE_NAMES.get(source_id, source_id)

    def fetch_news(self, selected_feeds: Optional[List[str]] = None) -> List[Dict]:
        """
        Основной метод сбора новостей из выбранных источников

        Args:
            selected_feeds: Список ID выбранных источников. Если None - используются все доступные.

        Returns:
            Отсортированный список новостей (от новых к старым)
        """
        if selected_feeds is None:
            selected_feeds = list(self.selected_feeds)

        if not selected_feeds:
            logger.warning("Нет выбранных источников для загрузки")
            return []

        # Очистка кэша дубликатов для новой сессии
        self.seen_guids.clear()
        self.seen_links.clear()

        all_items = []
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; NewsFetcher/1.0)'
        })

        for feed_id in selected_feeds:
            if feed_id not in self.ALL_FEEDS:
                logger.warning(f"Источник '{feed_id}' не найден в списке доступных")
                continue

            url = self.ALL_FEEDS[feed_id]
            try:
                logger.info(f"Загрузка ленты: {feed_id} ({url})")
                response = session.get(url, timeout=self.timeout)
                response.raise_for_status()

                # Парсинг RSS/Atom
                feed = feedparser.parse(response.content)

                for entry in feed.entries[:20]:  # Ограничиваем 20 последними новостями из источника
                    item = self._parse_entry(entry, feed_id, url)
                    if item and self._is_unique(item):
                        all_items.append(item)
                        self.seen_guids.add(item["guid"])
                        self.seen_links.add(item["link"])

            except Exception as e:
                logger.error(f"Ошибка загрузки {feed_id} ({url}): {e}")
                continue

        # Сортировка по дате (новые первыми)
        all_items.sort(key=lambda x: x.get("published_parsed", datetime.now(timezone.utc)), reverse=True)

        # Ограничение общего количества
        self.news = all_items[:self.max_items]
        self.last_fetch_time = time.time()

        logger.info(f"Загружено {len(self.news)} новостей из {len(selected_feeds)} источников")
        return self.news

    def _parse_entry(self, entry, feed_id: str, feed_url: str) -> Optional[Dict]:
        """Парсинг одной записи из RSS-ленты"""
        try:
            # Извлечение данных с обработкой отсутствующих полей
            title = getattr(entry, "title", "Без названия")
            link = getattr(entry, "link", "#")
            description = getattr(entry, "summary", getattr(entry, "description", "Нет описания"))

            # Обработка даты публикации
            published = getattr(entry, "published", "")
            published_parsed = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_parsed = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            # GUID - уникальный идентификатор записи
            guid = getattr(entry, "id", getattr(entry, "guid", link))

            return {
                "title": self._clean_html(title),
                "desc": self._clean_html(description),
                "link": link,
                "date": published,
                "published_parsed": published_parsed or datetime.now(timezone.utc),
                "sourceUrl": feed_url,
                "sourceId": feed_id,
                "sourceName": self.get_source_name(feed_id),
                "guid": guid,
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга записи из {feed_id}: {e}")
            return None

    def _is_unique(self, item: Dict) -> bool:
        """Проверка на дубликат по GUID или ссылке"""
        return item["guid"] not in self.seen_guids and item["link"] not in self.seen_links

    @staticmethod
    def _clean_html(text: str) -> str:
        """Очистка HTML-тегов из текста"""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def get_stats(self) -> Dict:
        """Получение статистики по собранным новостям"""
        sources_count = {}
        for item in self.news:
            src = item["sourceName"]
            sources_count[src] = sources_count.get(src, 0) + 1

        return {
            "total_news": len(self.news),
            "sources_count": len(set(item["sourceId"] for item in self.news)),
            "news_by_source": sources_count,
            "selected_feeds_count": len(self.selected_feeds),
            "last_fetch": self.last_fetch_time
        }

    def get_new_news_count(self) -> int:
        """Подсчёт количества новых (непросмотренных) новостей"""
        count = 0
        for item in self.news:
            news_id = item["link"] + item["title"]
            if news_id not in self.seen_news_ids:
                count += 1
        return count

    def clear_viewed_cache(self):
        """Очистка кэша просмотренных новостей"""
        self.seen_news_ids.clear()
        logger.info("Кэш просмотренных новостей очищен")

    def mark_as_viewed(self, news_item: Dict):
        """Отметить новость как просмотренную"""
        news_id = news_item["link"] + news_item["title"]
        self.seen_news_ids.add(news_id)

    def get_unique_sources(self) -> Set[str]:
        """Получение списка уникальных источников из загруженных новостей"""
        return {item["sourceId"] for item in self.news if item.get("sourceId")}

    # ==================== РАБОТА С СОХРАНЁННЫМИ СТАТЬЯМИ ====================

    def load_saved_links(self):
        """Загрузка списка сохранённых ссылок из JSON файла"""
        saved_file = Path("saved") / "articles.json"
        if saved_file.exists():
            try:
                with open(saved_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                    self.saved_links = {article.get("sourceUrl") for article in articles if article.get("sourceUrl")}
                logger.info(f"Загружено {len(self.saved_links)} сохранённых ссылок")
            except Exception as e:
                logger.error(f"Ошибка загрузки сохранённых ссылок: {e}")

    def fetch_full_text_from_page(self, url: str) -> str:
        """
        Парсинг полного текста статьи с веб-страницы

        Args:
            url: URL статьи

        Returns:
            Очищенный текст статьи
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            # Парсинг HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # Удаляем мусорные элементы
            for tag in soup.select('script, style, noscript, header, footer, nav, aside, iframe, embed'):
                tag.decompose()

            # Ищем тег <article> или основной контент
            article_tag = soup.find('article')
            if article_tag:
                text = article_tag.get_text(separator=' ', strip=True)
            else:
                # Если нет <article>, берём основной контент из <body>
                text = soup.body.get_text(separator=' ', strip=True) if soup.body else ''

            # Очистка текста
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        except Exception as e:
            logger.error(f"Ошибка парсинга полного текста статьи {url}: {e}")
            return ""

    def save_article(self, link: str) -> Dict:
        """
        Сохранение статьи в JSON файл

        Args:
            link: URL статьи

        Returns:
            Словарь с результатом операции
        """
        try:
            # Ищем статью в списке новостей
            article = None
            for news_item in self.news:
                if news_item.get("link") == link:
                    article = news_item
                    break

            if not article:
                return {"success": False, "message": "Статья не найдена"}

            # Проверяем, не сохранена ли уже
            if link in self.saved_links:
                return {"success": False, "message": "Статья уже сохранена"}

            # Загружаем полный текст статьи
            logger.info(f"Парсинг полного текста статьи: {link}")
            full_text = self.fetch_full_text_from_page(link)

            if not full_text:
                return {"success": False, "message": "Не удалось получить текст статьи"}

            # Подготавливаем данные для сохранения
            title = article.get("title", "Без названия")
            source_name = article.get("sourceName", "Неизвестно")

            # Первые 100 слов для превью
            words = full_text.split()
            preview_100 = ' '.join(words[:100]) if len(words) > 100 else full_text
            preview_with_title = f"{title}. {preview_100}"

            # Данные статьи
            article_data = {
                "sourceUrl": link,
                "sourceName": source_name,
                "title": title,
                "preview100": preview_with_title,
                "fullText": full_text,
                "savedAt": datetime.now(timezone.utc).isoformat(),
                "id": str(uuid.uuid4())
            }

            # Путь к файлу
            saved_dir = Path("saved")
            saved_dir.mkdir(exist_ok=True)
            articles_file = saved_dir / "articles.json"

            # Загрузка существующих статей
            if articles_file.exists():
                with open(articles_file, 'r', encoding='utf-8') as f:
                    all_articles = json.load(f)
            else:
                all_articles = []

            # Проверка на дубликат
            exists = any(a.get("sourceUrl") == link for a in all_articles)
            if exists:
                return {"success": False, "message": "Статья уже сохранена"}

            # Добавление новой статьи
            all_articles.append(article_data)

            # Сохранение в JSON
            with open(articles_file, 'w', encoding='utf-8') as f:
                json.dump(all_articles, f, ensure_ascii=False, indent=2)

            # Обновление кэша сохранённых ссылок
            self.saved_links.add(link)

            logger.info(f"Статья сохранена: {title}")
            return {"success": True, "message": "Статья успешно сохранена", "data": article_data}

        except Exception as e:
            logger.error(f"Ошибка при сохранении статьи {link}: {e}")
            return {"success": False, "message": f"Ошибка при сохранении: {str(e)}"}

    def get_saved_articles(self, page: int = 1, page_size: int = 10) -> Dict:
        """
        Получение списка сохранённых статей с пагинацией

        Args:
            page: Номер страницы
            page_size: Количество статей на странице

        Returns:
            Словарь с данными о статьях и пагинацией
        """
        articles_file = Path("saved") / "articles.json"

        if not articles_file.exists():
            return {
                "articles": [],
                "total": 0,
                "page": page,
                "total_pages": 0,
                "page_size": page_size
            }

        try:
            with open(articles_file, 'r', encoding='utf-8') as f:
                all_articles = json.load(f)

            total = len(all_articles)
            total_pages = (total + page_size - 1) // page_size

            # Валидация номера страницы
            page = max(1, min(page, total_pages if total_pages > 0 else 1))

            # Получение статей для текущей страницы
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_articles = all_articles[start_idx:end_idx]

            return {
                "articles": page_articles,
                "total": total,
                "page": page,
                "total_pages": total_pages,
                "page_size": page_size
            }

        except Exception as e:
            logger.error(f"Ошибка загрузки сохранённых статей: {e}")
            return {
                "articles": [],
                "total": 0,
                "page": page,
                "total_pages": 0,
                "page_size": page_size
            }

    # ==================== ПОИСК ====================

    def search_news(self, query: str) -> List[Dict]:
        """
        Поиск новостей по запросу

        Args:
            query: Поисковый запрос

        Returns:
            Список найденных новостей
        """
        if not query or not query.strip():
            return []

        query_lower = query.lower()
        results = []

        for item in self.news:
            title = item.get("title", "").lower()
            desc = item.get("desc", "").lower()
            source_name = item.get("sourceName", "").lower()

            if query_lower in title or query_lower in desc or query_lower in source_name:
                results.append(item)

        return results


# ==================== ПРИМЕР ИСПОЛЬЗОВАНИЯ ====================

def main():
    # Инициализация агрегатора
    fetcher = NewsFetcher(max_items=500)

    print("=" * 60)
    print("NewsHub - RSS Агрегатор")
    print("=" * 60)

    # Вывод статистики по выбранным источникам
    print(f"\nВыбрано источников: {len(fetcher.selected_feeds)}")
    print(f"Источники: {', '.join(sorted(fetcher.selected_feeds))}")

    # Загрузка новостей
    print("\nЗагрузка новостей...")
    news = fetcher.fetch_news()

    print(f"\nЗагружено новостей: {len(news)}")
    print(f"Новых новостей: {fetcher.get_new_news_count()}")

    # Вывод последних 5 новостей
    print("\n" + "=" * 60)
    print("Последние 5 новостей:")
    print("=" * 60)

    for i, item in enumerate(news[:5], 1):
        print(f"\n{i}. [{item['sourceName']}] {item['title']}")
        print(f"   {item['date']}")
        print(f"   {item['link']}")

    # Статистика
    print("\n" + "=" * 60)
    print("Статистика:")
    print("=" * 60)

    stats = fetcher.get_stats()
    print(f"Всего новостей: {stats['total_news']}")
    print(f"Источников: {stats['sources_count']}")
    print(f"Выбрано источников: {stats['selected_feeds_count']}")

    print("\nРаспределение по источникам:")
    for src, count in sorted(stats['news_by_source'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {src}: {count}")

    # Пример сохранения статьи
    print("\n" + "=" * 60)
    print("Пример сохранения статьи:")
    print("=" * 60)

    if news:
        first_article_link = news[0]['link']
        print(f"\nПопытка сохранить статью: {news[0]['title']}")
        result = fetcher.save_article(first_article_link)

        if result['success']:
            print("✓ Статья успешно сохранена!")
            print(f"  Сохранено в: saved/articles.json")
        else:
            print(f"✗ Ошибка: {result['message']}")

    # Просмотр сохранённых статей
    print("\n" + "=" * 60)
    print("Сохранённые статьи:")
    print("=" * 60)

    saved = fetcher.get_saved_articles(page=1, page_size=5)
    print(f"Всего сохранено статей: {saved['total']}")

    if saved['articles']:
        for i, article in enumerate(saved['articles'], 1):
            print(f"\n{i}. {article.get('title', 'Без названия')}")
            print(f"   Источник: {article.get('sourceName', 'Неизвестно')}")
            print(f"   URL: {article.get('sourceUrl', '#')}")
    else:
        print("Нет сохранённых статей")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
