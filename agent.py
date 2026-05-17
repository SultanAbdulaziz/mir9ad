from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

import os
load_dotenv()

llm = ChatOpenAI(model="gpt-4o",
                 api_key= os.getenv("GITHUB_TOKEN"),
                 base_url=os.getenv("GITHUB_API_URL"))


