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

# Імпорт необхідних модулів

# Зчитування конфігурацій з файлу config.ini
config = ConfigParser()
config.read('config.ini')
bot_token = config.get('bot', 'token')

# Зчитування пароля адміністратора з config.ini
admin_password = config.get('admin', 'password', fallback=None)

# Підключення до бази даних SQLite
conn = sqlite3.connect('products.db')
cursor = conn.cursor()

# Створення таблиці у базі даних, якщо її ще не існує
cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        carbs REAL,
        he REAL
    )
''')
conn.commit()

# Налаштування системи логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація MemoryStorage для зберігання станів
storage = MemoryStorage()

# Ініціалізація об'єкту бота та диспетчера з використанням MemoryStorage
bot = Bot(token=bot_token)
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Визначення станів для обробки різних кроків взаємодії з користувачем
class Form(StatesGroup):
    name = State()  # Стан для отримання назви продукту
    carbs = State()  # Стан для отримання вмісту вуглеводів
    he = State()  # Стан для отримання кількості хлібних одиниць

class Form2(StatesGroup):
    remove_name = State()  # Стан для видалення по назві продукту

# Функція для пошуку продуктів за запитом і відправки результатів користувачу
async def search_and_reply(query: str, message: types.Message):
    if len(query) >= 2:
        search_input = query.lower()  # Перетворення в нижній регістр для обходу проблеми подвійних регістрів літер
        query = "SELECT name, carbs, he FROM products WHERE LOWER(name) LIKE ?"
        cursor.execute(query, ('%' + search_input + '%',))
        results = cursor.fetchall()

        if results:
            reply_text = "Результати пошуку:\n"
            for result in results:
                name, carbs, he = result
                reply_text += f"Назва: {name}\nКолгідрати (вуглеводи) на 100 грам: {carbs}\nХлібні одиниці (приблизно): {he}\n\n"
            await message.reply(reply_text)
        else:
            await message.reply("Продукти за Вашим запитом не знайдені.")
    else:
        await message.reply("Введіть не менше ніж дві букви для пошуку.")

# Функція для видалення продукту з бази даних за назвою
async def remove_product_from_database(product_name: str):
    query = "DELETE FROM products WHERE LOWER(name) = ?"
    cursor.execute(query, (product_name,))
    conn.commit()

# Обробник для кнопки "Видалити продукт"
@dp.callback_query_handler(lambda c: c.data == "remove_product")
async def handle_remove_product(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Режим видалення продуктів. Введіть назву продукту для видалення:")
    await Form2.remove_name.set()

# Обробник для отримання назви продукту, який потрібно видалити
@dp.message_handler(state=Form2.remove_name)
async def process_remove_name(message: types.Message, state: FSMContext):
    product_name_to_remove = message.text.strip().lower()  # Перетворення в нижній регістр та видалення зайвих пробілів

    # Виклик функції для видалення продукту за його назвою
    await remove_product_from_database(product_name_to_remove)

    # Видалення клавіатури
    markup = ReplyKeyboardRemove()

    await bot.send_message(
        message.chat.id,
        md.text(
            md.text('Назва:', md.bold(product_name_to_remove)),
            md.text("Продукт видалено з бази даних. Продовжуйте пошук"),
            sep='\n'
        ),
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN
    )

    await state.finish()  # Завершення стану

# Обробник для команди "/start"
@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    await message.reply("Вітаю! Введіть не менше ніж дві букви для пошуку продуктів.")

# Обробник для взаємодії з користувачем
@dp.message_handler(lambda message: True)
async def handle_message(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if data.get('admin_access') == True:
            if message.text.startswith("/search"):
                await search_and_reply(message.text[len("/search"):], message)
            else:
                await message.reply("Доступ до адміністрування надано. Виберіть дію.")
        elif message.text == admin_password:
            keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
            admin_button = types.InlineKeyboardButton("Адміністрування", callback_data="admin_access")
            keyboard_markup.add(admin_button)

            await message.reply("Доступ до адміністрування надано. Виберіть дію:", reply_markup=keyboard_markup)
        else:
            await search_and_reply(message.text, message)

# Обробник для кнопки "Адміністрування"
@dp.callback_query_handler(lambda c: c.data == "admin_access")
async def handle_admin_button(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
    add_product_button = types.InlineKeyboardButton("Додати продукт", callback_data="add_product")
    remove_product_button = types.InlineKeyboardButton("Видалити продукт", callback_data="remove_product")
    keyboard_markup.add(add_product_button, remove_product_button)
    await bot.send_message(callback_query.from_user.id, "Оберіть дію:", reply_markup=keyboard_markup)

    async with state.proxy() as data:
        data['admin_access'] = True

# Обробник для кнопки "Додати продукт"
@dp.callback_query_handler(lambda c: c.data == "add_product")
async def handle_add_product(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Режим додавання продуктів. Введіть назву продукту:")
    await Form.name.set()

# Обробник для отримання назви нового продукту
@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['name'] = message.text.lower()  # Перетворення в нижній регістр

    await Form.next()
    await message.reply("Введіть кількість вуглеводів на 100 грам у продукті:")

# Обробник для отримання кількості вуглеводів нового продукту
@dp.message_handler(lambda message: message.text.replace('.', '', 1).isdigit(), state=Form.carbs)
async def process_carbs(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['carbs'] = float(message.text)

    await Form.next()
    await message.reply("Введіть кількість хлібних одиниць у продукті:")

# Обробник для отримання кількості хлібних одиниць нового продукту
@dp.message_handler(lambda message: message.text.replace('.', '', 1).isdigit(), state=Form.he)
async def process_he(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['he'] = float(message.text)

    await state.update_data(he=float(message.text))

    # Видалення клавіатури
    markup = ReplyKeyboardRemove()

    await bot.send_message(
        message.chat.id,
        md.text(
            md.text("Додані дані про продукт:"),
            md.text('Назва:', md.bold(data['name'])),
            md.text('Вуглеводи:', md.bold(data['carbs'])),
            md.text('Хлібні одиниці:', data['he']),
            md.text("Продукт додано до бази даних. Продовжуйте пошук"),
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

    await state.finish()  # Завершення стану

# Обробник для команди "/start"
@dp.message_handler(lambda message: message.text == "/start")
async def handle_start_command(message: types.Message, state: FSMContext):
    await state.finish()
    await handle_start(message)

# Запуск бота через виконавця
if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp, skip_updates=True)
