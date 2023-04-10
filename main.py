import os
import logging
from dotenv import load_dotenv
from heyoo import WhatsApp
from langchain import OpenAI
from flask import (
  Flask,
  request, 
  make_response,
)
from llama_index import (
  GPTSimpleVectorIndex,
  SimpleDirectoryReader,
  LLMPredictor,
  ServiceContext,
  QuestionAnswerPrompt,
)

# load env data
load_dotenv()

# messenger object
messenger = WhatsApp(
  os.environ["whatsapp_token"],
  phone_number_id=os.environ["phone_number_id"] )

#Flask app 
app=Flask(__name__)


VERIFY_TOKEN = "30cca545-3838-48b2-80a7-9e43b1ae8ce4"

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# open ai key
os.environ["OPENAI_API_KEY"]=os.environ["openai_key"]

# add predictor

llm_predictor = LLMPredictor(llm=OpenAI(temperature=0, model_name="text-davinci-003"))
# # load document

documents = SimpleDirectoryReader("documents").load_data()

service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
index = GPTSimpleVectorIndex.from_documents(documents, service_context=service_context)

# save index
index.save_to_disk("index.json")

# load saved index
index = GPTSimpleVectorIndex.load_from_disk("index.json")

#custom function 

def respond(query_str:str):
  QA_PROMPT_TMPL = (
    "Context information is below. \n"
    "---------------------\n"
    "{context_str}"
    "\n---------------------\n"
    "Given this information, answer from context, be polite and generate short and clear responses. please answer the question: {query_str}\n"
  )

  QA_PROMPT = QuestionAnswerPrompt(QA_PROMPT_TMPL)

  response = index.query(query_str, text_qa_template=QA_PROMPT)
  
  return response


@app.route("/", methods=["GET", "POST"])
def hook():
  if request.method == "GET":
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        logging.info("Verified webhook")
        response = make_response(request.args.get("hub.challenge"), 200)
        response.mimetype = "text/plain"
        return response
    logging.error("Webhook Verification failed")
    return "Invalid verification token"

  # get message update.. we want only to work with text only
  data = request.get_json()
  logging.info("Received data: $s")
  changed_field = messenger.changed_field(data)
  
  if changed_field == "messages":
    new_message = messenger.get_mobile(data)
    if new_message:
      mobile = messenger.get_mobile(data)
      message_type = messenger.get_message_type(data)

      if message_type == "text":
        message = messenger.get_message(data)
        response=respond(message)
        logging.info(f"\nAnswer: {response}\n")
        messenger.send_message(message=f"{response}",recipient_id=mobile)
      else:
        messenger.send_message(message="Please send me text messages",recipient_id=mobile)
        
  return "ok"


if __name__ == "__main__":
    app.run(debug=True)