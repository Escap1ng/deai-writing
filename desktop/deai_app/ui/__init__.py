"""ui — 无边框外壳、控件与 Tab 布局。

只有本层可以 import tkinter；尺寸与颜色一律走 ui/theme.py 的 token。
包本身不导入任何控件，保持 `import deai_app.ui` 在无界面环境下也能成功（测试与 --smoke 依赖这点）。
"""
