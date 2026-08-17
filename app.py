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

ADMIN_IDS = [5387087412]  # ⚠️ ضع رقمك هنا

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- 2. دالة مساعدة لتشغيل الكود غير المتزامن بأمان ---
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("الحلقة مغلقة، سننشئ جديدة.")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

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

@app.route('/assign', methods=['POST'])
def assign_question():
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        admin_id = data.get('admin_id')
        
        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        async def assign_async():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS assigned_to BIGINT;")
                result = await conn.execute(
                    "UPDATE questions SET status = 'processing', assigned_to = $1 WHERE id = $2 AND status = 'pending'",
                    admin_id, question_id
                )
                if result == "UPDATE 0":
                    return {"error": "السؤال ليس في حالة انتظار أو تم إسناده بالفعل"}
                return {"success": True}
            finally:
                await conn.close()
        
        result = run_async(assign_async())
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"خطأ في إسناد السؤال: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/unassign', methods=['POST'])
def unassign_question():
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        admin_id = data.get('admin_id')
        
        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        async def unassign_async():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                result = await conn.execute(
                    "UPDATE questions SET status = 'pending', assigned_to = NULL WHERE id = $1 AND assigned_to = $2 AND status = 'processing'",
                    question_id, admin_id
                )
                if result == "UPDATE 0":
                    return {"error": "السؤال ليس قيد المعالجة بواسطتك"}
                return {"success": True}
            finally:
                await conn.close()
        
        result = run_async(unassign_async())
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"خطأ في إلغاء التولي: {e}")
        return jsonify({"error": str(e)}), 500

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
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS assigned_to BIGINT;")
                rows = await conn.fetch("""
                    SELECT id, user_id, username, question, status, reply, assigned_to, created_at 
                    FROM questions 
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in rows]
            finally:
                await conn.close()
        
        questions = run_async(fetch_questions())
        
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
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS assigned_to BIGINT;")
                
                row = await conn.fetchrow(
                    "SELECT user_id, assigned_to FROM questions WHERE id = $1", 
                    question_id
                )
                if not row:
                    return {"error": "السؤال غير موجود"}
                
                student_id = row['user_id']
                assigned_to = row['assigned_to']
                
                if assigned_to and assigned_to != admin_id:
                    return {"error": "هذا السؤال يُعالج من قبل مشرف آخر"}
                
                await conn.execute(
                    "UPDATE questions SET reply = $1, status = 'answered', assigned_to = $2 WHERE id = $3",
                    reply_text, admin_id, question_id
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
        
        result = run_async(update_and_send())
        
        if result.get("error"):
            return jsonify(result), 400
            
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logging.error(f"خطأ في الرد: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/bulk_reply', methods=['POST'])
def bulk_reply():
    try:
        data = request.get_json()
        question_ids = data.get('question_ids', [])
        reply_text = data.get('reply_text')
        admin_id = data.get('admin_id')
        
        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403
            
        if not question_ids or not reply_text:
            return jsonify({"error": "بيانات ناقصة"}), 400

        async def bulk_async():
            conn = await asyncpg.connect(DATABASE_URL)
            success_count = 0
            failed_ids = []
            failed_reasons = []
            
            try:
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS reply TEXT;")
                await conn.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS assigned_to BIGINT;")
                
                for q_id in question_ids:
                    try:
                        row = await conn.fetchrow(
                            "SELECT user_id, assigned_to, status FROM questions WHERE id = $1", 
                            q_id
                        )
                        if not row:
                            failed_ids.append(q_id)
                            failed_reasons.append(f"السؤال {q_id} غير موجود")
                            continue
                        
                        student_id = row['user_id']
                        assigned_to = row['assigned_to']
                        status = row['status']
                        
                        if status == 'pending' or (status == 'processing' and assigned_to == admin_id):
                            await conn.execute(
                                "UPDATE questions SET reply = $1, status = 'answered', assigned_to = $2 WHERE id = $3",
                                reply_text, admin_id, q_id
                            )
                            global bot_app
                            if bot_app:
                                try:
                                    await bot_app.bot.send_message(
                                        chat_id=student_id,
                                        text=f"📩 *تم الرد على استفسارك:*\n\n{reply_text}",
                                        parse_mode="Markdown"
                                    )
                                except Exception as e:
                                    logging.error(f"فشل إرسال الرد للطالب {student_id}: {e}")
                            
                            success_count += 1
                        else:
                            failed_ids.append(q_id)
                            failed_reasons.append(f"السؤال {q_id} غير متاح للرد (الحالة: {status})")
                            
                    except Exception as e:
                        logging.error(f"خطأ في معالجة السؤال {q_id}: {e}")
                        failed_ids.append(q_id)
                        failed_reasons.append(f"خطأ تقني في السؤال {q_id}")
                
                return {
                    "success": True,
                    "sent": success_count,
                    "failed": len(failed_ids),
                    "failed_ids": failed_ids,
                    "failed_reasons": failed_reasons
                }
                
            finally:
                await conn.close()
        
        result = run_async(bulk_async())
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"خطأ في الرد الجماعي: {e}")
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
        
        result = run_async(delete_answered_async())
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"خطأ في حذف الأسئلة المجاب عليها: {e}")
        return jsonify({"error": str(e)}), 500

# --- 4. دوال البوت الأساسية ---

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📩 سؤال جديد"), KeyboardButton("📚 الأسئلة الشائعة")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

📌 يرجى تحديد الخيار المناسب من الأيقونات:

​📚 الأسئلة الشائعة — للاطلاع على الإرشادات والإجابات المعتمدة.
​📩 سؤال جديد — للتواصل المباشر مع الكادر الإشرافي بالمقرأة.

​🌱 «لا تتردد في السؤال، فوضوح الطريق يُعين على حسن المسير»
"""
    await update.message.reply_text(
        welcome_text,
        reply_markup=MAIN_KEYBOARD
    )

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username

    if text == "📩 سؤال جديد":
        # ✅ التحقق من وجود معرف (Username)
        if not username or username == "":
            # ❌ المستخدم ليس لديه معرف: نرسل رسالة التوجيه فوراً، ولا نفعّل حالة الانتظار
            await update.message.reply_text(
                "⚠️ *تنبيه:* لا يمكننا استقبال استفسارك لأن حسابك ليس لديه معرف عام (Username).\n\n"
                "📌 *يرجى إعداد معرف خاص بك، ثم العودة وإرسال استفسارك.*\n\n"
                "📝 *كيفية إنشاء معرف في تيليجرام:*\n"
                "1. افتح إعدادات تيليجرام (Settings).\n"
                "2. اضغط على اسمك أو صورتك الشخصية.\n"
                "3. اختر 'Username' (اسم المستخدم).\n"
                "4. اكتب اسماً فريداً (حروف وأرقام) واضغط حفظ.\n\n"
                "🔹 *إذا واجهتك صعوبة، يرجى التواصل مع الدعم التقني:* @zad41"
                "📌 سيساعدك الفريق في إعداد معرفك ليتمكن المشرف من التواصل معك والرد على استفسارك.",
                parse_mode="Markdown",
                reply_markup=MAIN_KEYBOARD
            )
            # ❌ نمنع المتابعة: لا نفعّل waiting_for_question
            context.user_data['waiting_for_question'] = False
            return

        # ✅ المستخدم لديه معرف: نسمح له بالكتابة
        await update.message.reply_text(
            "✍️ اكتب سؤالك الآن، وسنقوم بالرد عليه قريباً.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['waiting_for_question'] = True

    elif text == "📚 الأسئلة الشائعة":
        faq_text = """
أهلاً بكم.. نعمل حالياً على تحديث قسم الأسئلة الشائعة وستُتاح قريبا بإذن الله. وفي حال كان لديكم أي سؤال، يمكنكم التواصل مع المشرفين مباشرة بالضغط على (📩 سؤال جديد).
"""
        await update.message.reply_text(
            faq_text,
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username  # سيصبح None إذا لم يكن هناك معرف
    question_text = update.message.text

    # ✅ التحقق من وجود معرف (لن يصل إلى هنا المستخدمون بدون معرف، لكن للاحتياط)
    if not is_admin(user_id) and (not username or username == ""):
        # في حال وصول هنا (لن يحدث)، نرسل رسالة توجيه ونمنع الحفظ
        await update.message.reply_text(
            "⚠️ لا يمكننا استقبال استفسارك لأن حسابك ليس لديه معرف عام.\n"
            "يرجى إعداد معرف في الإعدادات ثم العودة لإرسال استفسارك.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    # ✅ التحقق من حالة الانتظار
    if not context.user_data.get('waiting_for_question'):
        await update.message.reply_text(
            "❌ يُرجى استخدام الأيقونات الظاهرة أدناه لاختيار الخدمة المناسبة:\n\n"
            "☜  اضغط \"📩 سؤال جديد\" للتواصل المباشر مع مشرفي المقرأة وطرح سؤالك\n\n"
            "☜ اضغط \"📚 الأسئلة الشائعة\" للاستفادة من أكثر ما يُطرح من استفسارات",
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
                    assigned_to BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute(
                "INSERT INTO questions (user_id, username, question) VALUES ($1, $2, $3)",
                user_id, username or "مجهول", question_text
            )
        finally:
            await conn.close()
            
        await update.message.reply_text(
            "✅ تم استلام استفسارك بنجاح! سيقوم أحد المشرفين بالرد عليه قريباً",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False

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
    await update.message.reply_text(
        "❌ عذراً، هذا البوت يقبل النصوص الكتابية فقط.\n"
        "☜ اختر الخدمة المطلوبة من القائمة أدناه",
        reply_markup=MAIN_KEYBOARD
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ عذراً، ليس لديك صلاحية.")
        return
    
    mini_app_url = "https://khcontrol41.github.io/ask_zadadmin/"  # ⚠️ غيّر هذا الرابط
    keyboard = [[InlineKeyboardButton("📊 فتح لوحة المشرفين", web_app={"url": mini_app_url})]]
    await update.message.reply_text(
        "مرحباً بك. تم تسجيل دخولك كمشرف 🌿",
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
