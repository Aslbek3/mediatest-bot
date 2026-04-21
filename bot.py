import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F, exceptions
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database

# Configure professional logging (File + Console)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

database.init_db()

# ---- States ----
class AddMovie(StatesGroup):
    waiting_for_video = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_code = State()

class Mailing(StatesGroup):
    waiting_for_message = State()
    waiting_for_type = State()

class SetChannel(StatesGroup):
    waiting_for_channel = State()

class PostChannel(StatesGroup):
    waiting_for_code = State()
    waiting_for_media = State()

class SetAdminLink(StatesGroup):
    waiting_for_link = State()

class EditMovie(StatesGroup):
    waiting_for_code = State()
    choosing_field = State()
    waiting_for_new_name = State()
    waiting_for_new_desc = State()
    waiting_for_new_video = State()

class DeleteMovie(StatesGroup):
    waiting_for_code = State()

class ManageAdmins(StatesGroup):
    waiting_for_add_id = State()
    waiting_for_delete_id = State()

class ManageUsers(StatesGroup):
    waiting_for_user_id = State()

# ---- Mailing Helper Function ----

async def send_mailing_broadcast(mail_type, users, from_chat_id, msg_id, status_msg):
    total = len(users)
    sent, blocked, errors = 0, 0, 0
    
    for idx, uid in enumerate(users):
        try:
            if mail_type == "copy":
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=msg_id)
            else:
                await bot.forward_message(chat_id=uid, from_chat_id=from_chat_id, message_id=msg_id)
            sent += 1
        except exceptions.TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            # Retry the same user after waiting
            try:
                if mail_type == "copy":
                    await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=msg_id)
                else:
                    await bot.forward_message(chat_id=uid, from_chat_id=from_chat_id, message_id=msg_id)
                sent += 1
            except Exception:
                errors += 1
        except exceptions.TelegramForbiddenError:
            blocked += 1
        except Exception as e:
            logger.error(f"Broadcast error for {uid}: {e}")
            errors += 1
        
        # Update progress every 50 users
        if (idx + 1) % 50 == 0:
            try:
                await status_msg.edit_text(f"⏳ Jarayon: {idx+1}/{total}\n✅ Yuborildi: {sent}\n🚫 Bloklangan: {blocked}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    
    return sent, blocked, errors

# ---- User Handlers ----

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    database.add_user(message.from_user.id)
    
    if database.is_user_blocked(message.from_user.id):
        await message.answer("❌ Kechirasiz, siz botdan foydalanishdan chetlatilgansiz (Bloklangansiz)!")
        return
    
    # Check subscription
    if not await is_subscribed(message.from_user.id):
        await send_subscription_warning(message)
        return

    if command and command.args:
        movie = database.get_movie_by_code(command.args)
        if movie:
            bot_info = await bot.get_me()
            caption = f"🎬 Nomi: {movie['name']}\n📝 Ma'lumot: {movie['description']}\n\n🤖 @{bot_info.username} orqali yuklab olindi."
            await bot.send_video(chat_id=message.from_user.id, video=movie['video_file_id'], caption=caption)
            return
        else:
            await message.answer("Kechirasiz, bunday kodli media topilmadi.")
            return

    text = (
        f"Assalomu alaykum, {message.from_user.full_name}!\n\n"
        f"Media kodini yuboring"
    )
    
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Media kodlari"), KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(text, reply_markup=markup)

@dp.message(F.text == "📋 Media kodlari", StateFilter(None))
async def movie_codes_handler(message: Message):
    if not await is_subscribed(message.from_user.id):
        await send_subscription_warning(message)
        return
        
    movies = database.get_all_movies()
    if not movies:
        await message.answer("📭 Hozircha bazada hech qanday media yo'q.")
        return

    lines = ["📋 MEDIA KODLARI RO'YXATI\n" + "="*30]
    for m in movies:
        lines.append(f"Kod: {m['code']}  |  Nomi: {m['name']}")
    lines.append("\n" + "="*30)
    lines.append(f"Jami: {len(movies)} ta media")

    content = "\n".join(lines).encode("utf-8")
    file = BufferedInputFile(content, filename="media_kodlari.txt")
    await message.answer_document(
        document=file,
        caption=f"📋 Bazadagi barcha medialar ro'yxati — jami {len(movies)} ta"
    )

@dp.message(F.text == "👨‍💻 Admin bilan bog'lanish", StateFilter(None))
async def contact_admin_handler(message: Message):
    if not await is_subscribed(message.from_user.id):
        await send_subscription_warning(message)
        return
        
    admin_link = database.get_admin_link()
    
    # Check if it's a username or a link
    if admin_link.startswith('@'):
        url = f"https://t.me/{admin_link[1:]}"
    elif admin_link.startswith('http'):
        url = admin_link
    else:
        url = f"https://t.me/{admin_link}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Bog'lanish", url=url)]
    ])
    await message.answer("Admin bilan bog'lanish uchun quyidagi tugmani bosing:", reply_markup=markup)

