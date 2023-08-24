import os
import logging
from dotenv import load_dotenv
from heyoo import WhatsApp
from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import TextLoader
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
# from langchain.retrievers import RetrievalQA
from langchain.chains import ConversationChain, LLMChain,RetrievalQA
from langchain.schema import SystemMessage
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)

import uvicorn
from fastapi import (
  FastAPI,
  Request,
  Response,
  BackgroundTasks
)

# load env data
load_dotenv()

# messenger object
messenger = WhatsApp(
  os.getenv("WHATSAPP-TOKEN"),
  phone_number_id=os.getenv("PHONE-NUMBER-ID") )
# open ai key
os.environ["OPENAI_API_KEY"]=os.getenv("OPENAI-API-KEY")
VERIFY_TOKEN = "30cca545-3838-48b2-80a7-9e43b1ae8ce4"

#Flask app 
app=FastAPI()



# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# load document from documents folder. I will load only .txt files
loader=DirectoryLoader("./documents/",glob="*.txt")
documents = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
texts = text_splitter.split_documents(documents)
retriever = FAISS.from_documents(texts, OpenAIEmbeddings()).as_retriever()

system_custom_prompt = """You are helpful chatbot. 
You are to respond to  Questions with answers from the document given"""

prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=system_custom_prompt),
        HumanMessagePromptTemplate.from_template(
            "{human_input}"
        ),
    ]
)

llm=ChatOpenAI(
   temperature=0,
   max_tokens=512, 
   model_name="gpt-3.5-turbo"
   )

conversation = LLMChain(
        llm=llm,
        prompt=prompt
    )

def get_chatgpt_response(query_str:str):
  qa=RetrievalQA.from_chain_type(llm=llm,chain_type="stuff",retriever=retriever)
  response=qa.run(query_str)    
  return response


def respond(message:str,mobile:str):
    response=str(get_chatgpt_response(message))

    messenger.send_message(response,mobile)
    logging.info("Response sent to %s", mobile)


@app.get("/")
async def webhook_verification(request:Request):
    if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        content=request.query_params.get("hub.challenge")
        logging.info("Verified webhook")
        return Response(content=content, media_type="text/plain", status_code=200)
    
    logging.error("Webhook Verification failed")
    return "Invalid verification token"

@app.post("/")
async def webhook_handler(request:Request,task:BackgroundTasks):

  # get message update.. we want only to work with text only
  data = await request.json()

  logging.info("Received data: %s",data)
  changed_field = messenger.changed_field(data)
  
  if changed_field == "messages":
    new_message = messenger.get_mobile(data)
    if new_message:
      mobile = messenger.get_mobile(data)
      message_type = messenger.get_message_type(data)

      # mark as read
      message_id = messenger.get_message_id(data)
      messenger.mark_as_read(message_id)

      if message_type == "text":
        message = messenger.get_message(data)
        # Add the task as background tasks as it may take time to generate response
        #  then acknowledge to whatsapp that you receive the message
        # to avoid receiving the same message again 
        task.add_task(respond, message,mobile)
      else:
        messenger.send_message(message="Please send me text messages",recipient_id=mobile)
        
  return "ok"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)