import os
from dotenv import load_dotenv
import yaml
from pyprojroot import here
from langchain_openai import ChatOpenAI
load_dotenv()

with open(here("configs/config.yml")) as cfg:
    app_config = yaml.load(cfg, Loader=yaml.FullLoader)


class LoadConfig:
    def __init__(self) -> None:
        # Databases directories
        self.local_file = here(app_config["directories"]["local_file"])
        os.environ['OPENAI_API_KEY'] = os.getenv("OPEN_AI_API_KEY")
        
        self.llm = ChatOpenAI(model=app_config["openai_models"]["model"], base_url="https://api.vsegpt.ru/v1" )
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
        os.environ["LANGCHAIN_TRACING_V2"] = str(
            app_config["langsmith"]["tracing"])
        os.environ["LANGCHAIN_PROJECT"] = str(
            app_config["langsmith"]["project_name"])