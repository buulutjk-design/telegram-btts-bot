import math
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "BOT_TOKEN_HERE"
ADMIN_ID = 8480843841

user_data_store = {}

# ---------------- VIP SYSTEM ----------------

def load_vip():
    try:
        with open("vip.json","r") as f:
            return json.load(f)
    except:
        return {}

def save_vip(data):
    with open("vip.json","w") as f:
        json.dump(data,f)

vip_users = load_vip()

def is_vip(user_id):

    if str(user_id) not in vip_users:
        return False

    expire = vip_users[str(user_id)]

    if datetime.now().timestamp() > expire:
        del vip_users[str(user_id]]
        save_vip(vip_users)
        return False

    return True


# ---------------- BOT STEPS ----------------

steps = [
"🏳 Home Team Name:",
"🚩 Away Team Name:",
"⚽ BTTS DATA\n\nEnter like this:\nHomeBTTS AwayBTTS\n\nExample:\n4 3",
"📊 GOALS DATA\n\nEnter like this:\nH5+ H5- A5+ A5-\n\nExample:\n8 6 7 8"
]


# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    if user_id != ADMIN_ID and not is_vip(user_id):

        await update.message.reply_text(
"""🔒 This bot is private.

To use this analysis bot you must purchase a membership.

💎 7 Days VIP Access
Price: 350 TRY

📩 Contact:
@blutad 🇹🇷"""
)
        return

    user_data_store[user_id] = {"step": 0, "data": []}

    await update.message.reply_text("👋 Welcome to the BTTS Analysis Bot")

    await update.message.reply_text("🏳 Home Team Name:")


# ---------------- HANDLE ----------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    if user_id != ADMIN_ID and not is_vip(user_id):
        return

    text = update.message.text
    step = user_data_store[user_id]["step"]

    user_data_store[user_id]["data"].append(text)
    user_data_store[user_id]["step"] += 1

    if step + 1 < len(steps):
        await update.message.reply_text(steps[step + 1])
        return

    data = user_data_store[user_id]["data"]

    home = data[0]
    away = data[1]

    btts = list(map(int, data[2].split()))
    goals = list(map(int, data[3].split()))

    h5_btts = btts[0]
    a5_btts = btts[1]

    h5_plus = goals[0]
    h5_minus = goals[1]
    a5_plus = goals[2]
    a5_minus = goals[3]

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

    result = "✅ BTTS YES" if percent >= 60 else "⛔️ BTTS NO"

    msg = f"""
📊 MATCH ANALYSIS

🏳 {home}
🚩 {away}

{result}
{percent}%
"""

    await update.message.reply_text(msg)

    del user_data_store[user_id]


# ---------------- VIP ADD ----------------

async def vipekle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id != ADMIN_ID:
        return

    user_id = context.args[0]

    expire = (datetime.now() + timedelta(days=7)).timestamp()

    vip_users[user_id] = expire

    save_vip(vip_users)

    await update.message.reply_text("VIP user added for 7 days.")


# ---------------- VIP COUNT ----------------

async def viptoplam(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id != ADMIN_ID:
        return

    total = len(vip_users)

    await update.message.reply_text(f"Total VIP users: {total}")


# ---------------- MAIN ----------------

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vipekle", vipekle))
    app.add_handler(CommandHandler("viptoplam", viptoplam))
    app.add_handler(MessageHandler(filters.TEXT, handle))

    print("Bot running...")

    app.run_polling()


if __name__ == "__main__":
    main()
