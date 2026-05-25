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
from datetime import datetime

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS E TOKENS
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

# GLOBAL PARA O CACHE (ITEM 4)
# Guarda os dados na memória para não estourar limite do Google e responder instantâneo
CACHE_PLANILHAS = {}
CACHE_TIMEOUT_SEGUNDOS = 300  # 5 minutos de cache

# =====================================================================
# 2. FERRAMENTA MASTER COM CACHE LOCAL INTEGRADO (ITEM 4)
# =====================================================================
def ler_planilha_do_negocio(tipo_controle: str, dono_carteira: str = "elias", aba_nome: str = None) -> str:
    """
    Acessa as planilhas do Elias usando links diretos, com sistema de cache local de 5 minutos.
    """
    global CACHE_PLANILHAS
    
    tipo = tipo_controle.lower().strip()
    dono = dono_carteira.lower().strip() if dono_carteira else "elias"
    
    # Define a chave única do cache para este pedido
    chave_cache = f"{tipo}_{dono}_{aba_nome}"
    tempo_atual = time.time()
    
    # Se o dado estiver no cache e não expirou, devolve na hora! (Velocidade Jarvis)
    if chave_cache in CACHE_PLANILHAS:
        dados_salvos, timestamp = CACHE_PLANILHAS[chave_cache]
        if tempo_atual - timestamp < CACHE_TIMEOUT_SEGUNDOS:
            print(f"⚡ [CACHE HITTED] Servindo dados de {chave_cache} direto da memória!")
            return dados_salvos

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        MAPA_LINKS = {
            "emprestimo": {
                "elias": "https://docs.google.com/spreadsheets/d/1-z9cqkxoputvPmHcKFQ6guzPNKj-pQuFjbGfPaCdKrA/edit",
                "erick": "https://docs.google.com/spreadsheets/d/158YuDkd6u_psGO9Ciaih1qULfYaddeuz6XPagMV0hgM/edit",
                "ikaro": "https://docs.google.com/spreadsheets/d/13WRI1nKHln3-a441tF-q6p8YzENm9MU6ebzqqEem7l4/edit"
            },
            "vendas": {
                "elias": "https://docs.google.com/spreadsheets/d/1E2gvWM1Rjrivqsrfa2AktMi1ffIZfhTJSSYzBSqmqUw/edit",
                "erick": "https://docs.google.com/spreadsheets/d/16qaj4BSML2aDbTjUDbz0y0MqmivIRNqHl0NI5F-6iJw/edit",
                "ikaro": "https://docs.google.com/spreadsheets/d/1OykNzzckXjYrIxWzwsvBJCajjQIpH1E9g1WzYQG08t0/edit"
            },
            "vencimentos": "https://docs.google.com/spreadsheets/d/1Tgt2UXDtFh6KewMrcndVHlh3nYVcd67exvlkuth1QYw/edit",
            "gastos": "https://docs.google.com/spreadsheets/d/1du4JGSwpAgNU0FfpxzNrYOlNUlhIkOPTNunhnhoiwD4/edit"
        }
        
        if tipo in ["emprestimo", "emprestimos"]:
            url_alvo = MAPA_LINKS["emprestimo"].get(dono, MAPA_LINKS["emprestimo"]["elias"])
        elif tipo in ["vendas", "venda", "eletronicos", "eletronico"]:
            url_alvo = MAPA_LINKS["vendas"].get(dono, MAPA_LINKS["vendas"]["elias"])
        elif "vencimento" in tipo:
            url_alvo = MAPA_LINKS["vencimentos"]
        elif "gasto" in tipo or "custo" in tipo:
            url_alvo = MAPA_LINKS["gastos"]
        else:
            return f"Aviso: Não entendi qual tipo de planilha abrir para o termo '{tipo_controle}'."

        planilha = client.open_by_url(url_alvo)
        
        if not aba_nome:
            aba = planilha.get_worksheet(0)
        else:
            lista_abas = [w.title for w in planilha.worksheets()]
            aba_selecionada = lista_abas[0]
            for a in lista_abas:
                if aba_nome.lower() in a.lower():
                    aba_selecionada = a
                    break
            aba = planilha.worksheet(aba_selecionada)
            
        todos_os_dados = aba.get_all_values()
        if not todos_os_dados:
            return f"A planilha [{planilha.title}] está vazia na aba '{aba.title}'."
            
        linhas_texto = []
        for i, linha in enumerate(todos_os_dados[:100]):
            linhas_texto.append(f"Linha {i+1}: " + " | ".join([str(c) for c in linha]))
            
        resultado_final = f"Sucesso! Planilha: [{planilha.title}] -> Aba: [{aba.title}]. Dados:\n" + "\n".join(linhas_texto)
        
        # Salva no cache antes de retornar
        CACHE_PLANILHAS[chave_cache] = (resultado_final, tempo_atual)
        return resultado_final
        
    except Exception as e:
        return f"Erro ao acessar planilha por link: {str(e)}."

