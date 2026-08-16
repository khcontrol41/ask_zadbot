import os
import logging
import asyncio
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncpg

# --- 1. الإعدادات الأساسية ---
TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not TOKEN:
    raise ValueError("لم يتم تعيين متغير البيئة BOT_TOKEN")
if not DATABASE_URL:
    raise ValueError("لم يتم تعيين متغير البيئة DATABASE_URL")

ADMIN_IDS = [5387987412]  # ⚠️ ضع رقمك هنا

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- 2. حلقة أحداث ثابتة ---
main_loop = asyncio.new_event_loop()
asyncio.set_event_loop(main_loop)

# --- 3. تهيئة Flask ---
app = Flask(__name__)
CORS(app)

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
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS reply TEXT;")
                rows = await conn.fetch("""
                    SELECT id, user_id, username, question, status, reply, created_at 
                    FROM questions 
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in rows]
            finally:
                await conn.close()
        
        questions = main_loop.run_until_complete(fetch_questions())
        
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
        
        result = main_loop.run_until_complete(update_and_send())
        
        if result.get("error"):
            return jsonify(result), 400
            
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logging.error(f"خطأ في الرد: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/delete_answered', methods=['POST'])
def delete_answered():
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        
        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403
            
        async def delete_answered_async():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                result = await conn.execute("DELETE FROM questions WHERE status = 'answered'")
                import re
                match = re.search(r'DELETE (\d+)', result)
                count = int(match.group(1)) if match else 0
                return {"success": True, "deleted": count}
            finally:
                await conn.close()
        
        result = main_loop.run_until_complete(delete_answered_async())
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"خطأ في حذف الأسئلة المجاب عليها: {e}")
        return jsonify({"error": str(e)}), 500

# --- 4. دوال البوت الأساسية ---

# ✅ تعريف الأزرار الثابتة
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📩 سؤال جديد"), KeyboardButton("📚 الأسئلة الشائعة")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# قائمة الأسئلة الشائعة (سيتم تعديلها لاحقاً)
FAQ_TEXT = """
📚 *الأسئلة الشائعة:*

1️⃣ *كيف أحفظ الجزء الثلاثين؟*
   - يمكنك الاستماع إلى التكرارات اليومية، وتقسيم الحفظ إلى مقاطع صغيرة.

2️⃣ *متى موعد الاختبار القادم؟*
   - سيتم الإعلان عن موعد الاختبار عبر قنوات المقرأة الرسمية.

3️⃣ *كيف أنضم إلى حلقات التحفيظ؟*
   - تواصل مع المشرفين عبر البوت، وسيتم توجيهك.

4️⃣ *هل هناك رسوم للانضمام؟*
   - جميع خدمات المقرأة مجانية.

📌 *للاستفسارات الأخرى، استخدم زر "📩 سؤال جديد".*
"""

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب الجديدة (محدثة)"""
    welcome_text = """
🌿 أهلاً وسهلاً بكم في مقرأة «زاد الفرقان»

​يسرّنا انضمامكم إلينا، ونسأل الله تعالى أن يوفقنا لخدمتكم وأن نكون عونًا لكم في رحلتكم.
​"يبدأ الطريق بخطوة، وتُقطف ثماره بختمة.. فابدأ مسيرتك، ونحن معك حتى تذوق حلاوة الختمة."

​🫧 الخدمات المتاحة عبر البوت:
صُمِّم هذا البوت للإجابة عن كافة استفساراتكم حول المقرأة، وتسهيل وصولكم إلى المعلومات التي تحتاجونها بكل يسر، بما في ذلك:

​📚 البرامج والمسارات التعليمية
​🗓️ مواعيد الحلقات واللقاءات
​📝 إجراءات التسجيل وضوابط الدراسة
​📖 اللوائح التنظيمية وآلية المتابعة
​💬 الاستفسارات العامة والخدمات الإدارية

📌 يرجى تحديد الخيار المناسب من القائمة أدناه:
​📚 الأسئلة الشائعة — للاطلاع على الإرشادات والإجابات المعتمدة.

​📩 سؤال جديد — للتواصل المباشر مع الكادر الإشرافي بالمقرأة.

​🌱 «لا تتردد في السؤال، فوضوح الطريق يُعين على حسن المسير»
"""
    await update.message.reply_text(
        welcome_text,
        reply_markup=MAIN_KEYBOARD
    )

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار الثابتة"""
    text = update.message.text

    if text == "📩 سؤال جديد":
        await update.message.reply_text(
            "✍️ اكتب سؤالك الآن، وسنقوم بالرد عليه قريباً.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['waiting_for_question'] = True

    elif text == "📚 الأسئلة الشائعة":
        await update.message.reply_text(
            FAQ_TEXT,
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال النص وحفظه كسؤال"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "مجهول"
    question_text = update.message.text

    if not context.user_data.get('waiting_for_question'):
        await update.message.reply_text(
            "❌ يرجى استخدام الأزرار أدناه لاختيار الإجراء المناسب:\n"
            "• اضغط *📩 سؤال جديد* لطرح سؤال.\n"
            "• اضغط *📚 الأسئلة الشائعة* لعرض الإجابات الجاهزة.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD
        )
        return

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
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
            
        await update.message.reply_text(
            "✅ تم استلام استفسارك بنجاح! سيتم الرد عليه قريباً.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False

        # ✅ إرسال إشعار للمشرفين (بدون معاينة)
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text="📩 هناك استفسار جديد في لوحة التحكم."
                )
            except Exception as e:
                logging.error(f"فشل إرسال الإشعار للمشرف {admin_id}: {e}")

    except Exception as e:
        logging.error(f"خطأ في حفظ السؤال: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ تقني، حاول مرة أخرى لاحقًا.",
            reply_markup=MAIN_KEYBOARD
        )

async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منع المرفقات"""
    await update.message.reply_text(
        "❌ عذراً، هذا البوت يقبل النصوص الكتابية فقط.\n"
        "يرجى استخدام الأزرار أدناه لاختيار الإجراء المناسب.",
        reply_markup=MAIN_KEYBOARD
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ عذراً، ليس لديك صلاحية.")
        return
    # ⚠️ استبدل هذا الرابط برابط GitHub Pages الخاص بك
    mini_app_url = "https://khcontrol41.github.io/ask_zadadmin/"
    keyboard = [[InlineKeyboardButton("📊 فتح لوحة المشرفين", web_app={"url": mini_app_url})]]
    await update.message.reply_text(
        "مرحباً أيها المشرف!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- 5. تشغيل البوت ---
def run_bot():
    global bot_app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.Regex("^(📩 سؤال جديد|📚 الأسئلة الشائعة)$"), handle_main_buttons))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    bot_app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, handle_non_text))
    bot_app.add_handler(CommandHandler("admin", admin_panel))
    
    print("✅ البوت يعمل...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)

# --- 6. تشغيل Flask ---
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
