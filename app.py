import os
import logging
import asyncio
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncpg

# --- 1. الإعدادات الأساسية ---
TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not TOKEN:
    raise ValueError("لم يتم تعيين متغير البيئة BOT_TOKEN")
if not DATABASE_URL:
    raise ValueError("لم يتم تعيين متغير البيئة DATABASE_URL")

# ⚠️ IMPORTANT: استبدل هذه الأرقام بأرقام المشرفين الحقيقية (بدون الصفر)
ADMIN_IDS = [5387087412‪]  # ضع رقمك هنا

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- 2. تهيئة Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "البوت يعمل! ✅"

@app.route('/health')
def health():
    return "OK"

# --- 3. دوال البوت ---
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📩 إرسال استفسار", callback_data="ask")]]
    await update.message.reply_text(
        "مرحباً بك في بوت استفسارات المقرأة! 📚\nاضغط على الزر أدناه لإرسال استفسارك.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ask_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✍️ من فضلك اكتب استفسارك كرسالة نصية الآن.")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "مجهول"
    question_text = update.message.text
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS questions (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, question TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        await conn.execute("INSERT INTO questions (user_id, username, question) VALUES ($1, $2, $3)", user_id, username, question_text)
        await conn.close()
        await update.message.reply_text("✅ تم استلام استفسارك بنجاح! سيتم الرد عليه قريبًا.")
    except Exception as e:
        logging.error(f"خطأ في حفظ السؤال: {e}")
        await update.message.reply_text("❌ حدث خطأ تقني، حاول مرة أخرى لاحقًا.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ عذراً، ليس لديك صلاحية.")
        return
    mini_app_url = "https://khcontrol41.github.io/ask_zadadmin41/"  # ⚠️ غيّر هذا الرابط
    keyboard = [[InlineKeyboardButton("📊 فتح لوحة المشرفين", web_app={"url": mini_app_url})]]
    await update.message.reply_text("مرحباً أيها المشرف!", reply_markup=InlineKeyboardMarkup(keyboard))

# --- 4. تشغيل البوت (تم الإصلاح النهائي) ---
def run_bot():
    """تشغيل البوت في حلقة (Polling) مع حلقة أحداث خاصة"""
    # إنشاء حلقة أحداث جديدة لهذا الخيط
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(ask_button, pattern="ask"))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    bot_app.add_handler(CommandHandler("admin", admin_panel))
    
    print("✅ البوت يعمل...")
    # 🔧 الإصلاح: تجاهل إشارات النظام (stop_signals=None) لتجنب خطأ set_wakeup_fd
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)

# --- 5. تشغيل Flask مع البوت في خلفية ---
if __name__ == "__main__":
    # تشغيل البوت في Thread منفصل
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    # تشغيل خادم Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
