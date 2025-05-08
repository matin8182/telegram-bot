from fastapi import FastAPI, Request, Response
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
import time
from datetime import datetime, timedelta
import jdatetime
import re
import os
import asyncio

app = FastAPI()

# توکن ربات
TOKEN = "7728604413:AAEDn6YAkMf1ohttgUsR5FoveUMScyqMmZU"
BOT_USERNAME = "@hfhfdhdfgh_bot"
CHANNEL_ID = "@signalbymatin"

# دیکشنری‌های موقت برای داده‌ها
users = {}
admins = set()
vip_users = {}
invites = {}
reminders_sent = {}
last_signal = None
last_gold_price = None

ADMIN_CODE = "secret123"

# منوها
ADMIN_MENU = ReplyKeyboardMarkup([["تعداد کاربران و یوزرها", "افراد VIP"], ["بلاک کردن کاربر", "ثبت اشتراک VIP"], ["حذف اشتراک VIP", "ارسال پیام"], ["ثبت ادمین جدید"]], resize_keyboard=True)
SENDING_MENU = ReplyKeyboardMarkup([["ارسال به همه", "ارسال به VIP"], ["خروج از ارسال"]], resize_keyboard=True)
USER_MENU = ReplyKeyboardMarkup([["عضویت VIP", "وضعیت من"], ["ارتباط با ادمین"]], resize_keyboard=True)
VIP_USER_MENU = ReplyKeyboardMarkup([["عضویت VIP", "وضعیت من"], ["ارتباط با ادمین", "آخرین سیگنال"], ["قیمت انس طلا"]], resize_keyboard=True)
VIP_MENU = ReplyKeyboardMarkup([["عضویت VIP رایگان", "خرید اشتراک"], ["برگشت"]], resize_keyboard=True)

# توابع کمکی
def to_jalali(dt):
    jalali_date = jdatetime.datetime.fromtimestamp(dt.timestamp())
    return jalali_date.year, jalali_date.month, jalali_date.day, jalali_date.hour, jalali_date.minute

def format_expiration_date(expiration_time):
    if expiration_time == float('inf'):
        return "دائمی (بدون انقضا)"
    jalali_year, jalali_month, jalali_day, hour, minute = to_jalali(datetime.fromtimestamp(expiration_time))
    jalali_months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    return f"{jalali_day} {jalali_months[jalali_month - 1]} {jalali_year} تا ساعت {hour:02d}:{minute:02d}"

def get_remaining_time(expiration_time):
    if expiration_time == float('inf'):
        return "دائمی"
    current_time = time.time()
    remaining_seconds = expiration_time - current_time
    if remaining_seconds <= 0:
        return "منقضی شده"
    remaining_days = remaining_seconds // (24 * 60 * 60)
    remaining_seconds %= (24 * 60 * 60)
    remaining_hours = remaining_seconds // (60 * 60)
    remaining_seconds %= (60 * 60)
    remaining_minutes = remaining_seconds // 60
    remaining_seconds %= 60
    parts = []
    if remaining_days > 0:
        parts.append(f"{int(remaining_days)} روز")
    if remaining_hours > 0 or remaining_days > 0:
        parts.append(f"{int(remaining_hours)} ساعت")
    if remaining_minutes > 0 or remaining_hours > 0 or remaining_days > 0:
        parts.append(f"{int(remaining_minutes)} دقیقه")
    if remaining_seconds > 0 or (remaining_days == 0 and remaining_hours == 0 and remaining_minutes == 0):
        parts.append(f"{int(remaining_seconds)} ثانیه")
    return " و ".join(parts)

async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"خطا در چک کردن عضویت: {e}")
        return False

