import os
import sqlite3
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

TOKEN = os.environ.get("BOT_TOKEN", "8329191195:AAHn4QbiglB8t_bjXp8qIhHJcfUpHPkvoFU")
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()] if ADMIN_IDS_STR else []

DB_PATH = "groups.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_group(chat_id: int, title: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO groups (chat_id, title) VALUES (?, ?)", (chat_id, title))
    conn.commit()
    conn.close()


def remove_group(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def get_all_groups():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id, title FROM groups")
    rows = c.fetchall()
    conn.close()
    return rows


def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True  # если список пуст — разрешаем всем (на старте)
    return user_id in ADMIN_IDS


# ─── Обработчики ───────────────────────────────────────────────

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Бот добавлен в группу — сохраняем"""
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            save_group(chat.id, chat.title or "Без названия")
            await update.message.reply_text(
                f"👋 Привет! Бот Monellyn подключён к группе *{chat.title}*.\n"
                "Теперь вы будете получать уведомления от команды Monellyn.",
                parse_mode="Markdown"
            )


async def on_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Бот удалён из группы — убираем из базы"""
    chat = update.effective_chat
    for member in update.message.left_chat_member:
        if member.id == context.bot.id:
            remove_group(chat.id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для рассылки уведомлений мерчантам Monellyn.\n\n"
        "📋 *Команды:*\n"
        "/broadcast <текст> — разослать сообщение во все группы\n"
        "/groups — список подключённых групп\n"
        "/myid — узнать свой Telegram ID",
        parse_mode="Markdown"
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать свой ID"""
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Ваш Telegram ID: `{user.id}`\n\n"
        "Добавьте его в переменную `ADMIN_IDS` на Railway чтобы стать администратором.",
        parse_mode="Markdown"
    )


async def cmd_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех групп"""
    if update.effective_chat.type != "private":
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return

    groups = get_all_groups()
    if not groups:
        await update.message.reply_text("📭 Бот ещё не добавлен ни в одну группу.")
        return

    text = f"📋 *Подключённые группы ({len(groups)}):*\n\n"
    for chat_id, title in groups:
        text += f"• {title} (`{chat_id}`)\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка сообщения во все группы"""
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚠️ Команду /broadcast используйте только в личке с ботом.")
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return

    if not context.args:
        await update.message.reply_text(
            "✏️ Укажите текст сообщения:\n`/broadcast Ваш текст здесь`",
            parse_mode="Markdown"
        )
        return

    message_text = " ".join(context.args)
    groups = get_all_groups()

    if not groups:
        await update.message.reply_text("📭 Нет подключённых групп для рассылки.")
        return

    status_msg = await update.message.reply_text(f"📤 Начинаю рассылку в {len(groups)} групп...")

    sent = 0
    failed = 0
    failed_groups = []

    for chat_id, title in groups:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📢 *Уведомление от Monellyn:*\n\n{message_text}",
                parse_mode="Markdown"
            )
            sent += 1
            await asyncio.sleep(0.1)  # небольшая пауза чтобы не словить лимит
        except Exception as e:
            failed += 1
            failed_groups.append(f"{title} ({chat_id}): {str(e)[:50]}")
            # если бот кикнут — удаляем группу
            if "bot was kicked" in str(e) or "chat not found" in str(e):
                remove_group(chat_id)

    result = f"✅ Рассылка завершена!\n\n📨 Отправлено: {sent}/{len(groups)}"
    if failed_groups:
        result += f"\n❌ Ошибки ({failed}):\n" + "\n".join(failed_groups[:5])

    await status_msg.edit_text(result)


# ─── Запуск ────────────────────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("groups", cmd_groups))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_bot_removed))

    print("🤖 Monellyn Bot запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
