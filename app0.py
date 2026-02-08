#!/usr/bin/env python3
"""
NewsHub - RSS агрегатор на Python (FastAPI)
Полный аналог Java-версии с сохранением всего функционала
"""
import os
import json
import sqlite3
import uuid
import re
import html
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from dataclasses import dataclass, asdict

import feedparser
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Конфигурация
DB_PATH = "newshub.db"
SAVED_ARTICLES_PATH = Path("saved/articles.json")
CACHE_DURATION_MINUTES = 5
PAGE_SIZE = 10
MAX_NEWS_ITEMS = 500

# Глобальное состояние приложения (в реальном проекте лучше использовать класс)
app_state = {
    "news": [],  # Список новостей
    "seen_news": set(),  # Множество просмотренных новостей (для бейджа "новое")
    "saved_links": set(),  # Сохраненные ссылки
    "last_fetch_time": None,  # Время последней загрузки
    "lock": threading.Lock(),  # Для потокобезопасности
}

# Все доступные источники с категориями
ALL_FEEDS = {
    # Российские
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
    
    # Международные
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
    
    # Технологии (русские)
    "habr": "https://habr.com/ru/rss/all/all/?fl=ru",
    "vc": "https://vc.ru/feed",
    "tproger": "https://tproger.ru/feed/",
    "xakep": "https://xakep.ru/feed/",
    "devby": "https://dev.by/rss",
    
    # Технологии (международные)
    "wired": "https://www.wired.com/feed/rss",
    "hackernews": "https://news.ycombinator.com/rss",
    "mittech": "https://www.technologyreview.com/feed/",
    "github": "https://github.blog/feed/",
    "stackoverflow": "https://stackoverflow.blog/feed/",
    "devto": "https://dev.to/feed",
    
    # Нейросети и ML
    "towardsds": "https://towardsdatascience.com/feed",
    "kdnuggets": "https://www.kdnuggets.com/feed",
    "tensorflow": "https://blog.tensorflow.org/feeds/posts/default",
    "pytorch": "https://pytorch.org/blog/rss.xml",
    "ai_news": "https://www.artificialintelligence-news.com/feed/",
}

