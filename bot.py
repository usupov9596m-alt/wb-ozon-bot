import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "ВАШ_GROQ_КЛЮЧ_СЮДА")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_ARTICLE = 1
WAITING_DESCRIPTION_INPUT = 2
WAITING_AUDIT_LINK = 3
WAITING_UNIT_DATA = 4

# ========== ГЛАВНОЕ МЕНЮ ==========
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Анализ конкурентов", callback_data="competitors")],
        [InlineKeyboardButton("✍️ Генератор описаний", callback_data="description")],
        [InlineKeyboardButton("📊 Аудит карточки", callback_data="audit")],
        [InlineKeyboardButton("💰 Юнит-экономика", callback_data="unit")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для аналитики *WB и Ozon*.\n\n"
        "Выбери что хочешь сделать 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Главное меню:",
        reply_markup=main_menu_keyboard()
    )

# ========== GROQ AI ==========
def ask_groq(prompt: str) -> str:
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000
            },
            timeout=30
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Ошибка AI: {str(e)}"

# ========== АНАЛИЗ КОНКУРЕНТОВ WB ==========
def get_wb_product(article: str) -> dict:
    try:
        url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={article}"
        r = requests.get(url, timeout=10)
        data = r.json()
        products = data.get("data", {}).get("products", [])
        if not products:
            return None
        p = products[0]
        price = p.get("salePriceU", 0) // 100
        name = p.get("name", "Нет названия")
        brand = p.get("brand", "Нет бренда")
        rating = p.get("reviewRating", 0)
        feedbacks = p.get("feedbacks", 0)
        return {
            "name": name,
            "brand": brand,
            "price": price,
            "rating": rating,
            "feedbacks": feedbacks,
            "article": article,
            "marketplace": "Wildberries"
        }
    except:
        return None

def get_ozon_product(article: str) -> dict:
    try:
        url = f"https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/product/{article}/"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        # Базовый парсинг Ozon
        widget = data.get("widgetStates", {})
        return {
            "name": "Товар Ozon",
            "article": article,
            "marketplace": "Ozon",
            "note": "Для детальной аналитики Ozon подключите официальный API"
        }
    except:
        return None

# ========== ХЕНДЛЕРЫ КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "competitors":
        await query.message.reply_text(
            "🔍 *Анализ конкурентов*\n\n"
            "Введи артикул товара с Wildberries (только цифры):\n"
            "Например: `12345678`",
            parse_mode="Markdown"
        )
        context.user_data["mode"] = "competitors"

    elif data == "description":
        await query.message.reply_text(
            "✍️ *Генератор описаний*\n\n"
            "Опиши товар кратко — я напишу продающее SEO-описание для карточки.\n\n"
            "Например: `Женская куртка зимняя, пуховик, размеры 42-52, цвет чёрный`",
            parse_mode="Markdown"
        )
        context.user_data["mode"] = "description"

    elif data == "audit":
        await query.message.reply_text(
            "📊 *Аудит карточки*\n\n"
            "Введи артикул товара с WB для аудита:",
            parse_mode="Markdown"
        )
        context.user_data["mode"] = "audit"

    elif data == "unit":
        await query.message.reply_text(
            "💰 *Расчёт юнит-экономики*\n\n"
            "Введи данные через запятую в таком формате:\n"
            "`цена продажи, себестоимость, комиссия маркетплейса %, логистика`\n\n"
            "Например: `2000, 600, 15, 100`",
            parse_mode="Markdown"
        )
        context.user_data["mode"] = "unit"

    elif data == "back_menu":
        await query.message.reply_text(
            "📋 Главное меню:",
            reply_markup=main_menu_keyboard()
        )

# ========== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get("mode", None)

    if mode == "competitors":
        await analyze_competitors(update, context, text)

    elif mode == "description":
        await generate_description(update, context, text)

    elif mode == "audit":
        await audit_card(update, context, text)

    elif mode == "unit":
        await calculate_unit(update, context, text)

    else:
        await update.message.reply_text(
            "👋 Используй меню для работы:",
            reply_markup=main_menu_keyboard()
        )

