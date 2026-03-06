# bot.py
import os
import math
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ---------------- CONFIG ----------------
# Put your admin id here (int)
ADMIN_ID = 8480843841

# Token from environment
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable TOKEN is not set. Add TOKEN in Railway Variables.")

VIP_FILE = "vip.json"
CLEANUP_INTERVAL_SECONDS = 60 * 60  # hourly cleanup

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- UTIL: VIP PERSISTENCE ----------------
def load_vip() -> Dict[str, float]:
    try:
        if not os.path.exists(VIP_FILE):
            return {}
        with open(VIP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure values are floats (timestamps)
            return {k: float(v) for k, v in data.items()}
    except Exception as e:
        logger.exception("Failed to load vip.json: %s", e)
        return {}

def save_vip(data: Dict[str, float]) -> None:
    try:
        with open(VIP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.exception("Failed to save vip.json: %s", e)

vip_users: Dict[str, float] = load_vip()  # key = str(user_id) -> expire_timestamp

def add_vip(user_id: int, days: int = 7) -> None:
    expire = (datetime.now() + timedelta(days=days)).timestamp()
    vip_users[str(user_id)] = expire
    save_vip(vip_users)

def remove_vip_str(user_id_str: str) -> None:
    if user_id_str in vip_users:
        del vip_users[user_id_str]
        save_vip(vip_users)

def is_vip(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True  # admin always allowed
    key = str(user_id)
    if key not in vip_users:
        return False
    expire = vip_users[key]
    if datetime.now().timestamp() > expire:
        # expired -> remove and persist
        try:
            del vip_users[key]
            save_vip(vip_users)
        except Exception:
            pass
        return False
    return True

# ---------------- BOT FLOW STEPS ----------------
STEPS = [
    "🏳 Home Team Name:",
    "🚩 Away Team Name:",
    "⚽ BTTS DATA\nEnter like: HomeBTTS AwayBTTS\nExample: 4 3",
    "📊 GOALS DATA\nEnter like: H5+ H5- A5+ A5-\nExample: 8 6 7 8",
]

# per-user runtime memory (cleared after each analysis)
user_state: Dict[int, Dict[str, Any]] = {}

# ---------------- HELPERS ----------------
def safe_parse_ints(text: str):
    try:
        parts = text.strip().split()
        nums = [int(x) for x in parts]
        return nums
    except Exception:
        return None

def compute_btts(h5_btts:int, a5_btts:int, h5_plus:int, h5_minus:int, a5_plus:int, a5_minus:int):
    # Attack / defense averages (per game)
    home_attack = h5_plus / 5
    home_defense = h5_minus / 5
    away_attack = a5_plus / 5
    away_defense = a5_minus / 5

    lambda_home = (home_attack + away_defense) / 2
    lambda_away = (away_attack + home_defense) / 2

    p_home0 = math.exp(-lambda_home)
    p_away0 = math.exp(-lambda_away)

    poisson = (1 - p_home0) * (1 - p_away0)
    trend = ((h5_btts / 5) + (a5_btts / 5)) / 2

    final = (poisson + trend) / 2
    percent = round(final * 100)
    return percent, lambda_home, lambda_away

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # If non-admin and not VIP -> send membership message (English)
    if not is_vip(user_id) and user_id != ADMIN_ID:
        await update.message.reply_text(
            "🔒 This bot is private.\n\n"
            "To use this analysis bot you must purchase a membership.\n\n"
            "💎 7 Days VIP Access\n"
            "Price: 350 TRY\n\n"
            "📩 Contact:\n"
            "@blutad 🇹🇷"
        )
        # optional: notify admin about attempt
        try:
            logger.info("Non-VIP tried to use bot: %s (%s)", user_id, update.effective_user.username)
            # do not spam admin if many tries; keep simple
        except Exception:
            pass
        return

    # initialize state
    user_state[user_id] = {"step": 0, "data": []}
    # Send short welcome then immediately ask first question
    await update.message.reply_text("👋 Welcome to the BTTS Analysis Bot")
    await update.message.reply_text(STEPS[0])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # admin always allowed; vip allowed; otherwise ask to purchase
    if not is_vip(user_id) and user_id != ADMIN_ID:
        # user may have started without /start; send membership message
        await update.message.reply_text(
            "🔒 This bot is private.\n\n"
            "To use this analysis bot you must purchase a membership.\n\n"
            "💎 7 Days VIP Access\n"
            "Price: 350 TRY\n\n"
            "📩 Contact:\n"
            "@blutad 🇹🇷"
        )
        return

    # if no state (user didn't use /start) start the flow
    if user_id not in user_state:
        user_state[user_id] = {"step": 0, "data": []}
        await update.message.reply_text(STEPS[0])
        return

    state = user_state[user_id]
    step = state["step"]
    text = update.message.text.strip()

    # Append answer for current step with validation
    # Step 0: home team name (any text)
    if step == 0:
        if len(text) == 0 or len(text) > 100:
            await update.message.reply_text("Please enter a valid Home Team Name (1-100 chars).")
            return
        state["data"].append(text)
        state["step"] += 1
        await update.message.reply_text(STEPS[1])
        return

    # Step 1: away team name
    if step == 1:
        if len(text) == 0 or len(text) > 100:
            await update.message.reply_text("Please enter a valid Away Team Name (1-100 chars).")
            return
        state["data"].append(text)
        state["step"] += 1
        await update.message.reply_text(STEPS[2])
        return

    # Step 2: BTTS data (two ints)
    if step == 2:
        nums = safe_parse_ints(text)
        if not nums or len(nums) != 2 or any(n < 0 or n > 5 for n in nums):
            await update.message.reply_text("Invalid BTTS data. Enter two integers: HomeBTTS(0-5) AwayBTTS(0-5). Example: 4 3")
            return
        state["data"].append(text)
        state["step"] += 1
        await update.message.reply_text(STEPS[3])
        return

    # Step 3: Goals data (four ints)
    if step == 3:
        nums = safe_parse_ints(text)
        if not nums or len(nums) != 4 or any(n < 0 or n > 50 for n in nums):
            await update.message.reply_text("Invalid goals data. Enter four integers: H5+ H5- A5+ A5- . Example: 8 6 7 8")
            return
        state["data"].append(text)
        # Now compute result
        try:
            home = state["data"][0]
            away = state["data"][1]

            btts = [int(x) for x in state["data"][2].split()]
            goals = [int(x) for x in state["data"][3].split()]

            percent, lambda_home, lambda_away = compute_btts(
                btts[0], btts[1], goals[0], goals[1], goals[2], goals[3]
            )

            result_text = "✅ BTTS YES" if percent >= 60 else "⛔️ BTTS NO"

            msg = (
                "📊 MATCH ANALYSIS\n\n"
                f"🏳 {home}\n"
                f"🚩 {away}\n\n"
                f"{result_text}\n"
                f"{percent}%\n"
            )

            await update.message.reply_text(msg)
        except Exception as e:
            logger.exception("Failed to compute BTTS: %s", e)
            await update.message.reply_text("An error occurred while computing. Please try again.")
        finally:
            # clear state for user
            if user_id in user_state:
                del user_state[user_id]
        return

    # default fallback (shouldn't happen)
    await update.message.reply_text("Unexpected state. Please send /start to begin again.")
    user_state.pop(user_id, None)

# ---------------- ADMIN COMMANDS ----------------
async def vipekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /vipekle USERID")
        return
    try:
        user_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid USERID. It must be a number.")
        return
    add_vip(user_id, days=7)
    await update.message.reply_text(f"VIP added for user {user_id} for 7 days.")
    logger.info("Admin added VIP for %s", user_id)

async def viptoplam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total = len(vip_users)
    await update.message.reply_text(f"Total VIP users: {total}")

# Optional: admin can remove vip manually
async def vipsil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /vipsil USERID")
        return
    try:
        user_id_str = str(int(context.args[0]))
    except Exception:
        await update.message.reply_text("Invalid USERID.")
        return
    if user_id_str in vip_users:
        remove_vip_str(user_id_str)
        await update.message.reply_text(f"VIP removed for {user_id_str}")
    else:
        await update.message.reply_text("User is not VIP.")

# ---------------- PERIODIC VIP CLEANUP (and notify expired users) ----------------
async def vip_cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    # runs periodically; checks expirations and notifies users whose VIP just expired
    try:
        now_ts = datetime.now().timestamp()
        expired = []
        for uid_str, expire in list(vip_users.items()):
            if now_ts > float(expire):
                expired.append(uid_str)
        for uid_str in expired:
            try:
                # try notify user
                chat_id = int(uid_str)
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "🔒 Your VIP membership has expired.\n\n"
                            "To continue using the bot please renew your membership.\n\n"
                            "💎 7 Days VIP Access\n"
                            "Price: 350 TRY\n\n"
                            "📩 Contact:\n"
                            "@blutad 🇹🇷"
                        ),
                    )
                except Exception as send_err:
                    # user may have blocked bot or other error; just log
                    logger.info("Could not notify expired VIP %s: %s", uid_str, send_err)
                # remove from vip list
                remove_vip_str(uid_str)
                logger.info("VIP expired and removed: %s", uid_str)
            except Exception as e:
                logger.exception("Error processing expired vip %s: %s", uid_str, e)
    except Exception as e:
        logger.exception("VIP cleanup job failed: %s", e)

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vipekle", vipekle))
    app.add_handler(CommandHandler("viptoplam", viptoplam))
    app.add_handler(CommandHandler("vipsil", vipsil))

    # Message handler for the step flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule periodic cleanup job (first run after 10s, repeat every CLEANUP_INTERVAL_SECONDS)
    try:
        app.job_queue.run_repeating(vip_cleanup_job, interval=CLEANUP_INTERVAL_SECONDS, first=10)
    except Exception as e:
        logger.exception("Failed to schedule vip cleanup job: %s", e)

    logger.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
