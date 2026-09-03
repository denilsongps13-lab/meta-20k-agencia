import os
import json
import asyncio
import random
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DAILY_GOAL = int(os.getenv("DAILY_GOAL", "40"))
DATA_FILE = Path("prospectador/leads.json")
USER_AGENT = "Meta20KProspectador/2.0 (business lead discovery)"
SEGMENTS = {
    "Barbearia": ["hairdresser"], "Salão de beleza": ["beauty"],
    "Restaurante": ["restaurant"], "Lanchonete": ["fast_food"],
    "Oficina mecânica": ["car_repair"], "Clínica": ["clinic", "doctors"],
    "Dentista": ["dentist"], "Academia": ["fitness_centre"],
    "Pet shop": ["pet"], "Loja de móveis": ["furniture"],
    "Mercado": ["supermarket", "convenience"], "Climatização": ["hvac"]
}
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
if not DATA_FILE.exists(): DATA_FILE.write_text("[]", encoding="utf-8")

def load_leads():
    try: return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception: return []
def save_leads(x): DATA_FILE.write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding="utf-8")
def http_json(url, data=None):
    req=Request(url,data=data,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
    with urlopen(req,timeout=40) as r: return json.loads(r.read().decode())
def geocode(city):
    q=urlencode({"q":f"{city}, Brasil","format":"jsonv2","limit":1,"countrycodes":"br"})
    r=http_json("https://nominatim.openstreetmap.org/search?"+q)
    if not r:return None
    b=r[0]["boundingbox"]; return float(b[0]),float(b[2]),float(b[1]),float(b[3])
def clean_phone(p):
    n=re.sub(r"\D","",p or "")
    if n.startswith("00"): n=n[2:]
    if n and not n.startswith("55"): n="55"+n
    return n if len(n)>=12 else ""
def offer_for(s):
    x=s.lower()
    if "barb" in x or "beleza" in x:return "agendamento online, catálogo de serviços e conteúdo para redes sociais"
    if "rest" in x or "lanch" in x:return "cardápio digital, pedidos e campanhas de fidelização"
    if "oficina" in x:return "orçamento digital, organização de clientes e lembretes automáticos"
    if "clín" in x or "dent" in x:return "agendamento, lembretes e presença digital profissional"
    if "academ" in x:return "captação de alunos, página de planos e automação de atendimento"
    if "pet" in x:return "agendamento, catálogo e campanhas para clientes recorrentes"
    if "móveis" in x:return "catálogo digital, orçamento pelo WhatsApp e página de produtos"
    if "mercado" in x:return "catálogo digital, promoções e pedidos pelo WhatsApp"
    if "climat" in x:return "orçamento digital, agendamento e automação de atendimento"
    return "site, automação de atendimento e soluções digitais personalizadas"
def message(name,segment,city):
    return (f"Olá! Tudo bem? Encontrei a {name} pesquisando empresas de {city}. "
            f"Trabalho com soluções digitais para negócios como o seu, incluindo {offer_for(segment)}.\n\n"
            "🎁 Para novos clientes: 50% de desconto no primeiro serviço e nenhum pagamento antecipado. "
            "Primeiro desenvolvemos e entregamos o serviço combinado; o pagamento é feito depois da entrega conforme o acordado.\n\n"
            "Posso fazer uma análise inicial do negócio e mostrar uma ideia prática, sem compromisso?")
def search_varied(city):
    bbox=geocode(city)
    if not bbox:return []
    s,w,n,e=bbox; parts=[]; type_map={}
    for label,vals in SEGMENTS.items():
        for v in vals:
            type_map[v]=label
            for key in ("shop","amenity","leisure","craft"):
                parts.append(f'nwr["{key}"="{v}"]({s},{w},{n},{e});')
    q='[out:json][timeout:30];('+''.join(parts)+');out center tags;'
    data=http_json("https://overpass-api.de/api/interpreter",urlencode({"data":q}).encode())
    rows=[]
    for el in data.get("elements",[]):
        t=el.get("tags",{}); name=t.get("name")
        if not name:continue
        raw=t.get("contact:whatsapp") or t.get("whatsapp") or t.get("contact:phone") or t.get("phone") or t.get("contact:mobile") or ""
        phone=clean_phone(raw)
        kind=t.get("shop") or t.get("amenity") or t.get("leisure") or t.get("craft") or ""
        rows.append({"name":name,"phone":phone,"raw_phone":raw,"website":t.get("contact:website") or t.get("website") or t.get("contact:instagram") or "","segment":type_map.get(kind,"Comércio local"),"osm_id":f'{el.get("type")}:{el.get("id")}'})
    random.shuffle(rows)
    # Contatos utilizáveis primeiro e depois alterna ramos.
    rows.sort(key=lambda x: bool(x["phone"]), reverse=True)
    return rows
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🚀 META 20K PROSPECTADOR\n\nMeta diária: {DAILY_GOAL} novos leads\n\nUse:\n/buscar Porto Velho 10\n/buscar Porto Velho 40\n/status\n/leads")
async def meta(update:Update,context:ContextTypes.DEFAULT_TYPE): await update.message.reply_text(f"🎯 Meta diária: {DAILY_GOAL} leads")
async def status(update:Update,context:ContextTypes.DEFAULT_TYPE):
    leads=load_leads(); today=datetime.now().strftime("%Y-%m-%d"); c=sum(x.get("date")==today for x in leads)
    await update.message.reply_text(f"📊 META 20K\nMeta: {DAILY_GOAL}\nLeads hoje: {c}\nFaltam: {max(0,DAILY_GOAL-c)}\nTotal CRM: {len(leads)}")
async def leads_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    leads=load_leads(); txt="📋 ÚLTIMOS LEADS\n\n"+"\n".join(f"• {x['name']} — {x.get('segment','')}" for x in leads[-10:])
    await update.message.reply_text(txt if leads else "Nenhum lead ainda.")
async def buscar(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if len(context.args)<2:
        await update.message.reply_text("Use: /buscar Porto Velho 10 ou /buscar Porto Velho 40");return
    try: qty=min(max(int(context.args[-1]),1),40)
    except ValueError:
        await update.message.reply_text("A quantidade deve ser de 1 a 40.");return
    city=" ".join(context.args[:-1])
    await update.message.reply_text(f"🔎 Buscando {qty} novos clientes variados em {city}...")
    try: found=await asyncio.to_thread(search_varied,city)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Busca indisponível agora ({type(e).__name__}). Tente novamente.");return
    leads=load_leads(); known={x.get("osm_id") for x in leads}; candidates=[x for x in found if x["osm_id"] not in known]
    # Round-robin para variedade de segmentos.
    buckets={}
    for x in candidates:buckets.setdefault(x["segment"],[]).append(x)
    fresh=[]
    while len(fresh)<qty and any(buckets.values()):
        for seg in list(buckets):
            if buckets[seg] and len(fresh)<qty:fresh.append(buckets[seg].pop(0))
    if not fresh:
        await update.message.reply_text("Não encontrei novos negócios ainda. Tente novamente mais tarde.");return
    today=datetime.now().strftime("%Y-%m-%d")
    for x in fresh:
        x.update({"city":city,"date":today,"status":"Novo contato","message":message(x["name"],x["segment"],city),"source":"OpenStreetMap"})
    leads.extend(fresh);save_leads(leads)
    await update.message.reply_text(f"✅ {len(fresh)} novos clientes variados encontrados. Vou mandar um por vez para facilitar o contato.")
    for i,x in enumerate(fresh,1):
        phone=x.get("phone",""); msg=x["message"]
        if phone:
            wa=f"https://wa.me/{phone}?text={quote(msg)}"
            keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("📲 ABRIR WHATSAPP",url=wa)]])
            contact="+"+phone
        else:
            keyboard=None; contact="não informado"
        txt=(f"{i}/{len(fresh)}  🏢 {x['name']}\n🏷️ {x['segment']}\n📞 {contact}\n🌐 {x.get('website') or 'não informado'}\n\n"
             f"📋 MENSAGEM — toque e segure para copiar:\n\n{msg}")
        await update.message.reply_text(txt[:4000],reply_markup=keyboard)
def main():
    if not TOKEN:raise RuntimeError("Configure TELEGRAM_BOT_TOKEN")
    app=Application.builder().token(TOKEN).build()
    for c,f in [("start",start),("buscar",buscar),("meta",meta),("status",status),("leads",leads_cmd)]:app.add_handler(CommandHandler(c,f))
    app.run_polling()
if __name__=="__main__":main()
