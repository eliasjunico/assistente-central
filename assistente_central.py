import os
import telebot
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import threading
import time
from datetime import datetime, timedelta

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS & MODELOS
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MEU_TELEGRAM_CHAT_ID = os.environ.get("MEU_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

modelo_jarvis = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    system_instruction=(
        "Você é o Jarvis, Diretor Financeiro (CFO) Virtual do Elias.\n"
        "Sua missão é ler o relatório estático dos 10 cruzamentos estratégicos calculados pelo Python "
        "e transformá-lo em uma análise de alto impacto, ultra-direta, apontando caminhos, "
        "alertas de risco de inadimplência e tomadas de decisão urgentes. Use negritos e emojis de forma executiva."
    )
)

CACHE_ULTIMO_STATUS = {"dados": "Aguardando primeira sincronização agendada...", "atualizado_em": "-"}

# =====================================================================
# 📊 UTILIÁRIOS DE TRATAMENTO DE DADOS
# =====================================================================
def limpar_valor(texto):
    """Transforma strings de moeda ('R$ 1.500,00') em floats utilizáveis."""
    if not texto: return 0.0
    try:
        return float(texto.replace("R$", "").replace(".", "").replace(",", ".").strip())
    except:
        return 0.0

def converter_data(texto):
    """Converte strings de data para objetos date de forma segura."""
    if not texto: return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None

