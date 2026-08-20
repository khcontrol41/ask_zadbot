import os
import logging
import asyncio
import threading
import requests
import traceback
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncpg

# --- 1. الإعدادات الأساسية ---
TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not TOKEN:
    raise ValueError("لم يتم تعيين متغير البيئة BOT_TOKEN")
if not DATABASE_URL:
    raise ValueError("لم يتم تعيين متغير البيئة DATABASE_URL")

ADMIN_IDS = [5387087412]  # ⚠️ ضع رقمك هنا
AUTO_UNASSIGN_MINUTES = 15

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. دالة مساعدة لتشغيل الكود غير المتزامن ---
def run_async(coro):
    """تشغيل دالة غير متزامنة في حلقة جديدة ومغلقة تلقائياً"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

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

# ===================== نقاط API للاستفسارات =====================
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
                updated_count = 0
                if result and result.startswith("UPDATE"):
                    updated_count = int(result.split()[1])
                logger.info(f"تولي السؤال {question_id}: تم تحديث {updated_count} صف")
                return {"success": updated_count == 1, "updated": updated_count}
            except Exception as e:
                logger.error(f"خطأ في قاعدة البيانات أثناء تولي السؤال {question_id}: {e}")
                return {"error": str(e)}
            finally:
                await conn.close()

        result = run_async(assign_async())
        if result.get("error"):
            return jsonify({"error": result["error"]}), 500
        if not result.get("success"):
            return jsonify({"error": "السؤال ليس في حالة انتظار أو تم توليه بالفعل"}), 400
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"خطأ في إسناد السؤال: {e}")
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
                updated_count = 0
                if result and result.startswith("UPDATE"):
                    updated_count = int(result.split()[1])
                return {"success": updated_count == 1}
            finally:
                await conn.close()

        result = run_async(unassign_async())
        if not result.get("success"):
            return jsonify({"error": "السؤال ليس قيد المعالجة بواسطتك"}), 400
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"خطأ في إلغاء التولي: {e}")
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

                await conn.execute(
                    f"""
                    UPDATE questions 
                    SET status = 'pending', assigned_to = NULL 
                    WHERE status = 'processing' 
                    AND created_at < NOW() - INTERVAL '{AUTO_UNASSIGN_MINUTES} minutes'
                    """
                )

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
        logger.error(f"خطأ في جلب الأسئلة: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reply', methods=['POST'])
def reply_question():
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        reply_text = data.get('reply_text')
        admin_id = data.get('admin_id')

        logger.info(f"📩 محاولة رد على السؤال {question_id} من المشرف {admin_id}")

        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        if not question_id or not reply_text:
            return jsonify({"error": "بيانات ناقصة"}), 400

        async def update_and_send():
            await asyncio.sleep(0)
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
                    logger.info(f"✅ تم إرسال الرد للطالب {student_id}")
                else:
                    logger.warning("⚠️ البوت غير جاهز لإرسال الرسائل")
                return {"success": True}

            finally:
                await conn.close()
                logger.info("🔒 تم إغلاق اتصال قاعدة البيانات")

        result = run_async(update_and_send())
        if result.get("error"):
            logger.error(f"❌ خطأ في الرد: {result['error']}")
            return jsonify(result), 400

        logger.info(f"✅ نجح الرد على السؤال {question_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"💥 خطأ غير متوقع في /reply: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/delete_answered', methods=['POST'])
def delete_answered():
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')

        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        async def delete_async():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                result = await conn.execute("DELETE FROM questions WHERE status = 'answered'")
                import re
                match = re.search(r'DELETE (\d+)', result)
                count = int(match.group(1)) if match else 0
                return {"deleted": count}
            finally:
                await conn.close()

        result = run_async(delete_async())
        return jsonify({"success": True, "deleted": result.get("deleted", 0)}), 200

    except Exception as e:
        logger.error(f"خطأ في حذف الأسئلة المجاب عليها: {e}")
        return jsonify({"error": str(e)}), 500

# ===================== نقاط API للتسميع =====================
@app.route('/tashmi/get', methods=['POST'])
def get_tashmi():
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        group = data.get('group', 'all')

        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        async def fetch_tashmi():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute(
                    f"""
                    UPDATE tashmi_records 
                    SET status = 'pending', assigned_to = NULL 
                    WHERE status = 'processing' 
                    AND created_at < NOW() - INTERVAL '{AUTO_UNASSIGN_MINUTES} minutes'
                    """
                )
                if group == 'all':
                    rows = await conn.fetch("""
                        SELECT id, student_id, username, group_number, voice_file_id, 
                               duration, status, teacher_note, assigned_to, created_at 
                        FROM tashmi_records 
                        ORDER BY created_at DESC
                    """)
                else:
                    rows = await conn.fetch("""
                        SELECT id, student_id, username, group_number, voice_file_id, 
                               duration, status, teacher_note, assigned_to, created_at 
                        FROM tashmi_records 
                        WHERE group_number = $1
                        ORDER BY created_at DESC
                    """, group)
                return [dict(row) for row in rows]
            finally:
                await conn.close()

        records = run_async(fetch_tashmi())
        for r in records:
            r['created_at'] = r['created_at'].isoformat() if r['created_at'] else None
        return jsonify(records), 200

    except Exception as e:
        logger.error(f"خطأ في جلب التسميعات: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/tashmi/assign', methods=['POST'])
def assign_tashmi():
    try:
        data = request.get_json()
        record_id = data.get('record_id')
        admin_id = data.get('admin_id')

        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403

        async def assign_async():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                result = await conn.execute(
                    "UPDATE tashmi_records SET status = 'processing', assigned_to = $1 WHERE id = $2 AND status = 'pending'",
                    admin_id, record_id
                )
                updated_count = 0
                if result and result.startswith("UPDATE"):
                    updated_count = int(result.split()[1])
                logger.info(f"تولي التسميع {record_id}: تم تحديث {updated_count} صف")
                return {"success": updated_count == 1, "updated": updated_count}
            except Exception as e:
                logger.error(f"خطأ في قاعدة البيانات أثناء تولي التسميع {record_id}: {e}")
                return {"error": str(e)}
            finally:
                await conn.close()

        result = run_async(assign_async())
        if result.get("error"):
            return jsonify({"error": result["error"]}), 500
        if not result.get("success"):
            return jsonify({"error": "التسميع ليس في حالة انتظار أو تم توليه بالفعل"}), 400
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"خطأ في تولي التسميع: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/tashmi/reply', methods=['POST'])
def reply_tashmi():
    try:
        data = request.get_json()
        record_id = data.get('record_id')
        note_text = data.get('note_text')
        admin_id = data.get('admin_id')

        logger.info(f"🎙️ محاولة إرسال ملاحظة على التسميع {record_id} من المشرف {admin_id}")

        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403
        if not record_id or not note_text:
            return jsonify({"error": "بيانات ناقصة"}), 400

        async def update_and_send():
            await asyncio.sleep(0)
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow("SELECT student_id, assigned_to FROM tashmi_records WHERE id = $1", record_id)
                if not row:
                    return {"error": "التسميع غير موجود"}
                student_id = row['student_id']
                assigned_to = row['assigned_to']
                if assigned_to and assigned_to != admin_id:
                    return {"error": "يُعالج من قبل مشرف آخر"}

                await conn.execute(
                    "UPDATE tashmi_records SET teacher_note = $1, status = 'answered', assigned_to = $2 WHERE id = $3",
                    note_text, admin_id, record_id
                )

                global bot_app
                if bot_app:
                    await bot_app.bot.send_message(
                        chat_id=student_id,
                        text=f"🎙️ *ملاحظة المعلم على تسميعك:*\n\n{note_text}",
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ تم إرسال الملاحظة للطالب {student_id}")
                else:
                    logger.warning("⚠️ البوت غير جاهز لإرسال الرسائل")
                return {"success": True}
            finally:
                await conn.close()
                logger.info("🔒 تم إغلاق اتصال قاعدة البيانات")

        result = run_async(update_and_send())
        if result.get("error"):
            logger.error(f"❌ خطأ في إرسال الملاحظة: {result['error']}")
            return jsonify(result), 400

        logger.info(f"✅ نجحت ملاحظة التسميع {record_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"💥 خطأ غير متوقع في /tashmi/reply: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ===================== نقطة الصوتيات =====================
@app.route('/get_audio_url', methods=['POST'])
def get_audio_url():
    try:
        data = request.get_json()
        file_id = data.get('file_id')
        admin_id = data.get('admin_id')

        if admin_id not in ADMIN_IDS:
            return jsonify({"error": "غير مصرح"}), 403
        if not file_id:
            return jsonify({"error": "معرف الملف مطلوب"}), 400

        url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": "فشل الاتصال بـ Telegram API"}), 500
        result = response.json()
        if not result.get('ok'):
            return jsonify({"error": result.get('description', 'خطأ غير معروف')}), 400
        file_path = result['result']['file_path']
        audio_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        return jsonify({"url": audio_url})

    except Exception as e:
        logger.error(f"خطأ في /get_audio_url: {e}")
        return jsonify({"error": str(e)}), 500

# ===================== دوال البوت الأساسية =====================
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📩 سؤال جديد"), KeyboardButton("🎙️ تسميع جديد")],
        [KeyboardButton("📚 الأسئلة الشائعة")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_admin_panel_keyboard():
    mini_app_url = "https://khcontrol41.github.io/ask_zadadmin/"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 فتح لوحة المشرفين", web_app={"url": mini_app_url})]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🌿 أهلاً وسهلاً بكم في مقرأة «زاد الفرقان»

يسرّنا انضمامكم إلينا، ونسأل الله تعالى أن يوفقنا لخدمتكم وأن نكون عونًا لكم في رحلتكم.
"يبدأ الطريق بخطوة، وتُقطف ثماره بختمة.. فابدأ مسيرتك، ونحن معك حتى تذوق حلاوة الختمة."

🫧 الخدمات المتاحة عبر البوت:
صُمِّم هذا البوت للإجابة عن كافة استفساراتكم حول المقرأة، وتسهيل وصولكم إلى المعلومات التي تحتاجونها بكل يسر، بما في ذلك:

📚 البرامج والمسارات التعليمية
🗓️ مواعيد الحلقات واللقاءات
📝 إجراءات التسجيل وضوابط الدراسة
📖 اللوائح التنظيمية وآلية المتابعة
💬 الاستفسارات العامة والخدمات الإدارية

📌 يرجى تحديد الخيار المناسب من الأيقونات:

📚 الأسئلة الشائعة — للاطلاع على الإرشادات والإجابات المعتمدة.
📩 سؤال جديد — للتواصل المباشر مع الكادر الإشرافي بالمقرأة.

🌱 «لا تتردد في السؤال، فوضوح الطريق يُعين على حسن المسير»
"""
    await update.message.reply_text(welcome_text, reply_markup=MAIN_KEYBOARD)

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    username = update.effective_user.username
    logger.info(f"📌 زر مضغوط: {text} من المستخدم {update.effective_user.id}")

    # زر "تسميع جديد" يُعالج بواسطة المعالج المباشر في run_bot (ليس هنا)
    if text == "🎙️ تسميع جديد":
        return

    if text == "📩 سؤال جديد":
        # مسح أي بيانات سابقة متعلقة بالتسميع
        context.user_data.pop('group_number', None)
        context.user_data.pop('tashmi_page', None)
        context.user_data.pop('tashmi_state', None)
        # تعيين حالة انتظار السؤال
        context.user_data['waiting_for_question'] = True

        if not username:
            await update.message.reply_text(
                "⚠️ *تنبيه:* يلزم وجود معرّف عام (اسم مستخدم) في حسابك لتتمكن من التواصل مع المشرفين\n\n"
                "📌 *يرجى إعداد معرف خاص بك، ثم العودة وإرسال استفسارك.*",
                parse_mode="Markdown",
                reply_markup=MAIN_KEYBOARD
            )
            context.user_data['waiting_for_question'] = False
            return

        await update.message.reply_text(
            "✍️ اكتب سؤالك الآن، وسنقوم بالرد عليه قريباً.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"✅ تم تفعيل وضع انتظار السؤال للمستخدم {update.effective_user.id}")

    elif text == "📚 الأسئلة الشائعة":
        await update.message.reply_text(
            "سيتم التحديث قريباً.",
            reply_markup=MAIN_KEYBOARD
        )

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ التأكد من أن المستخدم في حالة انتظار سؤال، وليس في حالة تسميع
    if not context.user_data.get('waiting_for_question'):
        return

    user_id = update.effective_user.id
    username = update.effective_user.username
    question_text = update.message.text
    logger.info(f"📩 استلام سؤال من {user_id}: '{question_text[:50]}...'")

    if not username:
        await update.message.reply_text(
            "⚠️ يلزم وجود معرف عام (اسم مستخدم) في حسابك لتتمكن من التواصل مع المشرفين.\n"
            "يرجى إعداد معرف ثم أعد إرسال سؤالك.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False
        return

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT,
                    question TEXT, status TEXT DEFAULT 'pending', reply TEXT,
                    assigned_to BIGINT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute(
                "INSERT INTO questions (user_id, username, question) VALUES ($1, $2, $3)",
                user_id, username, question_text
            )
            logger.info(f"✅ تم حفظ سؤال المستخدم {user_id}")
        finally:
            await conn.close()

        await update.message.reply_text(
            "✅ تم استلام استفسارك! سيتم الرد عليه قريباً.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False

        keyboard = get_admin_panel_keyboard()
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 استفسار جديد من {username} (ID: {user_id})",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"فشل إشعار المشرف {admin_id}: {e}")

    except Exception as e:
        logger.error(f"💥 خطأ في handle_question: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ تقني، حاول مرة أخرى لاحقاً.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data['waiting_for_question'] = False

async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ عذراً، هذا البوت يقبل النصوص فقط.",
        reply_markup=MAIN_KEYBOARD
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ غير مصرح.")
        return
    await update.message.reply_text("مرحباً مشرف.", reply_markup=get_admin_panel_keyboard())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("📊 إحصائيات متاحة في اللوحة.")

# ===================== تشغيل البوت =====================
def run_bot():
    global bot_app
    # استيراد دوال التسميع من الملف المستقل (داخل الدالة لتجنب الاستيراد الدائري)
    import tashmi_bot
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_app = Application.builder().token(TOKEN).build()

    # 1. معالج زر "تسميع جديد" (مباشر)
    bot_app.add_handler(MessageHandler(filters.Regex("^🎙️ تسميع جديد$"), tashmi_bot.start_tashmi))

    # 2. معالج أزرار المجموعات (CallbackQuery)
    bot_app.add_handler(CallbackQueryHandler(tashmi_bot.tashmi_callback_handler, pattern="^(group_|page_|back_to_main)"))

    # 3. معالج استقبال الصوتيات (مع شرط الحالة)
    bot_app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, tashmi_bot.receive_audio_file))

    # 4. معالج الأزرار الرئيسية (للاستفسارات والأسئلة الشائعة)
    bot_app.add_handler(MessageHandler(filters.Regex("^(📩 سؤال جديد|📚 الأسئلة الشائعة)$"), handle_main_buttons))

    # 5. معالج النصوص العامة (الاستفسارات) مع شرط waiting_for_question
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))

    # 6. معالج الوسائط غير النصية (نتجاهلها)
    bot_app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, handle_non_text))

    # 7. الأوامر
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("stats", stats_command))
    bot_app.add_handler(CommandHandler("admin", admin_panel))

    print("✅ البوت يعمل...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)

# --- 6. تشغيل Flask ---
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
