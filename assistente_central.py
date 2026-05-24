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

# Inicializa o Bot do Telegram
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Inicializa a API do Gemini
genai.configure(api_key=GEMINI_API_KEY)

# =====================================================================
# 2. FERRAMENTA DE BUSCA MULTI-PLANILHAS
# =====================================================================
def consultar_google_sheets(nome_da_planilha: str, aba_nome: str, termo_busca: str) -> str:
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        planilha = client.open(nome_da_planilha)
        aba = planilha.worksheet(aba_nome)
        celula = aba.find(termo_busca)
        if celula:
            dados_linha = aba.row_values(celula.row)
            return f"Sucesso! Dados encontrados: {dados_linha}"
        return f"Aviso: O termo '{termo_busca}' não foi encontrado."
    except Exception as e:
        return f"Erro ao acessar o Google Sheets: {str(e)}"

# =====================================================================
# 3. CONFIGURAÇÃO DO MOTOR DO GEMINI (Versão Alternativa Direta)
# =====================================================================
# Em vez de criar o chat global que pode falhar na inicialização, 
# vamos tentar criar a conversa com o nome padrão recomendado pelo Google
try:
    modelo_central = genai.GenerativeModel(
        model_name='gemini-pro', # Forçando o modelo clássico pro que nunca falha em versões antigas
        tools=[consultar_google_sheets]
    )
    chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)
except Exception as e:
    chat_ia = None
    print(f"Erro ao inicializar modelo principal: {e}")

# =====================================================================
# 4. TRATAMENTO DE MENSAGENS DO TELEGRAM
# =====================================================================
@bot.message_handler(func=lambda message: True)
def processar_mensagem(message):
    global chat_ia
    chat_id = message.chat.id
    texto_usuario = message.text
    
    bot.send_chat_action(chat_id, 'typing')
    
    # COMANDO SECRETO PARA DESCOBRIR OS MODELOS
    if texto_usuario.lower() == "lista":
        try:
            modelos = [m.name for m in genai.list_models()]
            lista_texto = "\n".join(modelos)
            bot.send_message(chat_id, f"📋 Modelos disponíveis na sua conta:\n\n{lista_texto}")
            return
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Erro ao listar modelos: {str(e)}")
            return

    # Se o chat_ia falhou na inicialização, tentamos criar um básico aqui dentro
    if chat_ia is None:
        try:
            modelo_central = genai.GenerativeModel(model_name='gemini-1.5-flash')
            chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Falha crítica ao ligar o Gemini: {str(e)}")
            return

    try:
        resposta_ia = chat_ia.send_message(texto_usuario)
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Erro ao processar o comando da IA: {str(e)}")

# =====================================================================
# 5. INICIALIZAÇÃO E SERVIDOR FALSO PARA O RENDER
# =====================================================================
def rodar_servidor_falso():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=rodar_servidor_falso, daemon=True).start()
    print("🧠 Assistente pronto e escutando...")
    bot.infinity_polling()
