import logging
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from text import (
    get_benvenuto_popolare_text,
    get_benvenuto_tecnica_text,
    get_benvenuto_prop_text,
    welcome_text
)
from profili import artists
import asyncio
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://sakurafestival.onrender.com/webhook").strip()
PORT = int(os.getenv("PORT", 8000))

# Stati della ConversationHandler
PASSWORD = 0
VOTE = 1

SET_OPTION = 10  
SET_DETAIL = 11      
SET_VALUE = 12       

PASSWORD_POPOLARE = "1234"
PASSWORD_TECNICA = "5678"
PASSWORD_OWNER = "9999"
ARTISTI_CHOICE = 20
ARTISTI_ADD_NAME = 31
ARTISTI_ADD_AGE = 32
ARTISTI_ADD_PHOTO = 33
ARTISTI_ADD_SONG = 34
ARTISTI_REMOVE = 22

TECHNICAL_AMBITI = [
    "Intonazione",
    "Interpretazione",
    "Tecninca Musicale/Strumentale",
    "Presenza Scenica"
]

# File per salvare i dati
DATA_FILE = "bot_data.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Funzioni per salvare e caricare i dati da file JSON
def save_bot_data(bot_data: dict) -> None:
    # Prepara un dizionario "persistente" con solo i dati serializzabili
    data_to_save = {
        "max_judges_popolare": bot_data.get("max_judges_popolare"),
        "max_judges_tecnica": bot_data.get("max_judges_tecnica"),
        "votes_popolare": bot_data.get("votes_popolare", {}),
        "votes_tecnica": bot_data.get("votes_tecnica", {}),
        "judges_popolare": list(bot_data.get("judges_popolare", [])),
        "judges_tecnica": list(bot_data.get("judges_tecnica", [])),
        "judge_types": bot_data.get("judge_types", {}),
        "password_popolare": PASSWORD_POPOLARE,
        "password_tecnica": PASSWORD_TECNICA,
        "password_owner": PASSWORD_OWNER,
        "owner_id": bot_data.get("owner_id")
    }
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data_to_save, f, indent=4)
    except Exception as e:
        logger.error(f"Errore nel salvataggio dei dati: {e}")

