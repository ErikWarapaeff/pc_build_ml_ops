import os
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt.tool_node import tools_condition

from src.agent_shema.agent_runnables import AIAgentRunnables
from src.agent_shema.build_agent_state import State
from src.agent_shema.build_assistants import (
    Assistant,
    ToPCBuildAssistant,
    ToPriceValidationCheckerAssistant,
)
from src.agent_shema.complete_or_escalate import CompleteOrEscalate
from src.utils.utilities import create_entry_node, create_tool_node_with_fallback

# Настройка альтернативного API-эндпоинта для OpenAI
os.environ["OPENAI_API_BASE"] = "https://api.vsegpt.ru/v1"
print("Использование альтернативного API-эндпоинта для OpenAI:", os.environ.get("OPENAI_API_BASE"))

AGENT_RUNNABLES = AIAgentRunnables()


def leave_skill(state: State) -> dict:
    """Завершение работы с подассистентом и возвращение в основной ассистент"""
    messages = []
    last_message = state["messages"][-1]
    if (
        isinstance(last_message, AIMessage)
        and last_message.tool_calls
        and last_message.tool_calls[0].get("id")
    ):
        messages.append(
            ToolMessage(
                content="Завершаем текущую задачу и возвращаемся к основному ассистенту.",
                tool_call_id=last_message.tool_calls[0]["id"],
            )
        )
    return {"dialog_state": "pop", "messages": messages}