async def is_vip(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if chat_id in admins:
        return True
    if chat_id in vip_users:
        expiration_time = vip_users[chat_id]
        if expiration_time == float('inf'):
            return True
        current_time = time.time()
        if expiration_time > current_time:
            return True
        else:
            if chat_id not in reminders_sent or not reminders_sent[chat_id].get("expired", False):
                try:
                    await context.bot.send_message(chat_id=chat_id, text="اشتراک VIP شما به پایان رسید. لطفاً برای تمدید اقدام کنید.", reply_markup=USER_MENU)
                    if chat_id not in reminders_sent:
                        reminders_sent[chat_id] = {"under_3_days": False, "under_1_day": False, "expired": False}
                    reminders_sent[chat_id]["expired"] = True
                except Exception as e:
                    print(f"خطا در ارسال پیام انقضا به کاربر {chat_id}: {e}")
            del vip_users[chat_id]
    return False

async def send_vip_reminders(context: ContextTypes.DEFAULT_TYPE):
    print("چک کردن یادآوری‌های VIP...")
    current_time = time.time()
    for chat_id in list(vip_users.keys()):
        if chat_id in admins:
            continue
        if not await is_vip(chat_id, context):
            continue
        expiration_time = vip_users[chat_id]
        if expiration_time == float('inf'):
            continue
        remaining_seconds = expiration_time - current_time
        remaining_days = remaining_seconds / (24 * 60 * 60)
        if chat_id not in reminders_sent:
            reminders_sent[chat_id] = {"under_3_days": False, "under_1_day": False, "expired": False}
        if 1 <= remaining_days <= 3 and not reminders_sent[chat_id]["under_3_days"]:
            try:
                await context.bot.send_message(chat_id=chat_id, text=f"یادآوری: کمتر از {get_remaining_time(expiration_time)} تا پایان اشتراک VIP شما باقی مانده است.\nلطفاً برای تمدید اقدام کنید.", reply_markup=VIP_USER_MENU)
                reminders_sent[chat_id]["under_3_days"] = True
            except Exception as e:
                print(f"خطا در ارسال یادآوری 3 روز به کاربر {chat_id}: {e}")
        if remaining_days < 1 and not reminders_sent[chat_id]["under_1_day"]:
            try:
                await context.bot.send_message(chat_id=chat_id, text=f"یادآوری فوری: کمتر از {get_remaining_time(expiration_time)} تا پایان اشتراک VIP شما باقی مانده است.\nلطفاً برای تمدید اقدام کنید.", reply_markup=VIP_USER_MENU)
                reminders_sent[chat_id]["under_1_day"] = True
            except Exception as e:
                print(f"خطا در ارسال یادآوری 1 روز به کاربر {chat_id}: {e}")

def generate_referral_link(chat_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME[1:]}?start={chat_id}"

# هندلرها
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "بدون یوزرنیم"
    args = context.args
    if args:
        context.user_data["referrer_id"] = int(args[0])
    if chat_id in users:
        if user_id in admins:
            await update.message.reply_text("خوش برگشتی!", reply_markup=ADMIN_MENU)
        elif await is_vip(chat_id, context):
            expiration_time = vip_users.get(chat_id, float('inf'))
            expiration_text = format_expiration_date(expiration_time)
            await update.message.reply_text(f"خوش برگشتی! شما عضو VIP هستید.\nعضویت شما تا {expiration_text} فعال است.", reply_markup=VIP_USER_MENU)
        else:
            await update.message.reply_text("خوش برگشتی!", reply_markup=USER_MENU)
        return
    is_member = await check_membership(user_id, context)
    if not is_member:
        await update.message.reply_text(f"برای استفاده از ربات، باید توی کانال ما عضو بشی!\nلینک کانال: {CHANNEL_ID}\nبعد از عضویت، /check رو بزن.", reply_markup=ReplyKeyboardRemove())
        return
    users[chat_id] = username
    invites[chat_id] = {"invited_count": 0, "referral_link": generate_referral_link(chat_id)}
    if user_id in admins:
        await update.message.reply_text("سلام! به ربات خوش اومدی.", reply_markup=ADMIN_MENU)
    else:
        await update.message.reply_text("سلام! به ربات خوش اومدی.", reply_markup=USER_MENU)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "بدون یوزرنیم"
    if chat_id in users:
        if user_id in admins:
            await update.message.reply_text("خوش برگشتی!", reply_markup=ADMIN_MENU)
        elif await is_vip(chat_id, context):
            expiration_time = vip_users.get(chat_id, float('inf'))
            expiration_text = format_expiration_date(expiration_time)
            await update.message.reply_text(f"خوش برگشتی! شما عضو VIP هستید.\nعضویت شما تا {expiration_text} فعال است.", reply_markup=VIP_USER_MENU)
        else:
            await update.message.reply_text("خوش برگشتی!", reply_markup=USER_MENU)
        return
    is_member = await check_membership(user_id, context)
    if not is_member:
        await update.message.reply_text(f"شما هنوز توی کانال عضو نشدی!\nلینک کانال: {CHANNEL_ID}\nبعد از عضویت، دوباره /check رو بزن.", reply_markup=ReplyKeyboardRemove())
        return
    users[chat_id] = username
    invites[chat_id] = {"invited_count": 0, "referral_link": generate_referral_link(chat_id)}
    referrer_id = context.user_data.get("referrer_id")
    if referrer_id and referrer_id in invites and chat_id != referrer_id:
        invites[referrer_id]["invited_count"] = invites.get(referrer_id, {}).get("invited_count", 0) + 1
        remaining = 4 - invites[referrer_id]["invited_count"]
        try:
            await context.bot.send_message(chat_id=referrer_id, text=f"تبریک می‌گم! یک نفر با لینک شما عضو شد.\n{remaining} نفر دیگه تا عضویت VIP رایگان باقی مونده!")
        except Exception as e:
            print(f"خطا در ارسال پیام به دعوت‌کننده {referrer_id}: {e}")
        context.user_data.pop("referrer_id", None)
    if user_id in admins:
        await update.message.reply_text("سلام! به ربات خوش اومدی.", reply_markup=ADMIN_MENU)
    else:
        await update.message.reply_text("سلام! به ربات خوش اومدی.", reply_markup=USER_MENU)

async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    args = context.args
    if not args:
        await update.message.reply_text("دستور نادرست!", reply_markup=ADMIN_MENU if user_id in admins else ReplyKeyboardRemove())
        return
    code = args[0]
    if code == ADMIN_CODE:
        admins.add(user_id)
        vip_users[user_id] = float('inf')
        reminders_sent[user_id] = {"under_3_days": False, "under_1_day": False, "expired": False}    
        await update.message.reply_text("شما ادمین شدید!", reply_markup=ADMIN_MENU)
    else:
        await update.message.reply_text("دستور نادرست!", reply_markup=ADMIN_MENU if user_id in admins else ReplyKeyboardRemove())

async def forward_message_to_all(update: Update, context: ContextTypes.DEFAULT_TYPE, target: str):
    global last_signal
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    message = update.message
    if user_id not in admins:
        await message.reply_text("نمی‌تونی پیام ارسال کنی!", reply_markup=USER_MENU if chat_id in users else ReplyKeyboardRemove())
        return
    if context.user_data.get("state") != "sending":
        return
    last_signal = {"type": "forward", "message_id": message.message_id, "chat_id": chat_id}
    sent_count = 0
    target_users = users if target == "all" else {cid: uname for cid, uname in users.items() if await is_vip(cid, context)}
    for user_chat_id in target_users:
        try:
            await message.forward(chat_id=user_chat_id, protect_content=True)
            sent_count += 1
            print(f"پیام به چت {user_chat_id} فوروارد شد.")
        except Exception as e:
            print(f"خطا در فوروارد به چت {user_chat_id}: {e}")
            continue
    await message.reply_text(f"پیام به {sent_count} چت ارسال شد.", reply_markup=SENDING_MENU)
    context.user_data.pop("state", None)

async def broadcast_message(message: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int, target: str):
    global last_signal
    sent_count = 0
    target_users = users if target == "all" else {cid: uname for cid, uname in users.items() if await is_vip(cid, context)}
    for user_chat_id in target_users:
        if user_chat_id == chat_id:
            continue
        try:
            sent_message = await context.bot.send_message(chat_id=user_chat_id, text=f"پیام از ادمین: {message}", protect_content=True)
            if user_chat_id == list(target_users.keys())[0]:
                last_signal = {"type": "text", "message_id": sent_message.message_id, "chat_id": user_chat_id, "text": f"پیام از ادمین: {message}"}
            sent_count += 1
            print(f"پیام به چت {user_chat_id} ارسال شد.")
        except Exception as e:
            print(f"خطا در ارسال به چت {user_chat_id}: {e}")
            continue
    await context.bot.send_message(chat_id=chat_id, text=f"پیام به {sent_count} چت ارسال شد.", reply_markup=SENDING_MENU)
    context.user_data.pop("state", None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text
    if user_id in admins:
        if context.user_data.get("state") == "sending":
            if text == "خروج از ارسال":
                context.user_data.pop("state", None)
                context.user_data.pop("send_target", None)
                await update.message.reply_text("از حالت ارسال خارج شدی.", reply_markup=ADMIN_MENU)
            elif text == "ارسال به همه":
                context.user_data["send_target"] = "all"
                await update.message.reply_text("پیام خودت رو بفرست، به همه ارسال می‌شه.", reply_markup=SENDING_MENU)
            elif text == "ارسال به VIP":
                context.user_data["send_target"] = "vip"
                await update.message.reply_text("پیام خودت رو بفرست، فقط به کاربران VIP ارسال می‌شه.", reply_markup=SENDING_MENU)
            else:
                target = context.user_data.get("send_target", "all")
                await broadcast_message(text, context, chat_id, target)
            return
        if context.user_data.get("state") == "register_vip_user":
            username = text[1:] if text.startswith("@") else text
            chat_id_to_register = None
            for cid, uname in users.items():
                if uname == username:
                    chat_id_to_register = cid
                    break
            if chat_id_to_register:
                context.user_data["vip_user_id"] = chat_id_to_register
                context.user_data["state"] = "register_vip_minutes"
                await update.message.reply_text("تعداد دقیقه‌های اشتراک VIP رو وارد کن (مثلاً 60 برای 1 ساعت):", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
            else:
                await update.message.reply_text("کاربر پیدا نشد!", reply_markup=ADMIN_MENU)
                context.user_data.pop("state", None)
            return
        if context.user_data.get("state") == "register_vip_minutes":
            if text == "لغو":
                context.user_data.pop("state", None)
                context.user_data.pop("vip_user_id", None)
                await update.message.reply_text("عملیات لغو شد.", reply_markup=ADMIN_MENU)
                return
            try:
                minutes = int(text)
                if minutes <= 0:
                    raise ValueError("تعداد دقیقه‌ها باید مثبت باشد!")
                vip_user_id = context.user_data["vip_user_id"]
                expiration_time = time.time() + minutes * 60
                vip_users[vip_user_id] = expiration_time
                reminders_sent[vip_user_id] = {"under_3_days": False, "under_1_day": False, "expired": False}
                expiration_text = format_expiration_date(expiration_time)
                await update.message.reply_text(f"اشتراک VIP برای کاربر @{users[vip_user_id]} ثبت شد.\nعضویت تا {expiration_text} فعال است.", reply_markup=ADMIN_MENU)
                try:
                    await context.bot.send_message(chat_id=vip_user_id, text=f"تبریک! اشتراک VIP شما توسط ادمین ثبت شد.\nعضویت شما تا {expiration_text} فعال است.", reply_markup=VIP_USER_MENU)
                except Exception as e:
                    print(f"خطا در ارسال پیام به کاربر {vip_user_id}: {e}")
            except ValueError as e:
                await update.message.reply_text(f"خطا: {str(e)}\nلطفاً یه عدد معتبر وارد کن!", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
                return
            context.user_data.pop("state", None)
            context.user_data.pop("vip_user_id", None)
            return
        if context.user_data.get("state") == "remove_vip":
            username = text[1:] if text.startswith("@") else text
            chat_id_to_remove = None
            for cid, uname in users.items():
                if uname == username and await is_vip(cid, context) and cid not in admins:
                    chat_id_to_remove = cid
                    break
            if chat_id_to_remove:
                del vip_users[chat_id_to_remove]
                if chat_id_to_remove in reminders_sent:
                    del reminders_sent[chat_id_to_remove]
                await update.message.reply_text(f"اشتراک VIP کاربر @{username} حذف شد.", reply_markup=ADMIN_MENU)
                try:
                    await context.bot.send_message(chat_id=chat_id_to_remove, text="اشتراک VIP شما توسط ادمین حذف شد.", reply_markup=USER_MENU)
                except Exception as e:
                    print(f"خطا در ارسال پیام به کاربر {chat_id_to_remove}: {e}")
            else:
                await update.message.reply_text("کاربر VIP پیدا نشد یا ادمین است!", reply_markup=ADMIN_MENU)
            context.user_data.pop("state", None)
            return
        if context.user_data.get("state") == "register_admin_manual":
            if text == "لغو":
                context.user_data.pop("state", None)
                await update.message.reply_text("عملیات لغو شد.", reply_markup=ADMIN_MENU)
                return
            username = text[1:] if text.startswith("@") else text
            chat_id_to_admin = None
            for cid, uname in users.items():
                if uname == username:
                    chat_id_to_admin = cid
                    break
            if chat_id_to_admin:
                admins.add(chat_id_to_admin)
                vip_users[chat_id_to_admin] = float('inf')
                reminders_sent[chat_id_to_admin] = {"under_3_days": False, "under_1_day": False, "expired": False}
                await update.message.reply_text(f"کاربر @{username} به عنوان ادمین ثبت شد.", reply_markup=ADMIN_MENU)
                try:
                    await context.bot.send_message(chat_id=chat_id_to_admin, text="تبریک! شما توسط ادمین به عنوان ادمین جدید ثبت شدید.", reply_markup=ADMIN_MENU)
                except Exception as e:
                    print(f"خطا در ارسال پیام به کاربر {chat_id_to_admin}: {e}")
            else:
                await update.message.reply_text("کاربر پیدا نشد!", reply_markup=ADMIN_MENU)
            context.user_data.pop("state", None)
            return
        if context.user_data.get("state") == "block_user":
            username = text[1:] if text.startswith("@") else text
            chat_id_to_block = None
            for cid, uname in users.items():
                if uname == username:
                    chat_id_to_block = cid
                    break
            if chat_id_to_block:
                del users[chat_id_to_block]
                await update.message.reply_text(f"کاربر @{username} بلاک شد.", reply_markup=ADMIN_MENU)
            else:
                await update.message.reply_text("کاربر پیدا نشد!", reply_markup=ADMIN_MENU)
            context.user_data.pop("state", None)
            return
        if text == "تعداد کاربران و یوزرها":
            if not users:
                await update.message.reply_text("هیچ کاربری ثبت نشده!", reply_markup=ADMIN_MENU)
            else:
                user_list = "\n".join([f"{chat_id}: @{username}" for chat_id, username in users.items()])
                await update.message.reply_text(f"تعداد کاربران: {len(users)}\nلیست کاربران:\n{user_list}", reply_markup=ADMIN_MENU)
        elif text == "افراد VIP":
            vip_list = {cid: uname for cid, uname in users.items() if await is_vip(cid, context)}
            if not vip_list:
                await update.message.reply_text("هیچ کاربر VIPای وجود نداره!", reply_markup=ADMIN_MENU)
            else:
                vip_details = []
                for cid, uname in vip_list.items():
                    remaining = get_remaining_time(vip_users.get(cid, float('inf')))
                    expiration_text = format_expiration_date(vip_users.get(cid, float('inf')))
                    vip_details.append(f"{cid}: @{uname} - زمان باقی‌مونده: {remaining} (تا {expiration_text})")
                await update.message.reply_text(f"تعداد کاربران VIP: {len(vip_list)}\nلیست کاربران VIP:\n" + "\n".join(vip_details), reply_markup=ADMIN_MENU)
        elif text == "بلاک کردن کاربر":
            if not users:
                await update.message.reply_text("هیچ کاربری برای بلاک کردن وجود نداره!", reply_markup=ADMIN_MENU)
                return
            keyboard = [[f"@{username}"] for chat_id, username in users.items() if chat_id != chat_id]
            keyboard.append(["لغو"])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("کاربری که می‌خوای بلاک کنی رو انتخاب کن:", reply_markup=reply_markup)
            context.user_data["state"] = "block_user"
        elif text == "ثبت اشتراک VIP":
            if not users:
                await update.message.reply_text("هیچ کاربری برای ثبت اشتراک وجود نداره!", reply_markup=ADMIN_MENU)
                return
            keyboard = [[f"@{username}"] for chat_id, username in users.items() if chat_id != chat_id]
            keyboard.append(["لغو"])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("کاربری که می‌خوای اشتراک VIP براش ثبت کنی رو انتخاب کن:", reply_markup=reply_markup)
            context.user_data["state"] = "register_vip_user"
        elif text == "حذف اشتراک VIP":
            vip_list = {cid: uname for cid, uname in users.items() if await is_vip(cid, context) and cid not in admins}
            if not vip_list:
                await update.message.reply_text("هیچ کاربر VIPای برای حذف وجود نداره!", reply_markup=ADMIN_MENU)
                return
            keyboard = [[f"@{username}"] for cid, username in vip_list.items()]
            keyboard.append(["لغو"])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("کاربری که می‌خوای اشتراک VIPش رو حذف کنی انتخاب کن:", reply_markup=reply_markup)
            context.user_data["state"] = "remove_vip"
        elif text == "ارسال پیام":
            context.user_data["state"] = "sending"
            await update.message.reply_text("وارد حالت ارسال شدی. مخاطب رو انتخاب کن:", reply_markup=SENDING_MENU)
        elif text == "ثبت ادمین جدید":
            if not users:
                await update.message.reply_text("هیچ کاربری برای ثبت به عنوان ادمین وجود نداره!", reply_markup=ADMIN_MENU)
                return
            keyboard = [[f"@{username}"] for chat_id, username in users.items() if chat_id != chat_id and chat_id not in admins]
            keyboard.append(["لغو"])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("کاربری که می‌خوای به عنوان ادمین ثبت کنی رو انتخاب کن:", reply_markup=reply_markup)
            context.user_data["state"] = "register_admin_manual"
        elif text == "لغو":
            await update.message.reply_text("عملیات لغو شد.", reply_markup=ADMIN_MENU)
            context.user_data.pop("state", None)
        return
    if text == "عضویت VIP":
        await update.message.reply_text("به بخش عضویت VIP خوش اومدی! گزینه مورد نظرت رو انتخاب کن:", reply_markup=VIP_MENU)
        context.user_data["state"] = "vip_menu"
        return
    elif text == "وضعیت من":
        if await is_vip(chat_id, context):
            expiration_time = vip_users.get(chat_id, float('inf'))
            remaining = get_remaining_time(expiration_time)
            expiration_text = format_expiration_date(expiration_time)
            await update.message.reply_text(f"شما عضو VIP هستید!\nزمان باقی‌مونده: {remaining}\nعضویت شما تا {expiration_text} فعال است.", reply_markup=VIP_USER_MENU)
        else:
            await update.message.reply_text("شما عضو عادی هستید. برای ارتقا به VIP، گزینه 'عضویت VIP' رو انتخاب کن.", reply_markup=USER_MENU)
        context.user_data.pop("state", None)
        return
    elif text == "ارتباط با ادمین":
        await update.message.reply_text("لطفاً پیام خودت رو بنویس تا برای ادمین‌ها ارسال بشه:", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
        context.user_data["state"] = "contact_admin"
        return
    elif text == "آخرین سیگنال":
        if not await is_vip(chat_id, context):
            await update.message.reply_text("این گزینه فقط برای کاربران VIP در دسترسه!", reply_markup=USER_MENU)
            context.user_data.pop("state", None)
            return
        if not last_signal:
            await update.message.reply_text("هنوز هیچ سیگنالی توسط ادمین ارسال نشده است.", reply_markup=VIP_USER_MENU)
            context.user_data.pop("state", None)
            return
        try:
            if last_signal["type"] == "forward":
                await context.bot.forward_message(chat_id=chat_id, from_chat_id=last_signal["chat_id"], message_id=last_signal["message_id"])
            elif last_signal["type"] == "text":
                await context.bot.send_message(chat_id=chat_id, text=last_signal["text"])
            print(f"آخرین سیگنال برای کاربر {chat_id} نمایش داده شد.")
        except Exception as e:
            print(f"خطا در نمایش آخرین سیگنال برای کاربر {chat_id}: {e}")
            await update.message.reply_text("خطایی در نمایش آخرین سیگنال رخ داد!", reply_markup=VIP_USER_MENU)
        context.user_data.pop("state", None)
        return
    elif text == "قیمت انس طلا":
        if not await is_vip(chat_id, context):
            await update.message.reply_text("این گزینه فقط برای کاربران VIP در دسترسه!", reply_markup=USER_MENU)
            context.user_data.pop("state", None)
            return
        await update.message.reply_text("متأسفانه قیمت طلا در حال حاضر در دسترس نیست. لطفاً برای فعال‌سازی با ادمین تماس بگیرید.", reply_markup=VIP_USER_MENU)
        context.user_data.pop("state", None)
        return
    elif context.user_data.get("state") == "contact_admin":
        if text == "لغو":
            context.user_data.pop("state", None)
            await update.message.reply_text("عملیات لغو شد.", reply_markup=USER_MENU if not await is_vip(chat_id, context) else VIP_USER_MENU)
            return
        sent_count = 0
        for admin_id in admins:
            try:
                await context.bot.send_message(chat_id=admin_id, text=f"پیام از کاربر @{users[chat_id]}:\n{text}")
                sent_count += 1
                print(f"پیام کاربر {chat_id} برای ادمین {admin_id} ارسال شد.")
            except Exception as e:
                print(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")
                continue
        await update.message.reply_text(f"پیام شما برای {sent_count} ادمین ارسال شد.", reply_markup=USER_MENU if not await is_vip(chat_id, context) else VIP_USER_MENU)
        context.user_data.pop("state", None)
        return
    elif context.user_data.get("state") == "vip_menu":
        if text == "عضویت VIP رایگان":
            invited_count = invites.get(chat_id, {}).get("invited_count", 0)
            if invited_count >= 4:
                expiration_time = time.time() + 2 * 24 * 60 * 60
                vip_users[chat_id] = expiration_time
                reminders_sent[chat_id] = {"under_3_days": False, "under_1_day": False, "expired": False}
                expiration_text = format_expiration_date(expiration_time)
                await update.message.reply_text(f"تبریک می‌گم! عضویت VIP شما تأیید شد.\nشما از الان تا {expiration_text} اشتراک VIP دارید.", reply_markup=VIP_USER_MENU)
            else:
                referral_link = invites.get(chat_id, {}).get("referral_link", generate_referral_link(chat_id))
                invites[chat_id] = {"invited_count": invited_count, "referral_link": referral_link}
                remaining = 4 - invited_count
                await update.message.reply_text(f"برای عضویت VIP رایگان، باید 4 نفر رو به ربات دعوت کنی.\nتعداد دعوت‌های فعلی: {invited_count}/4\n{remaining} نفر دیگه باقی مونده.\nلینک دعوتت: {referral_link}\nبعد از اینکه 4 نفر با لینکت وارد شدن، دوباره این گزینه رو انتخاب کن.", reply_markup=VIP_MENU)
        elif text == "خرید اشتراک":
            await update.message.reply_text("لطفاً برای خرید اشتراک با پشتیبانی تماس بگیر: @Support", reply_markup=VIP_MENU)
        elif text == "برگشت":
            context.user_data.pop("state", None)
            await update.message.reply_text("برگشتی به منوی اصلی.", reply_markup=USER_MENU if not await is_vip(chat_id, context) else VIP_USER_MENU)
        return
    else:
        await update.message.reply_text("نمی‌تونی پیام ارسال کنی!", reply_markup=USER_MENU if chat_id in users else ReplyKeyboardRemove())
        context.user_data.pop("state", None)

# تنظیم Application
application = Application.builder().token(TOKEN).build()
application.initialize()  # مقداردهی اولیه برای سازگاری با نسخه جدید
print(f"Application created and initialized: {application}")

# اضافه کردن هندلرها
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("check", check))
application.add_handler(CommandHandler("register_admin", register_admin))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(MessageHandler(filters.PHOTO, lambda update, context: forward_message_to_all(update, context, context.user_data.get("send_target", "all"))))
application.add_handler(MessageHandler(filters.VIDEO, lambda update, context: forward_message_to_all(update, context, context.user_data.get("send_target", "all"))))
application.add_handler(MessageHandler(filters.VOICE, lambda update, context: forward_message_to_all(update, context, context.user_data.get("send_target", "all"))))
application.add_handler(MessageHandler(filters.Document, lambda update, context: forward_message_to_all(update, context, context.user_data.get("send_target", "all"))))

# مسیر ریشه برای تست سرور
@app.get("/")
async def root():
    print("Root endpoint accessed")
    return {"message": "Server is running!"}

# مسیر HEAD برای ریشه (رفع خطای 405)
@app.head("/")
async def root_head():
    print("Root HEAD request received")
    return Response(status_code=200)

# مسیر Webhook برای درخواست‌های POST
@app.post("/webhook")
async def webhook(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data, application.bot)
    await application.process_update(update)
    return Response(status_code=200)

# مسیر Webhook برای درخواست‌های HEAD (رفع خطای 405)
@app.head("/webhook")
async def webhook_head():
    return Response(status_code=200)

# تنظیم Webhook در هنگام شروع
async def set_webhook():
    webhook_url = f"https://telegram-bot-xc8n.onrender.com/webhook"
    print(f"Setting webhook to: {webhook_url}")
    try:
        # چک کردن وضعیت فعلی Webhook
        webhook_info = await application.bot.getWebhookInfo()
        current_url = webhook_info.url
        if current_url == webhook_url:
            print("Webhook is already set to the correct URL!")
            return "Webhook is already set!", 200
        
        # تنظیم Webhook جدید
        success = await application.bot.setWebhook(url=webhook_url)
        if success:
            print("Webhook set successfully!")
            return "Webhook set successfully!", 200
        else:
            print("Failed to set webhook!")
            return "Failed to set webhook!", 500
    except Exception as e:
        print(f"Error setting webhook: {e}")
        return f"Error setting webhook: {e}", 500

# مسیر دستی برای تنظیم Webhook
@app.get("/set_webhook")
async def set_webhook_endpoint():
    result, status = await set_webhook()
    return {"message": result}, status

# تابع برای اجرای Job Queue و Webhook
async def on_startup():
    # تنظیم Webhook
    result, status = await set_webhook()
    print(result)
    
    # اجرای Job Queue
    if application.job_queue:
        application.job_queue.run_repeating(send_vip_reminders, interval=3600, first=10)
        print("Job queue started!")
    else:
        print("Job queue is None!")

# اجرای برنامه
if __name__ == "__main__":
    # اجرای تابع startup
    asyncio.run(on_startup())
    
    # خواندن پورت از متغیر محیطی
    port = int(os.getenv("PORT", 10000))
    print(f"Starting server on port {port}")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
