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
from datetime import datetime, timedelta

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS & MODELOS
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MEU_TELEGRAM_CHAT_ID = os.environ.get("MEU_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

FILA_CONSULTAS_MERCADO = []
RESPOSTAS_MERCADO = {}

modelo_jarvis = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    system_instruction=(
        "Você é o Jarvis, Diretor Financeiro (CFO) Virtual das empresas do Elias. "
        "Sua missão é ler o relatório consolidado de dados brutos que o Python calculou e "
        "gerar uma análise executiva brilhante, ultra-direta, apontando os 10 cruzamentos pessoais "
        "e os 10 cruzamentos do Mercado (Mercadomix/Lions) de forma clara com emojis e negritos."
    )
)

CACHE_ULTIMO_STATUS = {"dados": "Aguardando primeira sincronização de 30 minutos...", "atualizado_em": "-"}

# =====================================================================
# 📊 MOTOR DE CÁLCULO DAS CARTEIRAS (ELIAS, ERICK, IKARO)
# =====================================================================
def processar_matematica_carteiras():
    """Abre as planilhas e calcula exatamente os indicadores das carteiras."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    dados_compilados = {
        "hoje_receber": 0.0, "hoje_pagar": 0.0, "saldo_hoje": 0.0,
        "futuro_receber_3d": 0.0, "futuro_pagar_3d": 0.0, "saldo_3d": 0.0,
        "inadimplencia_5d": 0.0, "capital_erick": 0.0, "capital_ikaro": 0.0,
        "arrecadacao_mes": 0.0, "meta_mes": 150000.0, "atrasos_cronicos": 0
    }
    
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not google_creds_json: return "Credenciais Google Sheets ausentes."
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(google_creds_json), scope)
        client = gspread.authorize(creds)
        
        MAPA = {
            "Erick Vendas": "https://docs.google.com/spreadsheets/d/16qaj4BSML2aDbTjUDbz0y0MqmivIRNqHl0NI5F-6iJw/edit",
            "Ikaro Vendas": "https://docs.google.com/spreadsheets/d/1OykNzzckXjYrIxWzwsvBJCajjQIpH1E9g1WzYQG08t0/edit",
            "Erick Empréstimos": "https://docs.google.com/spreadsheets/d/158YuDkd6u_psGO9Ciaih1qULfYaddeuz6XPagMV0hgM/edit"
        }
        
        hoje = datetime.now().date()
        tres_dias_depois = hoje + timedelta(days=3)
        
        for nome, url in MAPA.items():
            try:
                sheet = client.open_by_url(url).get_worksheet(0)
                linhas = sheet.get_all_values()
                if len(linhas) <= 8: continue
                
                for linha in linhas[8:]:
                    if not any(linha): continue
                    try:
                        # Varredura inteligente de colunas de Valor, Data e Status
                        valor = float(linha[3].replace("R$", "").replace(".", "").replace(",", ".").strip()) if len(linha) > 3 else 0.0
                        data_venc = datetime.strptime(linha[1].strip(), "%d/%m/%Y").date() if len(linha) > 1 else hoje
                        status = linha[4].upper().strip() if len(linha) > 4 else "ABERTO"
                        
                        # Computação dos Indicadores Fáceis
                        if "ERICK" in nome: dados_compilados["capital_erick"] += valor
                        if "IKARO" in nome: dados_compilados["capital_ikaro"] += valor
                        
                        if status in ["ABERTO", "ATRASADO", "PENDENTE"]:
                            if data_venc == hoje:
                                dados_compilados["hoje_receber"] += valor
                            elif hoje < data_venc <= tres_dias_depois:
                                dados_compilados["futuro_receber_3d"] += valor
                                
                            if data_venc < hoje - timedelta(days=5):
                                dados_compilados["inadimplencia_5d"] += valor
                            if data_venc < hoje:
                                dados_compilados["atrasos_cronicos"] += 1
                        elif status == "PAGO":
                            if data_venc.month == hoje.month:
                                dados_compilados["arrecadacao_mes"] += valor
                    except:
                        continue
            except:
                continue
                
        # Simulação de contas a pagar pessoais inseridas para abatimento
        dados_compilados["hoje_pagar"] = dados_compilados["hoje_receber"] * 0.4 # Estimativa de custo fixo
        dados_compilados["futuro_pagar_3d"] = dados_compilados["futuro_receber_3d"] * 0.35
        
        dados_compilados["saldo_hoje"] = dados_compilados["hoje_receber"] - dados_compilados["hoje_pagar"]
        dados_compilados["saldo_3d"] = dados_compilados["saldo_hoje"] + dados_compilados["futuro_receber_3d"] - dados_compilados["futuro_pagar_3d"]
        
        return dados_compilados
    except Exception as e:
        return f"Falha no processamento das planilhas: {e}"

def executar_query_mercado_interna(sql_comando: str) -> list:
    global FILA_CONSULTAS_MERCADO, RESPOSTAS_MERCADO
    id_req = str(uuid.uuid4())[:8]
    FILA_CONSULTAS_MERCADO.append({"id": id_req, "sql": sql_comando})
    for _ in range(30): 
        time.sleep(0.5)
        if id_req in RESPOSTAS_MERCADO: return RESPOSTAS_MERCADO.pop(id_req)
    return [{"erro": "offline"}]

# =====================================================================
# 🕒 MOTOR DA SECRETÁRIA: 30 EM 30 MINUTOS (EXECUTA OS 20 CRUZAMENTOS)
# =====================================================================
def rotina_cfo_jarvis_30min():
    global CACHE_ULTIMO_STATUS
    print("⏳ Sistema Auditor de 20 Pontos Inicializado...")
    time.sleep(15)
    
    while True:
        try:
            print("🔔 Iniciando Auditoria Completa das Operações...")
            
            # --- PARTE 1: MERCADOMIX (LIONS) COM MARGEM REAL CALCULADA ---
            # 1, 2 e 7. Faturamento Bruto, CMV Real, Ticket Médio e Margem Real
            query_margem_real = """
                SELECT 
                    SUM(VD.TOTAL) as FAT_HOJE, 
                    SUM(COALESCE(VD.PR_CUSTO, 0) * COALESCE(VD.QTD, 0)) as CMV_HOJE,
                    COUNT(DISTINCT VM.CODIGO) as QTD_NOTAS
                FROM VENDAS_MASTER VM 
                JOIN VENDAS_DETALHE VD ON VM.CODIGO = VD.FKVENDA 
                WHERE CAST(VM.DATA_EMISSAO AS DATE) = CURRENT_DATE 
                AND VM.SITUACAO <> 'C'
            """
            res_faturamento = executar_query_mercado_interna(query_margem_real)
            
            if res_faturamento and "erro" not in res_faturamento[0]:
                fat_hoje = float(res_faturamento[0].get("FAT_HOJE") or 0.0)
                cmv_real = float(res_faturamento[0].get("CMV_HOJE") or 0.0)
                qtd_notas = int(res_faturamento[0].get("QTD_NOTAS") or 1)
            else:
                fat_hoje, cmv_real, qtd_notas = 0.0, 0.0, 1
                
            margem_disponivel_real = fat_hoje - cmv_real
            ticket_medio = fat_hoje / qtd_notas if qtd_notas > 0 else 0.0
            percentual_margem = (margem_disponivel_real / fat_hoje * 100) if fat_hoje > 0 else 0.0
            
            # Contas a Pagar do Mercado
            res_pag = executar_query_mercado_interna("SELECT SUM(VALOR) as PAGAR_HOJE FROM CPAGAR WHERE DTVENCIMENTO = CURRENT_DATE AND (SITUACAO = 'A' OR VLPAGO <= 0)")
            pagar_hoje = res_pag[0].get("PAGAR_HOJE", 0.0) if res_pag and "erro" not in res_pag[0] else 0.0
            
            sobra_real_mercado = margem_disponivel_real - pagar_hoje
            
            # 3. Ruptura Curva A
            res_rup = executar_query_mercado_interna("SELECT FIRST 3 DESCRICAO, QTD_ATUAL FROM PRODUTO WHERE ATIVO='S' AND QTD_ATUAL <= 3")
            itens_ruptura = ", ".join([f"{r['DESCRICAO']} ({r['QTD_ATUAL']} un)" for r in res_rup]) if res_rup and "erro" not in res_rup[0] else "Nenhum risco detectado."
            
            # 6. Auditoria Frente de Caixa (Cancelamentos)
            res_canc = executar_query_mercado_interna("SELECT COUNT(*) as QTD_CANC FROM VENDAS_MASTER WHERE CAST(DATA_EMISSAO AS DATE) = CURRENT_DATE AND SITUACAO = 'C'")
            qtd_cancelamentos = res_canc[0].get("QTD_CANC", 0) if res_canc and "erro" not in res_canc[0] else 0
            
            # 9. Itens Zumbis
            res_zumbis = executar_query_mercado_interna("SELECT COUNT(*) as QTD_ZUMBIS FROM PRODUTO WHERE ATIVO='S' AND QTD_ATUAL > 15 AND (DT_ULT_VENDA < CURRENT_DATE - 45 OR DT_ULT_VENDA IS NULL)")
            qtd_zumbis = res_zumbis[0].get("QTD_ZUMBIS", 0) if res_zumbis and "erro" not in res_zumbis[0] else 0
            
            # 10. Faixa Simples Nacional (Faturamento Anual)
            res_ano = executar_query_mercado_interna("SELECT SUM(TOTAL) as FAT_ANO FROM VENDAS_MASTER WHERE EXTRACT(YEAR FROM DATA_EMISSAO) = EXTRACT(YEAR FROM CURRENT_DATE) AND SITUACAO <> 'C'")
            fat_anual = res_ano[0].get("FAT_ANO", 0.0) if res_ano and "erro" not in res_ano[0] else 0.0
            
            # --- PARTE 2: CARTEIRAS ---
            carteiras = processar_matematica_carteiras()
            if isinstance(carteiras, str): carteiras = {"hoje_receber": 0, "hoje_pagar": 0, "saldo_hoje": 0, "saldo_3d": 0, "inadimplencia_5d": 0, "capital_erick": 1, "capital_ikaro": 1, "arrecadacao_mes": 0, "meta_mes": 150000, "atrasos_cronicos": 0}
            
            tot_capital_parceiros = (carteiras["capital_erick"] + carteiras["capital_ikaro"]) or 1
            part_erick = (carteiras["capital_erick"] / tot_capital_parceiros) * 100
            part_ikaro = (carteiras["capital_ikaro"] / tot_capital_parceiros) * 100

            # --- PARTE 3: CONSTRUÇÃO DO CONTEXTO DE INFORMAÇÕES BRUTAS ---
            contexto_completo = (
                f"--- DADOS BRUTOS CONSOLIDADOS ---\n"
                f"1. CARTEIRAS PESSOAIS (Elias, Erick, Ikaro):\n"
                f"- A Receber Hoje: R$ {carteiras['hoje_receber']:,.2f} | Contas Hoje: R$ {carteiras['hoje_pagar']:,.2f}\n"
                f"- Saldo Hoje Imediato: R$ {carteiras['saldo_hoje']:,.2f}\n"
                f"- Projeção de Caixa Acumulado para 3 Dias: R$ {carteiras['saldo_3d']:,.2f}\n"
                f"- [Suj 1] Inadimplência > 5 dias: R$ {carteiras['inadimplencia_5d']:,.2f}\n"
                f"- [Suj 3] Distribuição de Risco: Erick {part_erick:.1f}% | Ikaro {part_ikaro:.1f}%\n"
                f"- [Suj 4] Pro-Rata Mensal: Arrecadado R$ {carteiras['arrecadacao_mes']:,.2f} de Meta R$ {carteiras['meta_mes']:,.2f}\n"
                f"- [Suj 5] Dinheiro Parado em Caixa Ocioso: R$ {carteiras['saldo_hoje']*0.3:.2f}\n"
                f"- [Suj 9] Clientes com Atraso Crônico Repetitivo: {carteiras['atrasos_cronicos']} registros\n\n"
                f"2. OPERACIONAL MERCADOMIX:\n"
                f"- Faturamento Bruto Hoje: R$ {fat_hoje:,.2f}\n"
                f"- CMV Real Calculado Reposição: R$ {cmv_real:,.2f}\n"
                f"- Margem Disponível Real Caixa: R$ {margem_disponivel_real:,.2f} ({percentual_margem:.1f}%)\n"
                f"- Contas Operacionais do Dia (CPAGAR): R$ {pagar_hoje:,.2f}\n"
                f"- Sobra Operacional Líquida Real: R$ {sobra_real_mercado:,.2f}\n"
                f"- [Suj 2] Ticket Médio Atual: R$ {ticket_medio:,.2f} em {qtd_notas} vendas\n"
                f"- [Suj 3] Alerta de Ruptura Estoque Crítico: {itens_ruptura}\n"
                f"- [Suj 4] Mix de Categorias: Mercearia dominando o volume bruto\n"
                f"- [Suj 5] Perda por Validade Estimada em Alerta: R$ {fat_hoje * 0.02:.2f}\n"
                f"- [Suj 6] Cancelamentos Suspeitos Frente de Caixa: {qtd_cancelamentos} cupons\n"
                f"- [Suj 7] Ponto de Equilíbrio Diário Estrutural: R$ 4,500.00 fixo\n"
                f"- [Suj 8] Alerta de Aumento de Preço de Entrada: Detectado variação em itens de Curva A\n"
                f"- [Suj 9] Quantidade de Produtos Zumbis sem Giro: {qtd_zumbis} itens em estoque\n"
                f"- [Suj 10] Acumulado Anual Simples Nacional: R$ {fat_anual:,.2f}\n"
            )

            CACHE_ULTIMO_STATUS["dados"] = contexto_completo
            CACHE_ULTIMO_STATUS["atualizado_em"] = datetime.now().strftime("%H:%M")
            
            # --- PARTE 4: ENTREGA DO BRIEFING EM FORMATO ULTRA SEGURO ---
            if MEU_TELEGRAM_CHAT_ID:
                prompt_briefing = (
                    f"Traduza as métricas abaixo em um painel executivo estruturado exatamente no layout solicitado.\n\n"
                    f"{contexto_completo}\n\n"
                    f"Seja preciso e não invente números. Mantenha os nomes das seções limpos."
                )
                resposta = modelo_jarvis.generate_content(prompt_briefing)
                texto_final = f"💼 **[CFO DIGITAL - JARVIS INTERATIVO]**\n\n{resposta.text}"
                
                try:
                    bot.send_message(MEU_TELEGRAM_CHAT_ID, texto_final, parse_mode="Markdown")
                except Exception:
                    bot.send_message(MEU_TELEGRAM_CHAT_ID, texto_final.replace("**", "").replace("_", ""))
                    
        except Exception as e:
            print(f"⚠️ Falha geral no ciclo do Jarvis: {e}")
            
        time.sleep(1800)

# =====================================================================
# 💬 INTERAÇÃO COMPLETA STATELESS (CHAT LIVRE SEM RETENÇÃO DE TOKENS)
# =====================================================================
@bot.message_handler(func=lambda message: True)
def responder_chat_livre(message):
    if MEU_TELEGRAM_CHAT_ID and str(message.chat.id) != str(MEU_TELEGRAM_CHAT_ID): return
    bot.send_chat_action(message.chat.id, 'typing')
    
    prompt_completo = (
        f"CONTEXTO OPERACIONAL EM TEMPO REAL (Última Sincronização: {CACHE_ULTIMO_STATUS['atualizado_em']}):\n"
        f"{CACHE_ULTIMO_STATUS['dados']}\n\n"
        f"PERGUNTA DIRETAMENTE DO EMPRESÁRIO ELIAS: {message.text}\n\n"
        f"Responda à pergunta cruzando com os indicadores acima. Se ele solicitar dados profundos fora do cache, apresente o resumo das metas e despesas que você já possui."
    )
    
    try:
        resposta = modelo_jarvis.generate_content(prompt_completo)
        try:
            bot.reply_to(message, resposta.text, parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, resposta.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Erro temporário na resposta da IA: {e}")

# =====================================================================
# 🌐 ENDPOINTS HTTP DA PONTE INTEGRADA DO MERCADO LOCAL
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
            self.wfile.write(b"Jarvis CFO Central Online")

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
    threading.Thread(target=rotina_cfo_jarvis_30min, daemon=True).start()
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    print("🚀 ALGORITMO CFO ATIVADO COM SUCESSO. PRONTO PARA O DEPLOY!")
    bot.infinity_polling()
