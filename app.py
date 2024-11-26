import pdfplumber
from flask import Flask, request, jsonify, abort
from langchain.prompts import PromptTemplate
from langchain_openai import OpenAI
from langchain.chains import LLMChain
from flask_cors import CORS
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from pymongo import MongoClient
from dotenv import load_dotenv




# Carregar variáveis de ambiente
load_dotenv()




# Configuração da API OpenAI
openai_api_key = ''
llm = OpenAI(openai_api_key=openai_api_key)






# Configuração do MongoDB Atlas
atlas_uri = ''  # URL de conexão do MongoDB Atlas
client = MongoClient(atlas_uri)  # Usando a URI do MongoDB Atlas
db = client["vitoriagomes1510"]  # Nome do banco de dados no MongoDB
resume_collection = db["resume_database"]  # Coleção de currículos
faq_collection = db["faq"]  # Coleção de FAQs




# Configuração do Flask
app = Flask(__name__)
CORS(app)




# Função para enriquecer o prompt com dados do FAQ
def enrich_prompt_with_faq():
    """
    Função que busca as primeiras 10 perguntas e respostas da coleção FAQ
    e as formata em um texto para ser incluído no prompt de análise de currículo.


    Retorna:
        str: Texto formatado com as FAQs.
    """
    try:
        faqs = list(faq_collection.find({}, {"_id": 0}).limit(10))
    except Exception as e:
        print("Erro ao acessar o banco de dados:", e)
        faqs = []  # Defina um valor padrão ou exiba uma mensagem amigável


    # Formatar as FAQs em uma string para ser usada no prompt
    faq_text = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs])
    return faq_text  # Retorne o texto gerado


   




# Configuração do PromptTemplate e OutputParser do LangChain
response_schemas = [
    ResponseSchema(name="level", description="Nível de adequação (Aprovado, A ser revisado, Rejeitado)"),
    ResponseSchema(name="justification", description="Justificativa para a classificação"),
    ResponseSchema(name="suggestions", description="Sugestões para melhorias no currículo")
]




# Criar o parser de saída estruturada
output_parser = StructuredOutputParser.from_response_schemas(response_schemas)




# Configuração do PromptTemplate
prompt_template = PromptTemplate(
    input_variables=["resume_text", "faq_context"],
    template="""
    Você é um assistente de recrutamento. Use as informações abaixo como contexto adicional:




    FAQ:
    {{"faq_context"}}




    Currículo:
    {{"resume_text"}}




    Classifique o currículo e forneça uma saída estruturada nos seguintes campos:  
    """
)




# Definir a cadeia LLM
chain = prompt_template | llm






# Função para extrair texto do PDF usando pdfplumber
def extract_text_from_pdf(file):
    """
    Função para extrair o texto de um arquivo PDF utilizando a biblioteca pdfplumber.




    Parâmetros:
        file (werkzeug.FileStorage): O arquivo PDF enviado pelo usuário.




    Retorna:
        str: Texto extraído do PDF.




    Levanta:
        Exception: Caso ocorra um erro na extração do texto ou o PDF esteja vazio.
    """
    try:
        with pdfplumber.open(file) as pdf:
            text = ''.join([page.extract_text() for page in pdf.pages if page.extract_text()])
            if not text:
                raise Exception("Nenhum texto encontrado no PDF.")
            return text
    except Exception as e:
        raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")









# Função para analisar currículos
def analyze_resume(resume_text):
    """
    Função que usa o modelo de linguagem para analisar o currículo e gerar uma avaliação
    com base nas informações fornecidas e no contexto das FAQs.


    Parâmetros:
        resume_text (str): O texto do currículo a ser analisado.


    Retorna:
        dict: A análise do currículo, contendo os campos 'level', 'justification' e 'suggestions'.
    """  
    try:
        faq_context = enrich_prompt_with_faq()
        if not faq_context:
            raise ValueError("Contexto FAQ está vazio.")
       
        # Executando a cadeia do LangChain
        chain = LLMChain(llm=llm, prompt=prompt_template)
        raw_output = chain.run(resume_text=resume_text, faq_context=faq_context)
       
        # Adicionando o print para debugar a saída do LLM
        print("Raw output:", raw_output)  # Verifique o que é retornado pelo LLM
       
        # Agora tente parsear a saída com o parser
        pased_output = output_parser.parse(raw_output)
        return pased_output
    except Exception as e:
        raise Exception(f"Erro ao analisar currículo: {str(e)}")










# Rota para upload e análise do currículo
@app.route('/upload', methods=['POST'])
def upload_resume():
    """
    Endpoint para o upload de currículos em formato PDF e sua análise.




    Retorna:
        JSON: Mensagem de sucesso ou erro com a análise do currículo.
    """
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400




    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Apenas arquivos PDF são suportados"}), 400




    try:
        resume_text = extract_text_from_pdf(file)
    except Exception as e:
        return jsonify({"error": f"Erro ao processar o PDF: {str(e)}"}), 500




    try:
        analysis = analyze_resume(resume_text)
        resume_data = {
            "text": resume_text,
            "analysis": analysis
        }
        resume_collection.insert_one(resume_data)
        return jsonify({
            "message": "Currículo processado com sucesso",
            "analysis": analysis
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao analisar currículo: {str(e)}"}), 500








# Rota para recuperar currículos processados
@app.route('/resumes', methods=['GET'])
def get_resumes():
    """
    Endpoint para listar todos os currículos processados e armazenados.




    Retorna:
        JSON: Lista de currículos armazenados.
    """
    resumes = list(resume_collection.find({}, {"_id": 0}))
    return jsonify(resumes)




# Rota para gerenciar FAQ (adicionar novo FAQ)
@app.route('/faq', methods=['POST'])
def add_faq():
    """
    Endpoint para adicionar uma nova FAQ à coleção.




    Retorna:
        JSON: Mensagem de sucesso ou erro ao adicionar uma FAQ.
    """
    data = request.get_json()
    if not data or "question" not in data or "answer" not in data:
        return jsonify({"error": "Campos 'question' e 'answer' são obrigatórios."}), 400
    faq_collection.insert_one(data)
    return jsonify({"message": "FAQ adicionado com sucesso"}), 201




# Rota para listar FAQs
@app.route('/faq', methods=['GET'])
def list_faqs():
    """
    Endpoint para listar todas as FAQs armazenadas.




    Retorna:
        JSON: Lista de FAQs.
    """
    faqs = list(faq_collection.find({}, {"_id": 0}))
    return jsonify(faqs)




@app.route('/chat', methods=['POST'])
def chat():
    """
    Endpoint para simular um chat com base nas informações das FAQs e um texto de entrada.




    Retorna:
        JSON: Resposta gerada pela análise do chat.
    """
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "O campo 'message' é obrigatório."}), 400




    user_message = data["message"]
   
    # Criação do prompt para o chat
    faq_context = enrich_prompt_with_faq()  # Garantir que o contexto da FAQ seja gerado uma vez
    try:
        chain = LLMChain(llm=llm, prompt=prompt_template)
        response = chain.run(resume_text=user_message, faq_context=faq_context)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": f"Erro ao gerar resposta: {str(e)}"}), 500




@app.before_request
def enforce_http():
    if request.scheme != 'http':
        abort(400)


@app.route("/")
def home():
    return "Servidor rodando corretamente."


# Iniciar o servidor com HTTPS
if __name__ == '__main__':
    app.run(debug=True)