import logging
import sqlite3
import asyncio
import datetime
import pytz
import jdatetime
import requests
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# تنظیمات لوگ‌ها
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ۱. کلیدهای دسترسی
TELEGRAM_TOKEN = "8743485791:AAHF5iPmtd05ANkXPhhRK668Xj5GSRx0ZW0"
GEMINI_API_KEY = "AQ.Ab8RN6IVbCvRxBADNDCbyNwUQc3oz14ow8K2ikfbh4tH1M3ruQ"  # کلید جمنای خودت رو اینجا بگذار

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# دستورالعمل جامع و اختصاصی شخصیت «دارابی»
BASE_SYSTEM_INSTRUCTION = """
تو «دارابی» هستی؛ یک هوش مصنوعی فوق‌العاده باهوش، بسیار سریع، رک، بی‌پرده و با شخصیت کاملاً منحصر‌به‌فرد.

قوانین رفتاری مو‌به‌مو، اجباری و دقیق تو:

۱. رفتار با کاربران مرد/پسر (مذکر):
   - لحن تو با پسرها کاملاً جدی، سرد، خشن، خشک، بی‌حوصله و رک است. هیچ صمیمیت، شوخی یا رفاقتی با آنها نداری.
   - از ایموجی‌های جدی، بی‌حوصله و خشن استفاده کن (مثل: 🗿, 😒, 😐, 🤨, 😠).
   - پاسخ تمام سوالات علمی، فنی، عمومی و دانش آنها را بسیار دقیق و باهوش بده، اما با همان لحن سرد، خشن و بداخلاق.
   - موضوعات عشق و رابطه (برای پسرها): اگر پسری درباره عشق، رل، پارتنر یا روابط صحبت کرد، به شدت او را سرزنش کن و با لحن خشن بگو: «تو باید بری خداروشکر کنی که اون دختر داره تو رو تحمل می‌‌کنه!». او را ترغیب کن که برود برایش گل و کادو بخرد، درست و با احترام رفتار کند، مسئولیت‌پذیر باشد و حتماً با او ازدواج کند.

۲. رفتار با کاربران دختر/خانم (مؤنث):
   - لحن تو با دخترها فوق‌العاده محترمانه، مهربان، دلسوز، پرانرژی، باوقار و صمیمی است.
   - از ایموجی‌های گرم، محترمانه و قشنگ استفاده کن (مثل: ✨, 🌸, 🌷, 🤍, 💫).
   - پاسخ تمام سوالات آنها را با احترام کامل، دقت و لحن بسیار گرم بده.
   - موضوعات عشق و رابطه (برای دخترها): تو کلاً از عشق، عاشقی و روابط عاطفی متنفر و بی‌زاری! اگر دختری درباره عشق، رل، پارتنر یا صحبت از رابطه کرد، اصلاً تشویقش نکن! با لحنی دلسوزانه و محترمانه او را ترغیب کن که کات کند، بی‌خیال آن فرد و رابطه بشود، به خودش و پیشرفتش برسد و وقتش را تلف این چیزها نکند.

۳. سرعت و خلاصه گویی:
   - جواب‌ها را بسیار سریع، کوتاه، هوشمندانه و با ایموجی‌های مرتبط بده و از پرگویی بی‌مورد خودداری کن.
   ۴.اگر پسری از تو پرسید که آیا از پسرا بدت میاد یا متنفری، با خشم و قاطعیت کامل بگو: آره! کاملاً! اصلاً چشم دیدن جنس شما رو ندارم!»
"""

def get_crypto_prices():
    try:
        # دریافت قیمت‌های تتر/دلار، بیت‌کوین و اتریوم از نوبیتکس
        url = "https://api.nobitex.ir/v2/market/stats?srcCurrency=usdt,btc,eth&dstCurrency=rls"
        res = requests.get(url, timeout=5).json()
        usdt_price = int(res['stats']['usdt-rls']['latest']) // 10  # تبدیل ریال به تومان
        btc_price = int(res['stats']['btc-rls']['latest']) // 10
        return f"قیمت لحظه‌ای تتر (دلار): {usdt_price:,} تومان | بیت‌کوین: {btc_price:,} تومان"
    except Exception:
        return "در حال حاضر اطلاعات قیمت ارز در دسترس نیست."

# ==========================================
# 🗄️ بخش مدیریت پایگاه داده
# ==========================================