@dp.message(F.text & ~F.text.startswith('/'), StateFilter(None))
async def search_movie_handler(message: Message):
    if database.is_user_blocked(message.from_user.id):
        await message.answer("❌ Kechirasiz, siz botdan foydalanishdan chetlatilgansiz!")
        return

    if not await is_subscribed(message.from_user.id):
        await send_subscription_warning(message)
        return
        
    text = message.text.strip()
    
    if text.startswith('/'):
        return

    # Check if it's a code
    movie = database.get_movie_by_code(text)
    if movie:
        bot_info = await bot.get_me()
        caption = f"🎬 Nomi: {movie['name']}\n📝 Ma'lumot: {movie['description']}\n\n🤖 @{bot_info.username} orqali yuklab olindi."
        await bot.send_video(chat_id=message.from_user.id, video=movie['video_file_id'], caption=caption)
        return

    # Try searching by name
    movies = database.get_movies_by_name(text)
    if not movies:
        await message.answer("Bunday kod yoki nomdagi media bazadan topilmadi 😔")
        return

    bot_info = await bot.get_me()
    if len(movies) == 1:
        movie = movies[0]
        caption = f"🎬 Nomi: {movie['name']}\n📝 Ma'lumot: {movie['description']}\n\n🤖 @{bot_info.username} orqali yuklab olindi."
        await bot.send_video(chat_id=message.from_user.id, video=movie['video_file_id'], caption=caption)
    else:
        # Too many results, list them
        res_text = "Natijalar:\n\n"
        for idx, m in enumerate(movies[:10]):
            res_text += f"{idx+1}. {m['name']} (Kod: {m['code']})\n"
        if len(movies) > 10:
            res_text += "\nKo'p natijalar. Iltimos, aniqroq qidiring."
        res_text += "\n\nSiz ushbu ro'yxatdan mediani ko'rib, uning kodini yuborishingiz mumkin."
        await message.answer(res_text)

# ---- Admin Handlers ----

def is_admin(user_id):
    if not config.ADMIN_ID:
        return False
    # Support multiple admins separated by comma
    admins = [str(a).strip() for a in str(config.ADMIN_ID).split(',')]
    if str(user_id) in admins:
        return True
    return database.is_db_admin(user_id)

def is_super_admin(user_id):
    if not config.ADMIN_ID:
        return False
    super_admins = [str(a).strip() for a in str(config.ADMIN_ID).split(',')]
    return str(user_id) in super_admins

async def is_subscribed(user_id):
    if is_admin(user_id):
        return True
         
    channel_id = database.get_channel('sub_channel')
    if not channel_id:
        return True
        
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        # Log the error but don't just return True
        logging.error(f"Subscription check error for {user_id} in {channel_id}: {e}")
        # If bot is not admin, we might want to alert real admins
        # For now, we return True only if we really can't verify (to avoid blocking users due to bot issues)
        # But we logged it.
        return True
    return False

async def send_subscription_warning(message: Message):
    channel_id = database.get_channel('sub_channel')
    # Default URL
    url = "https://t.me/telegram"
    
    if channel_id:
        if str(channel_id).startswith('@'):
            url = f"https://t.me/{channel_id[1:]}"
        else:
            try:
                # If it's an ID, try to get or create an invite link
                chat = await bot.get_chat(channel_id)
                if chat.invite_link:
                    url = chat.invite_link
                elif chat.username:
                    url = f"https://t.me/{chat.username}"
                else:
                    invite = await bot.create_chat_invite_link(chat_id=channel_id)
                    url = invite.invite_link
            except Exception:
                # Fallback
                if str(channel_id).startswith('-100'):
                    url = f"https://t.me/c/{str(channel_id)[4:]}/1" # Approximate
                else:
                    url = f"https://t.me/{channel_id}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=url)],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
    ])
    
    text = (
        "❌ Botdan foydalanish uchun kanalimizga obuna bo'lishingiz shart!\n\n"
        "Obuna bo'lgach 'Tekshirish' tugmasini bosing."
    )
    if isinstance(message, Message):
        await message.answer(text, reply_markup=markup)
    else:
        # If it's a callback query
        await message.message.answer(text, reply_markup=markup)

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(call: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(call.from_user.id):
        await call.answer("✅ Rahmat! Endi botdan foydalanishingiz mumkin.", show_alert=True)
        await call.message.delete()
        
        # Trigger start properly
        await state.clear()
        database.add_user(call.from_user.id)
        
        text = (
            f"Assalomu alaykum, {call.from_user.full_name}!\n\n"
            f"Media kodini yuboring"
        )
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📋 Media kodlari"), KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")]
            ],
            resize_keyboard=True
        )
        await bot.send_message(chat_id=call.from_user.id, text=text, reply_markup=markup)
    else:
        await call.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)

