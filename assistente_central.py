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
    """
    Busca informações em qualquer planilha e aba do Google Sheets.
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # Pega as credenciais JSON da variável de ambiente
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        creds_dict = json.loads(google_creds_json)
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Abre a planilha específica indicada pelo Gemini
        planilha = client.open(nome_da_planilha)
        aba = planilha.worksheet(aba_nome)
        
        # Procura pelo termo solicitado
        celula = aba.find(termo_busca)
        if celula:
            dados_linha = aba.row_values(celula.row)
            return f"Sucesso! Na planilha '{nome_da_planilha}' -> aba '{aba_nome}', dados encontrados: {dados_linha}"
        return f"Aviso: O termo '{termo_busca}' não foi encontrado na aba '{aba_nome}' da planilha '{nome_da_planilha}'."
    except Exception as e:
        return f"Erro ao acessar o Google Sheets: {str(e)}"

# =====================================================================
# 3. CONFIGURAÇÃO DO MOTOR DO GEMINI (Global)
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    tools=[consultar_google_sheets],
    system_instruction=(
        "Você é o Assistente Executivo Central do Elias. Seu objetivo é gerenciar a vida pessoal, "
        "contas e os múltiplos negócios dele (minimarket, empréstimos, eletrônicos) através de suas planilhas.\n\n"
        "Regras Importantes:\n"
        "1. O Elias possui cerca de 8 planilhas diferentes no Google Drive. Use a ferramenta 'consultar_google_sheets' passando o nome exato da planilha, a aba e o termo de busca.\n"
        "2. Se você não tiver certeza de qual das 8 planilhas abrir, pergunte educadamente para ele antes de tentar adivinhar.\n"
        "3. Interprete os dados recebidos e organize em um resumo financeiro limpo.\n"
        "4. Seja sempre direto, profissional e responda usando formatação Markdown."
    )
)

# Criamos o chat de forma GLOBAL para que o interceptador do Telegram consiga ler sempre
chat_ia = modelo_central.start_chat(enable_automatic_function_calling=True)

# =====================================================================
# 4. TRATAMENTO DE MENSAGENS DO TELEGRAM
# =====================================================================
@bot.message_handler(func=lambda message: True)
def processar_mensagem(message):
    chat_id = message.chat.id
    texto_usuario = message.text
    
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        # Agora o chat_ia global será reconhecido perfeitamente aqui dentro
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
        print(f"🌍 Servidor Falso rodando na porta {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Liga o servidor web falso em segundo plano para o Render não dar timeout
    threading.Thread(target=rodar_servidor_falso, daemon=True).start()
    
    # Liga o Bot do Telegram
    print("🧠 Assistente Multi-Planilhas pronto e escutando no Telegram...")
    bot.infinity_polling()
