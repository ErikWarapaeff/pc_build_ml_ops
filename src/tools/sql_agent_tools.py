import json
import os
from typing import Any, Literal

from langchain.chains import create_sql_query_chain
from langchain.schema import HumanMessage, SystemMessage
from langchain.sql_database import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.tools import (
    InfoSQLDatabaseTool,
    ListSQLDatabaseTool,
    QuerySQLCheckerTool,
    QuerySQLDatabaseTool,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from pyprojroot import here
from sqlalchemy import create_engine, text

from src.load_config import LoadConfig

CFG = LoadConfig()
db_path = str(here("")) + "\\pc_accessories_2.db"
db_path = f"sqlite:///{db_path}"

engine = create_engine(db_path)
db = SQLDatabase(engine)


class SQLAgentRequest(BaseModel):
    question: str = Field(
        ..., description="Вопрос пользователя, на основе которого нужно сформировать SQL-запрос"
    )
    top_k: int = Field(1, description="Количество примеров для генерации SQL-запроса")
    table_info: str | None = Field(None, description="Информация о таблицах базы данных")


# ------------------- Класс SQLAgent с цепочкой Runnables  -------------------
class SQLAgent:
    def __init__(self, engine, llm: ChatOpenAI | None = None):
        """
        Инициализация SQL-агента.
          - engine: SQLAlchemy engine для подключения к базе.
          - llm: языковая модель (ChatOpenAI). Если не передана, создаётся по умолчанию.

        Все необходимые инструменты создаются внутри агента:
          - QuerySQLDatabaseTool
          - InfoSQLDatabaseTool
          - ListSQLDatabaseTool
          - QuerySQLCheckerTool (требует llm)
        """
        self.engine = engine
        self.llm = CFG.llm or ChatOpenAI(model="gpt-4o-mini")
        # , base_url="https://api.vsegpt.ru/v1"
        # Инициализируем объект базы через LangChain SQLDatabase
        self.db = SQLDatabase(engine)

        # Создаём необходимые инструменты, передавая db
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        self.tools = self.toolkit.get_tools()

        # Извлекаем нужные инструменты
        self.query_tool = next(
            tool for tool in self.tools if isinstance(tool, QuerySQLDatabaseTool)
        )
        self.info_tool = next(tool for tool in self.tools if isinstance(tool, InfoSQLDatabaseTool))
        self.list_tool = next(tool for tool in self.tools if isinstance(tool, ListSQLDatabaseTool))
        self.checker_tool = next(
            tool for tool in self.tools if isinstance(tool, QuerySQLCheckerTool)
        )

        self.final_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a MySQL expert. Given an input question, create a syntactically correct MySQL query "
                    "to run with {top_k} examples (use LIMIT {top_k}). Unless otherwise specified.\n\n"
                    "Here is the relevant table info: {table_info}\n\n"
                    "**Key Rules:**\n"
                    "For abstract/fuzzy requests (e.g. 'найти что-то связанное с X', 'показать всё похожее на Y'):\n"
                    "   - Use `LIKE '%value%'` for text searches\n"
                    "   - Return all matches when no specific filters provided\n\n"
                    "Below are a number of examples of questions and their corresponding SQL queries.",
                ),
                ("human", "{input}"),
            ]
        )

        self.generate_query = create_sql_query_chain(self.llm, self.db, self.final_prompt)

        # Собираем runnable-цепочку через assign:
        self.chain = (
            RunnablePassthrough.assign(
                query=lambda inp: self.generate_query.invoke(inp),
                question=lambda inp: inp["question"],
                top_k=lambda inp: inp["top_k"],
            )
            .assign(query=lambda x: self.clean_sql_query(x["query"]))
            .assign(result=lambda x: self.execute_query_with_retry(x["query"], x["question"]))
        )

    @staticmethod
    def clean_sql_query(query: str) -> str:
        query = query.strip()
        import re

        pattern = r"^```(?:sql)?\s*([\s\S]+?)\s*```$"
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Если не найден блок кода, удаляем все маркеры "```" (на случай, если они остались)
        query = query.replace("```", "")
        return query.strip()

    def query_to_json(self, query: str) -> list:
        """
        Выполняет SQL-запрос через engine и возвращает результат в виде списка словарей.
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]
        return rows

    def execute_query_with_retry(self, query: str, question: str, max_retries: int = 3) -> list:
        """
        Выполняет SQL-запрос с повторными попытками.
        При неудаче переписывает запрос через генерацию нового с помощью checker_tool/info_tool.
        Возвращает результат выполнения запроса в виде списка словарей.
        """
        for attempt in range(max_retries):
            try:
                _ = self.query_tool.run(query)
                return self.query_to_json(query)
            except Exception as e:
                print(f"Попытка {attempt + 1} завершилась ошибкой: {e}")
                if attempt < max_retries - 1:
                    query = self.validate_sql_query(query, question)
                    print(f"Переписываем запрос: {query}")
                else:
                    raise e
        return []

    def validate_sql_query(self, query: str, question: str) -> str:
        """
        Проверяет корректность SQL-запроса через checker_tool.
        Если проверка не проходит, генерирует новый запрос с помощью info_tool и генератора запроса.
        """
        try:
            # Очищаем запрос перед валидацией
            clean_query = self.clean_sql_query(query)
            validated_query = self.checker_tool.run(clean_query)

            # Дополнительная очистка результата
            return self.clean_sql_query(validated_query)

        except Exception as e:
            print(f"Проверка запроса не удалась: {e}")
            table_info = self.info_tool.run("Get all table and column information")
            new_query = self.generate_query.invoke(
                {"question": question, "table_info": table_info, "top_k": 1}
            )

        # Принудительная очистка сгенерированного запроса
        return self.clean_sql_query(str(new_query))

    def run(self, request: SQLAgentRequest) -> dict[str, Any]:
        """
        Основной метод SQL-агента, реализованный через цепочку Runnables.
        Принимает запрос (SQLAgentRequest) и возвращает результат в виде словаря.
        """
        if isinstance(request, dict):
            if "table_info" not in request:
                request["table_info"] = self.info_tool.run("Get all table and column information")
            input_dict = request
        else:
            input_dict = request.model_dump()
            if input_dict.get("table_info") is None:
                input_dict["table_info"] = self.info_tool.run(
                    "Get all table and column information"
                )

        output = self.chain.invoke(input_dict)
        return output  # type: ignore


def parse_user_request(user_input: str) -> str:
    """Парсит пользовательский запрос в структурированный JSON с валидацией"""

    # Pydantic модель внутри функции
    class BuildRequest(BaseModel):
        budget: int
        build_type: Literal["игровая", "офисная"]
        additional_info: dict[str, str] = {}

        @field_validator("build_type")
        def normalize_build_type(self, v):
            build_mapping = {
                "игр": "игровая",
                "гейм": "игровая",
                "стрим": "игровая",
                "монтаж": "игровая",
                "рендер": "игровая",
                "офис": "офисная",
                "работ": "офисная",
                "программ": "офисная",
                "веб": "офисная",
            }
            lower_v = v.lower()
            return next((val for key, val in build_mapping.items() if key in lower_v), "офисная")

    # Исправленный системный промпт с экранированием
    system_prompt = """Ты ИИ-ассистент для парсинга технических запросов. Строго следуй правилам:

        1. **Бюджет**: Число в рублях (200к → 200000)
        2. **Тип сборки** (ТОЛЬКО 2 варианта):
        - "игровая": игры, стримы, монтаж, 3D
        - "офисная": документы, программирование, веб
        3. **Компоненты** (только эти категории):
        - gpu: модели видеокарт (RTX 4080, RX 7900 XT)
        - cpu: модели процессоров (Core i9-14900K, Ryzen 9 7950X)
        - motherboard: чипсеты (Z790, X670)
        - memory: объём RAM (32GB DDR5)
        - corpus: форм-фактор (ATX, Mini-ITX)
        - power_supply: мощность (850W Gold)

        **Правила:**
        - Игнорируй компоненты не из списка
        - Конвертируй требования: "от 12 ГБ" → ">=12GB"
        - Синонимы: "корпус" → corpus, "ОЗУ" → memory
        - Если просят производителя, то укажи модель, например: "Intel" → "cpu Nvidia",
        - Но если просят Nvidea, то укажи: "Nvidia" → "gpu Geforce"

        Примеры:
        Запрос: "Игровой ПК до 300к с RTX 4090 и видеопамятью 24 гб, i9-14900K, корпус ATX с количеством слотов 4 штуки"
        Ответ: {{
        "budget": 300000,
        "build_type": "игровая",
        "additional_info": {{
            "gpu": "RTX 4090",
            "cpu": "i9-14900K",
            "corpus": "form factor ATX and memory slots = 4"
        }}
        }}

        Запрос: "Офисный компьютер с 32GB DDR5 и материнка на B760 и процессор от Intel"
        Ответ: {{
        "budget": 50000,
        "build_type": "офисная",
        "additional_info": {{
            "memory": "32GB",
            "motherboard": "B760",
            "cpu":"Intel"
        }}
        }}

        Запрос: "Сборка для рендеринга: Ryzen 9, 64GB, блок питания 1000W, производитель видеокарты - Nvidia и количество видеопамяти 24GB"
        Ответ: {{
        "budget": 250000,
        "build_type": "игровая",
        "additional_info": {{
            "gpu": "gpu Geforce and memory 24GB",
            "cpu": "Ryzen 9",
            "memory": "64GB",
            "power_supply": "1000"
        }}
        }}

        Текущий запрос: "{input}"
    """

    # Получение ответа от LLM
    openai_api_key_str = os.getenv("OPEN_AI_API_KEY")
    if not openai_api_key_str:
        raise ValueError("API ключ не найден в переменных окружения")
    openai_api_key = SecretStr(openai_api_key_str)

    # Получение ответа от LLM
    client = ChatOpenAI(api_key=openai_api_key, model="gpt-4o-mini")
    response = client.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_input)]
    )

    try:
        raw_content = response.content
        if not isinstance(raw_content, str):
            raise TypeError(
                f"Ожидалось, что содержимое ответа LLM будет строкой для JSON-парсинга, получено: {type(raw_content)}"
            )
        raw_data = json.loads(raw_content)
        validated = BuildRequest(**raw_data).model_dump()

        # Возвращаем строку JSON
        return json.dumps(validated, ensure_ascii=False)  # type: ignore

    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        print(f"Ошибка парсинга или валидации: {e}")
        default_data = BuildRequest(
            budget=50000, build_type="офисная", additional_info={}
        ).model_dump()
        return json.dumps(default_data, ensure_ascii=False)  # type: ignore


@tool
def question_answer_tool(user_input: str) -> str:
    """
    Обрабатывает запрос пользователя, выполняет SQL-запрос и перефразирует ответ в естественный язык.

    Аргументы:
    - user_input (str): Вопрос пользователя, который будет преобразован в SQL-запрос.

    Возвращает:
    - str: Перефразированный ответ на запрос пользователя в удобной для восприятия форме.

    Пример:
    Вход: "Какая цена у Intel Core i9-12900K?"
    Выход: "Цена процессора Intel Core i9-12900K составляет 600 долларов."
    """
    sql_agent = SQLAgent(engine, llm=CFG.llm)  # Создаем экземпляр SQL-агента
    request = SQLAgentRequest(
        question=user_input, top_k=5, table_info=sql_agent.db.get_table_info()
    )

    sql_response = sql_agent.run(request)

    answer_prompt = ChatPromptTemplate.from_template(
        "Вопрос пользователя: {user_question}\n\n"
        "Ответ SQL-агента (JSON): {sql_response}\n\n"
        "Перефразируй этот SQL-ответ, чтобы он звучал естественно для пользователя."
    )
    rephrase_chain = answer_prompt | CFG.llm | StrOutputParser()

    final_answer = rephrase_chain.invoke(
        {"user_question": user_input, "answer_prompt": answer_prompt, "sql_response": sql_response}
    )
    return final_answer


class BuildRequest(BaseModel):
    budget: int
    build_type: str  # например, "игровая" или "офисная"
    additional_info: dict[str, Any] | None = None


def calculate_component_budgets(
    budget: int, build_type: str, components_percentages: dict[str, dict[str, float]]
) -> dict[str, int]:
    """
    Распределяет общий бюджет между компонентами в зависимости от типа сборки.
    """
    percentages = components_percentages.get(build_type, {})
    return {component: int(budget * percentage) for component, percentage in percentages.items()}


# --- Заданные проценты для распределения бюджета ---
components_percentages = {
    "игровая": {
        "gpu": 0.4,
        "cpu": 0.3,
        "memory": 0.1,
        "motherboard": 0.1,
        "power_supply": 0.05,
        "corpus": 0.05,
    },
    "офисная": {"cpu": 0.4, "memory": 0.3, "motherboard": 0.2, "power_supply": 0.1},
}


# --- Основной класс для построения промптов ---
class DynamicPCBuilderPrompter:
    def __init__(self):
        self.selected_components: dict[str, Any] = {}
        # для сборки пк мы последовательно выбираем компоненты, так как необходимо учитывать совместимость
        self.component_order = ["gpu", "cpu", "motherboard", "memory", "corpus", "power_supply"]
        self.component_config = self._init_config()

    # Создание промптов с динамическими полями
    def _init_config(self) -> dict[str, dict]:
        return {
            "gpu": {
                "description": "Подбор видеокарты: ",
                "main_table": "gpu_full_info",
                "dynamic_rules": [
                    lambda p: "Таблица: gpu_full_info выбирать только dustinct gpu в запросе",
                    lambda p: "JOIN gpu_hierarchy ON gpu_hierarchy.gpu = gpu_full_info.gpu",
                    lambda p: (
                        f"Разрешение: {p.get('resolution')} (проверить в gpu_hierarchy.{p.get('resolution', '')} Ultra)"
                        if "resolution" in p
                        else None
                    ),
                    lambda p: (
                        f"Бюджет: <= {p['budget']} руб. Колонка average_price"
                        if "budget" in p
                        else None
                    ),
                    lambda p: self._gen_dynamic_conditions(p, "gpu_full_info"),
                    "Сортировка: рейтинг (по убыванию), average_price (по убыванию)",
                    "Вывести все поля",
                ],
            },
            "cpu": {
                "description": "Подбор процессора:",
                "main_table": "cpu_merged",
                "dynamic_rules": [
                    lambda p: "Таблица: cpu_merged",
                    lambda p: f"Бюджет: <= {p['budget']} руб." if "budget" in p else None,
                    lambda p: self._gen_dynamic_conditions(p, "cpu_merged"),
                    "Сортировка: рейтинг (по убыванию)",
                    "Вывести все поля",
                ],
            },
            "motherboard": {
                "description": "Подбор материнской платы:",
                "main_table": "motherboard",
                "dynamic_rules": [
                    lambda p: "Таблица: motherboard",
                    lambda p: "JOIN socket_compatibility ON socket_compatibility.motherboard_socket = motherboard.socket",
                    lambda p: f"Сокет процессора: {self.selected_components.get('cpu', {}).get('socket', 'N/A')}",
                    lambda p: f"Бюджет: <= {p['budget']} руб." if "budget" in p else None,
                    lambda p: self._gen_dynamic_conditions(p, "motherboard"),
                    "Сортировка: price (по убыванию)",
                    "Вывести все поля",
                ],
            },
            "memory": {
                "description": "Подбор оперативной памяти:",
                "main_table": "memory",
                "dynamic_rules": [
                    lambda p: "Таблица: memory",
                    lambda p: f"Совместимость: <= {self.selected_components.get('motherboard', {}).get('memory_slots', 'N/A')} слотов",
                    lambda p: f"Макс. объем: <= {self.selected_components.get('motherboard', {}).get('max_memory', 'N/A')} GB",
                    lambda p: f"Бюджет: <= {p['budget']} руб." if "budget" in p else None,
                    lambda p: self._gen_dynamic_conditions(p, "memory"),
                    "Сортировка: speed_num (по убыванию)",
                    "Вывести все поля",
                ],
            },
            "corpus": {
                "description": "Подбор корпуса:",
                "main_table": "corpus",
                "dynamic_rules": [
                    lambda p: "Таблица: corpus",
                    lambda p: "JOIN case_motherboard_compatibility ON corpus.form_factor = case_motherboard_compatibility.case_form_factor",
                    lambda p: f"Форм-фактор: {self.selected_components.get('motherboard', {}).get('form_factor', 'N/A')}",
                    lambda p: f"Бюджет: <= {p['budget']} руб." if "budget" in p else None,
                    lambda p: self._gen_dynamic_conditions(p, "corpus"),
                    "Сортировка: цена (по возрастанию)",
                    "Вывести все поля",
                ],
            },
            "power_supply": {
                "description": "Подбор блока питания:",
                "main_table": "'power-supply'",
                "dynamic_rules": [
                    lambda p: f"Таблица: {self._table_reference('power_supply')}",
                    lambda p: f"Мин. мощность: {self._calculate_power_consumption()}W",
                    lambda p: f"Бюджет: <= {p['budget']} руб." if "budget" in p else None,
                    lambda p: self._gen_dynamic_conditions(p, "power-supply"),
                    "Сортировка: цена (по убыванию)",
                    "Вывести все поля",
                ],
                "dependencies": ["gpu", "cpu"],
            },
        }

    def _table_reference(self, component: str) -> str:
        return self.component_config.get(component, {}).get("main_table", component)  # type: ignore

    def _calculate_power_consumption(self) -> int:
        total_power = 0
        for comp in self.selected_components.values():
            if isinstance(comp, dict) and "power" in comp:
                total_power += comp["power"]
        return total_power if total_power else 500

    def _gen_dynamic_conditions(self, params: dict, table: str) -> str | None:
        ignore = {"budget"}
        conditions = []
        for key, value in params.items():
            if key in ignore:
                continue
            if isinstance(value, dict):
                operator = value.get("operator")
                val = value.get("value")
                conditions.append(f"{operator} {val}")
            else:
                # Если значение строковое — оборачиваем в кавычки
                if isinstance(value, str):
                    conditions.append(f"{table}.{key} = '{value}'")
                else:
                    conditions.append(f"{table}.{key} = {value}")
        return "Доп. условия: " + ", ".join(conditions) if conditions else None

    def build_prompts(self, user_request: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
        """
        Для каждого компонента (из списка распределённых по бюджету) формируется промпт.
        """
        prompts = {}
        components = {}
        req_components = user_request.get("components", {})
        for component in self.component_order:
            if component not in req_components:
                continue

            params = req_components[component]
            config = self.component_config.get(component, {})
            prompt_lines = [config.get("description", "")]
            for rule in config.get("dynamic_rules", []):
                if callable(rule):
                    line = rule(params)
                else:
                    line = rule
                if line:
                    prompt_lines.append(f"• {line}")

            prompt = "\n".join(prompt_lines)
            prompts[component] = prompt
            print(prompt)

            agent = SQLAgent(engine=engine, llm=CFG.llm)
            response = agent.run(
                SQLAgentRequest(question=prompt, table_info=db.get_table_info(), top_k=1)
            )
            components[component] = response.get("result")

            raw_result = response.get("result", [])
            if isinstance(raw_result, str):
                try:
                    result_data = json.loads(raw_result)
                except Exception as e:
                    print(f"Ошибка при обработке JSON для компонента {component}: {e}")
                    result_data = []
            elif isinstance(raw_result, list):
                result_data = raw_result
            else:
                result_data = []

            selected = result_data[0] if result_data else {}

            if component == "cpu":
                comp_info = {"socket": selected.get("socket")}
            elif component == "motherboard":
                comp_info = {
                    "memory_slots": selected.get("memory_slots"),
                    "max_memory": selected.get("max_memory"),
                    "form_factor": selected.get("form_factor"),
                }
            else:
                comp_info = selected

            self.selected_components[component] = comp_info

        return prompts, components


@tool
def pc_builder_tool(user_input: str) -> dict[str, Any]:
    """
    Обрабатывает запрос пользователя на сборку ПК, рассчитывает бюджет для компонентов и генерирует рекомендации по сборке.

    Аргументы:
    - user_input (str): Строка с запросом пользователя, содержащая требования для сборки ПК, включая бюджет и тип сборки.

    Возвращает:
    - dict: Словарь с результатами, включающий компоненты сборки и соответствующие рекомендации.
      Пример возвращаемого значения
    """
    input_json = parse_user_request(user_input)

    try:
        build_req = BuildRequest.model_validate_json(input_json)
    except ValidationError as e:
        return {"error": e.errors()}

    component_budgets = calculate_component_budgets(
        build_req.budget, build_req.build_type, components_percentages
    )

    components = {}
    for comp, comp_budget in component_budgets.items():
        comp_params = {"budget": comp_budget}
        if build_req.additional_info and comp in build_req.additional_info:
            comp_params["additional_info"] = build_req.additional_info[comp]
        components[comp] = comp_params

    request_dict = {"components": components}
    builder = DynamicPCBuilderPrompter()
    prompts, components_results = builder.build_prompts(request_dict)
    return {"user_input": user_input, "components": components_results}