async def get_admin_menu_data():
    users_count = len(database.get_all_users())
    movies_count = database.get_movies_count()
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="statistics"),
            InlineKeyboardButton(text="🎬 Medialar boshqaruvi", callback_data="manage_movies")
        ],
        [
            InlineKeyboardButton(text="📨 Xabar tarqatish", callback_data="mailing"),
            InlineKeyboardButton(text="📢 Kanallar boshqaruvi", callback_data="manage_channels")
        ],
        [
            InlineKeyboardButton(text="📬 Kanalga po'st yuborish", callback_data="post_channel"),
            InlineKeyboardButton(text="🔗 Admin linkini sozlash", callback_data="set_admin_link")
        ],
        [
            InlineKeyboardButton(text="👥 Adminlar boshqaruvi", callback_data="manage_admins"),
            InlineKeyboardButton(text="👥 Foydalanuvchilar boshqaruvi", callback_data="manage_users")
        ]
    ])
    
    text = (
        f"Admin paneliga xush kelibsiz!"
    )
    return text, markup

@dp.message(Command("admin"))
async def admin_handler(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer(f"Siz admin emassiz!\nSizning Telegram ID'ingiz: <code>{message.from_user.id}</code>\nHozir bazada ulangan Admin ID: <code>{config.ADMIN_ID}</code>\n\n"
                             f"Admin bo'lish uchun @coder_uzzz ga yozing.", parse_mode="HTML")
        return

    await message.answer("Salom Boss!", reply_markup=ReplyKeyboardRemove())
    text, markup = await get_admin_menu_data()
    await message.answer(text, reply_markup=markup)

@dp.callback_query(F.data == "back_to_admin")
async def cb_back_to_admin(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_admin(call.from_user.id):
        await call.answer("Taqiqalangan!", show_alert=True)
        return
        
    text, markup = await get_admin_menu_data()
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        # If we can't edit (e.g. message too old or it was a different type), send new
        await call.message.answer(text, reply_markup=markup)
    await call.answer()

@dp.callback_query(F.data == "statistics")
async def cb_statistics(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    
    users_count = len(database.get_all_users())
    movies_count = database.get_movies_count()
    blocked_count = database.get_blocked_users_count()
    admins_count = len(database.get_all_admins()) + 1 # +1 for super admin
    
    text = (
        "📊 BOT STATISTIKASI\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        f"👥 Foydalanuvchilar: {users_count} ta\n"
        f"✅ Faol foydalanuvchilar: {users_count - blocked_count} ta\n"
        f"🚫 Bloklanganlar: {blocked_count} ta\n\n"
        f"🎬 Jami medialar: {movies_count} ta\n"
        f"👥 Adminlar: {admins_count} ta\n\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Ma'lumotlar real vaqt rejimida yangilanadi."
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")]
    ])
    
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()

async def get_manage_movies_data():
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Media yuklash", callback_data="add_movie"),
            InlineKeyboardButton(text="✏️ Mediani tahrirlash", callback_data="edit_movie")
        ],
        [
            InlineKeyboardButton(text="🗑 Mediani o'chirish", callback_data="delete_movie"),
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]
    ])
    return "🎬 Medialar boshqaruvi bo'limi:", markup

