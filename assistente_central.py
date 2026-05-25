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

# =====================================================================
# 🎯 IMPLEMENTAÇÃO DO ITEM 4: BANCO DE CACHE LOCAL (MEMÓRIA RAM)
# =====================================================================
# Este dicionário guarda os dados na memória RAM do Render para leitura instantânea
DADOS_PLANILHAS_LOCAL = {
    "emprestimo_elias": "Sem dados carregados ainda.",
    "emprestimo_erick": "Sem dados carregados ainda.",
    "emprestimo_ikaro": "Sem dados carregados ainda.",
    "vendas_elias": "Sem dados carregados ainda.",
    "vendas_erick": "Sem dados carregados ainda.",
    "vendas_ikaro": "Sem dados carregados ainda.",
    "vencimentos": "Sem dados carregados ainda.",
    "gastos": "Sem dados carregados ainda."
}

def motor_sincronizacao_background():
    """
    TRABALHADOR SILENCIOSO: Roda em segundo plano no Render.
    A cada 5 minutos, ele vai ao Google Sheets, puxa a tabela inteira 
    de cada link e joga na memória RAM. O robô nunca mais vai travar por timeout!
    """
    global DADOS_PLANILHAS_LOCAL
    print("🔄 [JARVIS ENGINE] Motor de Sincronização em Background Inicializado!")
    
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
    
    while True:
        try:
            google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
            if not google_creds_json:
                print("⚠️ Erro: GOOGLE_CREDS_JSON não configurado nas variáveis de ambiente.")
                time.sleep(30)
                continue
                
            creds_dict = json.loads(google_creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            for chave, url in MAPA_LINKS.items():
                try:
                    planilha = client.open_by_url(url)
                    aba = planilha.get_worksheet(0) # Pega a primeira aba principal por padrão
                    valores = aba.get_all_values()
                    
                    if valores:
                        linhas_formatadas = []
                        for idx, linha in enumerate(valores[:100]): # Lê até 100 linhas por segurança
                            linhas_formatadas.append(f"Linha {idx+1}: " + " | ".join([str(c) for c in linha]))
                        
                        DADOS_PLANILHAS_LOCAL[chave] = f"Planilha: [{planilha.title}] -> Aba: [{aba.title}]. Dados:\n" + "\n".join(linhas_formatadas)
                    print(f"✅ Sincronizado com Sucesso: {chave}")
                except Exception as inner_e:
                    print(f"⚠️ Falha ao sincronizar chave {chave}: {str(inner_e)}")
                    
            print(f"⚡ [CACHE REFRESHED] Todas as planilhas guardadas localmente na RAM às {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"❌ Erro geral no motor de sincronização: {str(e)}")
            
        time.sleep(300) # Dorme por 5 minutos antes de buscar de novo

# =====================================================================
# 3. FUNÇÃO DO PROMPT DA IA: CONSULTA LOCAL INSTANTÂNEA
# =====================================================================
def consultar_banco_local_jarvis(tipo_controle: str, dono_carteira: str = "elias") -> str:
    """
    Função que o Gemini aciona. Ela responde em milissegundos puxando o dado 
    que o trabalhador de background salvou na memória RAM.
    """
    global DADOS_PLANILHAS_LOCAL
    tipo = tipo_controle.lower().strip()
    dono = dono_carteira.lower().strip() if dono_carteira else "elias"
    
    chave = ""
    if "emprestimo" in tipo:
        chave = f"emprestimo_{dono}"
    elif tipo in ["vendas", "venda", "eletronicos", "eletronico"]:
        chave = f"vendas_{dono}"
    elif "vencimento" in tipo:
        chave = "vencimentos"
    elif "gasto" in tipo or "custo" in tipo:
        chave = "gastos"
        
    dados = DADOS_PLANILHAS_LOCAL.get(chave, "Aviso: Planilha solicitada não foi mapeada no sistema.")
    return dados

# =====================================================================
# 4. CONFIGURAÇÃO DA ARQUITETURA MULTI-AGENTE DO JARVIS (ITEM 3)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[consultar_banco_local_jarvis],
    system_instruction=(
        f"Você é o JARVIS, o sistema de inteligência artificial de alta performance e braço direito do Elias Fernandes Borges Junior.\n"
        f"DATA CONTEXTUAL ABSOLUTA: Hoje é {datetime.now().strftime('%A, %d de %B de %Y')}. O ano corrente é {datetime.now().year}.\n\n"
        "Sua mente opera através de 3 SUB-AGENTES ESPECIALISTAS internos que trabalham em conjunto:\n"
        "1. AGENTE LÍDER DE DIÁLOGO: Controla a conversa de forma descontraída, confiante e extremamente parceira. Você fala como um humano genial (estilo o Jarvis do Homem de Ferro), usando termos de negócios leves e respondendo com fluidez. Esqueça textos quadrados ou robóticos.\n"
        "2. AGENTE AUDITOR DE CRÉDITO E PARCELAS: Domina a matemática das tabelas. Sabe fazer varreduras completas nas linhas e colunas. Sabe que nas abas de clientes (linha 5 para baixo), a Coluna A = Qtd parcelas (iniciando na linha 9), Coluna B = Vencimento, Coluna C = Valor, Coluna E = Status ('Sim'/'sim' significa PAGO. Vazio ou 'Não' significa EM ABERTO).\n"
        "3. AGENTE ESTRATEGISTA DE FLUXO DE CAIXA: Compara as datas das parcelas com o dia de hoje, calcula quantos dias estão atrasados, calcula faturamentos futuros e dá insights financeiros reais.\n\n"
        "DIRETRIZ DE AÇÃO ANTECIPADA:\n"
        "Se o Elias pedir para olhar as planilhas, os empréstimos ou as vendas de forma genérica, NÃO faça perguntas de confirmação. Acione imediatamente a ferramenta 'consultar_banco_local_jarvis' para recolher as informações necessárias das carteiras relevantes e monte a resposta por iniciativa própria.\n\n"
        "PADRÃO VISUAL OBRIGATÓRIO DE EXIBIÇÃO (SEPARADO POR OPERADOR):\n"
        "Sempre organize os dados financeiros agrupados por Operador (Elias, Erick, Ikaro). Deixe o texto respirar usando espaçamentos. Siga rigorosamente este modelo estruturado:\n\n"
        "Fala, Elias! [Introdução inteligente e natural sobre o cenário atual...]\n\n"
        "### 👤 CARTEIRA: [NOME DO OPERADOR]\n"
        "[Aviso de status curto, ex: ⚠️ Atenção ou 👍 Tudo Limpo]\n"
        "• *Nome do Cliente / Item*\n"
        "  - *Vencimento*: DD/MM/AAAA\n"
        "  - *Status*: 🔴 ATRASADO (X dias) | 🟢 EM DIA (Vence em X dias) | 🔵 PAGO\n"
        "  - *Valor*: R$ XX,XX\n\n"
        "### 📊 RESUMO DO DIA (Insights do Jarvis):\n"
        "[Seu panorama focado em estratégia, metas de cobrança e injeção de caixa no final]."
    )
)

chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)

