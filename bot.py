import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime, timedelta

# Словарь для хранения запросов на выходной (аналог базы данных)
requests = {}

# Список смен
shifts = ["Ночь", "Утро", "День"]

# Регулярное выражение для проверки анкеты
valid_names = ["Виолетта", "Нести", "Мари", "Лила"]  # Обновлённый список анкет
name_regex = re.compile(r'^(?:' + '|'.join(valid_names) + r')$')

# Регулярное выражение для проверки даты в формате 00.00
date_regex = re.compile(r'^\d{2}\.\d{2}$')

# Функция для показа клавиатуры с кнопками "📅 Мои выходные" и "Доступные выходные"
def show_main_keyboard():
    keyboard = [
        [KeyboardButton("📅 Мои выходные"), KeyboardButton("📅 Доступные выходные")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функция для обработки запроса на выходной
async def request_off_day(update: Update, context):
    try:
        user = update.message.from_user
        request = update.message.text.strip().split("\n")

        if update.message.text == "📅 Мои выходные":
            await show_user_days(update, context)
            return
        
        if update.message.text == "📅 Доступные выходные":
            await show_available_days(update, context)
            return

        print(f"Received message: {update.message.text}")

        if len(request) != 3:
            await update.message.reply_text("Пожалуйста, укажите запрос в формате: \n1. Имя анкеты\n2. Дата\n3. Смена",
                                            reply_markup=show_main_keyboard())
            return

        name = request[0].strip().split(". ")[1]
        date = request[1].strip().split(". ")[1]
        shift = request[2].strip().split(". ")[1]

        if not name_regex.match(name):
            await update.message.reply_text("Неверная анкета. Пожалуйста, укажите одну из следующих: Виолетта, Нести, Мари, Лила.",
                                            reply_markup=show_main_keyboard())
            return

        if not date_regex.match(date):
            await update.message.reply_text("Неверный формат даты. Пожалуйста, используйте формат: 'День.Месяц' (например, 01.05).",
                                            reply_markup=show_main_keyboard())
            return

        if shift not in shifts:
            await update.message.reply_text("Неверная смена. Укажите одну из следующих: Ночь, Утро, День.",
                                            reply_markup=show_main_keyboard())
            return

        date = datetime.strptime(date, "%d.%m").strftime("%d.%m")

        if date not in requests:
            requests[date] = {}

        if name in requests[date]:
            await update.message.reply_text(f"На {date} для анкеты {name} уже был принят выходной. Не могу предоставить другой выходной в этот день.",
                                            reply_markup=show_main_keyboard())
            return

        if shift in [v['shift'] for v in requests.get(date, {}).values()]:
            await update.message.reply_text(f"На {date} смена {shift} уже занята. Пожалуйста, выберите другую смену.",
                                            reply_markup=show_main_keyboard())
            return

        requests[date][name] = {'shift': shift, 'user_id': user.id}
        await update.message.reply_text(f"Запрос на выходной принят: {name}, {date}, {shift}", reply_markup=show_main_keyboard())

        available_shifts = [s for s in shifts if s not in [v['shift'] for v in requests.get(date, {}).values()]]
        if not available_shifts:
            await update.message.reply_text(f"На {date} все смены заняты.", reply_markup=show_main_keyboard())
        else:
            await update.message.reply_text(f"На {date} доступны: {', '.join(available_shifts)}",
                                            reply_markup=show_main_keyboard())
    except Exception as e:
        print(f"Error occurred in request_off_day: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.", reply_markup=show_main_keyboard())

# Функция отображения выходных пользователя
async def show_user_days(update: Update, context):
    user = update.message.from_user
    name = None
    for day, records in requests.items():
        for n, record in records.items():
            if record['user_id'] == user.id:
                name = n
                break
    if not name:
        await update.message.reply_text("У вас нет зарегистрированных выходных.", reply_markup=show_main_keyboard())
        return

    days = []
    for date, users in requests.items():
        if name in users:
            shift = users[name]['shift']
            button = InlineKeyboardButton(f"❌ {date} ({shift})", callback_data=f"cancel:{name}:{date}")
            days.append([button])

    if not days:
        await update.message.reply_text("У вас нет зарегистрированных выходных.", reply_markup=show_main_keyboard())
        return

    await update.message.reply_text("Ваши выходные:", reply_markup=InlineKeyboardMarkup(days))

# Функция отображения доступных выходных на неделю вперёд
async def show_available_days(update: Update, context):
    today = datetime.now()
    available_days = []
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m")
        if date_str not in requests:
            requests[date_str] = {}

        if len(requests[date_str]) < len(shifts):
            available_shifts = [shift for shift in shifts if shift not in [v['shift'] for v in requests[date_str].values()]]
            available_days.append(f"На {date_str} доступны: {', '.join(available_shifts)}")

    if not available_days:
        await update.message.reply_text("На данный момент нет доступных выходных.", reply_markup=show_main_keyboard())
    else:
        await update.message.reply_text("\n".join(available_days), reply_markup=show_main_keyboard())

# Функция отмены выходного
async def cancel_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, name, date = query.data.split(":")
        user_id = update.callback_query.from_user.id

        if date in requests and name in requests[date] and requests[date][name]['user_id'] == user_id:
            del requests[date][name]
            if not requests[date]:
                del requests[date]
            await query.edit_message_text(f"Выходной {name} на {date} отменён.")
        else:
            await query.edit_message_text("Вы не можете отменить выходной другого пользователя или выходной не найден.")
    except Exception as e:
        print(f"Error in cancel_day: {e}")
        await query.edit_message_text("Произошла ошибка при отмене выходного.")

# Функция очистки базы данных
async def clear_data(update: Update, context):
    try:
        admin_user_ids = [8062513822]
        user_id = update.message.from_user.id

        if user_id not in admin_user_ids:
            await update.message.reply_text("У вас нет прав для очистки базы данных.")
            return

        global requests
        requests = {}
        await update.message.reply_text("База данных очищена.", reply_markup=show_main_keyboard())
    except Exception as e:
        print(f"Error occurred in clear_data: {e}")
        await update.message.reply_text("Произошла ошибка при очистке базы данных.")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я помогу тебе управлять выходными. Пожалуйста, отправь запрос в формате: \n1. Имя анкеты\n2. Дата\n3. Смена (Ночь, Утро, День)",
        reply_markup=show_main_keyboard()
    )

# Основной запуск
def main():
    try:
        BOT_TOKEN = "8028021620:AAFUf3q77NT9Xq0_LQbkzrzGajTXR4f3vXg"
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, request_off_day))
        application.add_handler(CommandHandler("clear", clear_data))
        application.add_handler(CallbackQueryHandler(cancel_day))

        application.run_polling()
    except Exception as e:
        print(f"Error occurred in main function: {e}")

if __name__ == '__main__':
    main()
