import logging
import os
import uuid
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from drive_sync import get_service, load_cards, save_cards
from groq_gen import generate_flashcards
from ingest import extract_drive_file, extract_youtube
from sm2 import calculate_sm2

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = int(os.getenv("TELEGRAM_USER_ID"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Brussels")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ASKING_QUESTION, ASKING_ANSWER, ASKING_TOPIC, WAITING_INGEST_URL = range(4)

# Single-user session state
_session: dict = {"queue": [], "current_card": None}


def _authorized(update: Update) -> bool:
    return update.effective_user.id == USER_ID


async def _push_next_card(bot, chat_id: int):
    if not _session["queue"]:
        await bot.send_message(chat_id=chat_id, text="🎉 Session terminée ! Bien joué !")
        return
    card = _session["queue"].pop(0)
    _session["current_card"] = card
    topic_line = f"📚 _{card['topic']}_\n\n" if card.get("topic") else ""
    await bot.send_message(
        chat_id=chat_id,
        text=f"{topic_line}❓ *{card['question']}*",
        parse_mode="Markdown",
    )


# ── Commandes ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text(
        "👋 *Flashcards Bot*\n\n"
        "/review — Démarrer une session de révision\n"
        "/stats — Voir tes statistiques\n"
        "/add — Ajouter une carte manuellement\n"
        "/ingest — Générer des cartes depuis une URL (YouTube ou Google Drive)",
        parse_mode="Markdown",
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    service = get_service()
    cards = load_cards(service)["cards"]
    today = date.today().isoformat()
    due = sum(1 for c in cards if c.get("next_review", today) <= today)
    mature = sum(1 for c in cards if c.get("interval", 1) > 21)
    await update.message.reply_text(
        f"📊 *Statistiques*\n\n"
        f"Total de cartes : *{len(cards)}*\n"
        f"À réviser aujourd'hui : *{due}*\n"
        f"Cartes matures (>21j) : *{mature}*",
        parse_mode="Markdown",
    )


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    service = get_service()
    today = date.today().isoformat()
    due = [c for c in load_cards(service)["cards"] if c.get("next_review", today) <= today]
    if not due:
        await update.message.reply_text("✅ Aucune carte à réviser pour l'instant !")
        return
    _session["queue"] = due
    _session["current_card"] = None
    await update.message.reply_text(
        f"🎯 *{len(due)} carte(s)* à réviser. C'est parti !",
        parse_mode="Markdown",
    )
    await _push_next_card(context.bot, update.effective_chat.id)


# ── Flux de révision ───────────────────────────────────────────────────────────

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    card = _session.get("current_card")
    if not card:
        return
    keyboard = [
        [
            InlineKeyboardButton("❌ Raté", callback_data="rate_0"),
            InlineKeyboardButton("😅 Difficile", callback_data="rate_2"),
        ],
        [
            InlineKeyboardButton("👍 Bien", callback_data="rate_3"),
            InlineKeyboardButton("✅ Facile", callback_data="rate_4"),
        ],
    ]
    await update.message.reply_text(
        f"💡 *Réponse :*\n{card['answer']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != USER_ID:
        return
    await query.answer()

    quality = int(query.data.split("_")[1])
    card = _session.get("current_card")
    if not card:
        return

    service = get_service()
    data = load_cards(service)
    updated_interval = 1
    for i, c in enumerate(data["cards"]):
        if c["id"] == card["id"]:
            updated = calculate_sm2(c, quality)
            data["cards"][i] = updated
            updated_interval = updated["interval"]
            break
    save_cards(service, data)

    labels = {0: "❌ Raté", 2: "😅 Difficile", 3: "👍 Bien", 4: "✅ Facile"}
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        f"_{labels[quality]}_ — prochaine révision dans *{updated_interval}* jour(s)",
        parse_mode="Markdown",
    )
    _session["current_card"] = None
    await _push_next_card(context.bot, query.message.chat_id)


# ── Ajout manuel de cartes (/add) ──────────────────────────────────────────────

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "✏️ *Nouvelle carte*\n\nQuelle est la *question* ?",
        parse_mode="Markdown",
    )
    return ASKING_QUESTION


async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["q"] = update.message.text
    await update.message.reply_text("Et la *réponse* ?", parse_mode="Markdown")
    return ASKING_ANSWER


async def add_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["a"] = update.message.text
    await update.message.reply_text(
        "Quel est le *sujet/topic* ? (tape /skip pour ignorer)",
        parse_mode="Markdown",
    )
    return ASKING_TOPIC


async def add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_new_card(update, context, update.message.text)


async def add_skip_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_new_card(update, context, "")


async def _save_new_card(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str):
    card = {
        "id": str(uuid.uuid4()),
        "question": context.user_data["q"],
        "answer": context.user_data["a"],
        "topic": topic,
        "source": "Manuel",
        "easiness_factor": 2.5,
        "interval": 1,
        "repetitions": 0,
        "next_review": date.today().isoformat(),
    }
    service = get_service()
    data = load_cards(service)
    data["cards"].append(card)
    save_cards(service, data)
    await update.message.reply_text(
        f"✅ Carte ajoutée !\n\n*Q :* {card['question']}\n*R :* {card['answer']}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Annulé.")
    return ConversationHandler.END


# ── Ingest (/ingest) ──────────────────────────────────────────────────────────

async def ingest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "🔗 Envoie l'URL à ingérer :\n"
        "• Lien YouTube\n"
        "• Lien Google Drive (PDF ou fichier texte)\n\n"
        "Tape /cancel pour annuler.",
    )
    return WAITING_INGEST_URL