# =====================================================================
# 🧮 ENGINE DE CÁLCULO DOS 10 CRUZAMENTOS ESTRATÉGICOS
# =====================================================================
def processar_10_cruzamentos():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Estrutura base de dados para consolidar tudo
    db = {
        "entradas_hoje": 0.0, "saidas_hoje": 0.0,
        "entradas_3d": 0.0, "saidas_3d": 0.0,
        "entradas_30d": 0.0, "saidas_30d": 0.0,
        "inadimplencia_critica": 0.0, "clientes_cronicos": 0,
        "capital_rua_erick": 0.0, "capital_rua_ikaro": 0.0, "capital_rua_elias": 0.0,
        "arrecadado_mes": 0.0, "meta_mes": 150000.0,
        "previsto_ontem": 0.0, "realizado_ontem": 0.0,
        "contas_pagar_mes": 0.0
    }
    
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not google_creds_json: return "Credenciais do Google Sheets ausentes no ambiente."
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(google_creds_json), scope)
        client = gspread.authorize(creds)
        
        # Mapeamentos das planilhas de entrada
        PLANILHAS_EMPRESTIMOS = {
            "Elias": "https://docs.google.com/spreadsheets/d/1-z9cqkxoputvPmHcKFQ6guzPNKj-pQuFjbGfPaCdKrA/edit",
            "Erick": "https://docs.google.com/spreadsheets/d/158YuDkd6u_psGO9Ciaih1qULfYaddeuz6XPagMV0hgM/edit",
            "Ikaro": "https://docs.google.com/spreadsheets/d/13WRI1nKHln3-a441tF-q6p8YzENm9MU6ebzqqEem7l4/edit"
        }
        
        PLANILHAS_VENDAS = {
            "Elias": "https://docs.google.com/spreadsheets/d/1E2gvWM1Rjrivqsrfa2AktMi1ffIZfhTJSSYzBSqmqUw/edit",
            "Erick": "https://docs.google.com/spreadsheets/d/16qaj4BSML2aDbTjUDbz0y0MqmivIRNqHl0NI5F-6iJw/edit",
            "Ikaro": "https://docs.google.com/spreadsheets/d/1OykNzzckXjYrIxWzwsvBJCajjQIpH1E9g1WzYQG08t0/edit"
        }
        
        URL_PAGAR = "https://docs.google.com/spreadsheets/d/1Tgt2UXDtFh6KewMrcndVHlh3nYVcd67exvlkuth1QYw/edit"
        
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=1)
        tres_dias_depois = hoje + timedelta(days=3)
        trinta_dias_depois = hoje + timedelta(days=30)
        
        # -----------------------------------------------------------------
        # PARTE A: PROCESSAR CONTAS A PAGAR (ATUALIZADO COM SUA NOVA ESTRUTURA)
        # -----------------------------------------------------------------
        try:
            sh_pagar = client.open_by_url(URL_PAGAR).get_worksheet(0)
            linhas_pagar = sh_pagar.get_all_values()
            
            # Se os dados reais começarem na linha 2 (abaixo do cabeçalho), mude para: linhas_pagar[1:]
            for linha in linhas_pagar[8:]: 
                if not any(linha) or len(linha) < 6: continue
                
                valor_conta = limpar_valor(linha[1])    # Coluna B (Índice 1)
                dt_venc = converter_data(linha[2])      # Coluna C (Índice 2)
                status_conta = linha[5].upper().strip()  # Coluna F (Índice 5)
                
                if dt_venc:
                    if status_conta in ["ABERTO", "A PAGAR", "PENDENTE"]:
                        if dt_venc == hoje: db["saidas_hoje"] += valor_conta
                        if hoje <= dt_venc <= tres_dias_depois: db["saidas_3d"] += valor_conta
                        if hoje <= dt_venc <= trinta_dias_depois: db["saidas_30d"] += valor_conta
                    
                    if dt_venc.month == hoje.month:
                        db["contas_pagar_mes"] += valor_conta
        except Exception as e:
            print(f"Aviso: Falha ao ler planilha de Contas a Pagar: {e}")

        # -----------------------------------------------------------------
        # PARTE B: PROCESSAR PLANILHAS DE EMPRÉSTIMOS
        # -----------------------------------------------------------------
        for operador, url in PLANILHAS_EMPRESTIMOS.items():
            try:
                sheet = client.open_by_url(url).get_worksheet(0)
                linhas = sheet.get_all_values()
                for linha in lines[8:]: 
                    if not any(linha) or len(linha) < 8: continue
                    
                    dt_venc = converter_data(linha[2]) # Coluna C
                    saldo_restante = limpar_valor(linha[6]) # Coluna G
                    status = linha[7].upper().strip() # Coluna H
                    
                    if status in ["ABERTO", "ATRASADO", "PENDENTE"]:
                        if operador == "Elias": db["capital_rua_elias"] += saldo_restante
                        elif operador == "Erick": db["capital_rua_erick"] += saldo_restante
                        elif operador == "Ikaro": db["capital_rua_ikaro"] += saldo_restante
                        
                        if dt_venc:
                            if dt_venc == hoje: db["entradas_hoje"] += saldo_restante
                            elif hoje < dt_venc <= tres_dias_depois: db["entradas_3d"] += saldo_restante
                            if dt_venc <= trinta_dias_depois: db["entradas_30d"] += saldo_restante
                            
                            if dt_venc < hoje - timedelta(days=5): db["inadimplencia_critica"] += saldo_restante
                            if dt_venc < hoje - timedelta(days=45): db["clientes_cronicos"] += 1
                            if dt_venc == ontem: db["previsto_ontem"] += saldo_restante
                            
                    elif status == "PAGO" and dt_venc:
                        if dt_venc.month == hoje.month: db["arrecadacao_mes"] += saldo_restante
                        if dt_venc == ontem: db["realizado_ontem"] += saldo_restante
            except Exception as e:
                print(f"Aviso: Falha ao ler Empréstimos de {operador}: {e}")

        # -----------------------------------------------------------------
        # PARTE C: PROCESSAR PLANILHAS DE VENDAS
        # -----------------------------------------------------------------
        for operador, url in PLANILHAS_VENDAS.items():
            try:
                sheet = client.open_by_url(url).get_worksheet(0)
                linhas = sheet.get_all_values()
                for linha in linhas[8:]: 
                    if not any(linha) or len(linha) < 12: continue
                    
                    falta_pagar = limpar_valor(linha[8]) # Coluna I (Restante devido)
                    dt_venc_parc = converter_data(linha[10]) # Coluna K
                    valor_parcela = limpar_valor(linha[11]) # Coluna L
                    status = "PAGO" if falta_pagar <= 0 else "ABERTO"
                    
                    if status == "ABERTO":
                        if operador == "Elias": db["capital_rua_elias"] += falta_pagar
                        elif operador == "Erick": db["capital_rua_erick"] += falta_pagar
                        elif operador == "Ikaro": db["capital_rua_ikaro"] += falta_pagar
                        
                        if dt_venc_parc:
                            if dt_venc_parc == hoje: db["entradas_hoje"] += valor_parcela
                            elif hoje < dt_venc_parc <= tres_dias_depois: db["entradas_3d"] += valor_parcela
                            if dt_venc_parc <= trinta_dias_depois: db["entradas_30d"] += valor_parcela
                            
                            if dt_venc_parc < hoje - timedelta(days=5): db["inadimplencia_critica"] += valor_parcela
                            if dt_venc_parc < hoje - timedelta(days=45): db["clientes_cronicos"] += 1
                            if dt_venc_parc == ontem: db["previsto_ontem"] += valor_parcela
                            
                    elif status == "PAGO" and dt_venc_parc:
                        if dt_venc_parc.month == hoje.month: db["arrecadacao_mes"] += valor_parcela
                        if dt_venc_parc == ontem: db["realizado_ontem"] += valor_parcela
            except Exception as e:
                print(f"Aviso: Falha ao ler Vendas de {operador}: {e}")

        # -----------------------------------------------------------------
        # CONSTRUÇÃO DOS 10 CRUZAMENTOS TRATADOS
        # -----------------------------------------------------------------
        saldo_hoje = db["entradas_hoje"] - db["saidas_hoje"]
        saldo_3d_acumulado = saldo_hoje + db["entradas_3d"] - db["saidas_3d"]
        custo_diario_estimado = db["contas_pagar_mes"] / 30
        
        total_carteira_rua = db["capital_rua_elias"] + db["capital_rua_erick"] + db["capital_rua_ikaro"] or 1.0
        part_elias = (db["capital_rua_elias"] / total_carteira_rua) * 100
        part_erick = (db["capital_rua_erick"] / total_carteira_rua) * 100
        part_ikaro = (db["capital_rua_ikaro"] / total_carteira_rua) * 100
        
        eficiencia_ontem = (db["realizado_ontem"] / db["previsto_ontem"] * 100) if db["previsto_ontem"] > 0 else 100.0
        
        dias_restantes_mes = 30 - hoje.day if 30 - hoje.day > 0 else 1
        falta_para_meta = db["meta_mes"] - db["arrecadacao_mes"]
        ritmo_diario_necessario = falta_para_meta / dias_restantes_mes if falta_para_meta > 0 else 0.0

        relatorio_bruto = (
            f"=== COMPILAÇÃO DOS 10 CRUZAMENTOS ESTRATÉGICOS ===\n"
            f"1. LIQUIDEZ DIÁRIA: A Receber Hoje R$ {db['entradas_hoje']:,.2f} | A Pagar Hoje R$ {db['saidas_hoje']:,.2f} | Saldo: R$ {saldo_hoje:,.2f}\n"
            f"2. COBERTURA CURTO PRAZO (3 DIAS): Projeção de Entradas R$ {db['entradas_3d']:,.2f} vs Saídas R$ {db['saidas_3d']:,.2f} | Saldo Acumulado Período: R$ {saldo_3d_acumulado:,.2f}\n"
            f"3. BREAK-EVEN OPERACIONAL: Despesa Média Diária R$ {custo_diario_estimado:,.2f} vs Faturamento do Dia R$ {db['entradas_hoje']:,.2f}\n"
            f"4. EXPOSIÇÃO À INADIMPLÊNCIA CRÍTICA: R$ {db['inadimplencia_critica']:,.2f} travados há mais de 5 dias (Equivale a {((db['inadimplencia_critica']/db['saidas_hoje']*100) if db['saidas_hoje'] > 0 else 0):.1f}% das contas de hoje)\n"
            f"5. CONCENTRAÇÃO DE RISCO EM PARCEIROS: Total na rua R$ {total_carteira_rua:,.2f} [Elias: {part_elias:.1f}% | Erick: {part_erick:.1f}% | Ikaro: {part_ikaro:.1f}%]\n"
            f"6. EFICIÊNCIA DE COBRANÇA (ONTEM): Previsto R$ {db['previsto_ontem']:,.2f} | Realizado R$ {db['realizado_ontem']:,.2f} | Eficiência: {eficiencia_ontem:.1f}%\n"
            f"7. RITMO DA META MENSAL: Arrecadado R$ {db['arrecadacao_mes']:,.2f} de R$ {db['meta_mes']:,.2f}. Necessário R$ {ritmo_diario_necessario:,.2f}/dia pelos próximos {dias_restantes_mes} dias.\n"
            f"8. CUSTO DE OPORTUNIDADE (CAIXA OCIOSO): Rendimento CDI Perdido Estimado R$ {max(0.0, saldo_hoje * 0.0004):,.2f}/dia sobre o saldo livre de hoje.\n"
            f"9. MONITOR DE CLIENTES ZUMBIS: {db['clientes_cronicos']} contratos inadimplentes crônicos (atrasados há mais de 45 dias).\n"
            f"10. PREVISIBILIDADE CASAMENTO DE SAFRA (30 DIAS): Entradas Futuras R$ {db['entradas_30d']:,.2f} vs Contas Fixas Projetadas R$ {db['saidas_30d']:,.2f}.\n"
        )
        return relatorio_bruto

    except Exception as e:
        return f"Falha crítica no cruzamento de dados: {e}"

