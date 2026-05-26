import os
import telebot
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import threading
import http.server
import socketserver
import time
import uuid
from datetime import datetime

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS & CHAVES
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MEU_TELEGRAM_CHAT_ID = os.environ.get("MEU_CHAT_ID") 

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

FILA_CONSULTAS_MERCADO = []
RESPOSTAS_MERCADO = {}

# Motor Inteligente do Jarvis (Utilizando o modelo flash para velocidade e economia)
modelo_jarvis = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    system_instruction=(
        "Você é o Jarvis, o assistente pessoal e secretário estratégico de altíssimo nível do empresário Elias. "
        "Você analisa dados do Supermercado Lions (Mercadomix) e das carteiras de cobrança das planilhas. "
        "Seja direto, inteligente, use termos de negócios (CMV, Lucro, Margem) e formate suas respostas com negritos e emojis."
    )
)

# Cache local para o Jarvis interativo saber o status sem rodar queries demoradas
CACHE_ULTIMO_STATUS = {"dados": "Nenhum dado coletado ainda.", "atualizado_em": "-"}

# =====================================================================
# 📊 COLETORES MATEMÁTICOS DE SUCESSO (100% GRATUITOS VIA PYTHON)
# =====================================================================
def puxar_resumo_planilhas_puro():
    """Varre as planilhas financeiras e traz os consolidados matemáticos."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not google_creds_json: return "Credenciais do Google Sheets não configuradas."
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(google_creds_json), scope)
        client = gspread.authorize(creds)
        
        MAPA = {
            "Erick Vendas": "https://docs.google.com/spreadsheets/d/16qaj4BSML2aDbTjUDbz0y0MqmivIRNqHl0NI5F-6iJw/edit",
            "Ikaro Vendas": "https://docs.google.com/spreadsheets/d/1OykNzzckXjYrIxWzwsvBJCajjQIpH1E9g1WzYQG08t0/edit",
            "Erick Empréstimos": "https://docs.google.com/spreadsheets/d/158YuDkd6u_psGO9Ciaih1qULfYaddeuz6XPagMV0hgM/edit"
        }
        
        resumo_texto = []
        for nome, url in MAPA.items():
            try:
                plan = client.open_by_url(url).get_worksheet(0).get_all_values()
                linhas_ativas = len([l for l in plan[8:] if any(l)]) if len(plan) > 8 else 0
                resumo_texto.append(f"- {nome}: {linhas_ativas} registros ativos em monitoramento.")
            except:
                resumo_texto.append(f"- {nome}: Planilha temporariamente inacessível.")
        return "\n".join(resumo_texto)
    except Exception as e:
        return f"Erro nas Planilhas: {e}"

def executar_query_mercado_interna(sql_comando: str) -> list:
    """Envia a query para a ponte local do mercado executar."""
    global FILA_CONSULTAS_MERCADO, RESPOSTAS_MERCADO
    id_req = str(uuid.uuid4())[:8]
    FILA_CONSULTAS_MERCADO.append({"id": id_req, "sql": sql_comando})
    
    for _ in range(30): 
        time.sleep(0.5)
        if id_req in RESPOSTAS_MERCADO:
            return RESPOSTAS_MERCADO.pop(id_req)
    return [{"erro": "offline"}]

# =====================================================================
# 🕒 MOTOR 1: ROTINA AUTOMÁTICA DE AUDITORIA (A CADA 30 MINUTOS)
# =====================================================================
def rotina_secretaria_30min():
    global CACHE_ULTIMO_STATUS
    print("⏳ Motor Proativo do Jarvis Inicializado...")
    time.sleep(10) # Espera rápida para o boot
    
    while True:
        try:
            print("🔔 Executando cruzamento estratégico de rotina...")
            
            # 1. Busca Faturamento Real-time
            sql_fat = "SELECT SUM(TOTAL) as FAT_HOJE FROM VENDAS_MASTER WHERE CAST(DATA_EMISSAO AS DATE) = CURRENT_DATE AND SITUACAO <> 'C'"
            res_fat = executar_query_mercado_interna(sql_fat)
            fat_hoje = res_fat[0].get("FAT_HOJE", 0.0) if res_fat and "erro" not in res_fat[0] else 0.0
            
            # 2. Busca Contas a Pagar do Dia
            sql_pagar = "SELECT SUM(VALOR) as PAGAR_HOJE FROM CPAGAR WHERE DTVENCIMENTO = CURRENT_DATE AND (SITUACAO = 'A' OR VLPAGO <= 0)"
            res_pag = executar_query_mercado_interna(sql_pagar)
            pagar_hoje = res_pag[0].get("PAGAR_HOJE", 0.0) if res_pag and "erro" not in res_pag[0] else 0.0
            
            # 3. Busca resumo das planilhas
            resumo_plan = puxar_resumo_planilhas_puro()
            
            # Monta o bloco de texto consolidado
            contexto_atual = (
                f"Faturamento do Mercado Hoje: R$ {fat_hoje:,.2f}\n"
                f"Contas do Mercado Vencendo Hoje: R$ {pagar_hoje:,.2f}\n"
                f"Status das Carteiras Externas:\n{resumo_plan}"
            )
            
            # Atualiza o cache global para o modo interativo usar
            CACHE_ULTIMO_STATUS["dados"] = contexto_atual
            CACHE_ULTIMO_STATUS["atualizado_em"] = datetime.now().strftime("%H:%M")
            
            # Dispara o Briefing Proativo para seu Telegram
            if MEU_TELEGRAM_CHAT_ID:
                prompt_briefing = (
                    f"Apresente um resumo executivo ultra-direto dos negócios para o Elias com base nestes dados de agora:\n\n{contexto_atual}\n\n"
                    f"Cruze as informações, indique a saúde do caixa hoje e sugira as prioridades administrativas de forma assertiva."
                )
                resposta = modelo_jarvis.generate_content(prompt_briefing)
                bot.send_message(MEU_TELEGRAM_CHAT_ID, f"💼 **[AUDITORIA 30 MIN]**\n\n{resposta.text}", parse_mode="Markdown")
                
        except Exception as e:
            print(f"⚠️ Erro na rotina proativa: {e}")
            
        time.sleep(1800) # Aguarda 30 minutos

# =====================================================================
# 💬 MOTOR 2: INTERAÇÃO LIVRE E STATELESS (CONSUMO ZERO DE ACÚMULO)
# =====================================================================
@bot.message_handler(func=lambda message: True)
def responder_chat_livre(message):
    # Trava de segurança para responder apenas a você
    if MEU_TELEGRAM_CHAT_ID and str(message.chat.id) != str(MEU_TELEGRAM_CHAT_ID):
        return

    bot.send_chat_action(message.chat.id, 'typing')
    
    # Injeta os últimos dados reais como contexto de fundo da pergunta
    prompt_completo = (
        f"CONTEXTO DO NEGÓCIO ATUALIZADO ({CACHE_ULTIMO_STATUS['atualizado_em']}):\n"
        f"{CACHE_ULTIMO_STATUS['dados']}\n\n"
        f"PERGUNTA DO ELIAS: {message.text}\n\n"
        f"Instrução: Responda à pergunta usando o contexto acima se aplicável. "
        f"Se ele pedir dados que não estão no contexto, informe o que você tem disponível ou sugira que ele aguarde a próxima sincronização."
    )
    
    try:
        # Executa de forma isolada (Não guarda histórico na API = Cota protegida!)
        resposta = modelo_jarvis.generate_content(prompt_completo)
        bot.reply_to(message, resposta.text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao processar comando com a IA: {e}")

# =====================================================================
# 🌐 ENDPOINTS DE CONEXÃO COM A PONTE LOCAL
# =====================================================================
class ServidorCentralAPI(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global FILA_CONSULTAS_MERCADO
        if self.path == '/api/mercado/pendente':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if FILA_CONSULTAS_MERCADO:
                self.wfile.write(json.dumps(FILA_CONSULTAS_MERCADO.pop(0)).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"status": "nada_pendente"}).encode('utf-8'))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Jarvis Central Online")

    def do_POST(self):
        global RESPOSTAS_MERCADO
        if self.path == '/api/mercado/resposta':
            content_length = int(self.headers['Content-Length'])
            dados_recebidos = json.loads(self.rfile.read(content_length).decode('utf-8'))
            RESPOSTAS_MERCADO[dados_recebidos.get("id")] = dados_recebidos.get("dados")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "recebido"}).encode('utf-8'))

def iniciar_servidor_web():
    PORT = int(os.environ.get("PORT", 10000))
    server = socketserver.TCPServer(("", PORT), ServidorCentralAPI)
    server.serve_forever()

if __name__ == "__main__":
    # Inicializa as duas frentes em paralelo
    threading.Thread(target=rotina_secretaria_30min, daemon=True).start()
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    
    print("🚀 JARVIS HÍBRIDO ATIVADO: RELATÓRIOS PROATIVOS + CHAT LIVRE PROTEGIDO!")
    bot.infinity_polling()
