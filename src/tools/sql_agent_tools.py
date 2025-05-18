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
        self.llm = CFG.llm
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
                    "Ты эксперт по SQLlite. На основе входного вопроса создай синтаксически правильный запрос SQLlite "
                    "для выполнения с {top_k} примерами (используй LIMIT {top_k}), если не указано иное.\n\n"
                    "Вот информация о доступных таблицах: {table_info}\n\n"
                    "**Ключевые правила:**\n"
                    "Для абстрактных/нечетких запросов (например, 'найти что-то связанное с X', 'показать всё похожее на Y'):\n"
                    "   - Используй `LIKE '%значение%'` для текстового поиска\n"
                    "   - Возвращай все совпадения, когда не указаны конкретные фильтры\n\n"
                    "**Специальные инструкции для поиска GPU с поддержкой разрешения:**\n"
                    "   - Если в таблице отсутствует определенный столбец, ищи по столбцам name/description\n"
                    "   - Если в запросе указано разрешение 4K, используй `%4K%'` для поиска GPU с поддержкой 4K\n",
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
                print(f"Выполняем SQL-запрос (попытка {attempt+1}):\n{query}")
                result = self.query_tool.run(query)
                print(f"Результат запроса:\n{result}")
                return self.query_to_json(query)
            except Exception as e:
                print(f"Попытка {attempt + 1} завершилась ошибкой: {e}")
                if attempt < max_retries - 1:
                    query = self.validate_sql_query(query, question)
                    print(f"Переписываем запрос: {query}")
                else:
                    print(
                        f"Все попытки выполнения запроса завершились неудачей. Последняя ошибка: {e}"
                    )
                    return []
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


