import os
import json
import re
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DAILY_GOAL = int(os.getenv("DAILY_GOAL", "40"))
DATA_FILE = Path("prospectador/leads.json")
USER_AGENT = "Meta20KProspectador/1.0 (Telegram bot; business lead discovery)"

DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
if not DATA_FILE.exists():
    DATA_FILE.write_text("[]", encoding="utf-8")

def load_leads():
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_leads(leads):
    DATA_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")

def http_json(url, data=None):
    req = Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=35) as r:
        return json.loads(r.read().decode("utf-8"))

def geocode(city):
    qs = urlencode({"q": f"{city}, Brasil", "format": "jsonv2", "limit": 1, "countrycodes": "br"})
    result = http_json("https://nominatim.openstreetmap.org/search?" + qs)
    if not result:
        return None
    b = result[0]["boundingbox"]
    return float(b[0]), float(b[2]), float(b[1]), float(b[3])

def normalize_segment(segment):
    s = segment.lower().strip()
    aliases = {
        "frutaria": ["greengrocer", "supermarket", "convenience"],
        "frutarias": ["greengrocer", "supermarket", "convenience"],
        "barbearia": ["hairdresser"], "barbearias": ["hairdresser"],
        "restaurante": ["restaurant"], "restaurantes": ["restaurant"],
        "academia": ["fitness_centre"], "academias": ["fitness_centre"],
        "pet shop": ["pet"], "pet shops": ["pet"],
        "clinica": ["clinic", "doctors", "dentist"], "clinicas": ["clinic", "doctors", "dentist"],
        "mecanica": ["car_repair"], "mecanicas": ["car_repair"],
        "oficina": ["car_repair"], "oficinas": ["car_repair"],
        "moveis": ["furniture"], "móveis": ["furniture"],
        "salao": ["hairdresser", "beauty"], "salão": ["hairdresser", "beauty"],
    }
    return aliases.get(s, [re.sub(r"[^a-z0-9_]", "", s)])

def overpass_search(segment, city, quantity):
    bbox = geocode(city)
    if not bbox:
        return []
    south, west, north, east = bbox
    values = normalize_segment(segment)
    parts = []
    for v in values:
        parts += [
            f'nwr["shop"="{v}"]({south},{west},{north},{east});',
            f'nwr["amenity"="{v}"]({south},{west},{north},{east});',
            f'nwr["leisure"="{v}"]({south},{west},{north},{east});',
            f'nwr["craft"="{v}"]({south},{west},{north},{east});'
        ]
    q = '[out:json][timeout:25];(' + ''.join(parts) + ');out center tags;'
    payload = urlencode({"data": q}).encode()
    data = http_json("https://overpass-api.de/api/interpreter", payload)
    rows = []
    for el in data.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name")
        if not name:
            continue
        phone = t.get("contact:phone") or t.get("phone") or t.get("contact:mobile") or ""
        whatsapp = t.get("contact:whatsapp") or t.get("whatsapp") or ""
        website = t.get("contact:website") or t.get("website") or ""
        instagram = t.get("contact:instagram") or t.get("instagram") or ""
        street = t.get("addr:street", "")
        number = t.get("addr:housenumber", "")
        rows.append({"name": name, "phone": phone, "whatsapp": whatsapp, "website": website,
                     "instagram": instagram, "address": (street + " " + number).strip(),
                     "osm_id": f'{el.get("type")}:{el.get("id")}'})
    seen = set()
    unique = []
    for r in rows:
        k = r["osm_id"]
        if k not in seen:
            seen.add(k); unique.append(r)
    return unique[:quantity]

def offer_for(segment):
    s = segment.lower()
    if "frut" in s:
        return "catálogo digital, pedidos pelo WhatsApp e promoções semanais"
    if "barb" in s or "sala" in s or "beleza" in s:
        return "agendamento online, catálogo de serviços e conteúdo para redes sociais"
    if "rest" in s or "lanch" in s:
        return "cardápio/pedidos digitais, campanhas e fidelização de clientes"
    if "mecan" in s or "oficina" in s or "auto" in s:
        return "orçamento digital, organização de clientes e lembretes automáticos"
    if "clinic" in s or "dent" in s:
        return "agendamento, lembretes e presença digital profissional"
    if "academ" in s:
        return "captação de alunos, página de planos e automação de atendimento"
    if "pet" in s:
        return "agendamento, catálogo e campanhas para clientes recorrentes"
    return "site, automação de atendimento, conteúdo digital e soluções personalizadas"