# =====================================================================
# 🕒 AGENDADOR DE DISPAROS FIXOS (07:00 E 21:00)
# =====================================================================
def executar_auditoria_e_enviar():
    global CACHE_ULTIMO_STATUS
    res_cruzamentos = processar_10_cruzamentos()
    
    if "Falha" in res_cruzamentos:
        print(f"⚠️ {res_cruzamentos}")
        return

    CACHE_ULTIMO_STATUS["dados"] = res_cruzamentos
    CACHE_ULTIMO_STATUS["atualizado_em"] = datetime.now().strftime("%H:%M")
    
    if MEU_TELEGRAM_CHAT_ID:
        prompt = (
            f"Com base nas métricas consolidadas abaixo, monte o Briefing do Diretor Financeiro para o Elias. "
            f"Analise criticamente cada um dos 10 cruzamentos estruturados e dê o seu veredito de ações estratégicas.\n\n"
            f"{res_cruzamentos}"
        )
        try:
            resposta = modelo_jarvis.generate_content(prompt)
            texto_final = f"💼 **[CFO DIGITAL - BRIEFING EXECUTIVO]**\n\n{resposta.text}"
            try:
                bot.send_message(MEU_TELEGRAM_CHAT_ID, texto_final, parse_mode="Markdown")
            except Exception:
                bot.send_message(MEU_TELEGRAM_CHAT_ID, texto_final.replace("**", "").replace("_", ""))
        except Exception as e:
            print(f"Erro na API do Gemini: {e}")

