from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt.tool_node import ToolNode

from src.agent_shema.build_agent_state import State


def handle_tool_error(state: dict[str, Any]) -> dict[str, list[ToolMessage]]:
    """
    Обрабатывает ошибки, форматируя их в сообщение и добавляя в историю чата.

    Эта функция извлекает ошибку из переданного состояния и форматирует её в объект `ToolMessage`,
    который затем добавляется в историю чата. Для прикрепления сообщения об ошибке используются последние вызовы инструментов из состояния.

    Аргументы:
        state (dict): Текущее состояние инструмента, содержащее информацию об ошибке и вызовы инструментов.

    Возвращает:
        dict: Словарь, содержащий список объектов `ToolMessage` с информацией об ошибке.
    """
    error = state.get("error")
    last_message = state["messages"][-1]
    tool_calls = []
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        tool_calls = last_message.tool_calls

    if not tool_calls:
        return {
            "messages": [
                ToolMessage(
                    content=f"Ошибка: {repr(error)}\nНе удалось определить ID вызова инструмента.",
                    name="error_handler",
                    tool_call_id="",
                )
            ]
        }

    return {
        "messages": [
            ToolMessage(
                content=f"Ошибка: {repr(error)}\nПожалуйста, исправьте ваши ошибки.",
                tool_call_id=tc["id"],
            )
            for tc in tool_calls
        ]
    }


def create_tool_node_with_fallback(tools: list) -> ToolNode:
    """
    Создает объект `ToolNode` с обработкой ошибок через fallback.

    Эта функция создает объект `ToolNode` и настраивает его на использование fallback-функции для обработки ошибок.
    Fallback-функция обрабатывает ошибки, вызывая функцию `handle_tool_error`.

    Аргументы:
        tools (list): Список инструментов, которые будут включены в объект `ToolNode`.

    Возвращает:
        dict: Объект `ToolNode`, настроенный с использованием fallback-обработки ошибок.
    """
    return ToolNode(tools).with_fallbacks(  # type: ignore
        [RunnableLambda(handle_tool_error)], exception_key="error"
    )


def _print_event(event: dict[str, Any], _printed: set[str], max_length: int = 1500) -> None:
    """
    Выводит текущее состояние и сообщения события с возможным усечением длинных сообщений.

    Эта функция выводит информацию о текущем состоянии диалога и последнем сообщении в событии.
    Если сообщение слишком длинное, оно обрезается до указанной максимальной длины.

    Аргументы:
        event (dict): Событие, содержащее состояние диалога и сообщения.
        _printed (set): Множество идентификаторов сообщений, которые уже были выведены, чтобы избежать дублирования.
        max_length (int, optional): Максимальная длина сообщения для вывода до усечения. По умолчанию 1500.
    """
    current_state = event.get("dialog_state")
    if current_state:
        print("Текущее состояние: ", current_state[-1])
    message = event.get("messages")
    if message:
        if isinstance(message, list):
            message = message[-1]
        if message.id not in _printed:
            msg_repr = message.pretty_repr(html=True)
            if len(msg_repr) > max_length:
                msg_repr = msg_repr[:max_length] + " ... (обрезано)"
            print(msg_repr)
            _printed.add(message.id)


def create_entry_node(
    assistant_name: str, new_dialog_state: str
) -> Callable[[State], dict[str, Any]]:
    """
    Создает функцию для перехода к новому этапу диалога с указанием состояния и инструмента.

    Аргументы:
        assistant_name (str): Имя помощника, который будет использоваться в сообщении.
        new_dialog_state (str): Новое состояние диалога после перехода.

    Возвращает:
        Callable: Функция, которая при вызове с объектом `State` возвращает словарь
        с инструментом и обновленным состоянием диалога.

    Описание работы функции:
        - Извлекает `tool_call_id` из последнего сообщения, в котором был вызван инструмент, в `State`.
        - Формирует сообщение для инструмента, информируя пользователя о том, что активирован указанный помощник.
        - Обновляет состояние диалога, устанавливая новое состояние.
        - Сообщение инструмента указывает помощнику, что задача считается незавершенной,
          пока необходимый инструмент не будет успешно вызван.
        - Если пользователь изменит свое решение или потребуется помощь в других вопросах,
          сообщение рекомендует вызвать функцию `CompleteOrEscalate`, чтобы передать управление основному помощнику.
    """

    def entry_node(state: State) -> dict[str, Any]:
        last_message = state["messages"][-1]
        tool_call_id = None
        if (
            isinstance(last_message, AIMessage)
            and last_message.tool_calls
            and last_message.tool_calls[0].get("id")
        ):
            tool_call_id = last_message.tool_calls[0]["id"]

        if not tool_call_id:
            return {
                "messages": [
                    ToolMessage(
                        content=(
                            f"Помощник {assistant_name} сейчас активен. Не удалось определить ID вызова инструмента."
                        ),
                        name=assistant_name,
                        tool_call_id="unknown_tool_call_id",
                    )
                ],
                "dialog_state": new_dialog_state,
            }

        return {
            "messages": [
                ToolMessage(
                    content=(
                        f"Помощник {assistant_name} сейчас активен. Пожалуйста, ознакомьтесь с предыдущим диалогом "
                        f"между основным помощником и пользователем. Цель пользователя пока не выполнена. "
                        f"Используйте доступные инструменты для завершения задачи. Помните, что вы {assistant_name}, "
                        "и действие считается завершенным только после успешного вызова необходимого инструмента. "
                        "Если пользователь изменит свое мнение или потребуется помощь по другим вопросам, вызовите функцию "
                        "CompleteOrEscalate, чтобы вернуть управление основному помощнику."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
            "dialog_state": new_dialog_state,
        }

    return entry_node
