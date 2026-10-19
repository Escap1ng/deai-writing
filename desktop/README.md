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

## 动效

动效只用于状态变化与反馈，不装饰静止内容：

- 分段控件的白色药丸滑动 180ms，窗口淡入 180ms，悬停反馈与滚轮补间 120ms，全部缓出。
- 系统关闭「显示动画」时一律瞬时到位；`tests/test_motion.py` 同时验证 100–300ms 的时长边界、
  缓动类型、滚轮落点与降级路径。

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
