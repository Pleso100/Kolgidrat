import sqlite3
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from configparser import ConfigParser

class ProductAdminStates(StatesGroup):
    SEARCH = State()
    ADMIN_MENU = State()
    REMOVE_PRODUCT = State()
    ADD_PRODUCT_NAME = State()
    ADD_PRODUCT_CARBS = State()
    ADD_PRODUCT_HE = State()

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

# Ініціалізація бота та диспетчера з MemoryStorage
bot = Bot(token=bot_token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Функція для пошуку та відповіді
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
        await message.reply("Введіть ще дві букви для пошуку продуктів.")

# Обробник команди /start
@dp.message_handler(Command('start'), state="*")
async def handle_start(message: types.Message, state: FSMContext):
    await message.reply("Вітаю! Введіть дві букви для пошуку продуктів.")
    await state.finish()  # Завершити всі стани

# Обробник повідомлень
@dp.message_handler(lambda message: True, state="*")
async def handle_message(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if data.get("waiting_for_product_name"):
            await add_product_name(message, state)
        elif data.get("waiting_for_carbs"):
            await add_product_carbs(message, state)
        elif data.get("waiting_for_he"):
            await add_product_he(message, state)
        elif message.text == admin_password:
            keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
            admin_button = types.InlineKeyboardButton("Адміністрування", callback_data="admin_access")
            keyboard_markup.add(admin_button)

            await message.reply("Доступ до адміністрування надано. Виберіть дію:", reply_markup=keyboard_markup)
            await ProductAdminStates.ADMIN_MENU.set()
        else:
            data["search_query"] = message.text
            await ProductAdminStates.SEARCH.set()
            await search_and_reply(data["search_query"], message)
            await state.finish()

# Обробник кнопки "Адміністрування"
@dp.callback_query_handler(lambda c: c.data == "admin_access", state="*")
async def handle_admin_button(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
    add_product_button = types.InlineKeyboardButton("Додати продукт", callback_data="add_product")
    remove_product_button = types.InlineKeyboardButton("Прибрати продукт", callback_data="remove_product")
    cancel_button = types.InlineKeyboardButton("Відмінити", callback_data="cancel")
    keyboard_markup.add(add_product_button, remove_product_button, cancel_button)
    await bot.send_message(callback_query.from_user.id, "Оберіть дію:", reply_markup=keyboard_markup)
    await ProductAdminStates.ADMIN_MENU.set()

# Обробник кнопки "Прибрати продукт"
@dp.callback_query_handler(lambda c: c.data == "remove_product", state=ProductAdminStates.ADMIN_MENU)
async def handle_remove_product(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Введіть назву продукту для видалення:")
    await state.update_data(waiting_for_product_name=True)
    await ProductAdminStates.REMOVE_PRODUCT.set()

# Обробник підтвердження видалення продукту
@dp.message_handler(state=ProductAdminStates.REMOVE_PRODUCT)
async def confirm_remove_product(message: types.Message, state: FSMContext):
    product_name = message.text
    cursor.execute("DELETE FROM products WHERE name = ?", (product_name,))
    conn.commit()
    await message.reply(f"Продукт '{product_name}' видалено.")
    await state.finish()

# Обробник кнопки "Відмінити" під час видалення продукту
@dp.callback_query_handler(lambda c: c.data == "cancel", state=ProductAdminStates.REMOVE_PRODUCT)
async def cancel_remove_product(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Видалення продукту скасовано.")
    await state.finish()

# Обробник кнопки "Додати продукт"
@dp.callback_query_handler(lambda c: c.data == "add_product", state=ProductAdminStates.ADMIN_MENU)
async def handle_add_product(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Введіть назву продукту:")
    await state.update_data(waiting_for_product_name=True)
    await ProductAdminStates.ADD_PRODUCT_NAME.set()

# Обробник введення назви продукту
@dp.message_handler(state=ProductAdminStates.ADD_PRODUCT_NAME)
async def add_product_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["product_name"] = message.text
        await message.reply("Введіть кількість вуглеводів:")
        await state.update_data(waiting_for_product_name=False, waiting_for_carbs=True)
        await ProductAdminStates.ADD_PRODUCT_CARBS.set()

# Обробник введення кількості вуглеводів
@dp.message_handler(lambda message: message.text.replace('.', '').isdigit(), state=ProductAdminStates.ADD_PRODUCT_CARBS)
async def add_product_carbs(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["product_carbs"] = float(message.text)
        await message.reply("Введіть кількість хлібних одиниць:")
        await state.update_data(waiting_for_carbs=False, waiting_for_he=True)

# Обробник введення кількості хлібних одиниць
@dp.message_handler(lambda message: message.text.replace('.', '').isdigit(), state=ProductAdminStates.ADD_PRODUCT_HE)
async def add_product_he(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["product_he"] = float(message.text)
        cursor.execute("INSERT INTO products (name, carbs, he) VALUES (?, ?, ?)",
                       (data["product_name"], data["product_carbs"], data["product_he"]))
        conn.commit()
        await message.reply("Продукт додано до бази даних.")
        await state.finish()


# Обробник кнопки "Відмінити" під час додавання продукту
@dp.callback_query_handler(lambda c: c.data == "cancel", state=ProductAdminStates.ADD_PRODUCT_NAME)
@dp.callback_query_handler(lambda c: c.data == "cancel", state=ProductAdminStates.ADD_PRODUCT_CARBS)
@dp.callback_query_handler(lambda c: c.data == "cancel", state=ProductAdminStates.ADD_PRODUCT_HE)
async def cancel_add_product(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Додавання продукту скасовано.")
    await state.finish()

# ... (інші обробники зворотного виклику та функції)

if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp, skip_updates=True)