@dp.callback_query(F.data == "manage_movies")
async def cb_manage_movies(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    text, markup = await get_manage_movies_data()
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()

# Handler removed as it is now integrated above into cb_back_to_admin or redundant


async def get_manage_channels_data():
    post_channel = database.get_channel('post_channel')
    sub_channel = database.get_channel('sub_channel')
    
    text = (
        "📢 KANALLAR BOSHQARUVI\n\n"
        f"📬 Po'st kanali: <code>{post_channel if post_channel else 'Ulanmagan ❌'}</code>\n"
        f"🔒 Majburiy obuna: <code>{sub_channel if sub_channel else 'Ulanmagan ❌'}</code>\n\n"
        "Kanalni o'zgartirish uchun quyidagi tugmalardan foydalaning:"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📬 Po'st kanali", callback_data="set_channel_post"),
            InlineKeyboardButton(text="🔒 Majburiy obuna", callback_data="set_channel_sub")
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]
    ])
    return text, markup

@dp.callback_query(F.data == "manage_channels")
async def cb_manage_channels(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    text, markup = await get_manage_channels_data()
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "add_movie")
async def cb_add_movie(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Xatolik", show_alert=True)
        return
    await call.message.answer("Mediani yuboring:")
    await state.set_state(AddMovie.waiting_for_video)
    await call.answer()

@dp.message(AddMovie.waiting_for_video, F.video)
async def state_add_movie_video(message: Message, state: FSMContext):
    # Telegram compressed video — always mp4
    await state.update_data(video_file_id=message.video.file_id)
    await message.answer("✅ Video qabul qilindi. Media nomini kiriting:")
    await state.set_state(AddMovie.waiting_for_name)

@dp.message(AddMovie.waiting_for_video, F.document)
async def state_add_movie_document(message: Message, state: FSMContext):
    mime = message.document.mime_type or ""
    name = message.document.file_name or ""
    if mime == "video/mp4" or name.lower().endswith(".mp4"):
        await state.update_data(video_file_id=message.document.file_id)
        await message.answer("✅ MP4 fayl qabul qilindi. Media nomini kiriting:")
        await state.set_state(AddMovie.waiting_for_name)
    else:
        file_info = name or mime or "noma'lum format"
        await message.answer(
            f"❌ Faqat MP4 formatdagi video qabul qilinadi!\n"
            f"Siz yuborgan fayl: {file_info}\n\n"
            f"Iltimos, MP4 formatdagi video yoki fayl yuboring."
        )

@dp.message(AddMovie.waiting_for_video)
async def state_add_movie_video_invalid(message: Message):
    await message.answer(
        "❌ Faqat MP4 formatdagi video qabul qilinadi!\n\n"
        "Iltimos, MP4 video yuboring (telegram orqali yoki fayl sifatida)."
    )

@dp.message(AddMovie.waiting_for_name, F.text)
async def state_add_movie_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Media haqidagi tavsifni kiriting:")
    await state.set_state(AddMovie.waiting_for_description)

@dp.message(AddMovie.waiting_for_description, F.text)
async def state_add_movie_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Media kodini kiriting:")
    await state.set_state(AddMovie.waiting_for_code)

@dp.message(AddMovie.waiting_for_code, F.text)
async def state_add_movie_code(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    
    success = database.add_movie(code, data['name'], data['description'], data['video_file_id'])
    if success:
        await message.answer(f"✅ Media muvaffaqiyatli qo'shildi!\nKodi: {code}")
                
    else:
        await message.answer("❌ Bunday kod bilan media allaqachon mavjud! Boshqa kod yuboring.")
        return # keep waiting for code
    
    await state.clear()
    text, markup = await get_manage_movies_data()
    await message.answer(text, reply_markup=markup)

# ---- Edit / Delete Movie Handlers ----

@dp.callback_query(F.data == "edit_movie")
async def cb_edit_movie(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.answer("Tahrirlamoqchi bo'lgan medianing KODini yuboring:\n(Bekor qilish uchun /cancel)")
    await state.set_state(EditMovie.waiting_for_code)
    await call.answer()

@dp.message(EditMovie.waiting_for_code)
async def state_edit_movie_code(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
        
    if not message.text:
        await message.answer("❌ Iltimos, matn yuboring.")
        return
        
    code = message.text.strip()
    movie = database.get_movie_by_code(code)
    if not movie:
        await message.answer("❌ Bunday kodli media topilmadi. Boshqa kod yuboring yoki /cancel bosing.")
        return
    
    await state.update_data(edit_code=code)
    text = (
        f"Media topildi!\n\n"
        f"Kodi: {movie['code']}\n"
        f"Nomi: {movie['name']}\n"
        f"Tavsifi: {movie['description']}\n\n"
        f"Nimani o'zgartirmoqchisiz?"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Nomini", callback_data="edit_name")],
        [InlineKeyboardButton(text="📝 Tavsifini", callback_data="edit_desc")],
        [InlineKeyboardButton(text="🎬 Videosini", callback_data="edit_video")],
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="back_to_admin")]
    ])
    await message.answer(text, reply_markup=markup)
    await state.set_state(EditMovie.choosing_field)

@dp.callback_query(EditMovie.choosing_field)
async def cb_edit_field_choice(call: types.CallbackQuery, state: FSMContext):
    field = call.data
    if field == "edit_name":
        await call.message.answer("Yangi NOMNI kiriting:")
        await state.set_state(EditMovie.waiting_for_new_name)
    elif field == "edit_desc":
        await call.message.answer("Yangi TAVSIFNI kiriting:")
        await state.set_state(EditMovie.waiting_for_new_desc)
    elif field == "edit_video":
        await call.message.answer("Yangi VIDEO faylni yuboring:")
        await state.set_state(EditMovie.waiting_for_new_video)
    await call.answer()

@dp.message(EditMovie.waiting_for_new_name, F.text)
async def state_edit_name_save(message: Message, state: FSMContext):
    data = await state.get_data()
    database.update_movie(data['edit_code'], name=message.text)
    await message.answer(f"✅ Nomi o'zgartirildi: {message.text}")
    await state.clear()
    text, markup = await get_manage_movies_data()
    await message.answer(text, reply_markup=markup)

@dp.message(EditMovie.waiting_for_new_desc, F.text)
async def state_edit_desc_save(message: Message, state: FSMContext):
    data = await state.get_data()
    database.update_movie(data['edit_code'], description=message.text)
    await message.answer(f"✅ Tavsifi o'zgartirildi.")
    await state.clear()
    text, markup = await get_manage_movies_data()
    await message.answer(text, reply_markup=markup)

@dp.message(EditMovie.waiting_for_new_video, F.video | F.document)
async def state_edit_video_save(message: Message, state: FSMContext):
    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.document and (message.document.mime_type == "video/mp4" or (message.document.file_name or "").lower().endswith(".mp4")):
        file_id = message.document.file_id
    
    if not file_id:
        await message.answer("❌ Iltimos, MP4 video yuboring.")
        return

    data = await state.get_data()
    database.update_movie(data['edit_code'], video_file_id=file_id)
    await message.answer(f"✅ Video muvaffaqiyatli yangilandi.")
    await state.clear()
    text, markup = await get_manage_movies_data()
    await message.answer(text, reply_markup=markup)

@dp.callback_query(F.data == "delete_movie")
async def cb_delete_movie(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.answer("O'chirmoqchi bo'lgan medianing KODini yuboring:\n(Bekor qilish uchun /cancel)")
    await state.set_state(DeleteMovie.waiting_for_code)
    await call.answer()

@dp.message(DeleteMovie.waiting_for_code)
async def state_delete_movie_save(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
        
    if not message.text:
        await message.answer("❌ Iltimos, matn yuboring.")
        return
        
    code = message.text.strip()
    movie = database.get_movie_by_code(code)
    if not movie:
        await message.answer("❌ Bunday kodli media topilmadi.")
        return
    
    database.delete_movie(code)
    await message.answer(f"✅ Media (Kod: {code}) muvaffaqiyatli o'chirildi.")
    await state.clear()
    text, markup = await get_manage_movies_data()
    await message.answer(text, reply_markup=markup)

@dp.callback_query(F.data == "mailing")
async def cb_mailing(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(Mailing.waiting_for_message)
    await call.message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni kiriting (yoki /cancel ni bosing):")
    logging.info(f"Mailing state set for user {call.from_user.id}")
    await call.answer()

@dp.message(Mailing.waiting_for_message)
async def state_mailing_msg(message: Message, state: FSMContext):
    logging.info(f"Received mailing message from user {message.from_user.id}")
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return

    # Store message details
    await state.update_data(
        from_chat_id=message.chat.id,
        msg_id=message.message_id
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Bot nomidan (Copy)", callback_data="mail_copy")],
        [InlineKeyboardButton(text="⏩ Uzatilgan holda (Forward)", callback_data="mail_forward")],
        [InlineKeyboardButton(text="🔍 Xabarni tekshirish (Test)", callback_data="mail_test")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="back_to_admin")]
    ])
    
    await message.answer("Xabarni qanday usulda tarqatmoqchisiz?", reply_markup=markup)
    await state.set_state(Mailing.waiting_for_type)

@dp.callback_query(F.data.startswith("mail_"), Mailing.waiting_for_type)
async def cb_start_mailing(call: types.CallbackQuery, state: FSMContext):
    mail_type = call.data.replace("mail_", "") # 'copy', 'forward' or 'test'
    data = await state.get_data()
    from_chat_id = data['from_chat_id']
    msg_id = data['msg_id']
    
    if mail_type == "test":
        try:
            await bot.copy_message(chat_id=call.from_user.id, from_chat_id=from_chat_id, message_id=msg_id)
            await call.message.answer("✅ Xabar 'Bot nomidan' ko'rinishida sizga yuborildi. Agar ma'qul bo'lsa, tarqatish usulini tanlang.")
            await bot.forward_message(chat_id=call.from_user.id, from_chat_id=from_chat_id, message_id=msg_id)
            await call.message.answer("✅ Xabar 'Uzatilgan' ko'rinishida sizga yuborildi.")
        except Exception as e:
            await call.answer(f"❌ Testda xatolik: {e}", show_alert=True)
        return

    users = database.get_active_users()
    total = len(users)
    
    status_msg = await call.message.edit_text(f"🚀 Tarqatish boshlandi ({'Bot nomidan' if mail_type == 'copy' else 'Uzatilgan'})...\nJami: {total} ta foydalanuvchi.")
    
    sent, blocked, errors = await send_mailing_broadcast(mail_type, users, from_chat_id, msg_id, status_msg)

    await status_msg.edit_text(
        f"✅ Tarqatish yakunlandi ({'Bot nomidan' if mail_type == 'copy' else 'Uzatilgan holda'})!\n\n"
        f"👥 Jami: {total}\n"
        f"📢 Yuborildi: {sent}\n"
        f"🚫 Bloklangan: {blocked}\n"
        f"❌ Xatoliklar: {errors}"
    )
    await state.clear()
    text, markup = await get_admin_menu_data()
    await call.message.answer(text, reply_markup=markup)



@dp.callback_query(F.data.startswith("set_channel_"))
async def cb_set_channel(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    channel_type = call.data.replace("set_channel_", "") # 'post' or 'sub'
    await state.update_data(channel_type=channel_type)
    
    text = "Po'st kanali" if channel_type == "post" else "Majburiy obuna kanali"
    await call.message.answer(f"Kanal ulash uchun ID ni @username_to_id_bot orqali olishingiz mumkin. Avval botni kanalga admin qiling!\n\nBekor qilish uchun /cancel bosing.")
    await state.set_state(SetChannel.waiting_for_channel)
    await call.answer()

@dp.message(SetChannel.waiting_for_channel)
async def state_set_channel(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
    
    if not message.text:
        await message.answer("❌ Iltimos, kanal ID si yoki username notasini yuboring.")
        return
    
    channel_id = message.text.strip()
    data = await state.get_data()
    channel_type = data.get('channel_type', 'post')
    db_key = 'post_channel' if channel_type == 'post' else 'sub_channel'
    
    try:
        msg = await bot.send_message(chat_id=channel_id, text="Sinov xabari... Kanal muvaffaqiyatli ulandi!")
        await bot.delete_message(chat_id=channel_id, message_id=msg.message_id)
        
        database.set_channel(channel_id, db_key)
        await message.answer(f"✅ O'zgarishlar saqlandi! {channel_id} kanali ulandi.")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi! \nBot {channel_id} kanalida admin ekanligiga ishonch hosil qiling!\n\nXato: {e}")
    finally:
        await state.clear()
        text, markup = await get_manage_channels_data()
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@dp.callback_query(F.data == "set_admin_link")
async def cb_set_admin_link(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
        
    admin_link = database.get_admin_link()
    text = (
        "🔗 ADMIN LINKINI SOZLASH\n\n"
        f"Hozirgi link: <code>{admin_link}</code>\n\n"
        "Yangi link yoki username yuboring (masalan: @coder_uzzz yoki t.me/link):\n"
        "(Bekor qilish uchun /cancel)"
    )
    
    await call.message.edit_text(text, parse_mode="HTML")
    await state.set_state(SetAdminLink.waiting_for_link)
    await call.answer()

@dp.message(SetAdminLink.waiting_for_link)
async def state_set_admin_link(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
    
    if not message.text:
        await message.answer("❌ Iltimos, linkni matn qilib yuboring.")
        return
    
    link = message.text.strip()
    database.set_admin_link(link)
    await message.answer(f"✅ Admin linki muvaffaqiyatli saqlandi: {link}")
    await state.clear()
    text, markup = await get_admin_menu_data()
    await message.answer(text, reply_markup=markup)


@dp.callback_query(F.data == "post_channel")
async def cb_post_channel(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    channel_id = database.get_channel('post_channel')
    if not channel_id:
        await call.message.answer("❌ Oldin Po'st kanalini ulang! (Admin paneldagi '📢 Kanallar boshqaruvi' -> '📬 Po'st kanali' orqali)")
        await call.answer()
        return
        
    await call.message.answer("Kanalga yubormoqchi bo'lgan medianing maxsus KODini kiriting:\n(Bekor qilish uchun /cancel)")
    await state.set_state(PostChannel.waiting_for_code)
    await call.answer()

@dp.message(PostChannel.waiting_for_code)
async def state_post_channel_code(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
        
    if not message.text:
        await message.answer("❌ Iltimos, matn yuboring.")
        return
        
    code = message.text.strip()
    movie = database.get_movie_by_code(code)
    if not movie:
        await message.answer("❌ Bunday kodli media topilmadi. Boshqa kod kiriting yoki /cancel bosing.")
        return
        
    await state.update_data(movie_code=code)
    await message.answer("✅ Media topildi! Endi kanal po'sti uchun e'tibor tortuvchi bitta **Rasm** yoki **Video** yuboring:\n(Bekor qilish uchun /cancel)", parse_mode="Markdown")
    await state.set_state(PostChannel.waiting_for_media)

@dp.message(PostChannel.waiting_for_media, F.photo | F.video)
async def state_post_channel_media(message: Message, state: FSMContext):
    data = await state.get_data()
    code = data['movie_code']
    movie = database.get_movie_by_code(code)
    channel_id = database.get_channel('post_channel')
    bot_info = await bot.get_me()
    
    deep_link = f"https://t.me/{bot_info.username}?start={code}"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Yuklab olish", url=deep_link)]
    ])
    channel_caption = f"🎬 Nomi: {movie['name']}\n📝 Ma'lumot: {movie['description']}\n\n👇 Mediani kutmasdan yuklab olish!"
    
    try:
        if message.photo:
            photo_id = message.photo[-1].file_id
            await bot.send_photo(chat_id=channel_id, photo=photo_id, caption=channel_caption, reply_markup=markup)
        elif message.video:
            video_id = message.video.file_id
            await bot.send_video(chat_id=channel_id, video=video_id, caption=channel_caption, reply_markup=markup)
            
        await message.answer("✅ Po'st va media muvaffaqiyatli kanalga joylandi!")
    except Exception as e:
        await message.answer(f"❌ Kanalga yuborishda xato yuz berdi: {e}")
        
    await state.clear()
    text, markup = await get_admin_menu_data()
    await message.answer(text, reply_markup=markup)

@dp.message(PostChannel.waiting_for_media)
async def state_post_channel_media_invalid(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
    await message.answer("Iltimos, faqat rasm yoki video formatidagi fayl yuboring yoyoki /cancel bosing.")


async def get_manage_admins_data():
    admins = database.get_all_admins()
    text = "👥 ADMINLAR RO'YXATI\n\n"
    text += f"👑 Super Admin: <code>{config.ADMIN_ID}</code>\n"
    text += "—"*15 + "\n"
    
    if not admins:
        text += "Hozircha qo'shimcha adminlar yo'q."
    else:
        for idx, aid in enumerate(admins):
            text += f"{idx+1}. <code>{aid}</code>\n"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_admin_db"),
            InlineKeyboardButton(text="🗑 Adminni o'chirish", callback_data="delete_admin_db")
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]
    ])
    return text, markup

@dp.callback_query(F.data == "manage_admins")
async def cb_manage_admins(call: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Bu bo'lim faqat Asosiy Admin (Super Admin) uchun!", show_alert=True)
        return
    
    text, markup = await get_manage_admins_data()
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "add_admin_db")
async def cb_add_admin_db(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi adminning Telegram ID sini yuboring:\n(Bekor qilish uchun /cancel)")
    await state.set_state(ManageAdmins.waiting_for_add_id)
    await call.answer()

@dp.message(ManageAdmins.waiting_for_add_id)
async def state_add_admin_id(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
    
    if not message.text:
        await message.answer("❌ Iltimos, matn yuboring.")
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqamlardan iborat Telegram ID yuboring.")
        return
    
    new_admin_id = int(message.text)
    if is_super_admin(new_admin_id):
        await message.answer("❌ Bu foydalanuvchi allaqachon Super Admin!")
        await state.clear()
        return

    if database.add_admin(new_admin_id):
        await message.answer(f"✅ Admin muvaffaqiyatli qo'shildi: <code>{new_admin_id}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Bu foydalanuvchi allaqachon admin yoki ma'lumotlar bazasida mavjud!")
    
    await state.clear()
    text, markup = await get_manage_admins_data()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data == "delete_admin_db")
async def cb_delete_admin_db(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("O'chirmoqchi bo'lgan adminning Telegram ID sini yuboring:\n(Bekor qilish uchun /cancel)")
    await state.set_state(ManageAdmins.waiting_for_delete_id)
    await call.answer()

@dp.message(ManageAdmins.waiting_for_delete_id)
async def state_delete_admin_id(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
    
    if not message.text:
        await message.answer("❌ Iltimos, matn yuboring.")
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, Telegram ID raqamini yuboring.")
        return
        
    admin_id = int(message.text)
    if is_super_admin(admin_id):
        await message.answer("❌ Asosiy adminni o'chirib bo'lmaydi!")
        await state.clear()
        return

    if database.delete_admin(admin_id):
        await message.answer(f"✅ Admin muvaffaqiyatli o'chirildi: <code>{admin_id}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Bunday ID dagi admin topilmadi.")
    
    await state.clear()
    text, markup = await get_manage_admins_data()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


async def get_manage_users_data():
    total = len(database.get_all_users())
    blocked = database.get_blocked_users_count()
    active = total - blocked
    
    text = (
        f"👥 FOYDALANUVCHILAR BOSHQARUVI\n\n"
        f"📊 Statistika:\n"
        f"✅ Faol: {active}\n"
        f"🚫 Bloklangan: {blocked}\n"
        f"👥 Jami: {total}\n\n"
        f"Foydalanuvchini bloklash yoki blokdan chiqarish uchun uning ID sini yuboring."
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 ID bo'yicha qidirish", callback_data="search_user_id")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")]
    ])
    return text, markup

@dp.callback_query(F.data == "manage_users")
async def cb_manage_users(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    
    text, markup = await get_manage_users_data()
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()

@dp.callback_query(F.data == "search_user_id")
async def cb_search_user_id(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Foydalanuvchi ID sini yuboring:\n(Bekor qilish uchun /cancel)")
    await state.set_state(ManageUsers.waiting_for_user_id)
    await call.answer()

@dp.message(ManageUsers.waiting_for_user_id)
async def state_manage_user_id(message: Message, state: FSMContext):
    text_check = message.text or message.caption or ""
    if text_check == '/cancel':
        await message.answer("Bekor qilindi.")
        await state.clear()
        return
    
    if not message.text:
        await message.answer("❌ Iltimos, matnli xabar yuboring.")
        return
        
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat ID raqamini yuboring.")
        return
    
    uid = int(message.text)
    is_blocked = database.is_user_blocked(uid)
    
    # Check if user exists in DB
    if not database.user_exists(uid):
        await message.answer("❌ Bunday ID dagi foydalanuvchi bazada topilmadi.")
        await state.clear()
        return

    text = f"Foydalanuvchi: <code>{uid}</code>\nHolati: {'🚫 Bloklangan' if is_blocked else '✅ Faol'}"
    
    btn_text = "✅ Blokdan chiqarish" if is_blocked else "🚫 Bloklash"
    btn_data = f"unblock_{uid}" if is_blocked else f"block_{uid}"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=btn_data)],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="manage_users")]
    ])
    await message.answer(text, reply_markup=markup, parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("block_"))
async def cb_block_user_exec(call: types.CallbackQuery):
    uid = int(call.data.replace("block_", ""))
    if is_admin(uid):
        await call.answer("❌ Adminni bloklab bo'lmaydi!", show_alert=True)
        return
        
    database.block_user(uid)
    await call.answer("Bloklandi", show_alert=True)
    text, markup = await get_manage_users_data()
    await call.message.edit_text(text, reply_markup=markup)

@dp.callback_query(F.data.startswith("unblock_"))
async def cb_unblock_user_exec(call: types.CallbackQuery):
    uid = int(call.data.replace("unblock_", ""))
    database.unblock_user(uid)
    await call.answer("Blokdan chiqarildi", show_alert=True)
    text, markup = await get_manage_users_data()
    await call.message.edit_text(text, reply_markup=markup)


async def main():
    bot_info = await bot.get_me()
    print(f"@{bot_info.username} ishga tushdi!")
    print("Xabarlarni qabul qilish boshlandi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
