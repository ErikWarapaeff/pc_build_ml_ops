import os

import yaml
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pyprojroot import here

load_dotenv()

with open(here("configs/config.yml")) as cfg:
    app_config = yaml.load(cfg, Loader=yaml.FullLoader)


class LoadConfig:
    def __init__(self) -> None:
        # Databases directories
        self.local_file = here(app_config["directories"]["local_file"])
        api_key: str | None = os.getenv("OPEN_AI_API_KEY")
        if api_key is not None:
            os.environ["OPENAI_API_KEY"] = api_key

        self.llm = ChatOpenAI(
            model=app_config["openai_models"]["model"], base_url="https://api.vsegpt.ru/v1"
        )
        langchain_api_key: str | None = os.getenv("LANGCHAIN_API_KEY")
        if langchain_api_key is not None:
            os.environ["LANGCHAIN_API_KEY"] = langchain_api_key

        os.environ["LANGCHAIN_TRACING_V2"] = str(app_config["langsmith"]["tracing"])
        os.environ["LANGCHAIN_PROJECT"] = str(app_config["langsmith"]["project_name"])
