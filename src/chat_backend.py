import uuid
import shutil
from agent_shema.mult_agents_graph import AgenticGraph
from load_config import LoadConfig
from utils.utilities import _print_event
from typing import List, Tuple
import os

CFG = LoadConfig()
db = CFG.local_file

db_exists = os.path.exists(db)

graph_instance = AgenticGraph()
graph = graph_instance.Compile_graph()
thread_id = str(uuid.uuid4())
print("=======================")
print("thread_id:", thread_id)
print("=======================")

config = {"configurable": {"thread_id": thread_id, "recursion_limit": 50}}


class ChatBot:
    @staticmethod
    def respond(chatbot: List[dict], message: str) -> Tuple:
        _printed = set()
        events = graph.stream(
            {"messages": [{"role": "user", "content": message}]}, config, stream_mode="values"
        )
        for event in events:
            _print_event(event, _printed)
        snapshot = graph.get_state(config)
        while snapshot.next:
            result = graph.invoke(None, config)
            snapshot = graph.get_state(config)
        chatbot.append({"role": "user", "content": message})
        chatbot.append({"role": "assistant", "content": snapshot[0]["messages"][-1].content})
        return "", chatbot, None
