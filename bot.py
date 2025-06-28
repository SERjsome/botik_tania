import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler
from datetime import datetime, timedelta

requests = {}
shifts = ["Ночь", "Утро", "День"]
valid_names = ["Виолетта", "Нести", "Мари", "Лила", "Ева"]
name_regex = re.compile(r'^(?:' + '|'.join(valid_names) + r')$')
date_regex = re.compile(r'^\d{2}\.\d{2}$')

admin_user_ids = [8062513822, 7500867626]

CHANGE_TAG_NEW = range(1)

def show_main_keyboard(user_id=None):
    keyboard = [[KeyboardButton("📅 Мои выходные"), KeyboardButton("📅 Доступные выходные")]]
    if user_id in admin_user_ids:
        keyboard.append([KeyboardButton("🔧 Админ-панель"), KeyboardButton("📋 Список выходных")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я помогу тебе с выходными. Отправь запрос:\n1. Имя анкеты\n2. Дата (дд.мм)\n3. Смена (Ночь/Утро/День)",
        reply_markup=show_main_keyboard(update.message.from_user.id)
    )

async def show_admin_panel(update: Update, context):
    user_id = update.message.from_user.id
    if user_id not in admin_user_ids:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    today = datetime.now()
    text = "📅 Запланированные выходные на ближайшие дни:\n\n"
    found = False
    for i in range(60):
        date = (today + timedelta(days=i)).strftime("%d.%m")
        if date in requests and requests[date]:
            found = True
            text += f"🗓 {date}:\n"

            buttons = []
            for name, data in requests[date].items():
                text += f"  — {name} ({data['shift']}) — {data['username']}\n"
                buttons.append([InlineKeyboardButton(f"Изменить тег: {name}", callback_data=f"tag:{name}:{date}")])

            text += "\n"
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            text = ""

    if not found:
        await update.message.reply_text("Нет запланированных выходных на ближайшие дни.")

async def start_tag_change_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    try:
        _, name, date = data.split(":")
    except Exception:
        await query.edit_message_text("Ошибка при обработке запроса.")
        return ConversationHandler.END

    context.user_data['tag_user'] = name
    context.user_data['tag_date'] = date

    await query.edit_message_text(f"Введите новый тег для пользователя {name} (выходной {date}):")
    return CHANGE_TAG_NEW[0]

async def receive_new_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_tag = update.message.text.strip()
    name = context.user_data.get('tag_user')
    date = context.user_data.get('tag_date')

    if not name or not date:
        await update.message.reply_text("Ошибка: нет данных о пользователе.")
        return ConversationHandler.END

    if date in requests and name in requests[date]:
        requests[date][name]['username'] = new_tag
        await update.message.reply_text(f"Тег пользователя {name} на {date} изменён на: {new_tag}",
                                        reply_markup=show_main_keyboard(update.message.from_user.id))
    else:
        await update.message.reply_text(f"Пользователь {name} с выходным на {date} не найден.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.", reply_markup=show_main_keyboard(update.message.from_user.id))
    return ConversationHandler.END

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
        if update.message.text == "🔧 Админ-панель":
            await show_admin_panel(update, context)
            return
        if update.message.text == "📋 Список выходных":
            await show_days_overview_for_admin(update, context)
            return

        if len(request) != 3:
            await update.message.reply_text("Пожалуйста, укажите запрос в формате:\n1. Имя анкеты\n2. Дата\n3. Смена",
                                            reply_markup=show_main_keyboard(user.id))
            return

        name = request[0].strip().split(". ")[1]
        date = request[1].strip().split(". ")[1]
        shift = request[2].strip().split(". ")[1]

        if not name_regex.match(name):
            await update.message.reply_text("Неверная анкета. Используйте: Виолетта, Нести, Мари, Лила, Ева.",
                                            reply_markup=show_main_keyboard(user.id))
            return

        if not date_regex.match(date):
            await update.message.reply_text("Неверный формат даты. Используйте 'День.Месяц', например, 01.05.",
                                            reply_markup=show_main_keyboard(user.id))
            return

        if shift not in shifts:
            await update.message.reply_text("Неверная смена. Укажите: Ночь, Утро, День.",
                                            reply_markup=show_main_keyboard(user.id))
            return

        date = datetime.strptime(date, "%d.%m").strftime("%d.%m")

        if date not in requests:
            requests[date] = {}

        if name in requests[date]:
            await update.message.reply_text(f"Для {name} уже зарегистрирован выходной на {date}.",
                                            reply_markup=show_main_keyboard(user.id))
            return

        if shift in [v['shift'] for v in requests.get(date, {}).values()]:
            await update.message.reply_text(f"На {date} смена {shift} уже занята.",
                                            reply_markup=show_main_keyboard(user.id))
            return

        requests[date][name] = {
            'shift': shift,
            'user_id': user.id,
            'username': f"@{user.username}" if user.username else user.first_name
        }

        await update.message.reply_text(f"Запрос принят: {name}, {date}, {shift} — {requests[date][name]['username']}",
                                        reply_markup=show_main_keyboard(user.id))

        available = [s for s in shifts if s not in [v['shift'] for v in requests.get(date, {}).values()]]
        if not available:
            await update.message.reply_text(f"На {date} все смены заняты.",
                                            reply_markup=show_main_keyboard(user.id))
        else:
            await update.message.reply_text(f"На {date} доступны: {', '.join(available)}",
                                            reply_markup=show_main_keyboard(user.id))
    except Exception as e:
        print(f"Ошибка в request_off_day: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.",
                                        reply_markup=show_main_keyboard(user.id))

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
                                        reply_markup=show_main_keyboard(user.id))
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
                                        reply_markup=show_main_keyboard(user.id))
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
        reply_markup=InlineKeyboardMarkup([buttons]) if buttons else show_main_keyboard(update.message.from_user.id)
    )

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

