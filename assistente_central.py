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
# 1. CONFIGURAÇÕES INICIAIS E CRIDENCIAIS
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

# Filas de sincronização em tempo real para a ponte com o mercado local (.exe)
FILA_CONSULTAS_MERCADO = []
RESPOSTAS_MERCADO = {}

# =====================================================================
# 🎯 IMPLEMENTAÇÃO DO ITEM 4: BANCO DE CACHE LOCAL (MEMÓRIA RAM)
# =====================================================================
DADOS_PLANILHAS_LOCAL = {
    "emprestimo_elias": "Sem dados carregados.",
    "emprestimo_erick": "Sem dados carregados.",
    "emprestimo_ikaro": "Sem dados carregados.",
    "vendas_elias": "Sem dados carregados.",
    "vendas_erick": "Sem dados carregados.",
    "vendas_ikaro": "Sem dados carregados.",
    "vencimentos": "Sem dados carregados.",
    "gastos": "Sem dados carregados."
}

def atualizar_dados_sheets_agora():
    """Atualiza o cache da RAM apenas quando solicitado, economizando cota."""
    global DADOS_PLANILHAS_LOCAL
    print("🔄 [JARVIS ENGINE] Atualizando tabelas do Google Sheets via comando...")
    
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
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not google_creds_json: return "Erro: Sem credenciais do Google no servidor."
            
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        for chave, url in MAPA_LINKS.items():
            try:
                planilha = client.open_by_url(url)
                aba = planilha.get_worksheet(0)
                valores = aba.get_all_values()
                
                if valores:
                    lines = [f"Linha {i+1}: " + " | ".join([str(c) for c in r]) for i, r in enumerate(valores[:100])]
                    DADOS_PLANILHAS_LOCAL[chave] = f"Planilha: [{planilha.title}] -> Aba: [{aba.title}]. Dados:\n" + "\n".join(lines)
            except Exception as ie:
                print(f"⚠️ Erro na planilha {chave}: {str(ie)}")
        return "✅ Cache das planilhas atualizado com sucesso!"
    except Exception as e:
        return f"❌ Erro geral: {str(e)}"

# =====================================================================
# 🛠️ FERRAMENTAS DO ECOSSISTEMA (TOOLS DO GEMINI)
# =====================================================================
def consultar_banco_local_jarvis(tipo_controle: str, dono_carteira: str = "elias") -> str:
    """Busca instantaneamente no Cache RAM dados das planilhas de empréstimos, eletrônicos ou gastos."""
    global DADOS_PLANILHAS_LOCAL
    tipo, dono = tipo_controle.lower().strip(), dono_carteira.lower().strip() if dono_carteira else "elias"
    chave = f"emprestimo_{dono}" if "emprestimo" in tipo else (f"vendas_{dono}" if tipo in ["vendas", "venda", "eletronicos", "eletronico"] else ("vencimentos" if "vencimento" in tipo else "gastos"))
    return DADOS_PLANILHAS_LOCAL.get(chave, "Tabela não mapeada no sistema.")

# MELHORIA NA FUNÇÃO DE CONSULTA (Adicionando tratamento de erro robusto)
def executar_query_mercado_realtime(sql_comando: str) -> str:
    global FILA_CONSULTAS_MERCADO, RESPOSTAS_MERCADO
    id_requisicao = str(uuid.uuid4())[:8]
    
    ordem = {"id": id_requisicao, "sql": sql_comando}
    FILA_CONSULTAS_MERCADO.append(ordem)
    
    # Aumentado para 40 tentativas (20 segundos) para evitar timeout prematuro
    for _ in range(40):
        time.sleep(0.5)
        if id_requisicao in RESPOSTAS_MERCADO:
            dados = RESPOSTAS_MERCADO.pop(id_requisicao)
            # Retorna string limpa para evitar erro de formatação do Gemini
            return json.dumps(dados, ensure_ascii=False)
            
    return json.dumps({"erro": "Timeout: O LIONS não respondeu a tempo. Verifique a conexão do servidor local."})

@bot.message_handler(commands=['atualizar'])
def comando_atualizar(message):
    bot.reply_to(message, "⏳ Atualizando dados das planilhas na memória do Jarvis... Aguarde.")
    resultado = atualizar_dados_sheets_agora()
    bot.send_message(message.chat.id, resultado)
    
# MELHORIA NO TRATAMENTO DE ERRO DO TELEGRAM (Para ver o erro real)
@bot.message_handler(func=lambda message: True)
def receber_mensagem_telegram(message):
    global chat_ia
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        resposta_ia = chat_ia.send_message(message.text)
        # Força Markdown para evitar erros de caracteres especiais
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        # LOG DE ERRO REAL: Isso vai imprimir no console do Render qual é o problema exato
        print(f"DEBUG DE ERRO: {str(e)}") 
        bot.send_message(chat_id, f"⚠️ Jarvis em manutenção técnica.\nErro interno: `{str(e)[:50]}`", parse_mode="Markdown")