def parse_user_request(user_input: str) -> dict[str, Any]:
    """Парсит пользовательский запрос в структурированный JSON с валидацией"""

    # Pydantic модель внутри функции
    class BuildRequest(BaseModel):
        budget: int
        build_type: Literal["игровая", "офисная"]
        additional_info: dict[str, str] = {}

        @field_validator("build_type")
        @staticmethod
        def normalize_build_type(v):
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

    # Полностью переписанный системный промпт для четкого и точного разбора запросов
    system_prompt = """Ты ИИ-парсер технических запросов. Строго следуй этим правилам:

        1. **Бюджет**: Число рублей из запроса.
           - "200к" → 200000
           - "150 тыс" → 150000

        2. **Тип сборки** (ТОЛЬКО 2 варианта):
           - "игровая": для игр, стриминга, высокой производительности, 4K
           - "офисная": для работы, документов, программирования

        3. **Главное**: в additional_info добавляй ТОЛЬКО то, что ЯВНО указано в запросе!
           - МАКСИМАЛЬНО КРАТКО
           - БЕЗ дополнительных слов или объяснений
           - Если упоминается "4K" - обязательно добавь "gpu": "4k" (только так, не более!)
           - Используй ТОЛЬКО следующие ключи: gpu, cpu, memory, motherboard, corpus, power_supply
           - Значения должны быть максимально краткими!

        Пример 1: Запрос "Игровой ПК 4K за 200k"
        {
          "budget": 200000,
          "build_type": "игровая",
          "additional_info": {"gpu": "4k"}
        }

        Пример 2: Запрос "RTX 3080 с AMD Ryzen 9"
        {
          "budget": 150000,
          "build_type": "игровая",
          "additional_info": {"gpu": "rtx 3080", "cpu": "ryzen 9"}
        }

        НЕ ДОБАВЛЯЙ никаких дополнительных объяснений или комментариев. Только конкретные детали из запроса.
        КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО добавлять компоненты, не упомянутые в запросе!

        Текущий запрос: "{input}"
    """

    # Получение ответа от LLM
    openai_api_key_str = os.getenv("OPEN_AI_API_KEY")
    if not openai_api_key_str:
        raise ValueError("API ключ не найден в переменных окружения")
    openai_api_key = SecretStr(openai_api_key_str)

    # Получение ответа от LLM
    client = ChatOpenAI(
        api_key=openai_api_key, model="gpt-4o-mini", base_url="https://api.vsegpt.ru/v1"
    )
    try:
        response = client.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_input)]
        )

        # Дополнительная обработка для обеспечения корректного JSON
        raw_content = response.content
        if not isinstance(raw_content, str):
            raise TypeError(
                f"Ожидалось, что содержимое ответа LLM будет строкой для JSON-парсинга, получено: {type(raw_content)}"
            )

        # Безопасный парсинг JSON с предварительной очисткой
        cleaned_content = raw_content.strip()
        # Удаляем все, что находится до первой { и после последней }
        first_brace = cleaned_content.find("{")
        last_brace = cleaned_content.rfind("}")
        if first_brace >= 0 and last_brace >= 0:
            cleaned_content = cleaned_content[first_brace : last_brace + 1]

        raw_data = json.loads(cleaned_content)

        # Обрабатываем случай, когда бюджет задан как строка
        if isinstance(raw_data.get("budget"), str):
            try:
                raw_data["budget"] = int(raw_data["budget"].replace("k", "000").replace("K", "000"))
            except ValueError:
                raw_data["budget"] = 150000  # дефолтный бюджет, если не удалось распарсить

        # Проверяем наличие и тип ключевых данных
        if not raw_data.get("budget"):
            raw_data["budget"] = 150000

        if "build_type" not in raw_data or raw_data["build_type"] not in ["игровая", "офисная"]:
            # Если в запросе упоминаются игры или 4K, предполагаем игровую сборку
            if (
                "игр" in user_input.lower()
                or "4k" in user_input.lower()
                or "4к" in user_input.lower()
            ):
                raw_data["build_type"] = "игровая"
            else:
                raw_data["build_type"] = "офисная"

        if "additional_info" not in raw_data:
            raw_data["additional_info"] = {}

        # Если в запросе упоминается 4K, добавляем в additional_info
        if "4k" in user_input.lower() or "4к" in user_input.lower():
            if "additional_info" not in raw_data:
                raw_data["additional_info"] = {}
            raw_data["additional_info"]["gpu"] = "4k"

        # Проверяем и очищаем компоненты, которые не были явно указаны в запросе
        if "additional_info" in raw_data:
            components_to_remove = []
            component_keywords = {
                "gpu": [
                    "видеокарт",
                    "rtx",
                    "gtx",
                    "nvidia",
                    "geforce",
                    "amd",
                    "radeon",
                    "rx",
                    "4k",
                    "4к",
                ],
                "cpu": ["процессор", "intel", "amd", "ryzen", "core", "i5", "i7", "i9"],
                "memory": ["память", "озу", "ram", "ddr", "гб", "gb"],
                "motherboard": ["мать", "материнск", "плат", "motherboard", "чипсет"],
                "corpus": ["корпус", "корпуса", "case"],
                "power_supply": ["блок питания", "бп", "питание", "ватт", "вт", "w"],
            }

            for comp in list(raw_data["additional_info"].keys()):
                # Проверяем, был ли этот компонент явно упомянут в запросе
                if comp in component_keywords:
                    was_mentioned = False
                    for keyword in component_keywords[comp]:
                        if keyword in user_input.lower():
                            was_mentioned = True
                            break
                    if not was_mentioned:
                        components_to_remove.append(comp)

            # Удаляем компоненты, которые не были явно упомянуты
            for comp in components_to_remove:
                if comp in raw_data["additional_info"]:
                    del raw_data["additional_info"][comp]

            # Упрощаем значения для краткости
            for key, value in raw_data["additional_info"].items():
                if isinstance(value, str):
                    # Если это 4K запрос, оставляем только "4k"
                    if "4k" in value.lower() or "4к" in value.lower():
                        raw_data["additional_info"][key] = "4k"
                    else:
                        # Удаляем лишние слова и пробелы, оставляем только ключевую информацию
                        raw_data["additional_info"][key] = value.strip()

        # Проверяем тип сборки - для игрового ПК с 4K нужна видеокарта
        if raw_data.get("build_type") == "игровая" and (
            "4k" in user_input.lower() or "4к" in user_input.lower()
        ):
            if "additional_info" not in raw_data:
                raw_data["additional_info"] = {}
            if "gpu" not in raw_data["additional_info"]:
                raw_data["additional_info"]["gpu"] = "4k"

        validated = BuildRequest(**raw_data).model_dump()

        print(f"Распознанный запрос: {validated}")
        return validated

    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        print(f"Ошибка парсинга или валидации: {e}")
        # Создаем запасной объект на основе анализа текста
        fallback_budget = 150000
        fallback_type = (
            "игровая"
            if "игр" in user_input.lower()
            or "4k" in user_input.lower()
            or "4к" in user_input.lower()
            else "офисная"
        )

        # Ищем числа в запросе, которые могут быть бюджетом
        import re

        budget_match = re.search(r"(\d+)\s*(?:k|K|к|тыс|тысяч|руб|₽)?", user_input)
        if budget_match:
            try:
                budget_str = budget_match.group(1)
                budget_val = int(budget_str)
                # Если число меньше 1000, вероятно это тысячи
                if budget_val < 1000:
                    budget_val *= 1000
                fallback_budget = budget_val
            except ValueError:
                pass

        additional_info = {}
        if "4k" in user_input.lower() or "4к" in user_input.lower():
            additional_info["gpu"] = "4k"

        # Проверяем упоминания конкретных компонентов - только явно указанных
        component_keywords = {
            "gpu": ["видеокарт", "rtx", "gtx", "nvidia", "geforce", "amd", "radeon", "rx"],
            "cpu": ["процессор", "intel", "amd", "ryzen", "core"],
            "memory": ["память", "озу", "ram", "ddr"],
            "motherboard": ["мать", "материнск", "плат", "motherboard"],
            "corpus": ["корпус", "корпуса", "case"],
            "power_supply": ["блок питания", "бп", "питание", "ватт", "вт", "w"],
        }

        # Находим конкретные модели, упомянутые в запросе
        for comp, keywords in component_keywords.items():
            # Проверяем, упоминается ли компонент в запросе
            was_mentioned = False
            mentions = []

            for keyword in keywords:
                if keyword in user_input.lower():
                    was_mentioned = True

                    # Ищем возможные значения для этого ключевого слова
                    # Например, для "rtx" ищем "rtx 4080" или для "процессор" ищем "i9-14900k"
                    if keyword in ["rtx", "gtx", "rx"]:
                        model_match = re.search(
                            f"{keyword}\\s*(\\d+\\s*[a-zA-Z0-9]*)", user_input.lower()
                        )
                        if model_match:
                            mentions.append(f"{keyword.upper()} {model_match.group(1)}")
                    elif keyword in ["intel", "core"]:
                        model_match = re.search(
                            f"{keyword}\\s*([a-zA-Z0-9\\-]+)", user_input.lower()
                        )
                        if model_match:
                            mentions.append(f"{keyword} {model_match.group(1)}")
                    elif keyword in ["ryzen", "amd"]:
                        model_match = re.search(
                            f"{keyword}\\s*([a-zA-Z0-9\\-]+)", user_input.lower()
                        )
                        if model_match:
                            mentions.append(f"{keyword} {model_match.group(1)}")
                    elif keyword in ["ddr"]:
                        model_match = re.search(
                            f"(\\d+)\\s*(?:гб|gb)?\\s*{keyword}(\\d+)?", user_input.lower()
                        )
                        if model_match:
                            gb = model_match.group(1) or ""
                            ver = model_match.group(2) or ""
                            mentions.append(f"{gb}GB {keyword.upper()}{ver}")

            if was_mentioned:
                if mentions:
                    additional_info[comp] = " ".join(mentions)
                else:
                    # Добавляем только категорию без конкретной модели
                    additional_info[comp] = ""

        default_data = BuildRequest(
            budget=fallback_budget, build_type=fallback_type, additional_info=additional_info
        ).model_dump()

        return default_data


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
        return self.component_config.get(component, {}).get("main_table", component)

    def _calculate_power_consumption(self) -> int:
        total_power = 0
        for comp in self.selected_components.values():
            if isinstance(comp, dict) and "power" in comp:
                total_power += comp["power"]
        return total_power if total_power else 500

    def _gen_dynamic_conditions(self, params: dict[str, Any], table: str) -> str | None:
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
                    # Специальное условие для поиска 4K видеокарт
                    if key == "additional_info" and "4k" in value.lower():
                        # Ищем по названию или описанию видеокарты
                        conditions.append(
                            "name LIKE '%4K%' OR name LIKE '%RTX%' OR name LIKE '%RX%'"
                        )
                    else:
                        conditions.append(f"{table}.{key} = '{value}'")
                else:
                    conditions.append(f"{table}.{key} = {value}")
        return "Доп. условия: " + ", ".join(conditions) if conditions else None

    def build_prompts(self, user_request: dict[str, Any]) -> dict[str, Any]:
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
                {"question": prompt, "table_info": db.get_table_info(), "top_k": 1}
            )

            # Добавляем отладочную информацию о запросе и результатах
            print(f"=== Компонент: {component} ===")
            print(f"Сформированный запрос: {response.get('query', 'Запрос не сформирован')}")
            print(f"Результат запроса (raw): {response.get('result', 'Результат не получен')}")
            print(f"Тип результата: {type(response.get('result', None))}")
            print(
                f"Длина результата: {len(response.get('result', [])) if isinstance(response.get('result', []), list) else 'не список'}"
            )

            components[component] = response.get("result")

            raw_result = response.get("result", [])
            if isinstance(raw_result, str):
                try:
                    result_data = json.loads(raw_result)
                    print(f"Преобразованный JSON: {result_data}")
                except Exception as e:
                    print(f"Ошибка при обработке JSON для компонента {component}: {e}")
                    result_data = []
            elif isinstance(raw_result, list):
                result_data = raw_result
            else:
                result_data = []

            print(f"Обработанный результат: {result_data}")
            print(f"Количество элементов: {len(result_data)}")

            selected = result_data[0] if result_data else {}
            print(f"Выбранный элемент: {selected}")

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
            print(f"Сохраненная информация: {comp_info}")
            print("=" * 50)

        return components


@tool
def pc_builder_tool(user_input: str) -> dict[str, Any]:
    """
    Обрабатывает запрос пользователя на сборку ПК, рассчитывает бюджет для компонентов и генерирует рекомендации по сборке.

    Аргументы:
    - user_input (str): Строка с запросом пользователя, содержащая требования для сборки ПК, включая бюджет и тип сборки.

    Возвращает:
    - Dict[str, Any]: Словарь с результатами, включающий компоненты сборки и соответствующие рекомендации.
      Пример возвращаемого значения
    """
    parsed_data = parse_user_request(user_input)

    try:
        build_req = BuildRequest.model_validate(parsed_data)
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
    components_results = builder.build_prompts(request_dict)
    return {"user_input": user_input, "components": components_results}
