from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import AnyMessage, add_messages


def update_dialog_stack(left: list[str], right: str | None) -> list[str]:
    """
    Push or pop the state: Updates the dialog stack by either adding a new state or removing the last state.

    Args:
        left (list[str]): The current state of the dialog stack, represented as a list of strings.
        right (Optional[str]): The operation to perform. If `right` is None, the function returns the current state.
                               If `right` is "pop", the last element of the stack is removed. Otherwise, `right` is
                               appended to the stack.

    Returns:
        list[str]: The updated dialog stack.
    """
    if right is None:
        return left
    if right == "pop" and left:
        return left[:-1]
    if right not in ["assistant", "build_pc", "validate_price"]:
        raise ValueError(f"Invalid state transition: {right}")
    return left + [right]


class State(TypedDict):
    """
    Состояние графа системы

    Attributes:
        messages (list[AnyMessage]): История сообщений, используется для отслеживания контекста.
        user_info (Optional[str]): Информация о пользователе (например, предпочтения, бюджет).
        dialog_state (list[str]): Стек состояний диалога, управляет активными агентами:
                                  - "assistant": Основной ассистент (начальное состояние).
                                  - "build_pc": Агент баз данных (SQLAgent) для поиска информации о компонентах.
                                  - "price_validation_checker": Агент для поиска актуальных цен и валидации сборки.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    user_info: str | None
    dialog_state: Annotated[
        list[Literal["assistant", "build_pc", "validate_price"]],
        update_dialog_stack,
    ]
