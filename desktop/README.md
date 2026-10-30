# desktop/ — 降 AI 写作桌面应用

无边框窗口的 exe。AI 改写走 OpenAI 兼容接口，三关门禁由仓库根 `code/` 的检查器判定。

## 分层契约

```
ui/     无边框外壳、分段控件、动效层      ← 只有这一层可以 import PySide6
core/   流水线、提示词拼装、供应商配置   ← 无界面依赖
bridge/ 载入 code/ 引擎的唯一出口        ← 不落盘、不复制规则
code/   三关检查器（仓库根，本目录之外）
```

依赖只许向下：`ui → core → bridge → code/`。`tests/test_layering.py` 用 AST 扫 import 钉住这条方向。

## 单一事实源

- 词表规则、结构指标与阈值只在 `code/phrasing-blacklist.json` 和 `code/check_style.py`，
  提示词从 `bridge.phrasing_rules()` / `bridge.style_thresholds()` 取，不在 App 里另抄。
- 颜色、字号、尺寸只在 `deai_app/assets/theme.json`，源码里出现裸色值会被测试拦下。
- 版本号只在 `deai_app/__init__.py` 的 `VERSION`。

## 闸门口径

App 左侧/右侧显示的命中数与风险等级，与命令行结果一致：

```bash
python3 code/check_phrasing.py article.md --json
python3 code/check_style.py article.md --json
```

`tests/test_bridge_parity.py` 会逐条比对两条路径的结果（含 `--lang en`、正例零命中、反例非零）。

## 改写闭环

- 「接口设置」（Ctrl+,）管理多个 OpenAI 兼容供应商与改写参数，配置存到 `%APPDATA%\deai\`；
  密钥只写本机，界面、错误信息与测试输出都不带出原文。
- 生成在后台线程里流式进行，窗口不会卡住；每轮结束跑本地三关，未通过就把命中与改法
  回灌给模型，按设置的轮次继续复检，命中清单是下一轮的唯一依据。
- 结果在「整段」视图展示，词表命中仍就地标色；切到「逐条」看该结果的三关报告。
  复制与存为文件始终取改写后的纯文本，不取带标记的 HTML。
- 本地供应商绕过系统代理：Windows 注册表代理会把 `127.0.0.1` 也接管成 502。

`tests/test_prompt.py` 与 `tests/test_pipeline.py` 钉住提示词来源与轮次判断；
`tests/test_llm_sse.py` 末段用同一家本地服务跑完整两轮；`tests/test_rewrite_e2e.py`
从按钮一直验到窗口里的最终文本。

## 学术翻译

- 模式切到「学术翻译」后主按钮变为「AI 翻译」；方向默认自动（中文↔英文），
  也可以在设置里固定为英文或中文。
- 翻译只负责跨语言：保住事实、数字、引用、LaTeX 与段落结构；术语前后一致。
- 译文随后自动进入同一套降 AI 闭环，由本地三关驱动复检，默认开启，不需要额外操作。
- 翻译阶段与去 AI 阶段各有一轮流式输出；界面在阶段切换时清空上一稿，最终只交付去 AI 后的文本。

`tests/test_translate.py` 覆盖方向判定与默译后去 AI；`tests/test_rewrite_e2e.py`
的中译英用例从按钮一路验到英文最终稿。

## 动效

动效只用于状态变化与反馈，不装饰静止内容：

- 分段控件的白色药丸滑动 180ms，窗口淡入 180ms，悬停反馈与滚轮补间 120ms，全部缓出。
- 系统关闭「显示动画」时一律瞬时到位；`tests/test_motion.py` 同时验证 100–300ms 的时长边界、
  缓动类型、滚轮落点与降级路径。

## 打包成 exe

打包清单只在 `build/bundle.py` 说一次：`code/` 的引擎与词表进 bundle 的 `code/`，
`deai_app/assets/` 进同名相对目录，`paths.py` 在 frozen 模式下按同一位置找它们；
`tests/test_packaging.py` 钉住这条对应关系。

```bash
python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
cd desktop
python3 build/build.py --dry-run   # 只打印 PyInstaller 命令，不装不跑
python3 build/build.py             # 目录版：build/dist/deai/deai.exe
python3 build/build.py --onefile   # 单文件版：build/dist/deai.exe，冷启动要先解包
```

构建后先用 exe 自检 bundle 内的引擎与主题（windowed exe 没有 stdout，结果写文件）：

```bash
build/dist/deai/deai.exe --smoke --out smoke.txt
```

目录版当前约 94 MB；`--smoke` 应输出 5 项 `[PASS]` 与「全部通过」。

默认出目录版：启动不慢，杀软误报也少。产物只含程序与规则，用户的
`providers.json`（含密钥）始终留在 `%APPDATA%\deai\`，不会被打进 exe。

## 测试

```bash
cd desktop
PYTHONIOENCODING=utf-8 python3 -m unittest discover -s tests -t .
cd .. && python3 code/selfcheck.py        # 引擎侧回归，须仍 12/12
```

项目文件不写 emoji 字面量；测试会扫描全树。`formatting-slop` 的覆盖改用码点构造的样本，
不靠静态文件里的表情符号。

运行时依赖只有一个：PySide6-Essentials（界面）。接口调用、SSE 解析与三关引擎全部只用标准库。

```bash
python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple PySide6-Essentials
```
