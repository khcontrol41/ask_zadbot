# tashmi_bot.py - النسخة النهائية (بدون run_async)
import logging
import os
import asyncpg
import traceback
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تعريفات محلية
TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL غير معرف في متغيرات البيئة!")
else:
    logger.info("✅ DATABASE_URL موجود")

ADMIN_IDS = [5387087412]  # ⚠️ ضع رقمك هنا

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [InlineKeyboardButton("📩 سؤال جديد"), InlineKeyboardButton("🎙️ تسميع جديد")],
        [InlineKeyboardButton("📚 الأسئلة الشائعة")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def get_admin_panel_keyboard():
    mini_app_url = "https://khcontrol41.github.io/ask_zadadmin/"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 فتح لوحة المشرفين", web_app={"url": mini_app_url})]
    ])

# المجموعات
GROUPS = ['1', '2', '3', '4', '5', '6']
GROUPS_PER_PAGE = 4

def build_group_keyboard(page=0):
    total_pages = (len(GROUPS) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE
    start = page * GROUPS_PER_PAGE
    end = min(start + GROUPS_PER_PAGE, len(GROUPS))
    current_groups = GROUPS[start:end]

    keyboard = []
    row = []
    for i, g in enumerate(current_groups):
        row.append(InlineKeyboardButton(f"المجموعة {g}", callback_data=f"group_{g}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔙 الرجوع للقائمة الرئيسية", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

async def start_tashmi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية التسميع - عرض أزرار المجموعات"""
    logger.info(f"🎙️ start_tashmi تم استدعاؤها من المستخدم {update.effective_user.id}")
    context.user_data.clear()
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "⚠️ يلزم وجود معرف عام (اسم مستخدم) لتتمكن من التسميع.\n"
            "يرجى إعداد معرف في إعدادات تيليجرام ثم حاول مجدداً."
        )
        return

    context.user_data['tashmi_state'] = 'GROUP_SELECTION'
    context.user_data['tashmi_page'] = 0
    await update.message.reply_text(
        "🎙️ *اختر رقم مجموعتك من الأزرار أدناه:*",
        parse_mode="Markdown",
        reply_markup=build_group_keyboard(0)
    )
    logger.info(f"✅ تم عرض أزرار المجموعات للمستخدم {user.id}")

async def tashmi_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الضغط على أزرار المجموعات أو التنقل"""
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.info(f"🔄 callback من {update.effective_user.id}: {data}")

    if data.startswith("group_"):
        group_number = data.split("_")[1]
        context.user_data['group_number'] = group_number
        context.user_data['tashmi_state'] = 'VOICE_RECORDING'
        await query.edit_message_text(
            f"✅ تم اختيار المجموعة {group_number}\n\n"
            "🎤 الآن، أرسل لي *الملف الصوتي* (يمكنك رفعه من جهازك أو تسجيله).",
            parse_mode="Markdown",
            reply_markup=None
        )
        logger.info(f"✅ تم اختيار المجموعة {group_number} للمستخدم {update.effective_user.id}")
        return

    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        context.user_data['tashmi_page'] = page
        await query.edit_message_text(
            "🎙️ *اختر رقم مجموعتك من الأزرار أدناه:*",
            parse_mode="Markdown",
            reply_markup=build_group_keyboard(page)
        )
        return

    elif data == "back_to_main":
        await query.edit_message_text(
            "🔙 تم العودة إلى القائمة الرئيسية.",
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD.keyboard, resize_keyboard=True)
        )
        context.user_data.clear()
        return

async def receive_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال الملف الصوتي بعد اختيار المجموعة"""
    logger.info(f"🎤 استلام ملف صوتي من {update.effective_user.id}")
    
    if context.user_data.get('tashmi_state') != 'VOICE_RECORDING':
        logger.warning(f"⚠️ تجاهل: المستخدم {update.effective_user.id} ليس في حالة VOICE_RECORDING")
        return

    user = update.effective_user
    group_number = context.user_data.get('group_number', 'غير محدد')
    audio = update.message.audio
    voice = update.message.voice
    document = update.message.document

    file_id = None
    duration = 0
    file_name = ""

    if audio:
        file_id = audio.file_id
        duration = audio.duration or 0
        file_name = audio.file_name or "تسجيل صوتي"
        logger.info(f"📁 استلام AUDIO: duration={duration}")
    elif voice:
        file_id = voice.file_id
        duration = voice.duration or 0
        file_name = "تسجيل صوتي (تليجرام)"
        logger.info(f"🎙️ استلام VOICE: duration={duration}")
    elif document and document.mime_type and document.mime_type.startswith('audio/'):
        file_id = document.file_id
        duration = 0
        file_name = document.file_name or "ملف صوتي"
        logger.info(f"📄 استلام DOCUMENT: {file_name}")
    else:
        await update.message.reply_text("❌ الرجاء إرسال ملف صوتي (MP3, M4A, OGG) أو تسجيل صوتي.")
        return

    if not file_id:
        await update.message.reply_text("❌ حدث خطأ في قراءة الملف، حاول مرة أخرى.")
        return

    try:
        # ✅ الحل الجذري: حفظ البيانات مباشرة باستخدام await (بدون run_async)
        async def save_audio():
            logger.info(f"💾 محاولة حفظ التسميع في قاعدة البيانات...")
            if not DATABASE_URL:
                raise Exception("DATABASE_URL غير معرف")
            
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tashmi_records (
                        id SERIAL PRIMARY KEY,
                        student_id BIGINT NOT NULL,
                        username TEXT,
                        group_number TEXT NOT NULL,
                        voice_file_id TEXT NOT NULL,
                        duration INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        teacher_note TEXT,
                        assigned_to BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await conn.execute(
                    """INSERT INTO tashmi_records 
                       (student_id, username, group_number, voice_file_id, duration) 
                       VALUES ($1, $2, $3, $4, $5)""",
                    user.id,
                    user.username or "مجهول",
                    group_number,
                    file_id,
                    duration
                )
                logger.info(f"✅ تم حفظ التسميع للمستخدم {user.id} في المجموعة {group_number}")
            except Exception as e:
                logger.error(f"❌ خطأ في save_audio: {e}")
                logger.error(traceback.format_exc())
                raise
            finally:
                await conn.close()
                logger.info("🔒 تم إغلاق اتصال قاعدة البيانات")

        # ✅ استدعاء الدالة مباشرة باستخدام await (بدون run_async)
        await save_audio()

        await update.message.reply_text(
            "✅ تم رفع التسجيل الصوتي بنجاح!\n"
            "📌 سيتم تصحيحه من قبل أحد المعلمين، وستصلك الملاحظات في أقرب وقت.",
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD.keyboard, resize_keyboard=True)
        )

        # إشعار المشرفين
        keyboard = get_admin_panel_keyboard()
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🎙️ *تسميع جديد*\nالمجموعة: {group_number}\nالطالب: @{user.username or 'مجهول'}\nالملف: {file_name}",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                logger.info(f"✅ تم إشعار المشرف {admin_id}")
            except Exception as e:
                logger.error(f"فشل إشعار المشرف {admin_id}: {e}")

        context.user_data.clear()
        logger.info(f"✅ اكتملت عملية التسميع للمستخدم {user.id}")

    except Exception as e:
        logger.error(f"💥 خطأ في receive_audio_file: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ حدث خطأ تقني: {str(e)[:100]}")