class AgenticGraph:
    def __init__(self) -> None:
        self.builder = StateGraph(State)
        self.builder.add_node("fetch_user_info", self.fetch_user_info)
        self.builder.add_edge(START, "fetch_user_info")
        self.shared_memory: dict[str, Any] = {}

    def fetch_user_info(self, state: State):
        """
        Сбор информации о пользователе. Это определяет, какие данные нужно собирать в контексте запроса.
        Например, информация о запросах на сборку ПК или проверку совместимости.
        """
        last_message_content = state["messages"][-1].content
        user_query = ""
        if isinstance(last_message_content, str):
            user_query = last_message_content.lower()
        elif (
            isinstance(last_message_content, list)
            and last_message_content
            and isinstance(last_message_content[0], dict)
            and isinstance(last_message_content[0].get("text"), str)
        ):
            # Если это список словарей (например, от AIMessage с content в виде list of dicts)
            user_query = last_message_content[0]["text"].lower()
        else:
            # Обработка других возможных типов content, или установка значения по умолчанию
            user_query = ""

        self.shared_memory["last_query"] = user_query
        return {"info": user_query}

    # ===========================
    # PC Build Assistant
    # ===========================
    def add_pc_build_nodes_to_graph(self):
        """
        Добавляет узлы и ребра графа для работы с помощником по сборке ПК.

        Здесь создаются узлы для входа в режим сборки ПК, непосредственного выполнения задачи
        сборки, а также узел для обработки инструментов, связанных со сборкой ПК. Кроме того,
        добавляется узел для завершения работы с подассистентом и возврата к основному ассистенту.
        """
        self.builder.add_node(
            "enter_build_pc",
            create_entry_node("PC Build Assistant", "build_pc"),
        )
        self.builder.add_node("build_pc", Assistant(AGENT_RUNNABLES.pc_build_runnable))
        self.builder.add_edge("enter_build_pc", "build_pc")
        self.builder.add_node(
            "build_pc_tools",
            create_tool_node_with_fallback(AGENT_RUNNABLES.pc_build_tools),
        )

        def route_build_pc(state: State) -> Literal["build_pc_tools", "leave_skill", "__end__"]:
            """
            Определяет маршрут для перехода после выполнения сборки ПК.

            Если условия не выполнены (например, если произошла отмена через CompleteOrEscalate),
            возвращает маршрут для выхода (leave_skill). Иначе возвращает маршрут для вызова инструментов.

            Аргументы:
                state (State): Текущее состояние диалога.

            Возвращает:
                Literal: Строку, обозначающую следующий узел в графе.
            """

            route = tools_condition(state)
            if route == END:
                return "__end__"
            last_message = state["messages"][-1]
            tool_calls = []
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                tool_calls = last_message.tool_calls

            if not tool_calls:
                return "__end__"

            did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
            if did_cancel:
                return "leave_skill"
            return "build_pc_tools"

        self.builder.add_edge("build_pc_tools", "build_pc")
        self.builder.add_conditional_edges("build_pc", route_build_pc)

        self.builder.add_node("leave_skill", leave_skill)
        self.builder.add_edge("leave_skill", "primary_assistant")

    # ===========================
    # Price Validation Checker
    # ===========================
    def add_price_validation_nodes_to_graph(self):
        """
        Добавляет узлы и ребра графа для работы с помощником по валидации цен и анализу узких мест.

        Создаются узлы для входа в режим проверки цен, выполнения логики проверки, а также узел для обработки
        инструментов с fallback-обработкой. При необходимости добавляется узел для завершения работы с
        подассистентом.
        """

        self.builder.add_node(
            "enter_validate_price",
            create_entry_node("Price Validation Assistant", "validate_price"),
        )
        self.builder.add_node(
            "validate_price", Assistant(AGENT_RUNNABLES.price_validation_checker_runnable)
        )
        self.builder.add_edge("enter_validate_price", "validate_price")
        self.builder.add_node(
            "price_validation_tools",
            create_tool_node_with_fallback(AGENT_RUNNABLES.price_validation_checker_tools),
        )

        def route_validate_price(
            state: State,
        ) -> Literal["price_validation_tools", "leave_skill", "__end__"]:
            """
            Определяет маршрут для перехода после проверки цен.

            Если в состоянии обнаружена отмена (через CompleteOrEscalate), возвращается маршрут для выхода.
            Иначе возвращается маршрут для вызова инструментов по проверке цен.

            Аргументы:
                state (State): Текущее состояние диалога.

            Возвращает:
                Literal: Строка, обозначающая следующий узел.
            """
            route = tools_condition(state)
            if route == END:
                return "__end__"
            last_message = state["messages"][-1]
            tool_calls = []
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                tool_calls = last_message.tool_calls

            if not tool_calls:
                return "__end__"

            did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
            if did_cancel:
                return "leave_skill"
            return "price_validation_tools"

        self.builder.add_edge("price_validation_tools", "validate_price")
        self.builder.add_conditional_edges("validate_price", route_validate_price)

        if "leave_skill" not in self.builder.nodes:
            self.builder.add_node("leave_skill", leave_skill)
        self.builder.add_edge("leave_skill", "primary_assistant")

    # ===========================
    # Primary Assistant
    # ===========================
    def add_primary_assistant_nodes_to_graph(self):
        """
        Добавляет узлы и ребра для основного ассистента.

        Создаются узлы для основного ассистента и его инструментов, а также определяются маршруты
        для перехода от основных узлов к другим подассистентам в зависимости от запроса пользователя.
        """

        self.builder.add_node(
            "primary_assistant", Assistant(AGENT_RUNNABLES.primary_assistant_runnable)
        )
        self.builder.add_node(
            "primary_assistant_tools",
            create_tool_node_with_fallback(AGENT_RUNNABLES.primary_assistant_tools),
        )

        def route_primary_assistant(
            state: State,
        ) -> Literal[
            "primary_assistant_tools", "enter_build_pc", "enter_validate_price", "__end__"
        ]:
            """
            Определяет маршрут для основного ассистента в зависимости от вызванного инструмента.

            Функция анализирует последнее сообщение пользователя и проверяет, какой инструмент был вызван.
            Если вызван инструмент для сборки ПК, происходит переход к узлу "enter_build_pc".
            Если вызван инструмент для проверки цен, переход осуществляется к узлу "enter_validate_price".
            Если инструмент не поддерживается, остается узел основных инструментов.

            Аргументы:
                state (State): Текущее состояние диалога.

            Возвращает:
                Literal: Строка, обозначающая следующий узел для маршрутизации.
            """

            print(f"Состояние перед маршрутом: {state}")

            route = tools_condition(state)
            if route == END:
                return "__end__"

            last_message = state["messages"][-1]
            tool_calls = []
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                tool_calls = last_message.tool_calls

            if tool_calls:
                tool_name = tool_calls[0]["name"]
                print(f"Используется инструмент: {tool_name}")
                if tool_calls[0]["name"] == ToPCBuildAssistant.__name__:
                    print("Переход на маршрут 'enter_build_pc'")
                    return "enter_build_pc"

                elif tool_calls[0]["name"] == ToPriceValidationCheckerAssistant.__name__:
                    print("Переход на маршрут 'enter_validate_price'")
                    return "enter_validate_price"
                else:
                    print(f"Ошибка: инструмент {tool_name} не поддерживается.")
                    return "primary_assistant_tools"
            return "primary_assistant_tools"

        self.builder.add_conditional_edges(
            "primary_assistant",
            route_primary_assistant,
            {
                "enter_build_pc": "enter_build_pc",
                "enter_validate_price": "enter_validate_price",
                "primary_assistant_tools": "primary_assistant_tools",
                "__end__": "__end__",
            },
        )
        self.builder.add_edge("primary_assistant_tools", "primary_assistant")

        def route_to_workflow(
            state: State,
        ) -> Literal["primary_assistant", "build_pc", "validate_price"]:
            """
            Определяет конечный маршрут для перехода в рабочий процесс на основе состояния диалога.

            Если состояние диалога отсутствует, возвращается основной ассистент. Иначе выбирается последний
            сохраненный этап (например, сборка ПК или проверка цен).

            Аргументы:
                state (State): Текущее состояние диалога.

            Возвращает:
                Literal: Строка с обозначением конечного маршрута.
            """

            dialog_state = state.get("dialog_state")
            if not dialog_state:
                return "primary_assistant"
            # Проверяем, что последний элемент dialog_state соответствует одному из Literal
            last_state = dialog_state[-1]
            if last_state in ("build_pc", "validate_price", "primary_assistant"):
                return last_state
            else:
                # Если состояние неизвестно, возвращаем ассистента по умолчанию
                return "primary_assistant"

        self.builder.add_conditional_edges("fetch_user_info", route_to_workflow)

    def compile_graph(self):
        """
        Компилирует полный граф, добавляя все необходимые узлы и ребра между ними.

        Сначала добавляются узлы для основного ассистента, затем - для различных подассистентов
        (например, для сборки ПК и проверки цен). В конце граф компилируется и возвращается
        вместе с сохранителем памяти для возможности сохранения состояния диалога.
        """
        self.add_primary_assistant_nodes_to_graph()
        self.add_pc_build_nodes_to_graph()
        self.add_price_validation_nodes_to_graph()
        memory = MemorySaver()
        graph = self.builder.compile(checkpointer=memory)
        return graph, memory
