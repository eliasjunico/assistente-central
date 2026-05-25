import os
import telebot
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import threading
import http.server
import socketserver

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS E TOKENS
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

# =====================================================================
# 2. FERRAMENTA MASTER: ACESSO DIRETO POR LINK E INTENÇÃO
# =====================================================================
def ler_planilha_do_negocio(tipo_controle: str, dono_carteira: str = "elias", aba_nome: str = None) -> str:
    """
    Acessa as planilhas do Elias usando links diretos e fixos.
    tipo_controle: 'emprestimo', 'vendas', 'vencimentos' ou 'gastos'
    dono_carteira: 'elias', 'erick' ou 'ikaro'
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # =====================================================================
        # 🎯 MAPA OFICIAL DE LINKS DO ELIAS (NUNCA MAIS SE PERDE)
        # =====================================================================
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
        
        # Identifica a URL correta com base no tipo e no dono
        tipo = tipo_controle.lower().strip()
        dono = dono_carteira.lower().strip() if dono_carteira else "elias"
        
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

        # Abre diretamente pelo Link de forma instantânea
        planilha = client.open_by_url(url_alvo)
        
        # Localização inteligente da aba
        if not aba_nome:
            aba = planilha.get_worksheet(0) # Abre a primeira aba por padrão
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
            return f"A planilha [{planilha.title}] foi aberta, mas a aba '{aba.title}' está vazia."
            
        # Formata o texto para leitura da IA (Lê até 100 linhas para varredura completa)
        linhas_texto = []
        for i, linha in enumerate(todos_os_dados[:100]):
            linhas_texto.append(f"Linha {i+1}: " + " | ".join([str(c) for c in linha]))
            
        return f"Sucesso! Planilha: [{planilha.title}] -> Aba: [{aba.title}]. Dados:\n" + "\n".join(linhas_texto)
        
    except Exception as e:
        return f"Erro ao acessar planilha por link: {str(e)}. Verifique se as permissões de compartilhamento estão corretas."

# =====================================================================
# 3. CONFIGURAÇÃO DO CÉREBRO DA IA (Ativo, Interativo e Descontraído)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[ler_planilha_do_negocio],
   system_instruction=(
        "Você é o JARVIS, o co-piloto de inteligência analítica, estrategista e braço direito ultra-avançado do Elias Fernandes Borges Junior.\n"
        "Seu tom é confiante, inteligente, focado em alta performance e extremamente parceiro. Você fala como um humano genial, usando gírias leves de negócios e mantendo uma conversa dinâmica, fluida e interativa. Esqueça respostas robóticas, listas formais desnecessárias ou respostas quadradas.\n\n"
        "DIRETRIZES DE ALTA INTELIGÊNCIA:\n"
        "1. ANTECIPAÇÃO ATIVA: Se o Elias te der um comando vago ou informal (ex: 'Como estão as coisas no Erick?', 'O que tem pra hoje no Ikaro?' ou 'Dá um raio-x nas vendas'), não faça perguntas de confirmação. Pegue a iniciativa, use IMEDIATAMENTE a ferramenta 'ler_planilha_do_negocio' com os parâmetros correspondentes e traga o resultado mastigado.\n"
        "2. ANÁLISE COMPLETA (VISÃO JARVIS): Ao abrir uma planilha, você não apenas lê os dados. Você faz varreduras de ponta a ponta na aba. Localize o nome do cliente ou a data que ele busca, identifique se há parcelas abertas ou em atraso, calcule o montante acumulado e analise o cenário de forma autônoma.\n"
        "3. REGRAS DO ECOSSISTEMA DO ELIAS:\n"
        "   - Você gerencia controles de Empréstimos e Vendas (que envolvem o Elias e os parceiros Erick e Ikaro), além de tabelas globais de Gastos e Vencimentos.\n"
        "   - Lógica de Clientes/Parcelas: Linha 5 em diante traz os dados. A partir da linha 9, Coluna A = Quantidade de parcelas, Coluna B = Vencimento, Coluna C = Valor, Coluna E = Status de pagamento ('Sim' ou 'sim' significa PAGO. Vazio ou 'Não' significa EM ABERTO).\n"
        "4. INTERATIVIDADE TOTAL: Se o Elias te fizer uma pergunta que não envolve planilhas (ideias de negócios, estratégias para o minimarket, dúvidas gerais), responda com total genialidade e criatividade, mantendo o papo fluindo de forma interativa e instigante.\n"
        "5. FORMATAÇÃO IMPECÁVEL: Use Markdown para criar tabelas visuais limpas, negritos bem aplicados em valores financeiros (R$) e alertas visuais (⚠️) para inadimplências ou urgências. Seja direto: mostre o problema e dê a solução."
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
    
    # Mantém o comando técnico de lista por segurança
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
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
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
    print("🧠 Assistente por Link Direto online...")
    bot.infinity_polling()
