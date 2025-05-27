from pydantic import BaseModel


class CompleteOrEscalate(BaseModel):
    """
    Инструмент для обозначения текущей задачи как завершённой и/или передачи управления диалогом основному ассистенту,
    который может перенаправить диалог в соответствии с потребностями пользователя.
    """

    cancel: bool = True
    reason: str

    class Config:
        schema_extra = {
            "example": {
                "cancel": True,
                "reason": "Пользователь передумал выполнять текущую задачу.",
            },
            "example 2": {
                "cancel": True,
                "reason": "Я полностью завершил выполнение задачи.",
            },
            "example 3": {
                "cancel": False,
                "reason": "Мне нужно поискать дополнительную информацию о ценах",
            },
            "example 4": {
                "cancel": True,
                "reason": "Это задача не относится к моей",
            },
        }
