import os
import logging
import asyncio
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
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

# ⚠️ IMPORTANT: اكتب رقمك هنا يدوياً (لا تنسخه من أي مكان)
ADMIN_IDS = [5387087412]  # ضع رقمك هنا

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- 2. تهيئة Flask مع دعم CORS ---
app = Flask(__name__)
CORS(app)

# متغير عام لحمل كائن البوت
bot_app = None

@app.route('/')
def home():
    return "البوت يعمل! ✅"

@app.route('/health')
def health():
    return "OK"

# --- نقاط النهاية للواجهة (API) ---

@app.route('/get_questions', methods=['POST'])
def get_questions():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if user_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        async def fetch_questions():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                # ✅ إصلاح الخطأ: إضافة عمود reply إذا لم يكن موجوداً
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS reply TEXT;")
                
                rows = await conn.fetch("""
                    SELECT id, user_id, username, question, status, reply, created_at 
                    FROM questions 
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in rows]
            finally:
                await conn.close()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        questions = loop.run_until_complete(fetch_questions())
        loop.close()
        
        for q in questions:
            q['created_at'] = q['created_at'].isoformat() if q['created_at'] else None
            
        return jsonify(questions), 200
        
    except Exception as e:
        logging.error(f"خطأ في جلب الأسئلة: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reply', methods=['POST'])
def reply_question():
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        reply_text = data.get('reply_text')
        admin_id = data.get('admin_id')
        
        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403
            
        if not question_id or not reply_text:
            return jsonify({"error": "بيانات ناقصة"}), 400
            
        async def update_and_send():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                # ✅ إصلاح إضافي: التأكد من وجود العمود قبل التحديث
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS reply TEXT;")
                
                row = await conn.fetchrow("SELECT user_id FROM questions WHERE id = $1", question_id)
                if not row:
                    return {"error": "السؤال غير موجود"}
                
                student_id = row['user_id']
                
                await conn.execute(
                    "UPDATE questions SET reply = $1, status = 'answered' WHERE id = $2",
                    reply_text, question_id
                )
                
                global bot_app
                if bot_app:
                    await bot_app.bot.send_message(
                        chat_id=student_id,
                        text=f"📩 *تم الرد على استفسارك:*\n\n{reply_text}",
                        parse_mode="Markdown"
                    )
                else:
                    logging.error("البوت ليس جاهزاً لإرسال الرسائل")
                    return {"error": "البوت غير جاهز"}
                
                return {"success": True}
                
            finally:
                await conn.close()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(update_and_send())
        loop.close()
        
        if result.get("error"):
            return jsonify(result), 400
            
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logging.error(f"خطأ في الرد: {e}")
        return jsonify({"error": str(e)}), 500

# --- 3. دوال البوت الأساسية ---
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
        try:
            # ✅ إضافة عمود reply أثناء إنشاء الجدول لمنع المشكلة مستقبلاً
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id SERIAL PRIMARY KEY, 
                    user_id BIGINT, 
                    username TEXT, 
                    question TEXT, 
                    status TEXT DEFAULT 'pending', 
                    reply TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute(
                "INSERT INTO questions (user_id, username, question) VALUES ($1, $2, $3)",
                user_id, username, question_text
            )
        finally:
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
    # ⚠️ IMPORTANT: استبدل هذا الرابط برابط GitHub Pages الخاص بك
    mini_app_url = "https://khcontrol41.github.io/ask_zadadmin41/"
    keyboard = [[InlineKeyboardButton("📊 فتح لوحة المشرفين", web_app={"url": mini_app_url})]]
    await update.message.reply_text("مرحباً أيها المشرف!", reply_markup=InlineKeyboardMarkup(keyboard))

# --- 4. تشغيل البوت ---
def run_bot():
    global bot_app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(ask_button, pattern="ask"))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    bot_app.add_handler(CommandHandler("admin", admin_panel))
    
    print("✅ البوت يعمل...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)

# --- 5. تشغيل Flask مع البوت في خلفية ---
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
