# type: ignore

from typing import Annotated, Any

from langchain.schema import HumanMessage
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, Field

from src.agent_shema.build_agent_state import State
from src.tools.regard_parser import RegardInput


class Assistant:
    """
    Класс для управления взаимодействием с исполняемым агентом (runnable agent) и обеспечения корректных ответов.

    Атрибуты:
        runnable (Runnable): Экземпляр класса Runnable, используемый для вызова действий и получения результатов.

    Методы:
        __call__(state: State, config: RunnableConfig) -> dict:
            Выполняет вызов runnable с заданным состоянием и конфигурацией, а также обрабатывает некорректные ответы,
            обновляя состояние с соответствующими сообщениями до получения корректного результата.

    Аргументы конструктора:
        runnable (Runnable): Экземпляр класса Runnable, который выполняет основную работу и предоставляет результат.
    """

    def __init__(self, runnable: Runnable):
        """
        Инициализирует объект Assistant с заданным экземпляром runnable.

        Аргументы:
            runnable (Runnable): Экземпляр класса Runnable для вызова действий.
        """
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig) -> dict[str, Any]:
        """
        Выполняет вызов runnable с заданным состоянием и конфигурацией, гарантируя получение корректного ответа.

        Метод циклически вызывает runnable до тех пор, пока не будет получен корректный ответ.
        Если ответ некорректен (например, отсутствуют вызовы инструментов или содержимое пустое или недопустимое),
        состояние обновляется сообщением с просьбой предоставить реальный вывод.

        Аргументы:
            state (State): Текущее состояние агента, содержащее историю сообщений и другую релевантную информацию.
            config (RunnableConfig): Конфигурационные настройки для runnable.

        Возвращает:
            dict: Словарь, содержащий обновленные сообщения и результат вызова runnable.

        Пример:
            result = self(state, config)
        """
        while True:
            result = self.runnable.invoke(state)

            # Если нет вызовов инструментов и содержимое результата пустое или недопустимое,
            # добавляем сообщение с просьбой дать реальный ответ.
            if not result.tool_calls and (
                not result.content
                or (isinstance(result.content, list) and not result.content[0].get("text"))
            ):
                messages = state["messages"] + [
                    HumanMessage(content="Дайте, пожалуйста, реальный ответ.")
                ]
                state = {**state, "messages": messages}
            else:
                break
        return {"messages": result}


class ToPCBuildAssistant(BaseModel):
    """
    Передает задачу специализированному ассистенту, который занимается сборкой ПК
    и отвечает на вопросы о компонентах и их совместимости.

    Атрибуты:
        user_input (Optional[str]): Вопрос или запрос пользователя, касающийся выбора компонентов,
                                      совместимости или сборки ПК.
    """

    user_input: Annotated[
        str | None,
        Field(
            default=None,
            description="Вопрос о конкретных компонентах, их совместимости или сборке ПК.",
            example="Собери мне компьютер за 200000 с поддержкой 4K.",
        ),
    ]


class GameRunInput(BaseModel):
    """
    Модель входных данных для проверки совместимости системы с игрой (например, для инструмента game_run_tool).

    Атрибуты:
        game_name (str): Название игры, которую нужно проверить.
        cpu (str): Модель процессора пользователя.
        gpu (str): Модель видеокарты пользователя.
        ram (int): Объем оперативной памяти в гигабайтах.
    """

    game_name: Annotated[
        str, Field(description="Название игры, которую нужно проверить.", example="Cyberpunk 2077")
    ]
    cpu: Annotated[
        str, Field(description="Модель процессора пользователя.", example="Intel Core i7-12700")
    ]
    gpu: Annotated[str, Field(description="Модель видеокарты пользователя.", example="RTX 3070")]
    ram: Annotated[int, Field(description="Объем оперативной памяти (в ГБ).", example=16)]


class BottleNeckInput(BaseModel):
    """
    Модель входных данных для проверки узкого горлышка системы (например, для инструмента calculate_bottleneck).

    Атрибуты:
        cpu (str): Модель процессора для проверки узкого горлышка.
        gpu (str): Модель видеокарты для проверки узкого горлышка.
        resolution (str): Разрешение экрана (например, '1440p').
    """

    cpu: Annotated[
        str,
        Field(
            description="Модель процессора для проверки узкого горлышка.",
            example="Intel Core i7-12700",
        ),
    ]
    gpu: Annotated[
        str,
        Field(description="Модель видеокарты для проверки узкого горлышка.", example="RTX 3070"),
    ]
    resolution: Annotated[
        str, Field(description="Разрешение экрана (например, '1440p').", example="1440p")
    ]


class ToPriceValidationCheckerAssistant(BaseModel):
    """
    Основной класс для передачи задачи специализированному ассистенту по проверке цен,
    совместимости или анализу узких мест.

    Атрибуты:
        input_data (Union[GameRunInput, BottleNeckInput, RegardInput]): Входные данные для проверки
            совместимости или поиска компонентов. В зависимости от запроса могут использоваться данные
            для проверки запуска игры, анализа узкого горлышка или анализа компонентов.
    """

    input_data: Annotated[
        GameRunInput | BottleNeckInput | RegardInput,
        Field(
            description="Входные данные для проверки совместимости или поиска компонентов.",
        ),
    ]

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "description": "Проверка запуска игры (game_run_tool)",
                    "input_data": {
                        "game_name": "Cyberpunk 2077",
                        "cpu": "Intel Core i7-12700",
                        "gpu": "RTX 3070",
                        "ram": 16,
                    },
                },
                {
                    "description": "Проверка узкого горлышка (calculate_bottleneck)",
                    "input_data": {
                        "cpu": "Ryzen 9 5950X",
                        "gpu": "GeForce RTX 4070",
                        "resolution": "1440p",
                    },
                },
                {
                    "description": "Анализ компонентов для сборки ПК (regard_parser_tool)",
                    "input_data": {
                        "components": [
                            {"cpu": "Intel Core i7-12700"},
                            {"gpu": "RTX 3070"},
                            {"name": "Corsair Vengeance 16 GB"},
                        ]
                    },
                },
            ]
        }