async def ingest_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return ConversationHandler.END

    url = update.message.text.strip()
    service = get_service()

    try:
        if "youtube.com" in url or "youtu.be" in url:
            status_msg = await update.message.reply_text("📥 Récupération du transcript YouTube...")
            text = extract_youtube(url)
        elif "drive.google.com" in url:
            status_msg = await update.message.reply_text("📥 Téléchargement du fichier Drive...")
            text = extract_drive_file(service, url)
        else:
            await update.message.reply_text("❌ URL non reconnue. Utilise un lien YouTube ou Google Drive.")
            return ConversationHandler.END

        await status_msg.edit_text("🧠 Génération des flashcards avec Groq...")
        cards_data = generate_flashcards(text)

        data = load_cards(service)
        today = date.today().isoformat()
        new_cards = []
        for c in cards_data:
            card = {
                "id": str(uuid.uuid4()),
                "question": c.get("question", "").strip(),
                "answer": c.get("answer", "").strip(),
                "topic": c.get("topic", "").strip(),
                "source": url,
                "easiness_factor": 2.5,
                "interval": 1,
                "repetitions": 0,
                "next_review": today,
            }
            if card["question"] and card["answer"]:
                data["cards"].append(card)
                new_cards.append(card)

        save_cards(service, data)

        preview = "\n".join(f"• {c['question']}" for c in new_cards[:5])
        if len(new_cards) > 5:
            preview += f"\n_...et {len(new_cards) - 5} autres_"

        await status_msg.edit_text(
            f"✅ *{len(new_cards)} carte(s) générée(s) et ajoutée(s)* !\n\n{preview}",
            parse_mode="Markdown",
        )

    except Exception as exc:
        await update.message.reply_text(f"❌ Erreur : {exc}")

    return ConversationHandler.END


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def _scheduled_review(app: Application):
    service = get_service()
    today = date.today().isoformat()
    due = [c for c in load_cards(service)["cards"] if c.get("next_review", today) <= today]
    if not due:
        return
    _session["queue"] = due
    _session["current_card"] = None
    await app.bot.send_message(
        chat_id=USER_ID,
        text=f"⏰ *Session de révision !*\n{len(due)} carte(s) à revoir.",
        parse_mode="Markdown",
    )
    await _push_next_card(app.bot, USER_ID)


async def _post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(_scheduled_review, "cron", hour=8, minute=0, args=[app])
    scheduler.add_job(_scheduled_review, "cron", hour=20, minute=0, args=[app])
    scheduler.start()
    logger.info("Scheduler actif — sessions à 8h et 20h (%s)", TIMEZONE)


# ── Entrée principale ──────────────────────────────────────────────────────────

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            ASKING_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question)],
            ASKING_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_answer)],
            ASKING_TOPIC: [
                CommandHandler("skip", add_skip_topic),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_topic),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    ingest_conv = ConversationHandler(
        entry_points=[CommandHandler("ingest", ingest_start)],
        states={
            WAITING_INGEST_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingest_url)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(add_conv)
    app.add_handler(ingest_conv)
    app.add_handler(CallbackQueryHandler(handle_rating, pattern=r"^rate_\d$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    logger.info("Bot démarré...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
