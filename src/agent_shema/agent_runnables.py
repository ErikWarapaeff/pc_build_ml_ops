from agent_shema.build_assistants import (  # type: ignore
    ToPCBuildAssistant,
    ToPriceValidationCheckerAssistant,
)
from agent_shema.build_system_prompts import AgentPrompts  # type: ignore
from agent_shema.complete_or_escalate import CompleteOrEscalate  # type: ignore
from src.load_config import LoadConfig
from src.tools.bottle_neck import calculate_bottleneck
from src.tools.game_runner import game_run_tool
from src.tools.regard_parser import regard_parser_tool
from src.tools.sql_agent_tools import pc_builder_tool, question_answer_tool

AGENT_PROMPTS = AgentPrompts()
CFG = LoadConfig()


class AIAgentRunnables:
    """
    Класс AIAgentRunnables предназначен для инициализации исполняемых модулей (runnables) для различных подассистентов.

    Этот класс создает и настраивает runnable'ы для:
      - Основного ассистента (primary assistant)
      - Ассистента по сборке ПК (PC Build Assistant)
      - Ассистента по проверке цен и анализу узких мест (Price Validation Checker Assistant)

    Каждый runnable формируется путем связывания соответствующего системного промпта с набором инструментов, а также с инструментом CompleteOrEscalate для обработки отмены задач.
    """

    def __init__(self) -> None:
        (
            self.primary_assistant_tools,
            self.primary_assistant_runnable,
        ) = self.build_primary_assistant_runnable()
        self.pc_build_tools, self.pc_build_runnable = self.build_pc_build_runnable()
        (
            self.price_validation_checker_tools,
            self.price_validation_checker_runnable,
        ) = self.build_price_validation_checker_runnable()

    def build_primary_assistant_runnable(self):
        primary_assistant_tools = [
            ToPCBuildAssistant,
            ToPriceValidationCheckerAssistant,
        ]
        primary_assistant_runnable = AGENT_PROMPTS.primary_assistant_prompt | CFG.llm.bind_tools(
            primary_assistant_tools
        )
        return primary_assistant_tools, primary_assistant_runnable

    def build_pc_build_runnable(self):
        pc_build_tools = [pc_builder_tool, question_answer_tool]
        pc_build_runnable = AGENT_PROMPTS.pc_info_prompt | CFG.llm.bind_tools(
            pc_build_tools + [CompleteOrEscalate]
        )
        return pc_build_tools, pc_build_runnable

    def build_price_validation_checker_runnable(self):
        price_validation_checker_tools = [regard_parser_tool, calculate_bottleneck, game_run_tool]
        price_validation_checker_runnable = (
            AGENT_PROMPTS.price_validation_checker_prompt
            | CFG.llm.bind_tools(price_validation_checker_tools + [CompleteOrEscalate])
        )
        return price_validation_checker_tools, price_validation_checker_runnable