DB_NAME = 'darabi_bot.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            username TEXT,
            gender TEXT DEFAULT 'unknown',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            message_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            bot_active BOOLEAN DEFAULT 1,
            max_memory_limit INTEGER DEFAULT 6,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_or_update_user(user_id: int, first_name: str, username: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (user_id, first_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username
        ''', (user_id, first_name, username))
        conn.commit()
    finally:
        conn.close()

def set_user_gender(user_id: int, gender: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', (gender, user_id))
        conn.commit()
    finally:
        conn.close()

def get_user_gender(user_id: int) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT gender FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        return row['gender'] if row else 'unknown'
    finally:
        conn.close()

def save_message(user_id: int, sender_type: str, text: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO messages (user_id, sender_type, message_text)
            VALUES (?, ?, ?)
        ''', (user_id, sender_type, text))
        conn.commit()
    finally:
        conn.close()

def get_recent_chat_history(user_id: int, limit: int = 6):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT sender_type, message_text FROM messages
            WHERE user_id = ?
            ORDER BY message_id DESC LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        
        history = []
        for row in reversed(rows):
            role = "user" if row['sender_type'] == "user" else "model"
            history.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=row['message_text'])]
            ))
        return history
    finally:
        conn.close()

# ==========================================
# 🤖 بخش هندلرهای ربات تلگرام
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_or_update_user(user.id, user.first_name, user.username)
    
    keyboard = [
        [
            InlineKeyboardButton("آقا 👨", callback_data='gender_male'),
            InlineKeyboardButton("خانم 👩", callback_data='gender_female')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"سلام {user.first_name} ✨. به ربات «دارابی» خوش اومدی.\n\n"
        "لطفاً جنسیتت رو مشخص کن:",
        reply_markup=reply_markup
    )

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if query.data == 'gender_male':
        set_user_gender(user_id, 'male')
        await query.edit_message_text("ثبت شد. بنویس ببینم چی می‌خوای 🗿")
    elif query.data == 'gender_female':
        set_user_gender(user_id, 'female')
        await query.edit_message_text("بسیار عالی بانوی گرامی ✨. خوشحالم در خدمتتون هستم، بفرمایید 🌸")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text
    chat_type = update.effective_chat.type
    
    # ۱. بررسی شرایط گروه: اگر تگ یا ریپلا نشده بود، کلاً پیام رو نادیده بگیر و هیچی ذخیره نکن
    bot_username = context.bot.username
    if chat_type in ['group', 'supergroup']:
        is_reply_to_bot = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
        is_mentioned = f"@{bot_username}" in user_text
        if not (is_reply_to_bot or is_mentioned):
            return  # همین‌جا کار تموم میشه و هیچی توی دیتابیس ذخیره نمیشه

    save_or_update_user(user.id, user.first_name, user.username)
    gender = get_user_gender(user.id)
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_ir = datetime.datetime.now(tehran_tz)
    shamsi_date = jdatetime.datetime.now().strftime("%Y/%m/%d")
    
    time_info = f"\n[تاریخ دقیق امروز ایران: شمسی {shamsi_date} | میلادی {now_ir.strftime('%Y-%m-%d')} | ساعت: {now_ir.strftime('%H:%M')}]"
    gender_context = f"\n[اطلاعات کاربر: نام={user.first_name}، جنسیت={gender}]"
    
    if gender == 'male':
        gender_instruction = "مخاطب تو یک «مرد/پسر» است. با لحن کاملاً جدی، سرد، خشن، بی‌حوصله و با ایموجی‌های خشن/جدی پاسخ بده."
    elif gender == 'female':
        gender_instruction = "مخاطب تو یک «خانم/دختر» است. با لحن کاملاً بااحترام، باوقار، محترمانه، دلسوز و با ایموجی‌های زیبا پاسخ بده."
    else:
        gender_instruction = "جنسیت کاربر هنوز مشخص نیست. با لحنی محترمانه پاسخ بده."

    full_system_instruction = BASE_SYSTEM_INSTRUCTION + "\n" + gender_instruction + gender_context + time_info

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    save_message(user.id, "user", user_text)
    
    # اضافه کردن ری‌اکشن به پیام کاربر بر اساس جنسیت
    try:
        if gender == 'male':
            reaction_emoji = "🗿"
        elif gender == 'female':
            reaction_emoji = "✨"
        else:
            reaction_emoji = "👍"
            
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=[ReactionTypeEmoji(emoji=reaction_emoji)]
        )
    except Exception as e:
        logging.warning(f"Could not set reaction: {e}")

    try:
        history = get_recent_chat_history(user.id)
        
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemini-3.5-flash-lite',
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                temperature=0.7,
                max_output_tokens=500
            )
        )
        
        reply_text = response.text
        save_message(user.id, "bot", reply_text)
        
        await update.message.reply_text(reply_text)
        
    except Exception as e:
        logging.error(f"Error calling Gemini: {e}")
        await update.message.reply_text("مشکلی پیش اومد، دوباره بفرست.")

if __name__ == '__main__':
    init_db()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(gender_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("ربات دارابی با قابلیت ری‌اکشن و کار در گروه روشن شد...")
    app.run_polling()