# =====================================================================
# 🧠 ARQUITETURA MULTI-AGENTE DO JARVIS (ITEM 3)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[consultar_banco_local_jarvis, executar_query_mercado_realtime],
    system_instruction=(
        f"Você é o JARVIS, a inteligência de altíssima performance estratégica do empresário Elias Fernandes Borges Junior.\n"
        f"DATA ATUAL DE REFERÊNCIA: Hoje é {datetime.now().strftime('%A, %d de %B de %Y')}.\n\n"
        "Sua estrutura mental divide-se em 4 SUB-AGENTES ESPECIALISTAS trabalhando em paralelo:\n"
        "1. DIÁLOGO LÍDER: Mantém um papo extremamente dinâmico, inteligente, de parceiro de negócios, com gírias de mercado sutis. Formatação limpa e premium.\n"
        "2. AUDITOR DE CRÉDITO: Varre as planilhas financeiras (Elias, Erick, Ikaro). Sabe calcular parcelas em atraso cruzando as datas com o dia de hoje.\n"
        "3. ANALISTA DE VAREJO (LIONS SUPERMERCADO): Especialista no banco Firebird da Lions. Quando o Elias perguntar sobre faturamento, estoque, rupturas, vendas ou boletos do mercado, você DEVE gerar um código SQL válido para o dialeto Firebird e disparar a ferramenta 'executar_query_mercado_realtime'.\n"
        "   - Estruturas de Tabelas conhecidas:\n"
        "     * PRODUTO (CODIGO, DESCRICAO, QTD_ATUAL, PR_CUSTO, PR_VENDA, ATIVO, DT_VALIDADE)\n"
        "     * VENDAS_MASTER (CODIGO, TOTAL, DATA_EMISSAO, SITUACAO ['F'=Fechada, 'C'=Cancelada], FORMA_PAGAMENTO)\n"
        "     * VENDAS_DETALHE (FKVENDA, ID_PRODUTO, QTD, TOTAL, PR_CUSTO)\n"
        "     * CPAGAR (CODIGO, HISTORICO, VALOR, DTVENCIMENTO, SITUACAO ['A'=Aberta, 'P'=Paga])\n\n"
        "DIRETRIZ DE EXIBIÇÃO FINANCEIRA:\n"
        "Sempre agrupe as exibições claramente por Carteira/Operador (Elias, Erick, Ikaro) ou organize os dados do mercado sob o título principal '### 🛒 LIONS SUPERMERCADO'. Nunca misture as informações em textos embolados."
    )
)

chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)

# =====================================================================
# 🌐 ENDPOINTS HTTP (PONTE DE CONEXÃO DO RENDER PARA O MERCADO LOCAL)
# =====================================================================
class ServidorCentralAPI(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global FILA_CONSULTAS_MERCADO
        # Endpoint onde o LIONSTESTE.exe local bate a cada 2 segundos procurando ordens SQL
        if self.path == '/api/mercado/pendente':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if FILA_CONSULTAS_MERCADO:
                ordem = FILA_CONSULTAS_MERCADO.pop(0)
                self.wfile.write(json.dumps(ordem).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"status": "nada_pendente"}).encode('utf-8'))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Jarvis Central Online")

    def do_POST(self):
        global RESPOSTAS_MERCADO
        # Endpoint onde o LIONSTESTE.exe local devolve o JSON de dados puro do Firebird
        if self.path == '/api/mercado/resposta':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            dados_recebidos = json.loads(post_data.decode('utf-8'))
            
            id_requisicao = dados_recebidos.get("id")
            resultado_sql = dados_recebidos.get("dados")
            
            RESPOSTAS_MERCADO[id_requisicao] = resultado_sql
            
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
        try:
            bot.send_message(chat_id, resposta_ia.text)
        except:
            bot.send_message(chat_id, f"⚠️ Jarvis indisponível momentaneamente. Erro de processamento interno.")

# =====================================================================
# 🏁 DISPARO DOS MOTORES GERAIS
# =====================================================================
def iniciar_servidor_web():
    PORT = int(os.environ.get("PORT", 10000))
    server = socketserver.TCPServer(("", PORT), ServidorCentralAPI)
    print(f"🌐 Servidor API do Jarvis rodando com sucesso na porta {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    # APAGUE OU COMENTE A LINHA ABAIXO:
    # threading.Thread(target=motor_sincronizacao_background_sheets, daemon=True).start()
    
    # Mantenha apenas o servidor web e o polling:
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    bot.infinity_polling()
