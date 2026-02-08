import requests
from bs4 import BeautifulSoup
import json
import time
import logging
from typing import Dict, Optional, List
from urllib.parse import urljoin, urlparse
import re
import subprocess
import sys
import atexit
import socket

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebContentAnalyzer:
    """Анализатор веб-контента с интеграцией Ollama Mistral 8B"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip('/')
        self.ollama_process = None
        self.model_name = "mistral:8b-instruct-q4_K_M"
        
        # Автоматический запуск сервера Ollama при необходимости
        self._ensure_ollama_running()
        
        # Проверка подключения и модели
        self._check_ollama_connection()
        
        # Настройка сессии для запросов
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Регистрация завершения процесса при выходе
        atexit.register(self._cleanup)

    def _is_port_open(self, host: str = "localhost", port: int = 11434, timeout: float = 1.0) -> bool:
        """Проверка, открыт ли порт"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect((host, port))
                return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                return False

    def _ensure_ollama_running(self):
        """Проверка и запуск сервера Ollama при необходимости"""
        if self._is_port_open():
            logger.info("✅ Ollama сервер уже запущен")
            return

        logger.info("🔍 Ollama сервер не обнаружен. Попытка запуска...")
        
        # Определение команды в зависимости от ОС
        if sys.platform == "win32":
            cmd = ["ollama", "serve"]
        else:
            cmd = ["ollama", "serve"]
        
        try:
            # Запуск в фоновом режиме
            self.ollama_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True if sys.platform != "win32" else False
            )
            logger.info("🚀 Запущен процесс Ollama (PID: %d)", self.ollama_process.pid)
            
            # Ожидание запуска сервера
            for i in range(15):
                time.sleep(1)
                if self._is_port_open():
                    logger.info("✅ Ollama сервер готов к работе")
                    return
                logger.debug("⏳ Ожидание запуска Ollama (%d/15)...", i + 1)
            
            raise TimeoutError("Ollama не запустился за 15 секунд")
        
        except FileNotFoundError:
            logger.error(
                "❌ Команда 'ollama' не найдена. Установите Ollama:\n"
                "   • Linux/macOS: https://ollama.com/download\n"
                "   • Windows: скачайте установщик с сайта"
            )
            sys.exit(1)
        except Exception as e:
            logger.error("❌ Ошибка запуска Ollama: %s", e)
            sys.exit(1)

    def _check_ollama_connection(self):
        """Проверка доступности Ollama и наличия модели"""
        try:
            # Ожидание полной инициализации сервера
            for i in range(5):
                try:
                    response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
                    if response.status_code == 200:
                        break
                except:
                    time.sleep(2)
            else:
                raise ConnectionError("Не удалось подключиться к Ollama API")

            models = [m['name'] for m in response.json().get('models', [])]
            
            if self.model_name not in models:
                logger.warning("Модель '%s' не найдена. Загрузка...", self.model_name)
                try:
                    pull_response = requests.post(
                        f"{self.ollama_url}/api/pull",
                        json={"name": self.model_name},
                        stream=True,
                        timeout=300
                    )
                    pull_response.raise_for_status()
                    
                    # Отслеживание прогресса
                    for line in pull_response.iter_lines():
                        if line:
                            data = json.loads(line)
                            if 'status' in data:
                                logger.info("Загрузка модели: %s", data['status'])
                            if data.get('status') == 'success':
                                break
                    logger.info("✅ Модель успешно загружена")
                except Exception as e:
                    logger.error("Ошибка загрузки модели: %s", e)
                    raise
            else:
                logger.info("✅ Используется модель: %s", self.model_name)
                
        except Exception as e:
            logger.error("Ошибка подключения к Ollama: %s", e)
            raise ConnectionError(
                "Ollama недоступен. Убедитесь, что сервер запущен: `ollama serve`"
            )

    def _cleanup(self):
        """Корректное завершение дочернего процесса Ollama"""
        if self.ollama_process and self.ollama_process.poll() is None:
            logger.info("Завершение процесса Ollama (PID: %d)...", self.ollama_process.pid)
            if sys.platform == "win32":
                self.ollama_process.terminate()
            else:
                self.ollama_process.kill()
            self.ollama_process.wait(timeout=5)
            logger.info("✅ Процесс Ollama завершён")

    def fetch_and_parse(self, url: str, max_length: int = 15000) -> Dict[str, str]:
        """Извлечение полезного контента со страницы"""
        try:
            logger.info("Загрузка страницы: %s", url)
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Удаляем мусор
            for tag in soup.select('script, style, noscript, iframe, embed, header, footer, nav, aside, .ad, .advertisement, .cookie-banner'):
                tag.decompose()
            
            # Извлекаем метаданные
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else self._extract_og_title(soup) or "Без названия"
            
            # Пытаемся найти основной контент
            main_content = (
                soup.find('article') or
                soup.find('main') or
                soup.find('div', class_=re.compile(r'(article|post|content|entry|story)', re.I)) or
                soup.find('div', id=re.compile(r'(article|post|content|entry|story)', re.I)) or
                soup.find('body')
            )
            
            if not main_content:
                raise ValueError("Не удалось найти основной контент на странице")
            
            # Извлекаем текст
            paragraphs = main_content.find_all('p')
            if len(paragraphs) < 3:
                text = main_content.get_text(separator='\n', strip=True)
            else:
                text = '\n\n'.join([
                    p.get_text(strip=True) 
                    for p in paragraphs 
                    if len(p.get_text(strip=True)) > 50
                ])
            
            # Очистка текста
            text = re.sub(r'\s+', ' ', text).strip()
            text = text[:max_length] + ('...' if len(text) > max_length else '')
            
            # Извлекаем изображения
            images = [
                urljoin(url, img['src']) 
                for img in main_content.find_all('img', src=True)
                if self._is_valid_image(img)
            ][:3]
            
            return {
                "url": url,
                "title": title_text,
                "content": text,
                "images": images,
                "domain": urlparse(url).netloc,
                "length": len(text)
            }
            
        except Exception as e:
            logger.error("Ошибка парсинга %s: %s", url, e)
            raise

    def _extract_og_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Извлечение заголовка из Open Graph метатегов"""
        og_title = soup.find('meta', property='og:title')
        return og_title['content'] if og_title and og_title.get('content') else None

    def _is_valid_image(self, img_tag) -> bool:
        """Проверка, что изображение релевантное"""
        src = img_tag.get('src', '')
        if not src:
            return False
        
        # Исключаем технические изображения
        if any(x in src.lower() for x in ['pixel', 'spacer', 'icon', 'logo', 'favicon', 'loader', 'spinner']):
            return False
        
        # Минимальный размер (если указаны атрибуты)
        width = img_tag.get('width', '0')
        height = img_tag.get('height', '0')
        try:
            if int(width) < 100 or int(height) < 100:
                return False
        except:
            pass
        
        return True

    def analyze_with_ollama(
        self, 
        content: Dict[str, str], 
        user_query: str,
        temperature: float = 0.3,
        timeout: int = 120
    ) -> Dict[str, str]:
        """Анализ контента через Mistral 8B в Ollama"""
        try:
            prompt = f"""Ты — эксперт-аналитик. Проанализируй следующую статью и ответь на вопрос пользователя.