# ========== АНАЛИЗ КОНКУРЕНТОВ ==========
async def analyze_competitors(update, context, article):
    await update.message.reply_text("⏳ Анализирую товар, подожди...")

    product = get_wb_product(article)

    if not product:
        await update.message.reply_text(
            "❌ Товар не найден. Проверь артикул и попробуй снова.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 В меню", callback_data="back_menu")
            ]])
        )
        return

    # AI анализ
    ai_prompt = f"""
    Ты эксперт по маркетплейсам. Проанализируй товар и дай краткие рекомендации:
    Название: {product['name']}
    Бренд: {product['brand']}
    Цена: {product['price']} руб
    Рейтинг: {product['rating']}
    Отзывов: {product['feedbacks']}
    
    Дай 3 конкретных совета как улучшить позиции этого товара. Коротко и по делу.
    """
    ai_advice = ask_groq(ai_prompt)

    result = (
        f"📦 *{product['name']}*\n"
        f"🏷️ Бренд: {product['brand']}\n"
        f"💰 Цена: {product['price']} ₽\n"
        f"⭐ Рейтинг: {product['rating']}\n"
        f"💬 Отзывов: {product['feedbacks']}\n"
        f"🔗 Маркетплейс: {product['marketplace']}\n\n"
        f"🤖 *Советы AI:*\n{ai_advice}"
    )

    await update.message.reply_text(
        result,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В меню", callback_data="back_menu")
        ]])
    )
    context.user_data["mode"] = None

# ========== ГЕНЕРАТОР ОПИСАНИЙ ==========
async def generate_description(update, context, product_info):
    await update.message.reply_text("✍️ Генерирую описание через AI...")

    prompt = f"""
    Ты копирайтер для маркетплейсов Wildberries и Ozon.
    Напиши продающее SEO-описание карточки товара.
    
    Товар: {product_info}
    
    Требования:
    - Длина 500-800 символов
    - Включи ключевые слова для поиска
    - Раздели на абзацы
    - Пиши на русском
    - Укажи преимущества товара
    - Добавь призыв к действию в конце
    """

    description = ask_groq(prompt)

    await update.message.reply_text(
        f"✅ *Готовое описание:*\n\n{description}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В меню", callback_data="back_menu")
        ]])
    )
    context.user_data["mode"] = None

# ========== АУДИТ КАРТОЧКИ ==========
async def audit_card(update, context, article):
    await update.message.reply_text("📊 Провожу аудит карточки...")

    product = get_wb_product(article)

    if not product:
        await update.message.reply_text("❌ Товар не найден. Проверь артикул.")
        return

    prompt = f"""
    Ты эксперт по оптимизации карточек на WB и Ozon.
    Проведи аудит карточки товара и дай конкретные рекомендации:
    
    Название: {product['name']}
    Цена: {product['price']} руб
    Рейтинг: {product['rating']}
    Отзывов: {product['feedbacks']}
    
    Проверь по критериям:
    1. Название карточки
    2. Ценообразование
    3. Работа с отзывами
    4. SEO оптимизация
    5. Что срочно исправить
    
    Дай оценку по каждому пункту и конкретные советы.
    """

    audit = ask_groq(prompt)

    await update.message.reply_text(
        f"📊 *Аудит карточки #{article}*\n\n{audit}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В меню", callback_data="back_menu")
        ]])
    )
    context.user_data["mode"] = None

# ========== ЮНИТ-ЭКОНОМИКА ==========
async def calculate_unit(update, context, data_str):
    try:
        parts = [x.strip() for x in data_str.split(",")]
        price = float(parts[0])
        cost = float(parts[1])
        commission_pct = float(parts[2])
        logistics = float(parts[3])

        commission = price * commission_pct / 100
        profit = price - cost - commission - logistics
        margin = (profit / price) * 100
        roi = (profit / cost) * 100

        emoji = "✅" if profit > 0 else "❌"

        result = (
            f"💰 *Юнит-экономика*\n\n"
            f"💵 Цена продажи: {price:.0f} ₽\n"
            f"🏭 Себестоимость: {cost:.0f} ₽\n"
            f"📦 Логистика: {logistics:.0f} ₽\n"
            f"🏪 Комиссия ({commission_pct}%): {commission:.0f} ₽\n\n"
            f"{'─'*25}\n"
            f"{emoji} *Прибыль с единицы: {profit:.0f} ₽*\n"
            f"📈 Маржинальность: {margin:.1f}%\n"
            f"🚀 ROI: {roi:.1f}%\n\n"
        )

        if profit < 0:
            result += "⚠️ *Товар убыточный!* Пересмотри цену или себестоимость."
        elif margin < 15:
            result += "⚠️ Низкая маржа. Рекомендуем минимум 20-25%."
        else:
            result += "✅ Хорошая экономика! Товар выгодный."

        await update.message.reply_text(
            result,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 В меню", callback_data="back_menu")
            ]])
        )

    except Exception as e:
        await update.message.reply_text(
            "❌ Ошибка в данных. Введи в формате:\n"
            "`цена, себестоимость, комиссия%, логистика`\n"
            "Например: `2000, 600, 15, 100`",
            parse_mode="Markdown"
        )

    context.user_data["mode"] = None

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
