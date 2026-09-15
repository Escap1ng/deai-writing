---
name: deai-writing
description: 通用降 AI 写作技能：词表级扫模板腔与套话、结构级校正句式与段落节奏、字符级清除零宽与不可见字符，中英双语稿件润色。当用户提出去 AI 味、降低 AI 痕迹、去 AI 化、读起来像不像 AI、AI slop、de-slop、去除零宽字符、改写模板腔与套话、优化句式与段落节奏时触发。
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# 降 AI 写作技能（去 AI 味 + 字符清理）

## 定位

本技能只管三件事：文稿读起来像不像人写的、带不带隐写字符。适用对象是任意中文或英文文稿，包括学术论文、技术报告、博客、公众号推文、邮件、对外介绍稿。

- **词表级**：`code/check_phrasing.py` 读取词表 `code/phrasing-blacklist.json`，扫描模板腔、套话、空泛、伪洞察等 AI 痕迹用词与句式，含英文规则 `en-slop-*`、格式装饰规则 `formatting-slop` 与破折号堆砌规则 `em-dash-cluster`。
- **结构级**：`code/check_style.py` 检查六项结构指标（过长被动句、句式重复、过渡词密度、长短句比例、相邻段落节奏、结果小数位），输出 `低/中/高/极高` 风险等级。
- **字符级**：`code/strip_invisible.py` 清除零宽字符、bidi 控制、tag 字符、变体选择符等不可见 Unicode（字符集移植自 watermarks-remover 的 Layer A），覆盖 `.tex` / `.docx` / `.pdf` 与纯文本。

**不管**：选题立意、事实核查、模型与算法、版式排版、评分。这些各有归属，本技能不承接。

**边界**：降 AI 只处理表述与字符，不改动事实、数据与结论。去 AI 不等于口语化，判据是「只有这位作者写得出」，来自作者本人的具体判断、具体数值与具体边界。

## 三道关

| 关 | 处理对象 | 工具 | 门禁 |
|---|---|---|---|
| 词表级 | 模板腔、套话、空泛、伪洞察等用词与句式 | `code/check_phrasing.py` + 词表 `code/phrasing-blacklist.json` | 命中即退出 1，改写后复检 |
| 结构级 | 过长被动句、句式重复、过渡词密度、长短句比例、相邻段落节奏、结果小数位 | `code/check_style.py`（阈值见 `--list-metrics`） | 命中即退出 1；风险等级「高/极高」不得交付 |
| 字符级 | 零宽字符、bidi 控制、tag 字符、变体选择符等不可见 Unicode | `code/strip_invisible.py`（Layer A 字符集） | 交付产物清理后复检必须退出 0 |

三关互补：词表级管「用词像不像 AI」，结构级管「句式与段落节奏像不像 AI」，字符级管「带不带生成工具的隐写标记」。三关都过，才算一篇干净的稿子。

## 快速流程

**第 1 步 表述级检查**（词表级与结构级依次跑）

```bash
python3 code/check_phrasing.py article.md                 # 词表级：命中即退出 1
python3 code/check_style.py article.md                    # 结构级：命中即退出 1
python3 code/check_phrasing.py --list-rules                # 查看词表规则与改法
python3 code/check_style.py --list-metrics                 # 查看结构指标与阈值
```

命中处按输出里 `→` 之后的改法提示改写：补具体数值、补可核实出处、拆长句、拉开相邻段落字数差。改完复检，两个检查器都要退出 0。词表规则里带 `max_per_document` 的是频次上限（按文件统计），超出上限的部分才算命中，例如全文用一次 `综上所述` 可以接受，堆砌则报错。长文与短文的口径不同：长文容忍少量修饰性破折号，短文（推文、邮件、摘要）里的破折号应为 0 处。

**第 2 步 字符级清理**

```bash
python3 code/strip_invisible.py --clean draft.tex                  # 编译或导出前：从源头清干净
python3 code/strip_invisible.py --clean deliver.pdf deliver.docx   # 交付前：就地清理最终产物
python3 code/strip_invisible.py deliver.pdf deliver.docx           # 复检：必须退出 0
```

先检测（报 `FOUND` 即退出 1），再用 `--clean` 就地清理，最后复检。PDF 模式需要 PyMuPDF（`pip install pymupdf`），`.tex` 与 `.docx` 模式只用标准库。最终 PDF 与 Word 都必须清理并复检，复检仍报 `CLEANED-RESIDUAL` 时不得交付。

