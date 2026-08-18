# tashmi_bot.py
import logging
import asyncpg
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# نستورد الثوابت من الملف الرئيسي app.py
from app import TOKEN, DATABASE_URL, ADMIN_IDS, get_admin_panel_keyboard

# حالات المحادثة (مراحل التفاعل مع الطالب)
GROUP_NUMBER, VOICE_RECORDING = range(2)

async def start_tashmi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: نطلب من الطالب كتابة رقم مجموعته"""
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "⚠️ يلزم وجود معرف عام (اسم مستخدم) لتتمكن من التسميع.\n"
            "يرجى إعداد معرف في إعدادات تيليجرام ثم حاول مجدداً."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🎙️ *مرحباً بك في خدمة التسميع*\n\n"
        "📌 يرجى إرسال *رقم مجموعتك* (مثال: 1، 2، 3) ثم اضغط إرسال.\n\n"
        "⏳ بعد إرسال الرقم، سأطلب منك رفع التسجيل الصوتي.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return GROUP_NUMBER

async def receive_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: نستلم رقم المجموعة ونحفظه مؤقتاً"""
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ الرجاء إدخال رقم مجموعة صحيح (أرقام فقط).")
        return GROUP_NUMBER
    
    context.user_data['group_number'] = text
    await update.message.reply_text(
        f"✅ تم حفظ رقم المجموعة: {text}\n\n"
        "🎤 الآن، أرسل لي *التسجيل الصوتي* (اضغط على زر الميكروفون).",
        parse_mode="Markdown"
    )
    return VOICE_RECORDING

async def receive_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: نستلم الملف الصوتي ونحفظه في قاعدة البيانات"""
    user = update.effective_user
    voice = update.message.voice
    group_number = context.user_data.get('group_number', 'غير محدد')

    if not voice:
        await update.message.reply_text("❌ يرجى إرسال تسجيل صوتي (Voice Message) وليس ملفاً عادياً.")
        return VOICE_RECORDING

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            # نتأكد من وجود الجدول (لن يضره لو كان موجوداً)
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
            
            # نحفظ بيانات التسميع
            await conn.execute(
                """INSERT INTO tashmi_records 
                   (student_id, username, group_number, voice_file_id, duration) 
                   VALUES ($1, $2, $3, $4, $5)""",
                user.id,
                user.username or "مجهول",
                group_number,
                voice.file_id,
                voice.duration or 0
            )
        finally:
            await conn.close()

        await update.message.reply_text(
            "✅ تم استلام تسميعك بنجاح!\n"
            "سيراجعه المعلم وستصلك الملاحظة عبر هذا البوت.",
            reply_markup=ReplyKeyboardMarkup([["🎙️ تسميع جديد"]], resize_keyboard=True)
        )

        # إشعار للمشرفين بوجود تسميع جديد
        keyboard = get_admin_panel_keyboard()
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🎙️ *تسميع جديد*\nالمجموعة: {group_number}\nالطالب: @{user.username or 'مجهول'}",
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
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية"""
    await update.message.reply_text("❌ تم إلغاء عملية التسميع.", reply_markup=ReplyKeyboardMarkup([["🎙️ تسميع جديد"]], resize_keyboard=True))
    context.user_data.clear()
    return ConversationHandler.END

def get_tashmi_handler():
    """هذه الدالة تُرجع معالج المحادثة لاستخدامه في الملف الرئيسي app.py"""
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("tashmi", start_tashmi)],
        states={
            GROUP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_number)],
            VOICE_RECORDING: [MessageHandler(filters.VOICE, receive_voice)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return conv_handler
