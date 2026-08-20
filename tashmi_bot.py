# tashmi_bot.py
import logging
import asyncpg
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler

from app import TOKEN, DATABASE_URL, ADMIN_IDS, get_admin_panel_keyboard

# حالات المحادثة
GROUP_SELECTION, VOICE_RECORDING = range(2)

# المجموعات المتاحة (يمكن زيادتها لاحقاً)
GROUPS = ['1', '2', '3', '4', '5', '6']
GROUPS_PER_PAGE = 4

def build_group_keyboard(page=0):
    """بناء لوحة أزرار المجموعات مع أزرار التنقل"""
    total_pages = (len(GROUPS) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE
    start = page * GROUPS_PER_PAGE
    end = min(start + GROUPS_PER_PAGE, len(GROUPS))
    current_groups = GROUPS[start:end]

    keyboard = []
    # صفوف الأزرار: كل صف يحوي زرين
    row = []
    for i, g in enumerate(current_groups):
        row.append(InlineKeyboardButton(f"المجموعة {g}", callback_data=f"group_{g}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # أزرار التنقل
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    # زر الرجوع للقائمة الرئيسية
    keyboard.append([InlineKeyboardButton("🔙 الرجوع للقائمة الرئيسية", callback_data="back_to_main")])

    return InlineKeyboardMarkup(keyboard)

async def start_tashmi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بداية اختيار المجموعة"""
    # تنظيف السياق بالكامل لضمان بداية نظيفة
    context.user_data.clear()
    
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "⚠️ يلزم وجود معرف عام (اسم مستخدم) لتتمكن من التسميع.\n"
            "يرجى إعداد معرف في إعدادات تيليجرام ثم حاول مجدداً."
        )
        return ConversationHandler.END

    context.user_data['tashmi_page'] = 0
    await update.message.reply_text(
        "🎙️ *اختر رقم مجموعتك من الأزرار أدناه:*",
        parse_mode="Markdown",
        reply_markup=build_group_keyboard(0)
    )
    return GROUP_SELECTION

async def group_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الضغط على أزرار المجموعات أو التنقل"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("group_"):
        # تم اختيار مجموعة
        group_number = data.split("_")[1]
        context.user_data['group_number'] = group_number
        await query.edit_message_text(
            f"✅ تم اختيار المجموعة {group_number}\n\n"
            "🎤 الآن، أرسل لي *الملف الصوتي* (يمكنك رفعه من جهازك أو تسجيله).",
            parse_mode="Markdown",
            reply_markup=None
        )
        return VOICE_RECORDING

    elif data.startswith("page_"):
        # تغيير الصفحة
        page = int(data.split("_")[1])
        context.user_data['tashmi_page'] = page
        await query.edit_message_text(
            "🎙️ *اختر رقم مجموعتك من الأزرار أدناه:*",
            parse_mode="Markdown",
            reply_markup=build_group_keyboard(page)
        )
        return GROUP_SELECTION

    elif data == "back_to_main":
        # الرجوع للقائمة الرئيسية (سيتم إنهاء المحادثة وعرض الأزرار الأساسية)
        from app import MAIN_KEYBOARD
        await query.edit_message_text(
            "🔙 تم العودة إلى القائمة الرئيسية.",
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD.keyboard, resize_keyboard=True)
        )
        context.user_data.clear()
        return ConversationHandler.END

    return GROUP_SELECTION

async def receive_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال الملف الصوتي بعد اختيار المجموعة"""
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
    elif voice:
        file_id = voice.file_id
        duration = voice.duration or 0
        file_name = "تسجيل صوتي (تليجرام)"
    elif document and document.mime_type and document.mime_type.startswith('audio/'):
        file_id = document.file_id
        duration = 0
        file_name = document.file_name or "ملف صوتي"
    else:
        await update.message.reply_text("❌ الرجاء إرسال ملف صوتي (MP3, M4A, OGG) أو تسجيل صوتي.")
        return VOICE_RECORDING

    if not file_id:
        await update.message.reply_text("❌ حدث خطأ في قراءة الملف، حاول مرة أخرى.")
        return VOICE_RECORDING

    try:
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
        finally:
            await conn.close()

        from app import MAIN_KEYBOARD
        await update.message.reply_text(
            "✅ تم رفع التسجيل الصوتي بنجاح!\n"
            "📌 سيتم تصحيحه من قبل أحد المعلمين، وستصلك الملاحظات في أقرب وقت.",
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD.keyboard, resize_keyboard=True)
        )

        # إشعار للمشرفين
        keyboard = get_admin_panel_keyboard()
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🎙️ *تسميع جديد*\nالمجموعة: {group_number}\nالطالب: @{user.username or 'مجهول'}\nالملف: {file_name}",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"فشل إشعار المشرف: {e}")

        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"خطأ في حفظ التسميع: {e}")
        await update.message.reply_text("❌ حدث خطأ تقني، حاول مرة أخرى لاحقاً.")
        return VOICE_RECORDING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية"""
    from app import MAIN_KEYBOARD
    await update.message.reply_text(
        "❌ تم إلغاء عملية التسميع.",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD.keyboard, resize_keyboard=True)
    )
    context.user_data.clear()
    return ConversationHandler.END

def get_tashmi_handler():
    """إرجاع معالج المحادثة مع دعم الأزرار"""
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("tashmi", start_tashmi),
            MessageHandler(filters.Regex("^🎙️ تسميع جديد$"), start_tashmi)  # أعدناها
        ],
        states={
            GROUP_SELECTION: [CallbackQueryHandler(group_selection_callback)],
            VOICE_RECORDING: [
                MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, receive_audio_file)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return conv_handler
