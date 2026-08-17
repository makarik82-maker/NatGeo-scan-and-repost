#!/usr/bin/env python3
"""
🌍 Telegram Nature Bot — генерирует и публикует посты о природе и планете.
Использует прямые запросы к GigaChat API v1.
Генерирует РЕЛЕВАНТНЫЕ изображения на основе темы поста.
Реализует круговой обход топиков без повторов.
"""

import os
import sys
import json
import uuid
import random
import logging
import urllib3
from datetime import datetime, timezone
from pathlib import Path

import requests

# Подавляем предупреждения о непроверенных HTTPS-запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ──────────────────────────── Настройки ───────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
GIGACHAT_CREDENTIALS = os.environ.get("GIGACHAT_CREDENTIALS", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

STATE_FILE = Path("used_topics.json")
TOPICS_FILE = Path("topics.json")

VERIFY_SSL = False

# ──────────────────── Загрузка топиков из файла ────────────────────

def load_topics() -> list:
    if not TOPICS_FILE.exists():
        logger.error("Файл %s не найден!", TOPICS_FILE)
        sys.exit(1)

    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            topics = json.load(f)
            if not isinstance(topics, list) or len(topics) == 0:
                logger.error("Файл %s должен содержать непустой массив строк", TOPICS_FILE)
                sys.exit(1)
            logger.info("Загружено %d топиков из %s", len(topics), TOPICS_FILE)
            return topics
    except Exception as e:
        logger.error("Не удалось загрузить %s: %s", TOPICS_FILE, e)
        sys.exit(1)

# ──────────────── Фолбэк: база готовых фактов ─────────────────────

FALLBACK_POSTS = [
    "🌊 **Знаете ли вы?**\n\nОкеан покрывает более 70% поверхности Земли, но мы исследовали менее 5% его глубин.\n\n#океан #природа #планета",
    "🍄 **Удивительный факт**\n\nПод лесом скрывается гигантская грибная сеть — микориза.\n\n#лес #грибы #экология",
]

# ──────────────────── Управление состоянием ────────────────────────

def load_used_topics() -> list:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("used_topics", [])
        except Exception as e:
            logger.warning("Не удалось загрузить %s: %s", STATE_FILE, e)
    return []

def save_used_topics(used_topics: list):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"used_topics": used_topics}, f, ensure_ascii=False, indent=2)
        logger.info("Состояние сохранено: использовано %d топиков", len(used_topics))
    except Exception as e:
        logger.error("Не удалось сохранить %s: %s", STATE_FILE, e)

def get_next_topic(topics: list) -> str:
    used_topics = load_used_topics()
    available_topics = [t for t in topics if t not in used_topics]

    if not available_topics:
        logger.info("🔄 Все %d топиков использованы! Начинаем по кругу.", len(topics))
        used_topics = []
        available_topics = topics.copy()

    selected_topic = random.choice(available_topics)
    logger.info("Выбран топик: %s", selected_topic)

    used_topics.append(selected_topic)
    save_used_topics(used_topics)
    return selected_topic

# ──────────────────────── GigaChat Token ──────────────────────────