**第 3 步 个人声音补写**

按 `docs/deai-rules.md` 第四节，在方法选型、结论评价、结果分析、推广展望处补上判断痕迹（候选比较与取舍依据）、量化的局限（点名假设，说明失效情形，给出影响幅度与适用边界）、机理阐释（因果链，而不是罗列数据）、可核实的现实锚定（案例与数据必须能查到来源，查不到就跳过），以及沿数据、方法、场景三个方向的展望。补写内容必须以作者本人的数据与逻辑为支撑。

补写完成后跑一次技能自检，确认检查器、词表与规范示例仍在同一口径上；改过词表、阈值或示例后必跑：

```bash
python3 code/selfcheck.py                                  # 回归自检：12 项断言全过才算通过
```

## 强制项摘要

- 章节开头直入主题，不用 `随着…的快速发展`、`在当今社会`、`众所周知` 式模板腔开场。
- 过渡句必须携带信息量：呼应上文的结论，或点明下文的实质任务；`综上所述`、`值得注意的是` 这类纯形式衔接按频次上限从严处理。
- 无依据空泛词与含糊收尾（`很明显`、`效果很好`、`一定程度上`、`有望`、`较为理想`）一律改为具体数值与具体场景。
- 权威含糊（`研究表明`、`专家认为`）必须补可核实的出处，找不到就删，宁缺毋假。
- 空泛形容词（`至关重要`、`显著提升`）改为与本题相关的专业表述，并补数值或机制。
- 句式与段落节奏：拆分超过 25 字的被动句；同类句式连续不超过 3 次；每段过渡词不超过 2 个；相邻段落字数差异不低于 20%；结果统一保留 2 到 4 位小数。
- 摘要开头必须有实质钩子（矛盾、数字或困境），不用 `本文对…问题进行了深入研究` 式开场。
- 逻辑与风格：全文至少 2 到 3 处客观自审（点名假设，说明失效情形与量化影响，给出适用边界）；所有结论须有数据或理论支撑。
- 门禁：全文跑两个检查器双双退出 0，风险等级「高/极高」时不得交付；每处改写保留「原句 → 改句 → 依据」痕迹。
- 最终产物跑字符级复检，退出 0 才算交付完成。

完整条文、负面清单、摘要去模板化对照表与结构级细则以 [`docs/deai-rules.md`](docs/deai-rules.md) 为准。

## 目录结构

```
deai-writing/
├── SKILL.md                       # 技能入口：定位、三道关、快速流程、强制项摘要
├── README.md                      # 目录组织与扩展约定
├── code/
│   ├── check_phrasing.py          # 词表级检查器（词表驱动，argparse 入口）
│   ├── phrasing-blacklist.json    # 中英词表与句式规则（单一事实源）
│   ├── check_style.py             # 结构级检查器（六项指标 + 风险等级）
│   ├── strip_invisible.py         # 字符级清理器（tex/docx/pdf，Layer A 字符集）
│   └── selfcheck.py               # 回归自检：对 examples/ 全部正反例断言期望结果
├── docs/
│   ├── deai-rules.md              # 降 AI 规范（中文，唯一权威）
│   └── no-ai-slop-reference.md    # 英文参考（含上游 MIT 声明与来源 SHA）
└── examples/
    ├── clean-sample.md            # 中文正例：词表级与结构级都应零命中
    ├── clean-sample.tex           # 中文正例（LaTeX 载体）：覆盖 .tex 代码路径
    ├── slop-sample.md             # 中文反例：词表级痕迹密集
    ├── style-slop-sample.md       # 中文反例：结构级痕迹密集
    ├── clean-sample-en.md         # 英文正例
    └── slop-sample-en.md          # 英文反例：en-slop-* 规则密集
```

## 与其他技能的关系

| 技能 | 定位 | 与本技能的关系 |
|---|---|---|
| `.trae/skills/no-ai-slop/` | 纯英文上游版本，单文件 `SKILL.md` 加 `eval.md`，给英文写作提供人工可读的 slop 模式清单与自评表 | 本技能是它的中英双语可执行版：英文规则 `en-slop-*` 整理自该上游，规则清单另存 `docs/no-ai-slop-reference.md` 并保留 MIT 声明与来源 SHA；上游保留为参考版本，不做改动，词表也不再重复维护 |

除 `no-ai-slop` 外，本技能不依赖也不引用其他技能，独立可用。
