#!/usr/bin/env python3
# type: ignore

import os
import sys

import gradio as gr

from chat_backend import ChatBot
from utils.ui_settings import UISettings

# Добавляем корневую директорию в пути для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with gr.Blocks() as demo:
    with gr.Tabs():
        with gr.TabItem("PC Customer Advisor"):
            ##############
            # Первая строка:
            ##############
            with gr.Row() as row_one:
                chatbot = gr.Chatbot(
                    value=[
                        {
                            "role": "assistant",
                            "content": "Привет! Я твой проводник в мир компьютерной техники. Чем сегодня могу тебе помочь?",
                        }
                    ],
                    type="messages",
                    elem_id="chatbot",
                    height=500,
                    avatar_images=("images/user.jpg", "images/chatbot.png"),
                )
                chatbot.like(UISettings.feedback, None, None)

            ##############
            # Вторая строка:
            ##############
            with gr.Row():
                input_txt = gr.Textbox(
                    lines=2,
                    scale=8,
                    placeholder="Введите текст и нажмите Enter или загрузите PDF файлы",
                    container=False,
                )

            ##############
            # Третья строка:
            ##############
            with gr.Row() as row_two:
                text_submit_btn = gr.Button(value="Отправить текст")
                clear_button = gr.ClearButton([input_txt, chatbot])

            ##############
            # Обработка:
            ##############
            txt_msg = input_txt.submit(
                fn=ChatBot.respond, inputs=[chatbot, input_txt], outputs=[input_txt, chatbot]
            )

            txt_msg = text_submit_btn.click(
                fn=ChatBot.respond, inputs=[chatbot, input_txt], outputs=[input_txt, chatbot]
            )

if __name__ == "__main__":
    demo.launch()
