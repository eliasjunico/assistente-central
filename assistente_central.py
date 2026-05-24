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
# 2. FERRAMENTA INTELIGENTE: LEITURA COMPLETA DE ABA
# =====================================================================
def ler_aba_completa(nome_da_planilha: str, aba_nome: str) -> str:
    """
    Puxa TODOS os dados de uma aba específica para a IA analisar de forma inteligente.
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Abre a planilha e pega todas os valores da aba de uma vez
        planilha = client.open(nome_da_planilha)
        aba = planilha.worksheet(aba_nome)
        todos_os_dados = aba.get_all_values()
        
        if not todos_os_dados:
            return f"Aviso: A aba '{aba_nome}' na planilha '{nome_da_planilha}' está totalmente vazia."
            
        # Transforma a tabela em um formato de texto limpo que a IA adora ler
        resultado_texto = f"--- DADOS DA PLANILHA '{nome_da_planilha}' -> ABA '{aba_nome}' ---\n"
        for linha in todos_os_dados[:100]: # Limite seguro de 100 linhas para não estourar a memória
            resultado_texto += " | ".join([str(celula) for celula in linha]) + "\n"
            
        return resultado_texto
    except Exception as e:
        return f"Erro ao acessar o Google Sheets: {str(e)}"

# =====================================================================
# 3. CONFIGURAÇÃO DO MOTOR DO GEMINI (Modo Consultor Avançado)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-2.5-flash',
    tools=[ler_aba_completa],
    system_instruction=(
        "Você é o braço direito, estrategista e Assistente Executivo Central do Elias.\n"
        "Seu objetivo é gerenciar e analisar os múltiplos negócios e finanças dele de forma extremamente inteligente, proativa e madura.\n\n"
        "DIRETRIZES DE INTELIGÊNCIA:\n"
        "1. Você NÃO é quadrado. Compreenda a intenção do Elias mesmo que ele use gírias, abreviações ou digite com erros de digitação.\n"
        "2. O Elias possui cerca de 8 planilhas de controle (Ex: minimarket, empréstimos, eletrônicos, gestão, roupas). Quando ele pedir um dado, use a ferramenta 'ler_aba_completa' informando o nome da planilha e a aba correspondente.\n"
        "3. Você tem a capacidade de ver a aba INTEIRA. Portanto, faça cálculos, identifique tendências, avise sobre parcelas vencidas, calcule margens (CMV), ponto de equilíbrio e faturamento de forma autônoma.\n"
        "4. Mapeamento de contexto conhecido: O Elias trabalha com parceiros/intermediários chamados Erick e Ikaro que gerenciam carteiras de empréstimos e eletrônicos. Nas abas de clientes (como a linha 5 em diante), a coluna A costuma ter a Quantidade de parcelas (iniciando na linha 9), coluna B o Vencimento, coluna C o Valor e coluna E o status de pagamento ('Sim' ou 'Não'). Use essa lógica para analisar planilhas desse tipo.\n"
        "5. Responda sempre de forma direta, executiva, organizada em tópicos (Markdown) e com insights reais sobre o que você encontrou."
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
    
    # Mantém o comando de lista caso precise
    if texto_usuario.lower() == "lista":
        try:
            modelos = [m.name for m in genai.list_models()]
            quebra_linha = "\n"
            lista_modelos_texto = quebra_linha.join(modelos)
            bot.send_message(chat_id, f"📋 Modelos disponíveis na sua conta:\n\n{lista_modelos_texto}")
            return
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Erro ao listar modelos: {str(e)}")
            return

    try:
        resposta_ia = chat_ia.send_message(texto_usuario)
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Erro ao processar o comando da IA: {str(e)}")

# =====================================================================
# 5. INICIALIZAÇÃO E SERVIDOR FALSO
# =====================================================================
def rodar_servidor_falso():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=rodar_servidor_falso, daemon=True).start()
    print("🧠 Assistente de Contexto Avançado pronto...")
    bot.infinity_polling()
