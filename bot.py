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
        return True
    return user_id in ADMIN_IDS


# ─── Handlers ───────────────────────────────────────────────

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            save_group(chat.id, chat.title or "Unnamed")
            await update.message.reply_text(
                f"👋 Hello! Monellyn Bot has been connected to *{chat.title}*.\n"
                "This group will now receive notifications from the Monellyn team.",
                parse_mode="Markdown"
            )


async def on_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    for member in update.message.left_chat_member:
        if member.id == context.bot.id:
            remove_group(chat.id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        f"👋 Hello, {user.first_name}!\n\n"
        "I'm the Monellyn broadcast bot for sending notifications to all merchant groups.\n\n"
        "📋 *Commands:*\n"
        "/broadcast <message> — send a message to all groups\n"
        "/groups — list all connected groups\n"
        "/myid — get your Telegram ID",
        parse_mode="Markdown"
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Your Telegram ID: `{user.id}`\n\n"
        "Add it to the `ADMIN_IDS` variable on Railway to become an admin.",
        parse_mode="Markdown"
    )


async def cmd_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have access to this command.")
        return

    groups = get_all_groups()
    if not groups:
        await update.message.reply_text("📭 The bot hasn't been added to any groups yet.")
        return

    text = f"📋 *Connected groups ({len(groups)}):*\n\n"
    for chat_id, title in groups:
        text += f"• {title} (`{chat_id}`)\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚠️ Please use /broadcast only in a private chat with the bot.")
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have access to this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "✏️ Please provide the message text:\n`/broadcast Your message here`",
            parse_mode="Markdown"
        )
        return

    message_text = " ".join(context.args)
    groups = get_all_groups()

    if not groups:
        await update.message.reply_text("📭 No connected groups to broadcast to.")
        return

    status_msg = await update.message.reply_text(f"📤 Starting broadcast to {len(groups)} groups...")

    sent = 0
    failed = 0
    failed_groups = []

    for chat_id, title in groups:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📢 *Notification from Monellyn:*\n\n{message_text}",
                parse_mode="Markdown"
            )
            sent += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            failed += 1
            failed_groups.append(f"{title} ({chat_id}): {str(e)[:50]}")
            if "bot was kicked" in str(e) or "chat not found" in str(e):
                remove_group(chat_id)

    result = f"✅ Broadcast complete!\n\n📨 Sent: {sent}/{len(groups)}"
    if failed_groups:
        result += f"\n❌ Errors ({failed}):\n" + "\n".join(failed_groups[:5])

    await status_msg.edit_text(result)


# ─── Run ────────────────────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("groups", cmd_groups))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_bot_removed))

    print("🤖 Monellyn Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
