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
# 1. CONFIGURAÇÕES INICIAIS E CREDENCIAIS
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

FILA_CONSULTAS_MERCADO = []
RESPOSTAS_MERCADO = {}

def consultar_planilha_financeira(tipo_controle: str, dono_carteira: str = "elias") -> str:
    """Abre a planilha e entrega um relatório ultra-estruturado para o Jarvis analisar."""
    tipo = tipo_controle.lower().strip()
    dono = dono_carteira.lower().strip() if dono_carteira else "elias"
    
    if "emprestimo" in tipo:
        chave = f"emprestimo_{dono}"
    elif tipo in ["vendas", "venda", "eletronicos", "eletronico"]:
        chave = f"vendas_{dono}"
    elif "vencimento" in tipo:
        chave = "vencimentos"
    else:
        chave = "gastos"

    MAPA_LINKS = {
        "emprestimo_elias": "https://docs.google.com/spreadsheets/d/1-z9cqkxoputvPmHcKFQ6guzPNKj-pQuFjbGfPaCdKrA/edit",
        "emprestimo_erick": "https://docs.google.com/spreadsheets/d/158YuDkd6u_psGO9Ciaih1qULfYaddeuz6XPagMV0hgM/edit",
        "emprestimo_ikaro": "https://docs.google.com/spreadsheets/d/13WRI1nKHln3-a441tF-q6p8YzENm9MU6ebzqqEem7l4/edit",
        "vendas_elias": "https://docs.google.com/spreadsheets/d/1E2gvWM1Rjrivqsrfa2AktMi1ffIZfhTJSSYzBSqmqUw/edit",
        "vendas_erick": "https://docs.google.com/spreadsheets/d/16qaj4BSML2aDbTjUDbz0y0MqmivIRNqHl0NI5F-6iJw/edit",
        "vendas_ikaro": "https://docs.google.com/spreadsheets/d/1OykNzzckXjYrIxWzwsvBJCajjQIpH1E9g1WzYQG08t0/edit",
        "vencimentos": "https://docs.google.com/spreadsheets/d/1Tgt2UXDtFh6KewMrcndVHlh3nYVcd67exvlkuth1QYw/edit",
        "gastos": "https://docs.google.com/spreadsheets/d/1du4JGSwpAgNU0FfpxzNrYOlNUlhIkOPTNunhnhoiwD4/edit"
    }
    
    url = MAPA_LINKS.get(chave)
    if not url:
        return "Erro: Tabela não encontrada ou não mapeada."

    print(f"🔄 [AÇÃO DO JARVIS] Processando relatório da planilha ({chave})...")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not google_creds_json: 
            return "Erro: GOOGLE_CREDS_JSON não configurado."
            
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        planilha = client.open_by_url(url)
        aba = planilha.get_worksheet(0)
        valores = aba.get_all_values()
        
        if not valores:
            return f"A planilha da carteira de {dono} está vazia."

        # Se for planilha de CLIENTE / VENDAS / EMPRÉSTIMOS (Baseado na estrutura da linha 5 e parcelas)
        # Coluna A: Qtd Parcelas (a partir da linha 9) | Coluna B: Vencimento | Coluna C: Valor | Coluna E: Pago (Sim/Não)
        relatorio = [f"📊 RELATÓRIO ESTRUTURADO - CARTEIRA: {dono.upper()} ({tipo.upper()})"]
        relatorio.append(f"Nome da Planilha: {planilha.title} | Aba: {aba.title}")
        relatorio.append("="*50)

        # Captura metadados das primeiras linhas (ex: Nome do Cliente nas linhas de cima se houver)
        for i in range(min(8, len(valores))):
            linha_texto = " | ".join([str(c).strip() for c in valores[i] if c])
            if linha_texto:
                relatorio.append(f"Info Topo [Linha {i+1}]: {linha_texto}")
        
        relatorio.append("\n📌 DETALHAMENTO DE LANÇAMENTOS/PARCELAS (Linha 9 em diante):")
        
        # Processa o miolo financeiro (Linha 9 em diante)
        total_pago = 0.0
        total_pendente = 0.0
        
        for idx, linha in enumerate(valores[8:]): # Linha 9 é índice 8
            if len(linha) < 3: continue
            
            parcela = str(linha[0]).strip()   # Coluna A
            vencimento = str(linha[1]).strip() # Coluna B
            valor_raw = str(linha[2]).strip()  # Coluna C
            status = str(linha[4]).strip().lower() if len(linha) > 4 else "" # Coluna E
            
            # Pula linhas vazias
            if not parcela and not vencimento and not valor_raw:
                continue
                
            # Tenta tratar o valor numérico para somatórios futuros
            try:
                val_limpo = valor_raw.replace("R$", "").replace(".", "").replace(",", ".").strip()
                valor_float = float(val_limpo) if val_limpo else 0.0
            except:
                valor_float = 0.0

            if status in ["sim", "pago", "s"]:
                total_pago += valor_float
                status_sel = "✅ PAGO"
            else:
                total_pendente += valor_float
                status_sel = "⏳ PENDENTE"

            relatorio.append(f"  • Parc: {parcela} | Venc: {vencimento} | Valor: {valor_raw} | Status: {status_sel}")

        relatorio.append("="*50)
        relatorio.append(f"📉 Resumo Financeiro Calculado:")
        relatorio.append(f"   - Total Pago Cadastrado: R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        relatorio.append(f"   - Total Pendente/Aberto: R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
        return "\n".join(relatorio)

    except Exception as e:
        return f"Erro ao processar e organizar dados do Google Sheets: {str(e)}"

def executar_query_mercado_realtime(sql_comando: str) -> str:
    """Envia uma query SQL direto para o LIONSTESTE.exe no servidor do mercado."""
    global FILA_CONSULTAS_MERCADO, RESPOSTAS_MERCADO
    id_requisicao = str(uuid.uuid4())[:8]
    
    ordem = {"id": id_requisicao, "sql": sql_comando}
    FILA_CONSULTAS_MERCADO.append(ordem)
    print(f"📡 [PONTE MERCADO] Query enviada para a fila. ID: {id_requisicao}")
    
    for _ in range(40): # Até 20 segundos de espera
        time.sleep(0.5)
        if id_requisicao in RESPOSTAS_MERCADO:
            return json.dumps(RESPOSTAS_MERCADO.pop(id_requisicao), ensure_ascii=False)
            
    return json.dumps([{"erro": "O servidor local do mercado demorou para responder. Verifique o LIONSTESTE.exe."}])

# =====================================================================
# 🧠 CONFIGURAÇÃO DO MODELO CENTRAL (JARVIS)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[consultar_planilha_financeira, executar_query_mercado_realtime],
    system_instruction=(
        f"Você é o JARVIS, a inteligência de altíssima performance estratégica do empresário Elias Fernandes Borges Junior.\n"
        f"DATA ATUAL DE REFERÊNCIA: Hoje é {datetime.now().strftime('%A, %d de %B de %Y')}.\n\n"
        "Sua principal habilidade é a AUDITORIA DE CRÉDITO. Quando o Elias pedir para olhar uma planilha ou consultar dados de vendas/empréstimos "
        "(seja dele, do Erick ou do Ikaro), você deve chamar a ferramenta 'consultar_planilha_financeira'.\n\n"
        "Como a ferramenta já te entrega os dados calculados de parcelas (Vencimento, Valor e Status '✅ PAGO' ou '⏳ PENDENTE'), sua tarefa é:\n"
        "1. Cruzar as datas das parcelas '⏳ PENDENTE' com o dia de hoje para descobrir o que está EM ATRASO.\n"
        "2. Apresentar um painel executivo direto, limpo, usando negritos e emojis.\n"
        "3. Se ele pedir para cruzar dados (ex: comparar as vendas dele com as do Erick), chame a ferramenta para a planilha do Elias, guarde o resultado, chame para a do Erick e faça o cruzamento matemático na sua resposta final.\n\n"
        "Se o assunto for o faturamento ou estoque do Supermercado Lions, use o dialeto Firebird SQL e a ferramenta 'executar_query_mercado_realtime'."
    )
)

chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)

# =====================================================================
# 🌐 ENDPOINTS HTTP (PONTE COM O SEU EXECUTÁVEL DO MERCADO)
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

# =====================================================================
# 💬 ENTRADA DE MENSAGENS TELEGRAM
# =====================================================================
@bot.message_handler(func=lambda message: True)
def receber_mensagem_telegram(message):
    global chat_ia
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        resposta_ia = chat_ia.send_message(message.text)
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        print(f"❌ ERRO NO TELEGRAM: {str(e)}")
        bot.send_message(chat_id, f"⚠️ Jarvis indisponível no momento. Detalhe: `{str(e)[:60]}`", parse_mode="Markdown")

def iniciar_servidor_web():
    PORT = int(os.environ.get("PORT", 10000))
    server = socketserver.TCPServer(("", PORT), ServidorCentralAPI)
    print(f"🌐 Servidor API do Jarvis ativo na porta {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    # O MOTOR DE LOOP INFINITO FOI REMOVIDO DAQUI TOTALMENTE.
    # Agora o sistema economiza 100% de cota quando você não está usando.
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    print("🧠 Jarvis pronto para operar sob demanda e sem estourar limites!")
    bot.infinity_polling()