ЗАГОЛОВОК СТАТЬИ:
{content['title']}

ТЕКСТ СТАТЬИ:
{content['content']}

ДОМЕН ИСТОЧНИКА: {content['domain']}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{user_query}

Требования к ответу:
1. Даже если текст статьи другой, всё равно отвечай на русском).
2. Будь точным, опирайся ТОЛЬКО на информацию из статьи.
3. Если информации для ответа недостаточно — так и скажи.
4. Выделяй ключевые факты, имена, даты, цифры.
5. Не выдумывай информацию.
6. Структурируй ответ: краткое введение → основные тезисы → вывод."""

            logger.info("Отправка запроса в Ollama (%s)...", self.model_name)
            start_time = time.time()

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": temperature,
                    "options": {
                        "num_ctx": 8192
                    }
                },
                timeout=timeout
            )

            response.raise_for_status()
            result = response.json()

            elapsed = time.time() - start_time
            logger.info("Анализ завершен за %.1f сек", elapsed)

            return {
                "analysis": result.get('response', '').strip(),
                "model": self.model_name,
                "tokens": result.get('eval_count', 0),
                "processing_time_sec": round(elapsed, 1),
                "source_title": content['title'],
                "source_url": content['url']
            }

        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama не ответил за {timeout} секунд. Увеличьте таймаут или упростите запрос.")
        except Exception as e:
            logger.error("Ошибка анализа через Ollama: %s", e)
            raise

    def summarize(self, url: str, style: str = "concise") -> Dict[str, str]:
        """Быстрая суммаризация статьи"""
        content = self.fetch_and_parse(url)

        styles = {
            "concise": "Кратко (2-3 предложения) перескажи суть статьи. Выдели главную мысль.",
            "detailed": "Подробно перескажи статью: основные тезисы, ключевые факты, выводы. Структурируй ответ.",
            "bullet": "Перечисли основные пункты статьи в виде маркированного списка. Каждый пункт — 1 предложение."
        }

        query = styles.get(style, styles["concise"])
        return self.analyze_with_ollama(content, query)

    def extract_facts(self, url: str) -> Dict[str, str]:
        """Извлечение ключевых фактов: даты, имена, цифры, события"""
        content = self.fetch_and_parse(url)
        query = """Извлеки из статьи ВСЕ конкретные факты:
