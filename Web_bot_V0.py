import requests
from bs4 import BeautifulSoup
import os
import time

# URL сайта для парсинга (замените на нужный)
BASE_URL = "https://www.reddit.com/"
# Заголовки для имитации браузера
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
# Папка для сохранения текстовых файлов
OUTPUT_DIR = "scraped_text"

def get_page_content(url):
    """Получает содержимое страницы."""
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Ошибка при запросе {url}: {e}")
        return None

def extract_text(html):
    """Извлекает весь видимый текст со страницы."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Удаляем скрипты, стили и комментарии
    for element in soup(["script", "style", "comment"]):
        element.decompose()
    
    # Извлекаем текст, убирая лишние пробелы
    text = soup.get_text(separator=" ", strip=True)
    return text

def save_text_to_file(text, filename):
    """Сохраняет текст в файл в указанной папке."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    file_path = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Текст сохранен в {file_path}")
    except IOError as e:
        print(f"Ошибка при сохранении файла {file_path}: {e}")

def main():
    # Получаем содержимое страницы
    html = get_page_content(BASE_URL)
    if not html:
        return
    
    # Извлекаем текст
    text = extract_text(html)
    if not text:
        print("Не удалось извлечь текст.")
        return
    
    # Генерируем имя файла (можно настроить, например, по URL или дате)
    filename = "scraped_text.txt"
    
    # Сохраняем текст
    save_text_to_file(text, filename)
    
    # Задержка для предотвращения перегрузки сервера
    time.sleep(1)

if __name__ == "__main__":
    main()
