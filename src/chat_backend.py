import os
import uuid
from typing import Any

from src.agent_shema.mult_agents_graph import AgenticGraph
from src.load_config import LoadConfig
from src.utils.utilities import _print_event

CFG = LoadConfig()
db = CFG.local_file

db_exists = os.path.exists(db)

graph_instance = AgenticGraph()
graph, _ = graph_instance.compile_graph()
thread_id = str(uuid.uuid4())
print("=======================")
print("thread_id:", thread_id)
print("=======================")

config = {"configurable": {"thread_id": thread_id, "recursion_limit": 50}}


class ChatBot:
    @staticmethod
    def respond(chatbot: list[dict], message: str) -> tuple:
        _printed: set[Any] = set()
        events = graph.stream(
            {"messages": [{"role": "user", "content": message}]}, config, stream_mode="values"
        )
        for event in events:
            _print_event(event, _printed)
        snapshot = graph.get_state(config)
        while snapshot.next:
            graph.invoke(None, config)
            snapshot = graph.get_state(config)
        chatbot.append({"role": "user", "content": message})
        chatbot.append({"role": "assistant", "content": snapshot.values["messages"][-1].content})
        return "", chatbot, None