# Отображение ID источника в человекочитаемое название
SOURCE_DISPLAY_NAMES = {
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

# Категории источников
FEED_CATEGORIES = {
    "российские": ["lenta", "ria", "rt", "tass", "kommersant", "rbc", "vedomosti", "mk", 
                  "gazeta", "meduza", "fontanka", "sport_express", "interfax", "rg", "kp", "ai", "vz"],
    "международные": ["bbc", "nytimes", "reuters", "cnn", "npr", "ap", "dw", "aljazeera", 
                     "bloomberg", "ft", "wsj", "guardian", "euronews"],
    "белорусские": ["belta", "tut"],
    "казахстанские": ["kazinform", "tengrinews"],
    "технологии": ["habr", "vc", "tproger", "xakep", "devby", "wired", "hackernews", "mittech", 
                  "github", "stackoverflow", "devto", "towardsds", "kdnuggets", "tensorflow", 
                  "pytorch", "ai_news"],
}

# Инициализация приложения
app = FastAPI(title="NewsHub", description="RSS агрегатор на Python")
templates = Jinja2Templates(directory="templates")
os.makedirs("templates", exist_ok=True)
os.makedirs("saved", exist_ok=True)

# Создаем базу данных при старте
def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorite_sources (
            source_id TEXT PRIMARY KEY
        )
    """)
    # Устанавливаем источники по умолчанию, если таблица пустая
    cursor.execute("SELECT COUNT(*) FROM favorite_sources")
    if cursor.fetchone()[0] == 0:
        default_sources = ["lenta", "ria", "bbc"]
        cursor.executemany(
            "INSERT INTO favorite_sources (source_id) VALUES (?)",
            [(src,) for src in default_sources]
        )
    conn.commit()
    conn.close()

# Загрузка выбранных источников из БД
def load_selected_feeds() -> Set[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source_id FROM favorite_sources")
    sources = {row[0] for row in cursor.fetchall()}
    conn.close()
    return sources if sources else {"lenta", "ria", "bbc"}

# Сохранение выбранных источников в БД
def save_selected_feeds(sources: Set[str]):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorite_sources")
    cursor.executemany(
        "INSERT INTO favorite_sources (source_id) VALUES (?)",
        [(src,) for src in sources]
    )
    conn.commit()
    conn.close()

# Получение человекочитаемого названия источника
def get_source_display_name(source_id: str) -> str:
    # Проверяем кастомные источники (начинаются с "custom_")
    if source_id.startswith("custom_") and source_id.endswith("_name"):
        return ALL_FEEDS.get(source_id, source_id.replace("_name", "").replace("custom_", ""))
    
    if source_id.startswith("custom_"):
        name_key = f"{source_id}_name"
        return ALL_FEEDS.get(name_key, source_id.replace("custom_", ""))
    
    return SOURCE_DISPLAY_NAMES.get(source_id, source_id)

# Форматирование времени "назад"
def format_time_ago(dt: datetime) -> str:
    now = datetime.now()
    diff = now - dt
    
    if diff.total_seconds() < 60:
        return "только что"
    elif diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)} мин назад"
    elif diff.days < 1:
        return f"{diff.seconds // 3600} ч назад"
    else:
        return f"{diff.days} дн назад"

# Экранирование HTML
def escape_html(text: str) -> str:
    return html.escape(text)

# Обрезка текста
def truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

# Подсветка поискового запроса
def highlight_text(text: str, query: str) -> str:
    if not query or not query.strip():
        return escape_html(text)
    
    escaped_text = escape_html(text)
    escaped_query = re.escape(query.strip())
    # Регистронезависимая замена с подсветкой
    return re.sub(
        f"({escaped_query})", 
        r"<mark>\1</mark>", 
        escaped_text, 
        flags=re.IGNORECASE
    )

# Получение полного текста статьи через парсинг
def fetch_full_text_from_page(url: str) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Удаляем ненужные элементы
        for tag in soup.select("script, style, noscript, header, footer, nav, aside, iframe, .advertisement"):
            tag.decompose()
        
        # Пытаемся найти основной контент статьи
        article = (
            soup.find("article") or
            soup.find("div", class_=re.compile(r"article|post|content", re.I)) or
            soup.find("div", id=re.compile(r"article|post|content", re.I)) or
            soup.find("main") or
            soup.body
        )
        
        if article:
            # Удаляем комментарии
            for element in article.find_all(text=lambda text: isinstance(text, str) and "коммент" in text.lower()):
                element.extract()
            
            text = article.get_text(separator=" ", strip=True)
            return re.sub(r"\s+", " ", text).strip()
        
        return ""
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return ""

# Загрузка сохраненных статей
def load_saved_articles() -> List[Dict]:
    if not SAVED_ARTICLES_PATH.exists():
        return []
    
    try:
        with open(SAVED_ARTICLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки сохраненных статей: {e}")
        return []

# Сохранение статьи
def save_article(article: Dict, link: str):
    saved_articles = load_saved_articles()
    
    # Проверка на дубликат
    if any(a.get("sourceUrl") == link for a in saved_articles):
        return False
    
    # Добавляем статью
    saved_articles.append(article)
    
    # Сохраняем в файл
    with open(SAVED_ARTICLES_PATH, "w", encoding="utf-8") as f:
        json.dump(saved_articles, f, ensure_ascii=False, indent=2)
    
    return True

# Загрузка новостей из RSS
def fetch_rss_feeds(selected_feeds: Set[str]):
    news_items = []
    seen_guids = set()
    seen_links = set()
    
    for feed_id in selected_feeds:
        if feed_id not in ALL_FEEDS:
            continue
            
        url = ALL_FEEDS[feed_id]
        try:
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:20]:  # Ограничиваем количество статей на источник
                guid = entry.get("id", entry.get("link", str(uuid.uuid4())))
                link = entry.get("link", "#")
                
                # Пропускаем дубликаты
                if guid in seen_guids or link in seen_links:
                    continue
                
                seen_guids.add(guid)
                seen_links.add(link)
                
                # Форматируем дату
                pub_date = ""
                if hasattr(entry, "published"):
                    try:
                        pub_date = entry.published
                    except:
                        pass
                
                news_items.append({
                    "title": entry.get("title", "без названия"),
                    "desc": entry.get("summary", entry.get("description", "нет описания")),
                    "link": link,
                    "date": pub_date,
                    "sourceUrl": url,
                    "sourceId": feed_id,
                    "sourceName": get_source_display_name(feed_id),
                    "guid": guid,
                })
        except Exception as e:
            print(f"Ошибка загрузки {feed_id} ({url}): {e}")
    
    # Сортируем по дате (новые сверху)
    news_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    # Ограничиваем общее количество
    return news_items[:MAX_NEWS_ITEMS]

# Инициализация при старте
@app.on_event("startup")
async def startup_event():
    init_database()
    selected_feeds = load_selected_feeds()
    
    # Загружаем сохраненные ссылки
    saved_articles = load_saved_articles()
    app_state["saved_links"] = {a.get("sourceUrl", "") for a in saved_articles if a.get("sourceUrl")}
    
    # Загружаем новости при старте (опционально)
    if not app_state["news"]:
        with app_state["lock"]:
            app_state["news"] = fetch_rss_feeds(selected_feeds)
            app_state["last_fetch_time"] = datetime.now()

# Главная страница
@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    page: int = Query(1, ge=1),
    sort: str = Query("date", regex="^(date|title|source)$"),
    source: Optional[str] = Query(None)
):
    with app_state["lock"]:
        # Фильтрация по источнику
        filtered_news = app_state["news"]
        if source:
            filtered_news = [n for n in app_state["news"] if n.get("sourceId") == source]
        
        # Сортировка
        if sort == "title":
            sorted_news = sorted(filtered_news, key=lambda x: x.get("title", "").lower())
        elif sort == "source":
            sorted_news = sorted(filtered_news, key=lambda x: x.get("sourceName", "").lower())
        else:  # date
            sorted_news = sorted(
                filtered_news, 
                key=lambda x: x.get("date", ""), 
                reverse=True
            )
        
        # Пагинация
        total_items = len(sorted_news)
        total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_items)
        page_news = sorted_news[start_idx:end_idx]
        
        # Уникальные источники для фильтров
        unique_sources = sorted(
            {n.get("sourceId") for n in app_state["news"] if n.get("sourceId")},
            key=lambda x: get_source_display_name(x).lower()
        )
        
        # Подсчет новых новостей
        new_count = sum(
            1 for n in app_state["news"] 
            if f"{n.get('link', '')}{n.get('title', '')}" not in app_state["seen_news"]
        )
        
        # Форматирование времени последнего обновления
        last_fetch_str = None
        if app_state["last_fetch_time"]:
            last_fetch_str = format_time_ago(app_state["last_fetch_time"])
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "news": page_news,
            "page": page,
            "total_pages": total_pages,
            "sort": sort,
            "source": source,
            "unique_sources": unique_sources,
            "get_source_display_name": get_source_display_name,
            "total_news": len(app_state["news"]),
            "selected_feeds_count": len(load_selected_feeds()),
            "active_sources_count": len({n.get("sourceId") for n in app_state["news"]}),
            "new_count": new_count,
            "last_fetch_time": last_fetch_str,
            "escape_html": escape_html,
            "truncate_text": truncate_text,
            "is_new": lambda n: f"{n.get('link', '')}{n.get('title', '')}" not in app_state["seen_news"],
            "is_saved": lambda n: n.get("link", "") in app_state["saved_links"],
        })

# Страница выбора источников
@app.get("/select-sources", response_class=HTMLResponse)
async def select_sources(request: Request):
    selected_feeds = load_selected_feeds()
    
    # Группируем источники по категориям
    categorized = {}
    for category, feed_ids in FEED_CATEGORIES.items():
        feeds_in_category = [
            {"id": fid, "name": get_source_display_name(fid), "checked": fid in selected_feeds}
            for fid in feed_ids if fid in ALL_FEEDS
        ]
        if feeds_in_category:
            categorized[category] = feeds_in_category
    
    # Кастомные источники
    custom_feeds = []
    for fid in selected_feeds:
        if fid.startswith("custom_") and not fid.endswith("_name") and fid in ALL_FEEDS:
            custom_feeds.append({
                "id": fid,
                "name": get_source_display_name(fid),
                "checked": True
            })
    
    if custom_feeds:
        categorized["кастомные"] = custom_feeds
    
    return templates.TemplateResponse("select_sources.html", {
        "request": request,
        "categorized": categorized,
        "selected_count": len(selected_feeds),
    })

# Обновление выбранных источников
@app.post("/update-sources")
async def update_sources(source: List[str] = Form(default=[])):
    save_selected_feeds(set(source))
    return RedirectResponse(url="/", status_code=303)

# Страница добавления кастомного источника
@app.get("/add-custom-feed", response_class=HTMLResponse)
async def add_custom_feed_page(request: Request):
    return templates.TemplateResponse("add_custom_feed.html", {"request": request})

# Добавление кастомного источника
@app.post("/add-custom-feed")
async def add_custom_feed(name: str = Form(...), url: str = Form(...)):
    feed_id = f"custom_{int(datetime.now().timestamp())}"
    
    # Добавляем источник и его название
    ALL_FEEDS[feed_id] = url
    ALL_FEEDS[f"{feed_id}_name"] = name
    
    # Добавляем в выбранные
    selected_feeds = load_selected_feeds()
    selected_feeds.add(feed_id)
    save_selected_feeds(selected_feeds)
    
    return RedirectResponse(url="/select-sources", status_code=303)

# Загрузка новостей
@app.post("/fetch")
async def fetch_news():
    now = datetime.now()
    
    # Проверка кэша
    if app_state["last_fetch_time"]:
        elapsed = now - app_state["last_fetch_time"]
        if elapsed < timedelta(minutes=CACHE_DURATION_MINUTES):
            minutes_left = CACHE_DURATION_MINUTES - int(elapsed.total_seconds() // 60)
            return RedirectResponse(
                url=f"/?notify=Подождите {minutes_left} минут перед обновлением", 
                status_code=303
            )
    
    try:
        selected_feeds = load_selected_feeds()
        with app_state["lock"]:
            app_state["news"] = fetch_rss_feeds(selected_feeds)
            app_state["last_fetch_time"] = now
            # Не очищаем seen_news при обновлении - пользователь сам управляет просмотренными
        return RedirectResponse(url="/?sort=date", status_code=303)
    except Exception as e:
        return RedirectResponse(
            url=f"/?notify=Ошибка загрузки: {str(e)}", 
            status_code=303
        )

# Поиск
@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query(..., min_length=1)):
    query = q.strip()
    results = []
    
    with app_state["lock"]:
        for item in app_state["news"]:
            title = item.get("title", "").lower()
            desc = item.get("desc", "").lower()
            source = item.get("sourceName", "").lower()
            
            if query.lower() in title or query.lower() in desc or query.lower() in source:
                results.append(item)
    
    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "query": query,
        "results": results,
        "result_count": len(results),
        "escape_html": escape_html,
        "truncate_text": truncate_text,
        "highlight_text": lambda text: highlight_text(text, query),
    })

# Сохранение статьи
@app.post("/save")
async def save_article_endpoint(link: str = Form(...)):
    try:
        # Ищем статью в кэше
        article = None
        with app_state["lock"]:
            for n in app_state["news"]:
                if n.get("link") == link:
                    article = n
                    break
        
        if not article:
            return RedirectResponse(url=f"/?notify=Статья не найдена", status_code=303)
        
        # Загружаем полный текст
        full_text = fetch_full_text_from_page(link)
        if not full_text:
            return RedirectResponse(url=f"/?notify=Не удалось получить текст статьи", status_code=303)
        
        # Формируем данные для сохранения
        title = article.get("title", "Без названия")
        words = full_text.split()
        preview100 = " ".join(words[:100]) if len(words) > 100 else full_text
        preview_with_title = f"{title}. {preview100}"
        
        article_data = {
            "sourceUrl": link,
            "preview100": preview_with_title,
            "fullText": full_text,
            "savedAt": datetime.now().isoformat(),
            "sourceName": article.get("sourceName", "Неизвестно"),
            "title": title,
        }
        
        # Сохраняем
        if save_article(article_data, link):
            with app_state["lock"]:
                app_state["saved_links"].add(link)
        
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        print(f"Ошибка сохранения статьи: {e}")
        return RedirectResponse(url=f"/?notify=Ошибка при сохранении статьи", status_code=303)

# Статистика
@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    with app_state["lock"]:
        # Статистика по источникам
        news_by_source = {}
        for item in app_state["news"]:
            source = item.get("sourceName", "неизвестно")
            news_by_source[source] = news_by_source.get(source, 0) + 1
        
        # Сортируем по количеству
        sorted_sources = sorted(news_by_source.items(), key=lambda x: x[1], reverse=True)[:20]
        
        # Выбранные источники с количеством новостей
        selected_feeds = load_selected_feeds()
        selected_with_counts = []
        for feed_id in selected_feeds:
            count = sum(1 for n in app_state["news"] if n.get("sourceId") == feed_id)
            selected_with_counts.append({
                "name": get_source_display_name(feed_id),
                "count": count
            })
        
        last_fetch_str = None
        if app_state["last_fetch_time"]:
            last_fetch_str = format_time_ago(app_state["last_fetch_time"])
        
        return templates.TemplateResponse("stats.html", {
            "request": request,
            "total_news": len(app_state["news"]),
            "total_sources": len(ALL_FEEDS),
            "selected_sources": len(selected_feeds),
            "new_count": sum(
                1 for n in app_state["news"] 
                if f"{n.get('link', '')}{n.get('title', '')}" not in app_state["seen_news"]
            ),
            "last_fetch_time": last_fetch_str,
            "news_by_source": sorted_sources,
            "selected_with_counts": selected_with_counts,
        })

# Очистка кэша просмотренных
@app.get("/clear-cache")
async def clear_cache():
    with app_state["lock"]:
        app_state["seen_news"].clear()
    return RedirectResponse(url="/?notify=Просмотренные очищены", status_code=303)

# Сохраненные статьи
@app.get("/saved", response_class=HTMLResponse)
async def saved_news(request: Request, page: int = Query(1, ge=1)):
    saved_articles = load_saved_articles()
    total_items = len(saved_articles)
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_items)
    page_articles = saved_articles[start_idx:end_idx]
    
    return templates.TemplateResponse("saved_news.html", {
        "request": request,
        "articles": page_articles,
        "page": page,
        "total_pages": total_pages,
        "total_items": total_items,
        "escape_html": escape_html,
        "truncate_text": truncate_text,
    })

# Шаблоны HTML (встроенные для удобства развертывания)
def init_templates():
    # Главный шаблон
    index_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>newshub - rss агрегатор</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; color: #333; line-height: 1.6; }
        .container { max-width: 1400px; margin: 0 auto; }
        header { background: #2c3e50; color: white; padding: 25px; border-radius: 8px; margin-bottom: 25px; }
        h1 { margin: 0; font-size: 2em; font-weight: 600; }
        .subtitle { font-size: 1em; opacity: 0.9; margin-top: 8px; color: #bdc3c7; }
        .control-panel { background: white; padding: 20px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
        .control-group { display: flex; flex-direction: column; gap: 10px; }
        .btn { background: #3498db; color: white; border: none; padding: 12px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 500; transition: background 0.3s; text-align: center; text-decoration: none; display: inline-block; }
        .btn:hover { background: #2980b9; }
        .btn-danger { background: #e74c3c; }
        .btn-success { background: #27ae60; }
        .btn-info { background: #9b59b6; }
        input, select { padding: 10px 14px; border: 1px solid #ddd; border-radius: 6px; font-size: 16px; }
        input:focus, select:focus { outline: none; border-color: #3498db; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .stat-card { background: white; padding: 18px; border-radius: 8px; text-align: center; box-shadow: 0 1px 5px rgba(0,0,0,0.05); }
        .stat-number { font-size: 1.8em; font-weight: 700; color: #2c3e50; margin-bottom: 5px; }
        .stat-label { font-size: 0.85em; color: #7f8c8d; text-transform: uppercase; }
        .news-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .news-card { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: box-shadow 0.3s; border: 1px solid #eee; }
        .news-card:hover { box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .news-card.new { border-left: 4px solid #27ae60; }
        .new-badge { position: absolute; top: 12px; right: 12px; background: #27ae60; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; }
        .news-header { padding: 20px; }
        .news-title { font-size: 1.2em; font-weight: 600; color: #2c3e50; margin-bottom: 10px; line-height: 1.4; }
        .news-title a { color: inherit; text-decoration: none; }
        .news-title a:hover { color: #3498db; }
        .news-meta { display: flex; justify-content: space-between; color: #7f8c8d; font-size: 0.85em; margin-top: 12px; }
        .news-source { background: #ecf0f1; padding: 2px 8px; border-radius: 3px; font-weight: 500; }
        .news-body { padding: 0 20px 20px; }
        .news-desc { color: #34495e; line-height: 1.6; font-size: 0.95em; }
        .pagination {
            display: flex;
            justify-content: center;
            gap: 6px;
            margin: 30px 0;
            flex-wrap: wrap;
            max-width: 100%;
            overflow-x: auto;
        }
        .page-btn { padding: 8px 14px; background: white; border: 1px solid #ddd; border-radius: 4px; text-decoration: none; color: #2c3e50; font-weight: 500; transition: all 0.2s; }
        .page-btn:hover { background: #f8f9fa; }
        .page-btn.active { background: #3498db; color: white; border-color: #3498db; }
        .filters { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; align-items: center; }
        .filter-tag { background: #ecf0f1; padding: 6px 14px; border-radius: 16px; text-decoration: none; color: #2c3e50; font-size: 0.9em; transition: background 0.2s; }
        .filter-tag:hover { background: #d5dbdb; }
        .filter-tag.active { background: #3498db; color: white; }
        @media (max-width: 768px) { 
            .news-grid { grid-template-columns: 1fr; } 
            .control-panel { grid-template-columns: 1fr; } 
            h1 { font-size: 1.6em; } 
        }
    </style>
    <script>
        // Автообновление каждые 5 минут
        setTimeout(() => {
            document.getElementById('refresh-btn').click();
        }, 300000);
        
        // Обработка уведомлений
        const urlParams = new URLSearchParams(window.location.search);
        const notify = urlParams.get('notify');
        if (notify) {
            alert(notify);
            // Убираем параметр из URL
            const newUrl = window.location.pathname;
            window.history.replaceState({}, document.title, newUrl);
        }
    </script>
</head>
<body>
<div class='container'>
    <header>
        <h1>newshub</h1>
        <div class='subtitle'>агрегатор rss новостей с выбором источников</div>
    </header>
    
    <div class='control-panel'>
        <div class='control-group'>
            <form action='/fetch' method='post' style='margin: 0;'>
                <button type='submit' class='btn' id='refresh-btn'>
                    {% if last_fetch_time == None %}загрузить новости{% else %}обновить новости{% endif %}
                </button>
                <a href='/saved' class='btn btn-info'>сохранённые новости</a>
                {% if last_fetch_time %}
                <small style='display: block; margin-top: 8px; color: #7f8c8d;'>
                    последнее обновление: {{ last_fetch_time }}
                </small>
                {% endif %}
            </form>
            <a href='/stats' class='btn btn-success'>статистика</a>
        </div>
        <div class='control-group'>
            <form action='/search' method='get' style='display: flex; gap: 10px;'>
                <input type='text' name='q' placeholder='поиск новостей...' style='flex: 1;'>
                <button type='submit' class='btn'>поиск</button>
            </form>
        </div>
        <div class='control-group'>
            <a href='/select-sources' class='btn btn-info'>выбрать источники</a>
            <a href='/add-custom-feed' class='btn btn-success'>добавить свой rss</a>
        </div>
    </div>
    
    <div class='stats'>
        <div class='stat-card'>
            <div class='stat-number'>{{ total_news }}</div>
            <div class='stat-label'>всего новостей</div>
        </div>
        <div class='stat-card'>
            <div class='stat-number'>{{ selected_feeds_count }}</div>
            <div class='stat-label'>выбрано источников</div>
        </div>
        <div class='stat-card'>
            <div class='stat-number'>{{ active_sources_count }}</div>
            <div class='stat-label'>активных источников</div>
        </div>
        <div class='stat-card'>
            <div class='stat-number'>{{ new_count }}</div>
            <div class='stat-label'>новых</div>
        </div>
    </div>
    
    <div class='filters'>
        <span style='font-weight:600'>сортировка:</span>
        <a href='/?sort=date{% if source %}&source={{ source }}{% endif %}' 
           class='filter-tag {% if sort == "date" %}active{% endif %}'>по дате</a>
        <a href='/?sort=title{% if source %}&source={{ source }}{% endif %}' 
           class='filter-tag {% if sort == "title" %}active{% endif %}'>по названию</a>
        <a href='/?sort=source{% if source %}&source={{ source }}{% endif %}' 
           class='filter-tag {% if sort == "source" %}active{% endif %}'>по источнику</a>
        <div style='margin-left: auto;'></div>
        <span style='font-weight:600'>источники:</span>
        <a href='/' class='filter-tag {% if source == None %}active{% endif %}'>все</a>
        {% for src in unique_sources %}
        <a href='/?source={{ src }}' 
           class='filter-tag {% if source == src %}active{% endif %}'>
            {{ get_source_display_name(src) }}
        </a>
        {% endfor %}
    </div>
    
    <div class='news-grid'>
        {% if not news %}
        <div style='grid-column: 1/-1; text-align: center; padding: 40px 20px;'>
            <h2 style='color: #7f8c8d; margin-bottom: 15px;'>новостей нет</h2>
            <p style='color: #95a5a6; max-width: 500px; margin: 0 auto;'>
                нажмите кнопку загрузить новости чтобы получить новости из выбранных источников
            </p>
        </div>
        {% else %}
        {% for item in news %}
        {% set news_id = item.link + item.title %}
        {% set is_new = is_new(item) %}
        {% set is_saved = is_saved(item) %}
        <div class='news-card {% if is_new %}new{% endif %}'>
            {% if is_new %}
            <div class='new-badge'>новое</div>
            {% endif %}
            <div class='news-header'>
                <h3 class='news-title'>
                    <a href='{{ item.link }}' target='_blank'>
                        {{ escape_html(item.title) }}
                    </a>
                </h3>
                <div class='news-meta'>
                    <span class='news-source'>{{ item.sourceName }}</span>
                    <span>{{ item.date }}</span>
                </div>
            </div>
            <div class='news-body'>
                <p class='news-desc'>
                    {{ truncate_text(escape_html(item.desc), 200) }}
                </p>
                {% if not is_saved %}
                <form action='/save' method='post'>
                    <input type='hidden' name='link' value='{{ item.link }}'>
                    <button type='submit' class='btn btn-success'>сохранить статью</button>
                </form>
                {% else %}
                <div style='color:#27ae60;font-weight:600;'>статья сохранена</div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
        {% endif %}
    </div>
    
    {% if total_pages > 1 %}
    <div class='pagination'>
        {% for i in range(1, total_pages + 1) %}
        <a href='/?page={{ i }}{% if sort %}&sort={{ sort }}{% endif %}{% if source %}&source={{ source }}{% endif %}' 
           class='page-btn {% if i == page %}active{% endif %}'>{{ i }}</a>
        {% endfor %}
    </div>
    {% endif %}
    
    <div style='text-align: center; color: #95a5a6; font-size: 0.85em; margin-top: 30px;'>
        newshub v2.1 • выбрано источников: {{ selected_feeds_count }} • 
        <a href='/clear-cache' style='color: #7f8c8d;'>очистить просмотренные</a>
    </div>
</div>
</body>
</html>
"""
    
    # Шаблон выбора источников
    select_sources_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>выбор источников</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 25px; max-width: 1200px; margin: 0 auto; }
        h1 { color: #2c3e50; }
        .back-btn { display: inline-block; margin-bottom: 15px; text-decoration: none; color: #3498db; font-weight: 600; }
        .sources-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .source-group { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid #eee; }
        .group-title { font-size: 1.1em; margin-bottom: 12px; color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 8px; }
        .source-item { margin: 8px 0; padding: 8px; border-radius: 6px; background: #f8f9fa; display: flex; align-items: center; gap: 10px; }
        .source-item:hover { background: #e9ecef; }
        .source-name { flex: 1; }
        input[type='checkbox'] { transform: scale(1.2); }
        .btn { background: #3498db; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 500; }
    </style>
    <script>
        function updateCounter() {
            const checked = document.querySelectorAll('input[type=checkbox]:checked').length;
            document.getElementById('selected-count').textContent = checked;
        }
        
        function selectAll() {
            document.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = true);
            updateCounter();
        }
        
        function deselectAll() {
            document.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = false);
            updateCounter();
        }
    </script>
</head>
<body>
    <a href='/' class='back-btn'>на главную</a>
    <h1>выбор источников новостей</h1>
    <p>отметьте источники которые хотите использовать. выбрано: <strong id='selected-count'>{{ selected_count }}</strong></p>
    
    <form action='/update-sources' method='post' id='sources-form'>
        {% for category, feeds in categorized.items() %}
        <div class='source-group'>
            <div class='group-title'>{{ category }} ({{ feeds|length }})</div>
            {% for feed in feeds %}
            <div class='source-item'>
                <input type='checkbox' id='{{ feed.id }}' name='source' value='{{ feed.id }}' 
                       onchange='updateCounter()' {% if feed.checked %}checked{% endif %}>
                <label for='{{ feed.id }}' class='source-name'>{{ feed.name }}</label>
            </div>
            {% endfor %}
        </div>
        {% endfor %}
        
        <div style='margin-top: 25px;'>
            <button type='submit' class='btn'>сохранить выбор</button>
            <button type='button' class='btn' onclick="selectAll()">выбрать все</button>
            <button type='button' class='btn' onclick="deselectAll()">очистить все</button>
        </div>
    </form>
</body>
</html>
"""
    
    # Шаблон добавления кастомного источника
    add_custom_feed_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>добавить свой rss</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 30px; max-width: 600px; margin: 0 auto; }
        h1 { color: #2c3e50; }
        .back-btn { display: inline-block; margin-bottom: 15px; text-decoration: none; color: #3498db; font-weight: 600; }
        form { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 6px; }
        .btn { background: #3498db; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 16px; }
    </style>
</head>
<body>
    <a href='/' class='back-btn'>на главную</a>
    <h1>добавить свой rss источник</h1>
    <form action='/add-custom-feed' method='post'>
        <input type='text' name='name' placeholder='название источника' required>
        <br>
        <input type='url' name='url' placeholder='https://example.com/rss' pattern='https?://.+' required>
        <br>
        <button type='submit' class='btn'>добавить источник</button>
    </form>
</body>
</html>
"""
    
    # Шаблон результатов поиска
    search_results_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>результаты поиска</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 25px; max-width: 1000px; margin: 0 auto; }
        .back-btn { display: inline-block; margin-bottom: 15px; text-decoration: none; color: #3498db; font-weight: 600; }
        .result-count { color: #7f8c8d; margin-bottom: 20px; }
        .news-item { border: 1px solid #eee; padding: 18px; margin: 12px 0; border-radius: 6px; }
        .news-title { font-size: 1.2em; margin-bottom: 8px; }
        .news-desc { color: #34495e; }
        mark { background: #fffacd; padding: 1px; }
    </style>
</head>
<body>
    <a href='/' class='back-btn'>на главную</a>
    <h1>результаты поиска</h1>
    <div class='result-count'>
        найдено <strong>{{ result_count }}</strong> новостей по запросу: <strong>{{ query }}</strong>
    </div>
    
    {% if not results %}
    <p style='color: #7f8c8d; text-align: center; padding: 30px;'>ничего не найдено</p>
    {% else %}
    {% for item in results %}
    <div class='news-item'>
        <h3 class='news-title'>
            <a href='{{ item.link }}' target='_blank'>
                {{ highlight_text(item.title) }}
            </a>
        </h3>
        <div style='color: #7f8c8d; font-size: 0.85em; margin-bottom: 8px;'>
            {{ item.sourceName }} • {{ item.date }}
        </div>
        <p class='news-desc'>{{ highlight_text(truncate_text(item.desc, 300)) }}</p>
    </div>
    {% endfor %}
    {% endif %}
</body>
</html>
"""
    
    # Шаблон статистики
    stats_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>статистика newshub</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 25px; max-width: 1000px; margin: 0 auto; }
        h1 { color: #2c3e50; }
        .back-btn { display: inline-block; margin-bottom: 15px; text-decoration: none; color: #3498db; font-weight: 600; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }
        .stat-box { background: white; padding: 18px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid #eee; }
        .stat-title { font-size: 1.1em; margin-bottom: 12px; color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 8px; }
        .source-item { display: flex; justify-content: space-between; margin: 6px 0; padding: 4px 0; border-bottom: 1px solid #f8f9fa; }
    </style>
</head>
<body>
    <a href='/' class='back-btn'>на главную</a>
    <h1>статистика newshub</h1>
    
    <div class='stats-grid'>
        <div class='stat-box'>
            <div class='stat-title'>общая статистика</div>
            <p><strong>всего новостей:</strong> {{ total_news }}</p>
            <p><strong>доступно источников:</strong> {{ total_sources }}</p>
            <p><strong>выбрано источников:</strong> {{ selected_sources }}</p>
            <p><strong>новых/непросмотренных:</strong> {{ new_count }}</p>
            {% if last_fetch_time %}
            <p><strong>последнее обновление:</strong> {{ last_fetch_time }}</p>
            {% endif %}
        </div>
        
        <div class='stat-box'>
            <div class='stat-title'>распределение по источникам</div>
            {% for source, count in news_by_source %}
            <div class='source-item'>
                <span>{{ source }}</span>
                <span><strong>{{ count }}</strong></span>
            </div>
            {% endfor %}
        </div>
        
        <div class='stat-box'>
            <div class='stat-title'>выбранные источники</div>
            {% for item in selected_with_counts %}
            <div class='source-item'>
                <span>{{ item.name }}</span>
                <span><strong>{{ item.count }}</strong></span>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""
    
    # Шаблон сохраненных новостей
    saved_news_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>сохранённые новости</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; color: #333; line-height: 1.6; }
        .container { max-width: 1400px; margin: 0 auto; }
        header { background: #2c3e50; color: white; padding: 25px; border-radius: 8px; margin-bottom: 25px; }
        h1 { margin: 0; font-size: 2em; font-weight: 600; }
        .subtitle { font-size: 1em; opacity: 0.9; margin-top: 8px; color: #bdc3c7; }
        .news-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .news-card { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: box-shadow 0.3s; border: 1px solid #eee; }
        .news-card:hover { box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .news-header { padding: 20px; }
        .news-title { font-size: 1.2em; font-weight: 600; color: #2c3e50; margin-bottom: 10px; line-height: 1.4; }
        .news-title a { color: inherit; text-decoration: none; }
        .news-title a:hover { color: #3498db; }
        .news-meta { display: flex; justify-content: space-between; color: #7f8c8d; font-size: 0.85em; margin-top: 12px; }
        .news-body { padding: 0 20px 20px; }
        .news-desc { color: #34495e; line-height: 1.6; font-size: 0.95em; }
        .pagination { 
            display: flex; 
            justify-content: center; 
            gap: 6px; 
            margin: 30px 0; 
            flex-wrap: wrap; 
            max-width: 100%; 
            overflow-x: auto; 
        }
        .page-btn { 
            padding: 8px 14px; 
            background: white; 
            border: 1px solid #ddd; 
            border-radius: 4px; 
            text-decoration: none; 
            color: #2c3e50; 
            font-weight: 500; 
            transition: all 0.2s; 
        }
        .page-btn:hover { background: #f8f9fa; }
        .page-btn.active { background: #3498db; color: white; border-color: #3498db; }
    </style>
</head>
<body>
<div class='container'>
    <header>
        <h1>Сохранённые новости</h1>
        <div class='subtitle'>просмотр сохранённых статей</div>
    </header>
    
    <div class='news-grid'>
        {% if not articles %}
        <div style='grid-column: 1/-1; text-align: center; padding: 40px 20px;'>
            <h2 style='color: #7f8c8d; margin-bottom: 15px;'>нет сохранённых статей</h2>
            <p style='color: #95a5a6; max-width: 500px; margin: 0 auto;'>
                сначала сохраните статьи на главной странице
            </p>
        </div>
        {% else %}
        {% for item in articles %}
        <div class='news-card'>
            <div class='news-header'>
                <h3 class='news-title'>
                    <a href='{{ item.sourceUrl }}' target='_blank'>
                        {{ escape_html(item.preview100) }}
                    </a>
                </h3>
                <div class='news-meta'>
                    <span class='news-source'>сохранено {{ item.savedAt[:10] if item.savedAt else "" }}</span>
                </div>
            </div>
            <div class='news-body'>
                <p class='news-desc'>
                    {{ truncate_text(escape_html(item.fullText), 300) }}
                </p>
            </div>
        </div>
        {% endfor %}
        {% endif %}
    </div>
    
    {% if total_pages > 1 %}
    <div class='pagination'>
        {% for i in range(1, total_pages + 1) %}
        <a href='/saved?page={{ i }}' class='page-btn {% if i == page %}active{% endif %}'>{{ i }}</a>
        {% endfor %}
    </div>
    {% endif %}
    
    <div style='text-align: center; color: #95a5a6; font-size: 0.85em; margin-top: 30px;'>
        <a href='/' style='color: #7f8c8d;'>на главную</a>
    </div>
</div>
</body>
</html>
"""
    
    # Сохраняем шаблоны
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    (templates_dir / "index.html").write_text(index_template, encoding="utf-8")
    (templates_dir / "select_sources.html").write_text(select_sources_template, encoding="utf-8")
    (templates_dir / "add_custom_feed.html").write_text(add_custom_feed_template, encoding="utf-8")
    (templates_dir / "search_results.html").write_text(search_results_template, encoding="utf-8")
    (templates_dir / "stats.html").write_text(stats_template, encoding="utf-8")
    (templates_dir / "saved_news.html").write_text(saved_news_template, encoding="utf-8")

# Инициализация шаблонов при запуске
init_templates()

if __name__ == "__main__":
    import uvicorn
    print("NewsHub запущен")
    print("Основа: http://localhost:8000")
    print("Выбор источников: http://localhost:8000/select-sources")
    print("Статистика: http://localhost:8000/stats")
    uvicorn.run(app, host="0.0.0.0", port=8000)
