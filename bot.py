import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime, timedelta

requests = {}
shifts = ["Ночь", "Утро", "День"]
valid_names = ["Виолетта", "Нести", "Мари", "Лила"]
name_regex = re.compile(r'^(?:' + '|'.join(valid_names) + r')$')
date_regex = re.compile(r'^\d{2}\.\d{2}$')

def show_main_keyboard():
    keyboard = [[KeyboardButton("📅 Мои выходные"), KeyboardButton("📅 Доступные выходные")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Главное сообщение
async def request_off_day(update: Update, context):
    try:
        user = update.message.from_user
        request = update.message.text.strip().split("\n")

        if update.message.text == "📅 Мои выходные":
            await show_user_days(update, context)
            return
        if update.message.text == "📅 Доступные выходные":
            await show_available_days(update, context, 0)
            return

        if len(request) != 3:
            await update.message.reply_text("Пожалуйста, укажите запрос в формате:\n1. Имя анкеты\n2. Дата\n3. Смена",
                                            reply_markup=show_main_keyboard())
            return

        name = request[0].strip().split(". ")[1]
        date = request[1].strip().split(". ")[1]
        shift = request[2].strip().split(". ")[1]

        if not name_regex.match(name):
            await update.message.reply_text("Неверная анкета. Используйте: Виолетта, Нести, Мари, Лила.",
                                            reply_markup=show_main_keyboard())
            return

        if not date_regex.match(date):
            await update.message.reply_text("Неверный формат даты. Используйте 'День.Месяц', например, 01.05.",
                                            reply_markup=show_main_keyboard())
            return

        if shift not in shifts:
            await update.message.reply_text("Неверная смена. Укажите: Ночь, Утро, День.",
                                            reply_markup=show_main_keyboard())
            return

        date = datetime.strptime(date, "%d.%m").strftime("%d.%m")

        if date not in requests:
            requests[date] = {}

        if name in requests[date]:
            await update.message.reply_text(f"Для {name} уже зарегистрирован выходной на {date}.",
                                            reply_markup=show_main_keyboard())
            return

        if shift in [v['shift'] for v in requests.get(date, {}).values()]:
            await update.message.reply_text(f"На {date} смена {shift} уже занята.",
                                            reply_markup=show_main_keyboard())
            return

        requests[date][name] = {'shift': shift, 'user_id': user.id}
        username = f"@{user.username}" if user.username else f"{user.first_name}"
        await update.message.reply_text(f"Запрос принят: {name}, {date}, {shift} — {username}",
                                        reply_markup=show_main_keyboard())

        available = [s for s in shifts if s not in [v['shift'] for v in requests.get(date, {}).values()]]
        if not available:
            await update.message.reply_text(f"На {date} все смены заняты.",
                                            reply_markup=show_main_keyboard())
        else:
            await update.message.reply_text(f"На {date} доступны: {', '.join(available)}",
                                            reply_markup=show_main_keyboard())
    except Exception as e:
        print(f"Ошибка в request_off_day: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.",
                                        reply_markup=show_main_keyboard())

# --- Доступные выходные с постраничной навигацией
async def show_available_days(update: Update, context: ContextTypes.DEFAULT_TYPE, offset=0):
    today = datetime.now()
    available_days = []
    for i in range(offset, offset + 7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m")
        if date_str not in requests:
            requests[date_str] = {}

        if len(requests[date_str]) < len(shifts):
            available = [s for s in shifts if s not in [v['shift'] for v in requests[date_str].values()]]
            available_days.append(f"{date_str} — {', '.join(available)}")

    text = "\n".join(available_days) if available_days else "Нет доступных смен на выбранный период."

    buttons = []
    if offset >= 7:
        buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page:{offset - 7}"))
    if offset + 7 < 60:
        buttons.append(InlineKeyboardButton("▶️ Далее", callback_data=f"page:{offset + 7}"))

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([buttons]) if buttons else show_main_keyboard()
    )

# --- Обработка callback для пагинации
async def handle_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    offset = int(query.data.split(":")[1])
    today = datetime.now()
    available_days = []
    for i in range(offset, offset + 7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m")
        if date_str not in requests:
            requests[date_str] = {}
        if len(requests[date_str]) < len(shifts):
            available = [s for s in shifts if s not in [v['shift'] for v in requests[date_str].values()]]
            available_days.append(f"{date_str} — {', '.join(available)}")

    text = "\n".join(available_days) if available_days else "Нет доступных смен на выбранный период."

    buttons = []
    if offset >= 7:
        buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page:{offset - 7}"))
    if offset + 7 < 60:
        buttons.append(InlineKeyboardButton("▶️ Далее", callback_data=f"page:{offset + 7}"))

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([buttons]) if buttons else None
    )

# --- Показывает выходные пользователя и кнопки отмены
async def show_user_days(update: Update, context):
    user = update.message.from_user
    name = None
    today = datetime.now()

    for day, records in list(requests.items()):
        for n, record in records.items():
            if record['user_id'] == user.id:
                name = n
                break
        if name:
            break

    if not name:
        await update.message.reply_text("У вас нет зарегистрированных выходных.",
                                        reply_markup=show_main_keyboard())
        return

    days = []
    for date_str in list(requests.keys()):
        try:
            date_obj = datetime.strptime(date_str, "%d.%m").replace(year=today.year)
            if date_obj < today:
                if name in requests[date_str]:
                    del requests[date_str][name]
                if not requests[date_str]:
                    del requests[date_str]
                continue
            if name in requests[date_str]:
                shift = requests[date_str][name]['shift']
                button = InlineKeyboardButton(f"❌ {date_str} ({shift})", callback_data=f"cancel:{name}:{date_str}")
                days.append([button])
        except ValueError:
            continue

    if not days:
        await update.message.reply_text("У вас нет зарегистрированных выходных.",
                                        reply_markup=show_main_keyboard())
    else:
        await update.message.reply_text("Ваши выходные:", reply_markup=InlineKeyboardMarkup(days))

async def cancel_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, name, date = query.data.split(":")
        user_id = query.from_user.id

        if date in requests and name in requests[date] and requests[date][name]['user_id'] == user_id:
            del requests[date][name]
            if not requests[date]:
                del requests[date]
            await query.edit_message_text(f"Выходной {name} на {date} отменён.")
        else:
            await query.edit_message_text("Вы не можете отменить чужой выходной или выходной не найден.")
    except Exception as e:
        print(f"Ошибка в cancel_day: {e}")
        await query.edit_message_text("Произошла ошибка при отмене выходного.")

async def clear_data(update: Update, context):
    try:
        admin_user_ids = [8062513822]
        if update.message.from_user.id not in admin_user_ids:
            await update.message.reply_text("У вас нет доступа к этой команде.")
            return

        global requests
        requests = {}
        await update.message.reply_text("База данных очищена.",
                                        reply_markup=show_main_keyboard())
    except Exception as e:
        print(f"Ошибка в clear_data: {e}")
        await update.message.reply_text("Ошибка при очистке.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я помогу тебе с выходными. Отправь запрос:\n1. Имя анкеты\n2. Дата (дд.мм)\n3. Смена (Ночь/Утро/День)",
        reply_markup=show_main_keyboard()
    )

def main():
    try:
        BOT_TOKEN = "8028021620:AAFUf3q77NT9Xq0_LQbkzrzGajTXR4f3vXg"
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("clear", clear_data))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, request_off_day))
        application.add_handler(CallbackQueryHandler(cancel_day, pattern=r"^cancel:"))
        application.add_handler(CallbackQueryHandler(handle_page_callback, pattern=r"^page:"))

        application.run_polling()
    except Exception as e:
        print(f"Ошибка в main(): {e}")

if __name__ == '__main__':
    main()