async def clear_data(update: Update, context):
    try:
        if update.message.from_user.id not in admin_user_ids:
            await update.message.reply_text("У вас нет доступа к этой команде.")
            return

        global requests
        requests = {}
        await update.message.reply_text("База данных очищена.",
                                        reply_markup=show_main_keyboard(update.message.from_user.id))
    except Exception as e:
        print(f"Ошибка в clear_data: {e}")
        await update.message.reply_text("Ошибка при очистке.")

# --- Новая функция: список выходных на 14 дней вперёд ---
async def show_days_overview_for_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admin_user_ids:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    today = datetime.now()
    text = "📋 Выходные по датам на 14 дней вперёд:\n\n"
    found = False

    for i in range(14):
        date = (today + timedelta(days=i)).strftime("%d.%m")
        if date in requests and requests[date]:
            found = True
            text += f"🗓 {date}:\n"
            for name, data in requests[date].items():
                text += f"  — {name} ({data['shift']}) — {data['username']}\n"
            text += "\n"

    if not found:
        await update.message.reply_text("Нет выходных на ближайшие 14 дней.")
    else:
        await update.message.reply_text(text)

def main():
    try:
        BOT_TOKEN = "8028021620:AAFUf3q77NT9Xq0_LQbkzrzGajTXR4f3vXg"
        application = Application.builder().token(BOT_TOKEN).build()

        tag_change_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_tag_change_from_button, pattern=r"^tag:")],
            states={
                CHANGE_TAG_NEW[0]: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_tag)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(tag_change_handler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, request_off_day))
        application.add_handler(CallbackQueryHandler(cancel_day, pattern=r"^cancel:"))
        application.add_handler(CallbackQueryHandler(handle_page_callback, pattern=r"^page:"))
        application.add_handler(CommandHandler("clear", clear_data))
        application.add_handler(CommandHandler("admin", show_admin_panel))

        application.run_polling()
    except Exception as e:
        print(f"Ошибка в main(): {e}")

if __name__ == '__main__':
    main()
