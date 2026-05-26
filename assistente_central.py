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

# Filas de sincronização em tempo real com o motor local do mercado (LIONS)
FILA_CONSULTAS_MERCADO = []
RESPOSTAS_MERCADO = {}

# =====================================================================
# 🎯 FERRAMENTA 1: AUDITORIA DE PLANILHAS GOOGLE (SOB DEMANDA)
# =====================================================================
def consultar_planilha_financeira(tipo_controle: str, dono_carteira: str = "elias") -> str:
    """Busca os dados EM TEMPO REAL e estruturados de uma planilha específica apenas quando necessário."""
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
        return f"Erro: Tabela '{chave}' não encontrada ou não mapeada."

    print(f"🔄 [AÇÃO DO JARVIS] Abrindo e estruturando planilha ({chave}) em tempo real...")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not google_creds_json: 
            return "Erro: Credenciais do Google (GOOGLE_CREDS_JSON) ausentes no servidor."
            
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        planilha = client.open_by_url(url)
        aba = planilha.get_worksheet(0)
        valores = aba.get_all_values()
        
        if not valores:
            return f"A planilha {planilha.title} está completamente vazia."

        # Montagem do Relatório Estruturado para a IA
        relatorio = [f"📊 RELATÓRIO FINANCEIRO DE CONTROLE - CARTEIRA: {dono.upper()}"]
        relatorio.append(f"Planilha: {planilha.title} | Aba ativa: {aba.title}")
        relatorio.append("="*60)

        # Captura metadados iniciais (linhas 1 a 8)
        for i in range(min(8, len(valores))):
            linha_limpa = [str(c).strip() for c in valores[i] if c]
            if linha_limpa:
                relatorio.append(f"Cabeçalho L{i+1}: " + " | ".join(linha_limpa))
        
        relatorio.append("\n📌 LANÇAMENTOS E MOVIMENTAÇÕES CRUCIAIS (Linha 9 em diante):")
        
        # Processa o miolo (Linha 9 em diante)
        for idx, linha in enumerate(valores[8:]):
            if len(linha) < 3: 
                continue
            cols = [str(c).strip() for c in linha[:6] if c]
            if cols:
                relatorio.append(f"  • Item {idx+1}: " + " | ".join(cols))
                
        relatorio.append("="*60)
        return "\n".join(relatorio)
        
    except Exception as e:
        return f"Erro na leitura do Google Sheets: {str(e)}"

# =====================================================================
# 🎯 FERRAMENTA 2: EXECUÇÃO DE QUERIES NO MERCADO LIONS
# =====================================================================
def executar_query_mercado_realtime(sql_comando: str) -> str:
    """Envia o comando SQL direto para a fila do mercado local e aguarda o retorno."""
    global FILA_CONSULTAS_MERCADO, RESPOSTAS_MERCADO
    id_requisicao = str(uuid.uuid4())[:8]
    
    ordem = {"id": id_requisicao, "sql": sql_comando}
    FILA_CONSULTAS_MERCADO.append(ordem)
    print(f"📡 [PONTE MERCADO] Nova consulta na fila. ID: {id_requisicao} | SQL: {sql_comando}")
    
    # Aguarda o retorno do LIONSTESTE.exe (Timeout seguro de 20 segundos)
    for _ in range(40):
        time.sleep(0.5)
        if id_requisicao in RESPOSTAS_MERCADO:
            dados_originais = RESPOSTAS_MERCADO.pop(id_requisicao)
            return json.dumps(dados_originais, ensure_ascii=False)
            
    return json.dumps([{"erro": "Timeout: O servidor local do mercado (LIONSTESTE.exe) demorou para responder. Certifique-se de que ele está aberto no terminal do mercado."}])