- Даты и временные периоды
- Имена людей, организаций, компаний
- Цифры, суммы, проценты, статистика
- Места событий (города, страны)
- Цитаты ключевых лиц
- Причины и следствия событий

Представь результат в структурированном виде с категориями."""
        return self.analyze_with_ollama(content, query)


# ==================== ПРИМЕР ИСПОЛЬЗОВАНИЯ ====================
def interactive_demo():
    """Интерактивный демо-режим"""
    print("=" * 70)
    print("Web Content Analyzer + Mistral 8B (Ollama с автозапуском)")
    print("=" * 70)
    try:
        analyzer = WebContentAnalyzer()
        
        # Пример 1: Суммаризация
        print("\n📌 Пример 1: Суммаризация статьи")
        url = input("Введите URL статьи (или нажмите Enter для демо): ").strip()
        if not url:
            url = "https://lenta.ru/news/2024/06/15/ai_summit/"
            print(f"Используется демо-ссылка: {url}")
        
        print("\n⏳ Загрузка и парсинг статьи...")
        content = analyzer.fetch_and_parse(url)
        print(f"✅ Заголовок: {content['title']}")
        print(f"📊 Длина текста: {content['length']} символов")
        if content['images']:
            print(f"🖼️  Найдено изображений: {len(content['images'])}")
        
        # Пример 2: Анализ по запросу пользователя
        print("\n🔍 Пример 2: Анализ по вашему запросу")
        user_query = input("Введите запрос для анализа (например: 'Какие выводы делает автор?'): ").strip()
        if not user_query:
            user_query = "Какие основные тезисы и выводы содержит эта статья?"
            print(f"Используется демо-запрос: {user_query}")
        
        print("\n🧠 Анализ через Mistral 8B...")
        result = analyzer.analyze_with_ollama(content, user_query)
        
        print("\n" + "= " * 35)
        print("РЕЗУЛЬТАТ АНАЛИЗА")
        print("= " * 35)
        print(f"\n📄 Источник: {result['source_title']}")
        print(f"🔗 URL: {result['source_url']}")
        print(f"\n💬 Ответ модели ({result['model']}):")
        print("-" * 70)
        print(result['analysis'])
        print("-" * 70)
        print(f"\n⏱️  Обработано за {result['processing_time_sec']} сек | Токенов: {result['tokens']}")
        
        # Пример 3: Быстрая суммаризация
        print("\n" + "= " * 35)
        print("📌 Пример 3: Быстрая суммаризация")
        print("= " * 35)
        summary = analyzer.summarize(url, style="bullet")
        print("\nКраткое содержание:")
        print("-" * 70)
        print(summary['analysis'])
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        print("\n💡 Советы по устранению:")
        print("   1. Убедитесь, что Ollama установлен в системе")
        print("   2. Проверьте интернет-соединение для загрузки страницы")
        print("   3. Убедитесь, что URL корректен и доступен")
    finally:
        print("\n👋 Спасибо за использование анализатора!")


if __name__ == "__main__":
    interactive_demo()
