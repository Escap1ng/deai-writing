"""core — 与界面无关的业务：流水线、提示词拼装、供应商配置、任务队列。

依赖方向只能是 core → bridge → code/。本层不许 import tkinter，也不许 import deai_app.ui。
"""