def load_bot_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                data["judges_popolare"] = set(data.get("judges_popolare", []))
                data["judges_tecnica"] = set(data.get("judges_tecnica", []))
                return data
        except Exception as e:
            logger.error(f"Errore nel caricamento dei dati: {e}")
    return {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("logged_in"):
        await update.message.reply_text("_⏸️ Sei già autenticato\\. Se desideri effettuare un nuovo autenticazione, premi \\/logout\\._", parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    photo_id = "AgACAgQAAxkBAAEy2_Jn3EllD1xN6UYFqJ5Ys8piN7eg3gAC6cMxG4kB4FKb4z4XTBrmmQEAAwIAA3kAAzYE"
    await update.message.reply_photo(
        photo=photo_id,
        caption=welcome_text(update),
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return PASSWORD

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global PASSWORD_POPOLARE, PASSWORD_TECNICA, PASSWORD_OWNER
    user_password = update.message.text.strip()
    
    if user_password == PASSWORD_POPOLARE:
        context.user_data['jury_type'] = "popolare"
        context.user_data["logged_in"] = True  # Imposta lo stato autenticato
        judges_popolare = context.bot_data.setdefault("judges_popolare", set())
        max_limit = context.bot_data.get("max_judges_popolare")
        if max_limit and len(judges_popolare) >= max_limit:
            await update.message.reply_text("_⚠️ È stato raggiunto il limite di componenti della giuria popolare\\!_", parse_mode=ParseMode.MARKDOWN_V2)
            return ConversationHandler.END
        judges_popolare.add(update.effective_chat.id)
        context.bot_data["judges_popolare"] = judges_popolare
        context.bot_data.setdefault("votes_popolare", {})
        await update.message.reply_text(get_benvenuto_popolare_text(update), parse_mode=ParseMode.MARKDOWN_V2)
        await notify_owner(update, context, "popolare")
        save_bot_data(context.bot_data)
        return VOTE

    elif user_password == PASSWORD_TECNICA:
        context.user_data['jury_type'] = "tecnica"
        context.user_data["logged_in"] = True  # Imposta lo stato autenticato
        judges_tecnica = context.bot_data.setdefault("judges_tecnica", set())
        max_limit = context.bot_data.get("max_judges_tecnica")
        if max_limit and len(judges_tecnica) >= max_limit:
            await update.message.reply_text("_⚠️ È stato raggiunto il limite di componenti della giuria tecnica\\!_", parse_mode=ParseMode.MARKDOWN_V2)
            return ConversationHandler.END
        judges_tecnica.add(update.effective_chat.id)
        context.bot_data["judges_tecnica"] = judges_tecnica
        context.bot_data.setdefault("votes_tecnica", {})
        judge_types = context.bot_data.setdefault("judge_types", {})
        judge_types[update.effective_chat.id] = "tecnica"
        await update.message.reply_text(get_benvenuto_tecnica_text(update), parse_mode=ParseMode.MARKDOWN_V2)
        await notify_owner(update, context, "tecnica")
        save_bot_data(context.bot_data)
        return VOTE

    elif user_password == PASSWORD_OWNER:
        context.user_data['user_role'] = "owner"
        context.user_data["logged_in"] = True
        context.bot_data["owner_id"] = update.effective_chat.id
        save_bot_data(context.bot_data)
        await update.message.reply_text(get_benvenuto_prop_text(update), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

async def notify_owner(update: Update, context: ContextTypes.DEFAULT_TYPE, jury_type: str) -> None:
    owner_id = context.bot_data.get("owner_id")
    if owner_id:
        user_name = update.effective_user.first_name
        escape_username = escape_markdown(user_name, version=2)
        user_id = update.effective_chat.id
        clickable_name = f"[{escape_username}](tg://user?id={user_id})"
        text = f"_👤 Il giudice {clickable_name} si è registrato come giuria di tipo *{jury_type}*\\._"
        try:
            await context.bot.send_message(chat_id=owner_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica al proprietario: {e}")

async def votazioni_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner_id = context.bot_data.get("owner_id")
    if update.effective_chat.id != owner_id:
        await update.message.reply_text("Non sei autorizzato ad eseguire questo comando.")
        return
    await send_owner_buttons(update, context)

async def send_owner_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    artists_data = context.bot_data['artists']
    buttons = []
    row = []
    for i, (key, artist) in enumerate(artists_data.items()):
        row.append(InlineKeyboardButton(artist['nome'], callback_data=key))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🛑 Interrompi votazioni", callback_data="stop_voting")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.effective_message.reply_text(
        text="*Che le votazioni abbiano inizio\\!*\n\n_Premi sul nome dell'artista per il quale vuoi che venga espresso il voto della giuria\\._" ,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def owner_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    artist_key = query.data

    if artist_key == "stop_voting":
        await stop_voting_handler(update, context)
        return

    if artist_key == "back_to_main_menu":
        await main_menu_keyboard(update, context) 
        return

    artists = context.bot_data.get("artists", {})
    if artist_key not in artists:
        await query.edit_message_text("Artista non trovato.")
        return

    artist = artists[artist_key]
    await query.message.reply_text(
        f"*🔜 Cominciano le votazioni per {artist['nome']}*",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    context.bot_data["current_selected_artist"] = artist_key

    response_text = (
        f"*Nome\\:* {artist['nome']}\n"
        f"*Età\\:* {artist['età']}\n"
        f"*Canzone\\:* {artist['canzone']}"
    )
    
    judges = set()
    judges.update(context.bot_data.get("judges_popolare", set()))
    judges.update(context.bot_data.get("judges_tecnica", set()))
    judge_types = context.bot_data.get("judge_types", {})

    for judge_chat_id in judges:
        try:
            if judge_types.get(judge_chat_id) == "tecnica":
                prompt = "\n\n_🔽 Esprimi il tuo voto per la categoria *{}*\\:_".format(TECHNICAL_AMBITI[0])
            else:
                prompt = "\n\n_🔽 Inserisci il tuo voto per questo artista\\:_"

            if artist.get('foto'):
                await context.bot.send_photo(
                    chat_id=judge_chat_id,
                    photo=artist['foto'],
                    caption=response_text + prompt,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await context.bot.send_message(
                    chat_id=judge_chat_id,
                    text=response_text + prompt,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
        except Exception as e:
            logger.error(f"Errore nell'invio del profilo all'utente {judge_chat_id}: {e}")

async def vote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "current_selected_artist" not in context.bot_data:
        await update.message.reply_text("Nessun artista selezionato, attendi che il proprietario lo scelga.")
        return VOTE

    current_artist = context.bot_data["current_selected_artist"]
    user_id = update.effective_user.id
    vote_input_str = update.message.text.strip()
    try:
        vote_value = float(vote_input_str)
    except ValueError:
        await update.message.reply_text("❌ Inserisci un numero valido per il voto.")
        return VOTE

    jury_type = context.user_data.get('jury_type', 'popolare')

    if jury_type == "popolare":
        votes_dict = context.bot_data.setdefault("votes_popolare", {})
        if current_artist not in votes_dict:
            votes_dict[current_artist] = {}
        if user_id in votes_dict[current_artist]:
            await update.message.reply_text("🔚 Hai già votato per questo artista!")
            return VOTE
        
        if vote_value < 1 or vote_value > 10:
            await update.message.reply_text("#️⃣ Il voto deve essere compreso tra 1 e 10. Riprova.")
            return VOTE

        votes_dict[current_artist][user_id] = vote_value
        await update.message.reply_text("Grazie per il tuo voto!")
        owner_id = context.bot_data.get("owner_id")
        if owner_id:
            user_name = update.effective_user.first_name
            escape_username = escape_markdown(user_name, version=2)
            clickable_name = f"[{escape_username}](tg://user?id={user_id})"
            formatted_vote = escape_markdown(str(vote_value), version=2)
            artist_nome = escape_markdown(context.bot_data['artists'][current_artist]['nome'], version=2)
            notification_text = (
                f"🔝 Il giudice {clickable_name} ha votato per l'artista {artist_nome} con voto\\: {formatted_vote}\\."
            )
            try:
                await context.bot.send_message(chat_id=owner_id, text=notification_text, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e:
                logger.error(f"Errore nell'invio della notifica al proprietario: {e}")
        save_bot_data(context.bot_data)
        return VOTE

    else:
        votes_dict = context.bot_data.setdefault("votes_tecnica", {})
        if current_artist not in votes_dict:
            votes_dict[current_artist] = {}
        if user_id not in votes_dict[current_artist]:
            votes_dict[current_artist][user_id] = {}

        ambito_index = context.user_data.get("ambito_index", 0)
        current_ambito = TECHNICAL_AMBITI[ambito_index]

        if vote_value < 1 or vote_value > 10:
            await update.message.reply_text(
                f"\\#️⃣ Il voto per la categoria *{current_ambito}* deve essere compreso tra 1 e 10\\. Riprova\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return VOTE

        if current_ambito in votes_dict[current_artist][user_id]:
            await update.message.reply_text("🔚 Hai già votato per questo artista in questo ambito!")
            return VOTE

        votes_dict[current_artist][user_id][current_ambito] = vote_value
        ambito_index += 1
        context.user_data["ambito_index"] = ambito_index

        if ambito_index < len(TECHNICAL_AMBITI):
            next_ambito = TECHNICAL_AMBITI[ambito_index]
            await update.message.reply_text(
                f"_🔽 Esprimi il tuo voto per la categoria *{next_ambito}*\\:_",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            save_bot_data(context.bot_data)
            return VOTE
        else:
            user_votes = votes_dict[current_artist][user_id]
            total = sum(user_votes[amb] for amb in TECHNICAL_AMBITI)
            avg = total / len(TECHNICAL_AMBITI)
            avg2 = escape_markdown(f"{avg:.2f}", version=2)
            await update.message.reply_text(
                f"*🆒 Grazie per il tuo voto\\! La media dei voti è\\: {avg2}*",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            owner_id = context.bot_data.get("owner_id")
            if owner_id:
                user_name = update.effective_user.first_name
                escape_username = escape_markdown(user_name, version=2)
                clickable_name = f"[{escape_username}](tg://user?id={user_id})"
                formatted_avg = escape_markdown(f"{avg:.2f}", version=2)
                artist_nome = escape_markdown(context.bot_data['artists'][current_artist]['nome'], version=2)
                notification_text = (
                    f"🔝 Il giudice {clickable_name} ha votato per l'artista {artist_nome}\\. Media dei voti\\: {formatted_avg}"
                )
                try:
                    await context.bot.send_message(chat_id=owner_id, text=notification_text, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception as e:
                    logger.error(f"Errore nell'invio della notifica al proprietario: {e}")
            context.user_data["ambito_index"] = 0
            save_bot_data(context.bot_data)
            return VOTE

async def stop_voting_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    artists_data = context.bot_data.get("artists", {})
    votes_popolare = context.bot_data.get("votes_popolare", {})
    votes_tecnica = context.bot_data.get("votes_tecnica", {})

    ranking = []
    for artist_key, artist in artists_data.items():
        pop_votes = votes_popolare.get(artist_key, {})
        if pop_votes:
            avg_pop = sum(pop_votes.values()) / len(pop_votes)
        else:
            avg_pop = 0

        tech_votes = votes_tecnica.get(artist_key, {})
        tech_vote_list = []
        for judge, aspects in tech_votes.items():
            if aspects:
                avg_aspect = sum(aspects.values()) / len(aspects)
                tech_vote_list.append(avg_aspect)
        if tech_vote_list:
            avg_tech = sum(tech_vote_list) / len(tech_vote_list)
        else:
            avg_tech = 0

        overall_avg = (avg_pop + avg_tech) / 2
        artist_nome_escaped = escape_markdown(artist['nome'], version=2)
        ranking.append((overall_avg, artist_nome_escaped, avg_pop, avg_tech))

    ranking.sort(key=lambda x: x[0], reverse=True)

    results = []
    for overall, nome, avg_pop, avg_tech in ranking:
        media = escape_markdown(f"{overall:.2f}", version=2)
        pop_media = escape_markdown(f"{avg_pop:.2f}", version=2)
        tech_media = escape_markdown(f"{avg_tech:.2f}", version=2)

        results.append(f"_*{nome}\\: {media}*_\n\\- Popolare\\: {pop_media}\n\\- Tecnica\\: {tech_media}\n")

    message = "*🏆 Risultati Votazioni\\:*\n\n" + "\n".join(results)

    owner_id = context.bot_data.get("owner_id")
    if owner_id:
        try:
            await context.bot.send_message(chat_id=owner_id, text=message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Errore nell'invio dei risultati al proprietario: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operazione annullata. Usa /start per riprovare.")
    return ConversationHandler.END

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("logged_in"):
        context.user_data.pop("logged_in")
    
    if context.user_data.get("user_role") == "owner":
        context.bot_data.pop("owner_id", None)
        context.user_data.pop("user_role", None)
    await update.message.reply_text("_🆓 Hai effettuato il logout\\. Usa /start per reinserire la password\\._", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("⚖️ Numero Giudici", callback_data="set_judges"),
            InlineKeyboardButton("⚙️ Password", callback_data="set_passwords")
        ],
        [InlineKeyboardButton("🗑 Chiudi", callback_data="close_keyboard")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    owner_id = context.bot_data.get("owner_id")
    if update.effective_chat.id != owner_id:
        await update.message.reply_text("Non sei autorizzato ad eseguire questo comando.")
        return ConversationHandler.END

    await update.message.reply_text(
        "*ℹ️ Seleziona l'impostazione che vuoi modificare\\:*",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return SET_OPTION

async def close_keyboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    return ConversationHandler.END

async def set_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "set_judges":
        keyboard = [
            [
                InlineKeyboardButton("👥 Giuria Popolare", callback_data="set_limit_popolare"),
                InlineKeyboardButton("🗣 Giuria Tecnica", callback_data="set_limit_tecnica")
            ],
            [InlineKeyboardButton("🔙 Indietro", callback_data="back_to_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "*🛃 Seleziona il tipo di giuria per cui impostare il numero di giudici\\:*",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_DETAIL

    elif data == "set_passwords":
        keyboard = [
            [InlineKeyboardButton("1️⃣ Password Giuria Popolare", callback_data="set_pass_popolare")],
            [InlineKeyboardButton("2️⃣ Password Giuria Tecnica", callback_data="set_pass_tecnica")],
            [InlineKeyboardButton("3️⃣ Password Owner", callback_data="set_pass_owner")],
            [InlineKeyboardButton("🔙 Indietro", callback_data="back_to_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "*🛃 Seleziona la password che vuoi modificare\\:*",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_DETAIL

async def set_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ["set_limit_popolare", "set_limit_tecnica"]:
        context.user_data["limit_type"] = "popolare" if data == "set_limit_popolare" else "tecnica"
        await query.edit_message_text(
            f"*🛃 Inserisci il nuovo limite per la giuria {context.user_data['limit_type']}\\:*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_VALUE

    elif data in ["set_pass_popolare", "set_pass_tecnica", "set_pass_owner"]:
        context.user_data["pass_type"] = {
            "set_pass_popolare": "popolare",
            "set_pass_tecnica": "tecnica",
            "set_pass_owner": "owner"
        }[data]
        await query.edit_message_text(
            f"*🛃 Inserisci la nuova password per {context.user_data['pass_type']}\\:*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_VALUE

    elif data == "back_to_main_menu":
        await query.edit_message_text(
            "*ℹ️ Seleziona l'impostazione che vuoi modificare\\:*",
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_OPTION

async def set_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_value = update.message.text.strip()
    keyboard = []

    if "limit_type" in context.user_data:
        try:
            new_limit = int(new_value)
            limit_type = context.user_data["limit_type"]
            if limit_type == "popolare":
                context.bot_data["max_judges_popolare"] = new_limit
            elif limit_type == "tecnica":
                context.bot_data["max_judges_tecnica"] = new_limit

            message_text = f"_✅ Limite per la giuria {limit_type} impostato a {new_limit}\\._"
            keyboard = [[InlineKeyboardButton("🔙 Indietro", callback_data="back_to_limit_menu")]]
        except ValueError:
            await update.message.reply_text("Inserisci un numero valido.")
            return SET_VALUE

    elif "pass_type" in context.user_data:
        # Se preferisci, salva queste password in un sistema persistente
        global PASSWORD_POPOLARE, PASSWORD_TECNICA, PASSWORD_OWNER
        pass_type = context.user_data["pass_type"]
        if pass_type == "popolare":
            PASSWORD_POPOLARE = new_value
        elif pass_type == "tecnica":
            PASSWORD_TECNICA = new_value
        elif pass_type == "owner":
            PASSWORD_OWNER = new_value

        message_text = f"_✅ Nuova password per {pass_type} impostata correttamente\\._"
        keyboard = [[InlineKeyboardButton("🔙 Indietro", callback_data="back_to_password_menu")]]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    save_bot_data(context.bot_data)  # Funzione per salvare i dati, definiscila in base alle tue esigenze
    return SET_VALUE

async def back_to_password_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("1️⃣ Password Giuria Popolare", callback_data="set_pass_popolare")],
        [InlineKeyboardButton("2️⃣ Password Giuria Tecnica", callback_data="set_pass_tecnica")],
        [InlineKeyboardButton("3️⃣ Password Owner", callback_data="set_pass_owner")],
        [InlineKeyboardButton("🔙 Indietro", callback_data="back_to_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "*🛃 Seleziona la password che vuoi modificare\\:*",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return SET_DETAIL

async def back_to_limit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("👥 Giuria Popolare", callback_data="set_limit_popolare"),
            InlineKeyboardButton("🗣 Giuria Tecnica", callback_data="set_limit_tecnica")
        ],
        [InlineKeyboardButton("🔙 Indietro", callback_data="back_to_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "*🛃 Seleziona il tipo di giuria per cui impostare il numero di giudici\\:*",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return SET_DETAIL

async def reset_voting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner_id = context.bot_data.get("owner_id")
    if update.effective_chat.id != owner_id:
        await update.message.reply_text("Non sei autorizzato ad eseguire questo comando.")
        return

    context.bot_data["votes_popolare"] = {}
    context.bot_data["votes_tecnica"] = {}
    context.bot_data["judges_popolare"] = set()
    context.bot_data["judges_tecnica"] = set()
    context.bot_data["judge_types"] = {}

    save_bot_data(context.bot_data)
    await update.message.reply_text("✅ I dati sono stati eliminati.")

async def artisti_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    owner_id = context.bot_data.get("owner_id")
    if update.effective_chat.id != owner_id:
        await update.message.reply_text("Non sei autorizzato ad eseguire questo comando.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ Aggiungi Artista", callback_data="add_artist")],
        [InlineKeyboardButton("➖ Rimuovi Artista", callback_data="remove_artist")],
        [InlineKeyboardButton("✖️ Annulla", callback_data="cancel_artists")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Seleziona l'azione da eseguire:", reply_markup=reply_markup)
    return ARTISTI_CHOICE

async def artisti_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "add_artist":
        context.user_data["new_artist"] = {}
        await query.edit_message_text("_🔤 Inserisci il *nome* dell'artista\\:_", parse_mode=ParseMode.MARKDOWN_V2)
        return ARTISTI_ADD_NAME

    elif choice == "remove_artist":
        artists = context.bot_data.get("artists", {})
        if not artists:
            await query.edit_message_text("Non ci sono artisti da rimuovere.")
            return ConversationHandler.END

        keyboard = []
        for key, artist in artists.items():
            keyboard.append([InlineKeyboardButton(artist['nome'], callback_data=f"rm_{key}")])
        keyboard.append([InlineKeyboardButton("✖️ Annulla", callback_data="cancel_artists")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("_Seleziona l'artista da rimuovere\\:_", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
        return ARTISTI_REMOVE

    elif choice == "cancel_artists":
        await query.edit_message_text("Operazione annullata.")
        return ConversationHandler.END

# Fase 1: riceve il nome
async def add_artist_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome = update.message.text.strip()
    context.user_data["new_artist"]["nome"] = nome
    await update.message.reply_text("_🔢 Inserisci l'*età* dell'artista\\:_", parse_mode=ParseMode.MARKDOWN_V2)
    return ARTISTI_ADD_AGE

# Fase 2: riceve l'età
async def add_artist_age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    eta_str = update.message.text.strip()
    try:
        eta = int(eta_str)
    except ValueError:
        await update.message.reply_text("L'età deve essere un numero intero. Riprova:")
        return ARTISTI_ADD_AGE

    context.user_data["new_artist"]["età"] = eta
    await update.message.reply_text("_🎦 Invia la *foto* dell'artista\\:_", parse_mode=ParseMode.MARKDOWN_V2)
    return ARTISTI_ADD_PHOTO

async def add_artist_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Per favore, invia una foto valida.")
        return ARTISTI_ADD_PHOTO

    photo_id = update.message.photo[-1].file_id
    context.user_data["new_artist"]["foto"] = photo_id
    await update.message.reply_text("_🎵 Inserisci il *titolo della canzone*\\:_", parse_mode=ParseMode.MARKDOWN_V2)
    return ARTISTI_ADD_SONG

async def add_artist_song_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    canzone = update.message.text.strip()
    context.user_data["new_artist"]["canzone"] = canzone

    new_key = f"artist{len(artists) + 1}"
    artists[new_key] = context.user_data["new_artist"]

    update_artists_file(artists)

    await update.message.reply_text(
        f"_✅ Artista *{context.user_data['new_artist']['nome']}* aggiunto con successo\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    context.user_data.pop("new_artist", None)
    return ConversationHandler.END

async def remove_artist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_artists":
        await query.edit_message_text("Operazione annullata.")
        return ConversationHandler.END

    if data.startswith("rm_"):
        key = data[3:]
        artists = context.bot_data.get("artists", {})
        if key in artists:
            nome = artists[key]['nome']
            del artists[key]
            update_artists_file(artists)
            await query.edit_message_text(f"_❎ Artista *{nome}* rimosso con successo\\._", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.edit_message_text("Artista non trovato.")
    return ConversationHandler.END

def update_artists_file(artists: dict) -> None:
    content = "artists = " + json.dumps(artists, indent=4, ensure_ascii=False)
    try:
        with open("profili.py", "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Errore nell'aggiornamento di profili.py: {e}")

async def handle_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Errore nel parse del JSON: {e}")
        return web.Response(status=400, text="Invalid JSON")

    # Questa funzione ora usa la variabile globale 'application'
    update = Update.de_json(data, application.bot)

    asyncio.create_task(application.process_update(update))

    return web.Response(text="OK")


async def start_webserver() -> None:
    load_dotenv()
    PORT = int(os.getenv('PORT', '8443'))

    webapp = web.Application()
    webapp.router.add_get('/', health_check)
    webapp.router.add_get('/health', health_check)
    webapp.router.add_post('/webhook', handle_webhook)

    runner = web.AppRunner(webapp)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    logger.info(f"Webserver avviato su 0.0.0.0:{PORT}")


async def main() -> None:
    load_dotenv()
    # TOKEN e WEBHOOK_URL vengono già caricati a livello globale
    
    if not TOKEN or not WEBHOOK_URL:
        logger.error("Le variabili d'ambiente TOKEN e WEBHOOK_URL devono essere definite.")
        return

    # --- INIZIO MODIFICA ---
    # Rimuoviamo la creazione di 'app' e 'global application' da qui.
    # L'oggetto 'application' è già stato creato globalmente.
    # Usiamo 'application' al posto di 'app' per caricare i dati e aggiungere gli handler.

    data = load_bot_data()
    if data:
        application.bot_data.update(data)
    application.bot_data.setdefault("artists", artists)
    application.bot_data.setdefault("owners_ids", set())

    application.add_handler(CommandHandler('start', start), group=0)
    application.add_handler(CommandHandler('set', set_limit_command), group=0)
    application.add_handler(CommandHandler('artisti', artisti_command), group=0)
    application.add_handler(CommandHandler('votazioni', votazioni_command), group=0)
    application.add_handler(CommandHandler('reset', reset_voting), group=0)
    application.add_handler(CommandHandler('logout', logout), group=0)
    application.add_handler(CommandHandler('cancel', cancel), group=0)

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_password),
            ],
            VOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, vote_handler),
            ],
            MAIN_MENU: [
                CallbackQueryHandler(owner_button_handler, pattern="^artist[0-9]+$"),
                CallbackQueryHandler(owner_button_handler, pattern="^stop_voting$"),
            ],
            SET_OPTION: [
                CallbackQueryHandler(set_option_callback, pattern="^(set_judges|set_passwords|set_home_picture)$"),
                CallbackQueryHandler(close_keyboard_callback, pattern="^close_keyboard$")
            ],
            SET_DETAIL: [
                CallbackQueryHandler(set_detail_callback, pattern="^set_limit_popolare|set_limit_tecnica|set_pass_popolare|set_pass_tecnica|set_pass_owner|back_to_main_menu$")
            ],
            SET_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_value_handler),
                CallbackQueryHandler(back_to_password_menu_callback, pattern="^back_to_password_menu$"),
                CallbackQueryHandler(back_to_limit_menu_callback, pattern="^back_to_limit_menu$")
            ],
            SET_HOME_PICTURE: [
                MessageHandler(filters.PHOTO, set_home_picture_handler)
            ],
            ARTISTI_CHOICE: [
                CallbackQueryHandler(artisti_choice_callback, pattern="^(add_artist|remove_artist|cancel_artists)$")
            ],
            ARTISTI_ADD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_artist_name_handler)
            ],
            ARTISTI_ADD_AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_artist_age_handler)
            ],
            ARTISTI_ADD_PHOTO: [
                MessageHandler(filters.PHOTO, add_artist_photo_handler)
            ],
            ARTISTI_ADD_SONG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_artist_song_handler)
            ],
            ARTISTI_ADD_CATEGORY: [
                CallbackQueryHandler(add_artist_category_handler, pattern="^categoria_")
            ],
            ARTISTI_REMOVE: [
                CallbackQueryHandler(remove_artist_callback, pattern="^(rm_.*|cancel_artists)$")
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
        per_chat=True
    )
    application.add_handler(conv, group=1)
    application.add_handler(CallbackQueryHandler(owner_button_handler), group=0)
    # --- FINE MODIFICA ---

    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook impostato su: {WEBHOOK_URL}")

    await start_webserver()
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())
