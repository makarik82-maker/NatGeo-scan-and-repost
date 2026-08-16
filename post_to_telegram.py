#!/usr/bin/env python3
"""
🌍 Telegram Nature Bot — генерирует и публикует посты о природе и планете.
Использует прямые запросы к GigaChat API v1 (проверенный метод).
Реализует круговой обход топиков без повторов.
"""

import os
import sys
import json
import uuid
import random
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

# ──────────────────────────── Настройки ────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
GIGACHAT_CREDENTIALS = os.environ.get("GIGACHAT_CREDENTIALS", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

STATE_FILE = Path("used_topics.json")
TOPICS_FILE = Path("topics.json")

VERIFY_SSL = False  # Как в вашем рабочем скрипте

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
    "🌊 **Знаете ли вы?**\n\nОкеан покрывает более 70% поверхности Земли, но мы исследовали менее 5% его глубин. В Марианской впадине давление в 1000 раз выше, чем на поверхности — и там всё равно есть жизнь!\n\n#океан #природа #планета",
    "🍄 **Удивительный факт**\n\nПод лесом скрывается гигантская грибная сеть — микориза. Деревья обмениваются через неё питательными веществами и даже «предупреждают» соседей об опасности. Учёные называют её Wood Wide Web.\n\n#лес #грибы #экология",
    "🐝 **Без них мы голодны**\n\nОколо 75% мировых продовольственных культур зависят от опыления. Пчёлы, бабочки и даже летучие мыши — невидимые герои нашего стола.\n\n#опылители #пчёлы #природа",
    "🌋 **Вулканы — не только разрушение**\n\nВулканический пепел обогащает почву минералами. Именно благодаря вулканам острова вроде Исландии и Гавайев покрыты буйной растительностью.\n\n#вулканы #геология #планета",
    "🐋 **Песни океана**\n\nГорбатые киты поют сложные песни, которые длятся часами и распространяются на тысячи километров. Каждый год их мелодии меняются.\n\n#киты #океан #животные",
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

# ──────────────────────── Генерация поста (ПРЯМОЙ API) ────────────

def get_gigachat_token() -> str | None:
    """Получает OAuth-токен GigaChat (как в рабочем скрипте)."""
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

def generate_post_ai(topic: str) -> str | None:
    """Генерирует пост через прямой запрос к GigaChat API v1."""
    if not GIGACHAT_CREDENTIALS:
        logger.warning("GIGACHAT_CREDENTIALS не задан — использую фолбэк.")
        return None

    access_token = get_gigachat_token()
    if not access_token:
        return None

    prompt = f"""Ты — автор популярного Telegram-канала о природе и планете Земля.
Напиши один пост на тему: «{topic}».

Требования:
- Язык: русский.
- Длина: 3–6 предложений (не более 800 символов).
- Стиль: живой, увлекательный, научно-популярный. Избегай клише.
- Начни с подходящего эмодзи и цепляющего заголовка жирным шрифтом (**заголовок**).
- В конце добавь 2–4 хештега через пробел.
- Не используй Markdown-ссылки, только жирный шрифт и эмодзи.
- Не добавляй вступлений вроде «Конечно!» — сразу пост."""

    url = "https://api.giga.chat/v1/chat/completions" # ЯВНО УКАЗАН v1
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    
    # ВАЖНО: Используем модель "GigaChat-2", как в вашем рабочем скрипте
    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": "Ты — талантливый научпоп-автор Telegram-канала о природе."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 400,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=VERIFY_SSL, timeout=30)
        response.raise_for_status()
        
        # Парсим ответ в формате OpenAI-compatible
        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()
        
        logger.info("Пост сгенерирован успешно (%d символов).", len(text))
        return text
    except Exception as e:
        logger.error("Ошибка генерации через GigaChat: %s", e)
        if 'response' in locals():
            logger.error("Ответ сервера: %s", response.text[:500])
        return None

def generate_post(topics: list) -> str:
    topic = get_next_topic(topics)
    post = generate_post_ai(topic)
    return post if post else random.choice(FALLBACK_POSTS)

# ──────────────────────── Отправка в Telegram ──────────────────────

def send_to_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы!")
        sys.exit(1)

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
        logger.info("✅ Пост успешно отправлен в %s", TELEGRAM_CHANNEL_ID)
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
        logger.error("❌ Неизвестная ошибка: %s", e)
        return False

# ──────────────────────────── Main ─────────────────────────────────

def main():
    logger.info("🚀 Запуск Nature Telegram Bot (GigaChat v1 Direct) — %s", datetime.now(timezone.utc).isoformat())
    topics = load_topics()
    post = generate_post(topics)
    logger.info("Содержимое поста:\n%s", post)
    success = send_to_telegram(post)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