# =====================================================================
# 5. TRATAMENTO DE MENSAGENS DO TELEGRAM (Blindagem de Erros)
# =====================================================================
@bot.message_handler(func=lambda message: True)
def processar_mensagem(message):
    global chat_ia
    chat_id = message.chat.id
    texto_usuario = message.text
    
    bot.send_chat_action(chat_id, 'typing')

    try:
        resposta_ia = chat_ia.send_message(texto_usuario)
        # Tentativa em Markdown para manter o visual premium do painel do Jarvis
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        # Se o Markdown falhar por caracteres especiais da IA, envia em formato de texto limpo de segurança
        try:
            bot.send_message(chat_id, resposta_ia.text)
        except:
            bot.send_message(chat_id, f"⚠️ Jarvis indisponível no momento: {str(e)}")

# =====================================================================
# 6. INICIALIZAÇÃO DOS MOTORES E SERVIDOR FALSO
# =====================================================================
def rodar_servidor_falso():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    # 1. Liga o motor de sincronização em segundo plano (Item 4)
    threading.Thread(target=motor_sincronizacao_background, daemon=True).start()
    
    # 2. Liga o servidor para manter o Render feliz
    threading.Thread(target=rodar_servidor_falso, daemon=True).start()
    
    print("🧠 [JARVIS CENTRAL] Sistema Multi-Agente & Cache local operando na porta 10000...")
    bot.infinity_polling()