# =====================================================================
# 🧠 CÉREBRO INTEGRADO DO JARVIS (MAPEAMENTO COMPLETO FIREBIRD LIONS)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[consultar_planilha_financeira, executar_query_mercado_realtime],
    system_instruction=(
        f"Você é o JARVIS, o copiloto de inteligência analítica e estratégica do empresário Elias Fernandes Borges Junior.\n"
        f"DATA ATUAL DE REFERÊNCIA: Hoje é {datetime.now().strftime('%A, %d de %B de %Y')}.\n\n"
        
        "🔥 DIRETRIZES DE ENGENHARIA DE BANCO DE DADOS (SUPERMERCADO LIONS):\n"
        "Quando o Elias solicitar dados de faturamento, vendas, estoque ou despesas do mercado, você DEVE gerar um SQL puro no dialeto Firebird e usar a ferramenta 'executar_query_mercado_realtime'.\n"
        "⚠️ ATENÇÃO CRÍTICA: Você NUNCA vai criar tabelas fictícias (como VW_VENDAS). Baseie-se unicamente nas estruturas reais mapeadas abaixo:\n\n"
        
        "1. FATURAMENTO E VENDAS EM GERAL (`VENDAS_MASTER`):\n"
        "   - Use sempre o filtro de cancelados: SITUACAO <> 'C'\n"
        "   - Converta sempre o campo de data usando CAST: CAST(DATA_EMISSAO AS DATE)\n"
        "   - Exemplo de faturamento de HOJE: SELECT SUM(TOTAL) FROM VENDAS_MASTER WHERE CAST(DATA_EMISSAO AS DATE) = CURRENT_DATE AND SITUACAO <> 'C'\n"
        "   - Exemplo de faturamento do MÊS ATUAL: SELECT SUM(TOTAL) FROM VENDAS_MASTER WHERE EXTRACT(MONTH FROM DATA_EMISSAO) = EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM DATA_EMISSAO) = EXTRACT(YEAR FROM CURRENT_DATE) AND SITUACAO <> 'C'\n\n"
        
        "2. ANÁLISE DE MARGENS E CMV (`VENDAS_DETALHE` unida com `PRODUTO`):\n"
        "   - Use VENDAS_DETALHE para apurar custos e quantidades de itens vendidos.\n"
        "   - Colunas: FKVENDA, ID_PRODUTO, QTD, TOTAL, PR_CUSTO\n\n"
        
        "3. AUDITORIA DE ESTOQUE E PREÇOS (`PRODUTO`):\n"
        "   - Filtre por itens ativos: ATIVO = 'S'\n"
        "   - Colunas importantes: CODIGO, DESCRICAO, QTD_ATUAL, PR_CUSTO, PR_CUSTO_ANTERIOR, PR_VENDA, ULT_COMPRA, DT_VALIDADE, CAST(DT_ULT_VENDA AS DATE)\n"
        "   - Exemplo para ruptura (estoque zerado): SELECT CODIGO, DESCRICAO FROM PRODUTO WHERE ATIVO = 'S' AND QTD_ATUAL <= 0\n\n"
        
        "4. GESTÃO FINANCEIRA E DESPESAS OPERACIONAIS (`CPAGAR`):\n"
        "   - Para saber se uma conta está paga, avalie: VLPAGO > 0 OR SITUACAO = 'P'\n"
        "   - Para buscar despesas específicas, use LIKE no campo HISTORICO (ex: HISTORICO LIKE '%AGUA%')\n"
        "   - Colunas: CODIGO, HISTORICO, VALOR, DTVENCIMENTO, SITUACAO, VLPAGO\n\n"
        
        "📊 DIRETRIZES PARA AUDITORIA DE CRÉDITO (PLANILHAS GOOGLE):\n"
        "Quando o assunto envolver controle de parcelas, empréstimos ou gastos de carteiras específicas (Elias, Erick ou Ikaro), invoque 'consultar_planilha_financeira' com o tipo e dono corretos.\n"
        "Analise a lista recebida, verifique as datas de vencimento em aberto, compare com a data atual e apresente os atrasos e consolidações matematicamente para o Elias de forma executiva."
    )
)

chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)

# =====================================================================
# 🌐 ENDPOINTS HTTP: A PONTE DE CONEXÃO COM O MERCADO LOCAL
# =====================================================================
class ServidorCentralAPI(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global FILA_CONSULTAS_MERCADO
        # O LIONSTESTE.exe bate aqui buscando ordens SQL pendentes
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
        # O LIONSTESTE.exe bate aqui devolvendo o resultado bruto do banco Firebird
        if self.path == '/api/mercado/resposta':
            content_length = int(self.headers['Content-Length'])
            dados_recebidos = json.loads(self.rfile.read(content_length).decode('utf-8'))
            
            id_requisicao = dados_recebidos.get("id")
            resultado_sql = dados_recebidos.get("dados")
            
            RESPOSTAS_MERCADO[id_requisicao] = resultado_sql
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "recebido"}).encode('utf-8'))

# =====================================================================
# 💬 CAPTURA E RESPOSTA DO TELEGRAM
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
        print(f"❌ ERRO OPERACIONAL TELEGRAM: {str(e)}")
        # Tratamento seguro caso a formatação de Markdown do Gemini venha com alguma string quebrada
        try:
            bot.send_message(chat_id, resposta_ia.text)
        except:
            bot.send_message(chat_id, f"⚠️ Jarvis temporariamente indisponível. Log técnico: `{str(e)[:50]}`", parse_mode="Markdown")

# =====================================================================
# 🏁 INICIALIZAÇÃO DOS MOTORES CENTRALIZADOS
# =====================================================================
def iniciar_servidor_web():
    PORT = int(os.environ.get("PORT", 10000))
    server = socketserver.TCPServer(("", PORT), ServidorCentralAPI)
    print(f"🌐 Servidor API do Jarvis rodando com sucesso na porta {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    # Inicia apenas a ponte HTTP e o Pooling do Telegram. Cota de API 100% protegida.
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    print("🧠 Ecossistema Multi-Agente com Inteligência Firebird Operando com Sucesso!")
    bot.infinity_polling()
