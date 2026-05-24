import os
import telebot
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS E TOKENS (Pronto para Variáveis de Ambiente)
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
    
    Parâmetros:
    - nome_da_planilha: O nome exato do arquivo da planilha no Google Drive (ex: 'Controle de Empréstimos', 'Vendas Eletrônicos').
    - aba_nome: O nome da aba dentro dessa planilha (ex: 'Erick', 'Ikaro', 'Vencimentos').
    - termo_busca: O texto, nome de cliente ou conta que deseja encontrar na linha.
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # Pega as credenciais JSON seguras da variável de ambiente
        google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        creds_dict = json.loads(google_creds_json)
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Abre a planilha específica que o Gemini escolheu buscar
        planilha = client.open(nome_da_planilha)
        aba = planilha.worksheet(aba_nome)
        
        # Procura pelo termo solicitado
        celula = aba.find(termo_busca)
        if celula:
            dados_linha = aba.row_values(celula.row)
            return f"Sucesso! Na planilha '{nome_da_planilha}' -> aba '{aba_nome}', dados encontrados para '{termo_busca}': {dados_linha}"
        return f"Aviso: O termo '{termo_busca}' não foi encontrado na aba '{aba_nome}' da planilha '{nome_da_planilha}'."
    except gspread.exceptions.SpreadsheetNotFound:
        return f"Erro: A planilha chamada '{nome_da_planilha}' não foi encontrada. Certifique-se de que o nome está correto e que ela foi compartilhada com o e-mail da conta de serviço."
    except Exception as e:
        return f"Erro ao acessar o Google Sheets: {str(e)}"

# =====================================================================
# 3. CONFIGURAÇÃO DO MOTOR DO GEMINI
# =====================================================================
modelo_central = genai.GenerativeModel(
    model_name='models/gemini-1.5-flash',
    tools=[consultar_google_sheets], # Acopla a nova ferramenta flexível
    system_instruction=(
        "Você é o Assistente Executivo Central do Elias. Seu objetivo é gerenciar a vida pessoal, "
        "contas e os múltiplos negócios dele (minimarket, empréstimos, eletrônicos) através de suas planilhas.\n\n"
        "Regras Importantes:\n"
        "1. O Elias possui cerca de 8 planilhas diferentes no Google Drive. Quando ele te pedir algo, identifique de qual assunto se trata, deduza qual planilha deve ser aberta e use a ferramenta 'consultar_google_sheets' passando o nome exato da planilha, a aba e o termo de busca.\n"
        "2. Se você não tiver certeza de qual das 8 planilhas abrir, pergunte educadamente para ele antes de chutar.\n"
        "3. Interprete os dados recebidos. Se a linha contiver valores de parcelas e datas, organize isso em um resumo financeiro limpo.\n"
        "4. Seja sempre direto, profissional e responda usando formaturamento Markdown (negritos, listas, tabelas e alertas ⚠️)."
    )
)

# Inicia o chat ativo com chamadas automáticas de função
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
        resposta_ia = chat_ia.send_message(texto_usuario)
        bot.send_message(chat_id, resposta_ia.text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Erro ao processar o comando da IA: {str(e)}")

# =====================================================================
# 5. INICIALIZAÇÃO E SERVIDOR FALSO PARA O RENDER
# =====================================================================
import threading
import http.server
import socketserver

def rodar_servidor_falso():
    """Cria um servidor web simples para enganar o Render e manter o plano grátis"""
    PORT = int(os.environ.get("PORT", 10000)) # O Render injeta a porta automaticamente
    Handler = http.server.SimpleHTTPRequestHandler
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌍 Servidor Falso rodando na porta {PORT} para o Render.")
        httpd.serve_forever()

if __name__ == "__main__":
    # 1. Liga o servidor web falso em segundo plano
    threading.Thread(target=rodar_servidor_falso, daemon=True).start()
    
    # 2. Liga o seu Bot do Telegram principal
    print("🧠 Assistente Multi-Planilhas pronto e escutando no Telegram...")
    bot.infinity_polling()
