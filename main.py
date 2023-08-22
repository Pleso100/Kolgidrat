import logging
import sqlite3
from configparser import ConfigParser
import aiogram.utils.markdown as md
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode, ReplyKeyboardRemove

# Зчитування конфігурацій
config = ConfigParser()
config.read('config.ini')
bot_token = config.get('bot', 'token')

# Зчитування пароля з config.ini
admin_password = config.get('admin', 'password', fallback=None)

# Підключення до бази даних
conn = sqlite3.connect('products.db')
cursor = conn.cursor()

# Створення таблиці, якщо її ще немає
cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        carbs REAL,
        he REAL
    )
''')
conn.commit()

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація MemoryStorage
storage = MemoryStorage()

# Ініціалізація бота та диспетчера з використанням MemoryStorage
bot = Bot(token=bot_token)
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# States
class Form(StatesGroup):
    name = State()
    carbs = State()
    he = State()

async def search_and_reply(query: str, message: types.Message):
    if len(query) >= 2:
        search_input = query
        query = "SELECT name, carbs, he FROM products WHERE LOWER(name) LIKE ?"
        cursor.execute(query, ('%' + search_input.lower() + '%',))
        results = cursor.fetchall()

        if results:
            reply_text = "Результати пошуку:\n"
            for result in results:
                name, carbs, he = result
                reply_text += f"Назва: {name}\nКолгідрати: {carbs}\nХлібні одиниці: {he}\n\n"
            await message.reply(reply_text)
        else:
            await message.reply("Продукти за цими буквами не знайдені.")
    else:
        await message.reply("Введіть ще дві букви для пошуку.")

@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    await message.reply("Вітаю! Введіть дві букви для пошуку продуктів.")

@dp.message_handler(lambda message: True, state="*")
async def handle_message(message: types.Message):
    if message.text == admin_password:
        keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_button = types.InlineKeyboardButton("Адміністрування", callback_data="admin_access")
        keyboard_markup.add(admin_button)

        await message.reply("Доступ до адміністрування надано. Виберіть дію:", reply_markup=keyboard_markup)
    else:
        await search_and_reply(message.text, message)

@dp.callback_query_handler(lambda c: c.data == "admin_access")
async def handle_admin_button(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
    add_product_button = types.InlineKeyboardButton("Додати продукт", callback_data="add_product")
    remove_product_button = types.InlineKeyboardButton("Прибрати продукт", callback_data="remove_product")
    keyboard_markup.add(add_product_button, remove_product_button)
    await bot.send_message(callback_query.from_user.id, "Оберіть дію:", reply_markup=keyboard_markup)

@dp.callback_query_handler(lambda c: c.data == "add_product")
async def handle_add_product(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Режим додавання продуктів. Введіть назву продукту:")
    await Form.name.set()

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['name'] = message.text

    await Form.next()
    await message.reply("Введіть кількість вуглеводів у продукті:")

@dp.message_handler(lambda message: message.text.replace('.', '', 1).isdigit(), state=Form.carbs)
async def process_carbs(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['carbs'] = float(message.text)

    await Form.next()
    await message.reply("Введіть кількість хлібних одиниць у продукті:")

@dp.message_handler(lambda message: message.text.replace('.', '', 1).isdigit(), state=Form.he)
async def process_he(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['he'] = float(message.text)

    await state.update_data(he=float(message.text))

    # Remove keyboard
    markup = ReplyKeyboardRemove()

    await bot.send_message(
        message.chat.id,
        md.text(
            md.text("Додані дані про продукт:"),
            md.text('Назва:', md.bold(data['name'])),
            md.text('Вуглеводи:', md.bold(data['carbs'])),
            md.text('Хлібні одиниці:', data['he']),
            sep='\n'
        ),
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN
    )

    cursor.execute(
        "INSERT INTO products (name, carbs, he) VALUES (?, ?, ?)",
        (data['name'], data['carbs'], data['he'])
    )
    conn.commit()

    await state.finish()

if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp, skip_updates=True)