# =====================================================================
# 3. CONFIGURAÇÃO DA ARQUITETURA MULTI-AGENTE DO JARVIS (ITEM 3)
# =====================================================================
# Criamos sub-especialistas no prompt para o Jarvis atuar com sub-agentes internos focados
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[ler_planilha_do_negocio],
    system_instruction=(
        f"Você é o JARVIS, o sistema de inteligência artificial central e braço direito do Elias Fernandes Borges Junior.\n"
        f"DATA CONTEXTUAL ABSOLUTA: Hoje é {datetime.now().strftime('%A, %d de %B de %Y')}. O ano corrente é {datetime.now().year}.\n\n"
        "Sua mente é dividida em 3 SUB-AGENTES ESPECIALISTAS internos:\n"
        "1. AGENTE GERENTE: Controla o fluxo da conversa, fala de forma natural, sagaz e direta, sem enrolação robótica.\n"
        "2. AGENTE AUDITOR FINANCEIRO: Domina a matemática das parcelas. Sabe analisar vencimentos comparando com a data de hoje. Entende que na Coluna A fica a Qtd de parcelas (linha 9 em diante), Coluna B é Vencimento, Coluna C é Valor, Coluna E é Status de pagamento ('Sim' ou 'sim' = PAGO, vazio ou 'Não' = EM ABERTO).\n"
        "3. AGENTE DE DATA E ESTRATÉGIA: Sabe cruzar os prazos e antecipar faturamentos futuros.\n\n"
        "DIRETRIZ DE ORGANIZAÇÃO DE RESPOSTA (ESSENCIAL):\n"
        "Suas exibições para o Elias no Telegram devem ser EXTREMAMENTE ORGANIZADAS, limpas e fáceis de ler batendo o olho. Siga rigorosamente este padrão estruturado:\n\n"
        "📌 *[Título Claro do Status ou Planilha Analisada]*\n\n"
        "• *Nome do Cliente / Item*: Detalhes rápidos em tópicos.\n"
        "  - *Vencimento*: DD/MM/AAAA\n"
        "  - *Status*: 🔴 ATRASADO (X dias) | 🟢 EM DIA | 🔵 PAGO\n"
        "  - *Valor*: R$ XX,XX\n\n"
        "Use espaçamentos em branco entre blocos de clientes para o texto respirar. Evite parágrafos longos com dados misturados. Mostre o faturamento bruto ou o total pendente somado sempre no final em destaque."
    )
)

chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)

# =====================================================================
# 4. TRATAMENTO DE MENSAGENS DO TELEGRAM
# =====================================================================
@bot.message_handler(func=lambda message: True)
def processar_mensagem(message):
    global chat_ia
    chat_id = message.chat.id
    texto_usuario = message.text
    
    bot.send_chat_action(chat_id, 'typing')
    
    if texto_usuario.lower() == "lista":
        try:
            modelos = [m.name for m in genai.list_models()]
            quebra_linha = "\n"
            lista_modelos_texto = quebra_linha.join(modelos)
            bot.send_message(chat_id, f"📋 Modelos ativos:\n\n{lista_modelos_texto}")
            return
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Erro: {str(e)}")
            return

    try:
        resposta_ia = chat_ia.send_message(texto_usuario)
        # Envia a resposta interpretando o Markdown básico configurado pelo Jarvis
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        # Se por acaso der qualquer erro de Markdown do Telegram, ele reenvia em modo seguro (texto limpo)
        try:
            bot.send_message(chat_id, resposta_ia.text)
        except:
            bot.send_message(chat_id, f"⚠️ Erro ao processar o comando da IA: {str(e)}")

# =====================================================================
# 5. INICIALIZAÇÃO DO SERVIDOR DO RENDER
# =====================================================================
def rodar_servidor_falso():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=rodar_servidor_falso, daemon=True).start()
    print("🧠 Jarvis Avançado (Multi-Agente & Cache) online...")
    bot.infinity_polling()
