import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from parser import parse_expense_image, parse_expense_text
from sheets import append_expense, ensure_headers

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _format_confirmation(expense: dict) -> str:
    ht = expense.get("ht")
    tva_eur = expense.get("tva_eur")
    tva_pct = expense.get("tva_pct")
    ttc = expense.get("ttc")
    devise = expense.get("devise", "EUR")

    ht_str = f"{ht:.2f} {devise}" if isinstance(ht, (int, float)) else "NC"
    tva_str = f"{tva_eur:.2f} € ({tva_pct}%)" if isinstance(tva_eur, (int, float)) else "NC"
    ttc_str = f"{ttc:.2f} {devise}" if isinstance(ttc, (int, float)) else "NC"

    return (
        "✅ *Dépense enregistrée !*\n\n"
        f"🏪 *Marchand :* {expense.get('marchand', 'N/A')}\n"
        f"📅 *Date :* {expense.get('date', 'N/A')}\n"
        f"📂 *Catégorie :* {expense.get('categorie', 'N/A')}\n"
        f"💶 *HT :* {ht_str}\n"
        f"🧾 *TVA :* {tva_str}\n"
        f"💰 *TTC :* {ttc_str}"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Bot de dépenses professionnelles*\n\n"
        "Envoyez-moi :\n"
        "• Un *texte* décrivant votre dépense\n"
        "• Une *photo* de votre reçu\n\n"
        "Exemples :\n"
        "`Déjeuner chez Paul 25€`\n"
        "`Taxi 18.50€`\n"
        "`Station Total essence 65€`",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now().strftime("%d/%m/%Y")
    text = update.message.text
    processing_msg = await update.message.reply_text("⏳ Analyse en cours…")
    try:
        expense = parse_expense_text(text, today)
        append_expense(expense)
        await processing_msg.edit_text(_format_confirmation(expense), parse_mode="Markdown")
    except Exception as exc:
        logger.error("Erreur texte : %s", exc, exc_info=True)
        await processing_msg.edit_text(f"❌ Erreur : {exc}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now().strftime("%d/%m/%Y")
    processing_msg = await update.message.reply_text("⏳ Analyse du reçu en cours…")
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        expense = parse_expense_image(bytes(image_bytes), "image/jpeg", today)
        append_expense(expense)
        await processing_msg.edit_text(_format_confirmation(expense), parse_mode="Markdown")
    except Exception as exc:
        logger.error("Erreur photo : %s", exc, exc_info=True)
        await processing_msg.edit_text(f"❌ Erreur : {exc}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now().strftime("%d/%m/%Y")
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("❌ Veuillez envoyer une image (JPEG, PNG…) ou du texte.")
        return
    processing_msg = await update.message.reply_text("⏳ Analyse du reçu en cours…")
    try:
        file = await context.bot.get_file(doc.file_id)
        image_bytes = await file.download_as_bytearray()
        expense = parse_expense_image(bytes(image_bytes), doc.mime_type, today)
        append_expense(expense)
        await processing_msg.edit_text(_format_confirmation(expense), parse_mode="Markdown")
    except Exception as exc:
        logger.error("Erreur document : %s", exc, exc_info=True)
        await processing_msg.edit_text(f"❌ Erreur : {exc}")


def main() -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN manquant dans les variables d'environnement")

    try:
        ensure_headers()
    except Exception as exc:
        logger.warning("Impossible d'initialiser les en-têtes Google Sheets : %s", exc)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))

    logger.info("Bot démarré en mode polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
