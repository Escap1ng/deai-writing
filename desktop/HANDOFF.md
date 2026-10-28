# 桌面端交接（2026-10-19）

## 当前状态

- M0–M4 已完成：PySide6 无边框外壳、本地三关体检、改写闭环、学术翻译。
- M5 只完成脚手架：打包清单、构建脚本与 9 项清单测试已就位；PyInstaller 6.22.3
  已装在本机 Python 3.14 上，但 **exe 还没有实际构建过**。
- 仓库测试：桌面端 199 项全绿；引擎自检 12/12。
- 远端 `main` 在本批提交前位于 `204edfb`；本批包含 M4 与 M5 两个提交。

## 运行与门禁

```bash
cd desktop
python3 -m deai_app                     # 源码运行
PYTHONIOENCODING=utf-8 python3 -m unittest discover -s tests -t .
cd .. && python3 code/selfcheck.py      # 12 项断言
```

## M5 打包

清单只在 `desktop/build/bundle.py` 写一次：

- `bridge.engines.engine_files()` 返回的三个检查器与词表进 bundle 的 `code/`。
- `deai_app/assets/` 的文件进 bundle 的 `deai_app/assets/`。
- `paths.py` 在 frozen 模式下用同一相对位置取它们；`tests/test_packaging.py` 钉住对应关系。

构建命令（本轮未执行）：

```bash
python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
cd desktop
python3 build/build.py --dry-run        # 只打印命令
python3 build/build.py                  # 目录版：build/dist/deai/deai.exe
python3 build/build.py --onefile        # 单文件版：build/dist/deai.exe
```

产物目录已加入 `.gitignore`；`build/bundle.py`、`build/build.py` 与测试本身要跟踪。

## 下一步（按顺序）

1. **补 exe 自检入口**：windowed 构建里 `sys.stdout` 为 `None`，`print` 会静默丢弃，
   `--checkup` / `--version` 在 exe 里看不到输出。建议加 `--smoke --out FILE`：
   跑词表反例、结构反例、字符级清理、主题载入与配置目录读取，把结论写进文件。
   这项要在构建前做，否则无法证明 bundle 里的 `code/` 与 `assets/` 真的可读。
2. **实际构建并验证**：先出目录版；用 `deai.exe --smoke --out` 核对引擎与主题，
   再启动窗口跑一次本地三关；关窗后确认进程退出。单文件版另测冷启动时间。
3. **根 README 中英同步**：根 `README.md` 与 `README.en.md` 的目录树里仍没有 `desktop/`，
   需要补一行桌面端与打包入口的说明。
4. 可选：应用图标、代码签名、安装器、exe 体积与杀软误报测试。

## 已知约束与既定决策

- `code/` 是公开路径契约，目录名与检查器调用方式不能改；桌面端只读调用，不复制规则。
- 用户配置与密钥在 `%APPDATA%\deai\`，仓库里只有不含密钥的 `providers.example.json`；
  界面与测试输出都不带出密钥原文。
- 翻译默认必须再过降 AI；`Settings.auto_deai_after_translate` 默认 True，界面没有关闭开关。
- 本地供应商绕过系统代理（Windows 注册表代理会把 `127.0.0.1` 接管成 502）。
- 改写/翻译结果在「整段」视图展示；复制与保存始终取纯文本，不取报告 HTML。
- 全项目不写 emoji 字面量，`tests/test_ui_contract.py` 扫全树；规则覆盖用码点构造样本。
- 所有模型调用只用标准库 `urllib` 手写 SSE；运行时第三方依赖只有 PySide6-Essentials。

## 本轮改动清单

- `desktop/build/bundle.py`：打包清单、排除模块、PyInstaller 参数组装。
- `desktop/build/build.py`：目录版/单文件版构建入口，支持 `--dry-run`。
- `desktop/tests/test_packaging.py`：清单覆盖、frozen 路径、参数互斥、Qt 导入白名单。
- `desktop/README.md`：新增「打包成 exe」一节。
- `.gitignore`：从整目录忽略 `desktop/build/` 改为只忽略 `dist/`、`work/` 与 spec。
- `desktop/deai_app/paths.py`、`__init__.py`：修正过期注释（spec 路径、Tkinter 字样）。
