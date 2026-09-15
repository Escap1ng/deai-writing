# deai-writing

通用降 AI 写作技能：面向任意中文或英文文稿降低 AI 痕迹，并清除不可见字符。入口是 [SKILL.md](SKILL.md)，规范条文以 [docs/deai-rules.md](docs/deai-rules.md) 为唯一权威出处；本文件只说明目录组织、分类依据与扩展约定。

## 目录结构

```
deai-writing/
├── SKILL.md                       # 技能入口：定位、三道关、快速流程、强制项摘要、目录结构、与其他技能的关系
├── README.md                      # 本文件：目录组织、分类依据与扩展约定
├── code/                          # 可执行脚本与数据
│   ├── check_phrasing.py          #   词表级检查器：扫模板腔、套话、空泛、伪洞察，命中退出 1
│   ├── phrasing-blacklist.json    #   中英词表与句式规则（单一事实源，加词只改它）
│   ├── check_style.py             #   结构级检查器：六项指标 + 风险等级
│   ├── strip_invisible.py         #   字符级清理器：覆盖 tex/docx/pdf 与纯文本
│   └── selfcheck.py               #   回归自检：对 examples/ 全部正反例断言期望退出码
├── docs/                          # 规范
│   ├── deai-rules.md              #   降 AI 规范（唯一权威）：痕迹清单、改写规则、负面清单、个人声音保留、摘要去模板化、结构级细则、字符级清理
│   └── no-ai-slop-reference.md    #   英文参考：slop 模式清单与规则映射表（MIT，含来源 SHA 与版权声明）
└── examples/                      # 可复现示例
    ├── clean-sample.md            #   中文正例：词表级与结构级都应零命中
    ├── clean-sample.tex           #   中文正例（LaTeX 载体）：覆盖脚本的 .tex 代码路径
    ├── slop-sample.md             #   中文反例：词表级痕迹密集
    ├── style-slop-sample.md       #   中文反例：结构级痕迹密集
    ├── clean-sample-en.md         #   英文正例
    └── slop-sample-en.md          #   英文反例：en-slop-* 规则密集
```

## 分类依据

- **一级按内容类型分**：`code/` `docs/` `examples/`。这套目录词表在跨技能检索时语义不变，`code/` 恒为「可执行脚本与数据」，`docs/` 恒为「规范」，`examples/` 恒为「可复现示例」。
- **词表是数据不是代码**：`code/phrasing-blacklist.json` 既可被检查器读取，也可被第三方程序消费；加词只改这一处，`check_phrasing.py` 与 `docs/deai-rules.md` 随之生效。
- **字符集与句式规则各有上游**：`code/strip_invisible.py` 的字符集与保护逻辑移植自 [guillaumemeyer/watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover) 的 Layer A；句式规则与结构指标分类参考 [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop)，其英文 slop 模式清单整理为 `docs/no-ai-slop-reference.md`，MIT 版权声明与来源 SHA 随文保留。
- **层级最深 2 层**：`code/` `docs/` `examples/` 下方直接放文件，不再向下嵌套。

## 扩展约定

新增规则或清理规则集的交付清单：

```
code/phrasing-blacklist.json    # 在 rules 里加一条（id/label/severity/why/fix/patterns/max_per_document）
docs/deai-rules.md              # 对应补一行说明（反例写成行内代码，检查器会跳过，故文档可自检）
examples/                       # 必要时补正例或反例 fixture
python3 code/selfcheck.py       # 跑回归，确认全部断言仍通过
```

约定：

- 词表规则一律带 `why`（为什么算痕迹）与 `fix`（怎么改），检查器输出直接引用，保证「报出即有改法」。
- 结构级阈值写在 `code/check_style.py` 头部常量；调整后须同步 `docs/deai-rules.md` 与 `examples/` 的期望结果。
- 正则用 Python `re` 语法；写错正则应报错而不是静默跳过，规则加载时统一预编译。
- 规范文档里出现的反例一律用反引号包成行内代码，使其自身通过词表级自检。
- 脚本一律提供 `argparse` 入口，退出码统一为 `0` 成功 / `1` 校验失败 / `2` 用法或环境错误。
- 新增或修改示例后必须跑 `python3 code/selfcheck.py`。