def personalized_message(name, segment, city):
    return (f"Olá! Tudo bem? Encontrei a {name} pesquisando empresas de {city}. "
            f"Trabalho com soluções digitais para negócios do ramo de {segment}, como {offer_for(segment)}.\n\n"
            "🎁 Para novos clientes: 50% de desconto no primeiro serviço e nenhum pagamento antecipado. "
            "Primeiro desenvolvemos e entregamos o serviço combinado; o pagamento é feito depois da entrega conforme o acordado.\n\n"
            "Posso fazer uma análise inicial do negócio e mostrar uma ideia prática, sem compromisso?")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 META 20K PROSPECTADOR\n\n" f"Meta diária: {DAILY_GOAL} novos leads\n\n"
        "Comandos:\n/buscar <segmento> <cidade> <quantidade>\n/meta\n/status\n/leads\n\n"
        "Exemplo:\n/buscar frutarias Porto Velho 40")

async def meta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🎯 Meta diária atual: {DAILY_GOAL} leads.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leads = load_leads(); today = datetime.now().strftime("%Y-%m-%d")
    today_leads = [x for x in leads if x.get("date") == today]
    await update.message.reply_text(f"📊 META 20K — STATUS\n\nMeta: {DAILY_GOAL}\nLeads registrados hoje: {len(today_leads)}\nTotal no CRM: {len(leads)}")

async def leads_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leads = load_leads()
    if not leads:
        await update.message.reply_text("Nenhum lead registrado ainda."); return
    last = leads[-10:]
    text = "📋 ÚLTIMOS LEADS\n\n" + "\n".join(f"• {x.get('name')} — {x.get('status','Novo contato')}" for x in last)
    await update.message.reply_text(text[:4000])

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Use: /buscar <segmento> <cidade> <quantidade>\nEx.: /buscar frutarias Porto Velho 40"); return
    try:
        quantity = min(max(int(context.args[-1]), 1), 40)
    except ValueError:
        await update.message.reply_text("A quantidade precisa ser um número de 1 a 40."); return
    # Para cidades com duas palavras, o segmento é o primeiro argumento neste MVP.
    segment = context.args[0]
    city = " ".join(context.args[1:-1])
    await update.message.reply_text(f"🔎 Procurando até {quantity} negócios de {segment} em {city}...")
    try:
        found = await asyncio.to_thread(overpass_search, segment, city, quantity * 2)
    except Exception as e:
        await update.message.reply_text(f"⚠️ A fonte pública não respondeu agora. Tente novamente em alguns minutos.\nErro: {type(e).__name__}"); return
    leads = load_leads(); known = {x.get("osm_id") for x in leads}
    fresh = [x for x in found if x.get("osm_id") not in known][:quantity]
    if not fresh:
        await update.message.reply_text("Não encontrei novos estabelecimentos com dados públicos para esse segmento/cidade. Tente outro segmento."); return
    today = datetime.now().strftime("%Y-%m-%d")
    for x in fresh:
        x.update({"segment": segment, "city": city, "date": today, "status": "Novo contato",
                  "message": personalized_message(x["name"], segment, city), "source": "OpenStreetMap"})
    leads.extend(fresh); save_leads(leads)
    await update.message.reply_text(f"✅ {len(fresh)} novos leads encontrados e salvos no CRM.\nFonte: OpenStreetMap (ODbL).\nVou enviar os resultados abaixo.")
    for i, x in enumerate(fresh, 1):
        contact = x.get("whatsapp") or x.get("phone") or "não informado"
        txt = (f"{i}. 🏢 {x['name']}\n📞 {contact}\n🌐 {x.get('website') or x.get('instagram') or 'não informado'}\n\n"
               f"💬 MENSAGEM PERSONALIZADA:\n{x['message']}")
        await update.message.reply_text(txt[:4000])


def main():
    if not TOKEN: raise RuntimeError("Configure TELEGRAM_BOT_TOKEN como variável de ambiente.")
    app = Application.builder().token(TOKEN).build()
    for cmd, fn in [("start",start),("buscar",buscar),("meta",meta),("status",status),("leads",leads_cmd)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.run_polling()

if __name__ == "__main__": main()