def rotina_cronometrada_cfo():
    print("⏳ Monitor Horário Ativado (Disparos agendados para 07:00 e 21:00)...")
    
    res_init = processar_10_cruzamentos()
    if "Falha" not in res_init:
        CACHE_ULTIMO_STATUS["dados"] = res_init
        CACHE_ULTIMO_STATUS["atualizado_em"] = datetime.now().strftime("%H:%M")

    while True:
        agora = datetime.now()
        if (agora.hour == 7 and agora.minute == 0) or (agora.hour == 21 and agora.minute == 0):
            executar_auditoria_e_enviar()
            time.sleep(61)
        time.sleep(30)

# =====================================================================
# 💬 CHAT LIVRE (STATELESS - DISPONÍVEL TODO O TEMPO)
# =====================================================================
@bot.message_handler(func=lambda message: True)
def responder_chat_livre(message):
    if MEU_TELEGRAM_CHAT_ID and str(message.chat.id) != str(MEU_TELEGRAM_CHAT_ID): return
    bot.send_chat_action(message.chat.id, 'typing')
    
    prompt_completo = (
        f"CONTEXTO OPERACIONAL FINANCEIRO (Última Sincronização Estática: {CACHE_ULTIMO_STATUS['atualizado_em']}):\n"
        f"{CACHE_ULTIMO_STATUS['dados']}\n\n"
        f"PERGUNTA DO EMPRESÁRIO ELIAS: {message.text}\n\n"
        f"Responda ao Elias utilizando a base dos 10 cruzamentos acima de forma rápida, clara e executiva."
    )
    try:
        resposta = modelo_jarvis.generate_content(prompt_completo)
        try:
            bot.reply_to(message, resposta.text, parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, resposta.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Erro na resposta da IA: {e}")

if __name__ == "__main__":
    threading.Thread(target=rotina_cronometrada_cfo, daemon=True).start()
    print("🚀 ALGORITMO DOS 10 CRUZAMENTOS ESTRATÉGICOS ATIVADO!")
    bot.infinity_polling()
