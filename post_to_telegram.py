#!/usr/bin/env python3
"""
🌍 Telegram Nature Bot — генерирует и публикует посты о природе и планете.
Использует GigaChat от Сбера.
Реализует круговой обход топиков без повторов.
"""

import os
import sys
import json
import random
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from gigachat import GigaChat

# ──────────────────────────── Настройки ────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
GIGACHAT_CREDENTIALS = os.environ.get("GIGACHAT_CREDENTIALS", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

GIGACHAT_MODEL = "GigaChat"

STATE_FILE = Path("used_topics.json")
TOPICS_FILE = Path("topics.json")

# ──────────────────── Загрузка топиков из файла ────────────────────

def load_topics() -> list:
    """Загружает список топиков из файла topics.json."""
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
    "🐝 **Без них мы голодны**\n\nОколо 75% мировых продовольственных культур зависят от опыления. Пчёлы, бабочки и даже летучие мыши — невидимые герои нашего стола. Одна пчелиная семья опыляет до 3 млн цветков в день.\n\n#опылители #пчёлы #природа",
    "🌋 **Вулканы — не только разрушение**\n\nВулканический пепел обогащает почву минералами. Именно благодаря вулканам острова вроде Исландии и Гавайев покрыты буйной растительностью. Разрушение рождает новую жизнь.\n\n#вулканы #геология #планета",
    "🐋 **Песни океана**\n\nГорбатые киты поют сложные песни, которые длятся часами и распространяются на тысячи километров. Каждый год их мелодии меняются — все самцы в популяции подхватывают новую «версию».\n\n#киты #океан #животные",
]

# ──────────────────── Управление состоянием ────────────────────────

def load_used_topics() -> list:
    """Загружает список использованных топиков из файла."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("used_topics", [])
        except Exception as e:
            logger.warning("Не удалось загрузить %s: %s", STATE_FILE, e)
    return []


def save_used_topics(used_topics: list):
    """Сохраняет список использованных топиков в файл."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"used_topics": used_topics}, f, ensure_ascii=False, indent=2)
        logger.info("Состояние сохранено: использовано %d топиков", len(used_topics))
    except Exception as e:
        logger.error("Не удалось сохранить %s: %s", STATE_FILE, e)


def get_next_topic(topics: list) -> str:
    """
    Выбирает следующий топик из неиспользованных.
    Если все топики использованы — сбрасывает список и начинает по кругу.
    """
    used_topics = load_used_topics()

    # Находим неиспользованные топики
    available_topics = [t for t in topics if t not in used_topics]

    # Если все топики использованы — начинаем по кругу
    if not available_topics:
        logger.info("🔄 Все %d топиков использованы! Начинаем по кругу.", len(topics))
        used_topics = []
        available_topics = topics.copy()

    # Выбираем случайный топик из доступных
    selected_topic = random.choice(available_topics)
    logger.info("Выбран топик: %s", selected_topic)

    # Добавляем в список использованных
    used_topics.append(selected_topic)
    save_used_topics(used_topics)

    return selected_topic

# ──────────────────────── Генерация поста ──────────────────────────

def generate_post_ai(topic: str) -> str | None:
    """Генерирует пост через GigaChat API."""
    if not GIGACHAT_CREDENTIALS:
        logger.warning("GIGACHAT_CREDENTIALS не задан — использую фолбэк.")
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

    try:
        with GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            scope="GIGACHAT_API_PN",
            verify_ssl_certs=False,
            model=GIGACHAT_MODEL,
        ) as giga:
            response = giga.chat(
                messages=[
                    {"role": "system", "content": "Ты — талантливый научпоп-автор Telegram-канала о природе. Пиши красиво и образно."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=400,
            )

        text = response.choices[0].message.content.strip()
        logger.info("Пост сгенерирован через %s (%d символов).", GIGACHAT_MODEL, len(text))
        return text
    except Exception as e:
        logger.error("Ошибка генерации через GigaChat: %s", e)
        return None


def generate_post(topics: list) -> str:
    """Возвращает пост: AI-генерация или фолбэк."""
    topic = get_next_topic(topics)
    post = generate_post_ai(topic)
    if post:
        return post
    return random.choice(FALLBACK_POSTS)

# ──────────────────────── Отправка в Telegram ──────────────────────

def send_to_telegram(text: str) -> bool:
    """Отправляет сообщение в Telegram-канал."""
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
    logger.info("🚀 Запуск Nature Telegram Bot (GigaChat) — %s", datetime.now(timezone.utc).isoformat())

    # Загружаем топики из файла
    topics = load_topics()

    # Генерируем пост
    post = generate_post(topics)
    logger.info("Содержимое поста:\n%s", post)

    # Отправляем в Telegram
    success = send_to_telegram(post)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