def get_gigachat_token() -> str | None:
    """Получает OAuth-токен GigaChat."""
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGACHAT_CREDENTIALS}",
    }
    data = {"scope": "GIGACHAT_API_PERS"}

    try:
        response = requests.post(url, headers=headers, data=data, verify=VERIFY_SSL, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        logger.error("Ошибка получения токена GigaChat: %s", e)
        return None

# ──────────────────────── Генерация текста поста ──────────────────

def generate_post_ai(topic: str, access_token: str) -> tuple[str, str] | None:
    """
    Генерирует пост через GigaChat API.
    Возвращает кортеж: (текст_поста, промпт_для_картинки)
    """
    if not access_token:
        logger.warning("GIGACHAT_CREDENTIALS не задан — использую фолбэк.")
        return None

    prompt = f"""Ты — автор популярного Telegram-канала о природе и планете Земля.
Напиши один пост на тему: «{topic}».

Требования:
- Язык: русский.
- Длина: 3–6 предложений (не более 800 символов).
- Стиль: живой, увлекательный, научно-популярный.
- Начни с подходящего эмодзи и цепляющего заголовка жирным шрифтом (**заголовок**).
- В конце добавь 2–4 хештега через пробел.
- Не добавляй вступлений вроде «Конечно!» — сразу пост.

В конце ответа добавь строку:
IMAGE_PROMPT: [краткое описание на английском для генерации картинки, 3-5 слов]"""

    url = "https://api.giga.chat/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    
    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": "Ты — талантливый научпоп-автор Telegram-канала о природе."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 500,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=VERIFY_SSL, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        full_text = result["choices"][0]["message"]["content"].strip()
        
        # Извлекаем промпт для картинки
        image_prompt = topic  # По умолчанию используем топик
        
        if "IMAGE_PROMPT:" in full_text:
            parts = full_text.split("IMAGE_PROMPT:")
            full_text = parts[0].strip()
            image_prompt = parts[1].strip() if len(parts) > 1 else topic
        
        logger.info("Пост сгенерирован успешно (%d символов).", len(full_text))
        logger.info("Промпт для картинки: %s", image_prompt)
        
        return full_text, image_prompt
    
    except Exception as e:
        logger.error("Ошибка генерации через GigaChat: %s", e)
        return None

# ─────────────────────── Генерация изображения ───────────────────

def generate_image_from_gigachat(image_prompt: str, access_token: str) -> str | None:
    """Генерирует изображение через GigaChat API."""
    logger.info("Генерирую изображение по запросу: %s", image_prompt)
    
    # Улучшаем промпт для лучшего качества
    enhanced_prompt = f"Photorealistic nature photography: {image_prompt}, high quality, detailed, professional, 4K"
    
    url = "https://api.giga.chat/v1/files"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    
    payload = {
        "model": "GigaChat-2-Images",
        "prompt": enhanced_prompt,
        "size": "1024x1024",
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, verify=VERIFY_SSL, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        file_id = result.get("id")
        
        if not file_id:
            logger.error("GigaChat не вернул file_id для изображения")
            return None
        
        # Скачиваем сгенерированное изображение
        download_url = f"https://api.giga.chat/v1/files/{file_id}/content"
        img_response = requests.get(
            download_url, 
            headers={"Authorization": f"Bearer {access_token}"}, 
            verify=VERIFY_SSL, 
            timeout=30
        )
        img_response.raise_for_status()
        
        # Сохраняем во временный файл
        temp_file = Path("temp_image.jpg")
        with open(temp_file, "wb") as f:
            f.write(img_response.content)
        
        logger.info("✅ Изображение сгенерировано и сохранено.")
        return str(temp_file)
    
    except Exception as e:
        logger.error("Ошибка генерации изображения: %s", e)
        return None


def download_image_from_unsplash(query: str) -> str | None:
    """Скачивает релевантное фото с Unsplash по ключевому слову."""
    if not UNSPLASH_ACCESS_KEY:
        logger.warning("UNSPLASH_ACCESS_KEY не задан — пропускаем Unsplash.")
        return None
    
    url = "https://api.unsplash.com/photos/random"
    params = {
        "query": query,
        "orientation": "landscape",
        "client_id": UNSPLASH_ACCESS_KEY,
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        image_url = data["urls"]["regular"]
        
        # Скачиваем изображение
        img_response = requests.get(image_url, timeout=15)
        img_response.raise_for_status()
        
        temp_file = Path("temp_image.jpg")
        with open(temp_file, "wb") as f:
            f.write(img_response.content)
        
        logger.info("✅ Фото загружено с Unsplash: %s", query)
        return str(temp_file)
    
    except Exception as e:
        logger.error("Ошибка загрузки фото с Unsplash: %s", e)
        return None


def get_relevant_image(topic: str, access_token: str | None) -> str | None:
    """
    Получает релевантное теме изображение.
    Приоритет: 1) GigaChat генерация, 2) Unsplash поиск.
    """
    if not access_token:
        logger.warning("Нет токена GigaChat — пробуем Unsplash.")
        return download_image_from_unsplash(topic)
    
    # Пробуем сгенерировать через GigaChat
    image_path = generate_image_from_gigachat(topic, access_token)
    
    if image_path:
        return image_path
    
    # Fallback на Unsplash
    logger.info("GigaChat не сгенерировал — пробуем Unsplash.")
    return download_image_from_unsplash(topic)

# ──────────────────────── Отправка в Telegram ──────────────────────

def send_photo_to_telegram(photo_path: str, caption: str) -> bool:
    """Отправляет фото с подписью в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы!")
        return False
    
    url = f"{TELEGRAM_API}/sendPhoto"
    
    try:
        with open(photo_path, "rb") as photo_file:
            files = {"photo": photo_file}
            data = {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            resp = requests.post(url, files=files, data=data, timeout=30)
            resp.raise_for_status()
        
        logger.info("✅ Фото с постом успешно отправлено в %s", TELEGRAM_CHANNEL_ID)
        
        # Удаляем временный файл
        try:
            Path(photo_path).unlink()
        except Exception:
            pass
        
        return True
    
    except Exception as e:
        logger.error("❌ Ошибка отправки фото: %s", e)
        return False


def send_text_to_telegram(text: str) -> bool:
    """Отправляет текстовое сообщение в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы!")
        return False

    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        logger.info("✅ Текстовый пост успешно отправлен в %s", TELEGRAM_CHANNEL_ID)
        return True
    except requests.HTTPError as e:
        logger.error("❌ Ошибка Telegram API: %s — %s", resp.status_code, resp.text)
        if resp.status_code == 400 and "can't parse entities" in resp.text:
            logger.info("Повтор без Markdown...")
            payload["parse_mode"] = None
            resp2 = requests.post(url, json=payload, timeout=30)
            if resp2.ok:
                logger.info("✅ Пост отправлен (без форматирования).")
                return True
        return False
    except Exception as e:
        logger.error(" Неизвестная ошибка: %s", e)
        return False

# ──────────────────────────── Main ─────────────────────────────────

def main():
    logger.info("🚀 Запуск Nature Telegram Bot (GigaChat v1 + Images) — %s", datetime.now(timezone.utc).isoformat())
    
    topics = load_topics()
    topic = get_next_topic(topics)
    
    # Получаем токен GigaChat
    access_token = get_gigachat_token()
    
    # Генерируем текст поста И промпт для картинки
    result = generate_post_ai(topic, access_token)
    
    if not result:
        # Fallback на готовый пост
        post_text = random.choice(FALLBACK_POSTS)
        image_prompt = topic
    else:
        post_text, image_prompt = result
    
    logger.info("Содержимое поста:\n%s", post_text)
    
    # Получаем релевантное изображение
    image_path = None
    if access_token or UNSPLASH_ACCESS_KEY:
        image_path = get_relevant_image(image_prompt, access_token)
    
    # Отправляем пост (с фото или без)
    if image_path and Path(image_path).exists():
        success = send_photo_to_telegram(image_path, post_text)
    else:
        logger.warning("Изображение не получено — отправляю только текст.")
        success = send_text_to_telegram(post_text)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
