import os
import json
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DAILY_GOAL = int(os.getenv("DAILY_GOAL", "40"))
DATA_FILE = Path("prospectador/leads.json")

DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
if not DATA_FILE.exists():
    DATA_FILE.write_text("[]", encoding="utf-8")

def load_leads():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def save_leads(leads):
    DATA_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 META 20K PROSPECTADOR\n\n"
        f"Meta diária: {DAILY_GOAL} novos leads\n\n"
        "Comandos:\n"
        "/buscar <segmento> <cidade> <quantidade>\n"
        "/meta\n/status\n/leads\n\n"
        "Exemplo:\n/buscar frutarias Porto Velho 40"
    )

async def meta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🎯 Meta diária atual: {DAILY_GOAL} leads.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leads = load_leads()
    today = datetime.now().strftime("%Y-%m-%d")
    today_leads = [x for x in leads if x.get("date") == today]
    await update.message.reply_text(
        "📊 META 20K — STATUS\n\n"
        f"Meta: {DAILY_GOAL}\n"
        f"Leads registrados hoje: {len(today_leads)}\n"
        f"Total no CRM: {len(leads)}\n\n"
        "🔧 Busca automática e integração de envio serão conectadas na próxima etapa."
    )

async def leads_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leads = load_leads()
    if not leads:
        await update.message.reply_text("Nenhum lead registrado ainda.")
        return
    last = leads[-10:]
    text = "📋 ÚLTIMOS LEADS\n\n" + "\n".join(
        f"• {x.get('name','Sem nome')} — {x.get('status','Novo contato')}" for x in last
    )
    await update.message.reply_text(text)

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Use: /buscar <segmento> <cidade> <quantidade>\nEx.: /buscar frutarias Porto Velho 40")
        return
    await update.message.reply_text(
        "🔎 Busca recebida:\n"
        f"{query}\n\n"
        "O núcleo do bot está funcionando. A fonte autorizada de estabelecimentos será conectada na próxima etapa para localizar, deduplicar e qualificar os leads."
    )

def main():
    if not TOKEN:
        raise RuntimeError("Configure TELEGRAM_BOT_TOKEN como variável de ambiente.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("meta", meta))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("leads", leads_cmd))
    app.run_polling()

if __name__ == "__main__":
    main()
