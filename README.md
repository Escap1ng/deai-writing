# deai-writing

[中文](README.md) | [English](README.en.md)

给中文或英文文稿过三道可执行门禁：去掉 AI 味，也去掉看不见的隐写字符。规则能跑、能复检、能回归，不靠通读时的感觉。

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![gates](https://img.shields.io/badge/gates-3-brightgreen.svg)
![rules](https://img.shields.io/badge/rules-21-orange.svg)
![self-check](https://img.shields.io/badge/self--check-12%20assertions-success.svg)
![python](https://img.shields.io/badge/tested%20on-3.13%20%7C%203.14-informational.svg)

## 它做什么

| 关 | 工具 | 检查什么 | 门禁 |
|---|---|---|---|
| **词表级** | `code/check_phrasing.py`<br>词表 `code/phrasing-blacklist.json` | 模板腔、套话、空泛、伪洞察等用词与句式，21 条中英规则 | 命中即退出 1，每条命中都附改法 |
| **结构级** | `code/check_style.py` | 过长被动句、句式重复、过渡词密度、长短句比例、相邻段落节奏、结果小数位 | 命中即退出 1；风险「高/极高」不得交付 |
| **字符级** | `code/strip_invisible.py` | 零宽字符、bidi 控制、tag 字符、变体选择符等不可见 Unicode | 交付产物清理后复检必须退出 0 |

**边界**：只处理表述与字符，不改动事实、数据与结论。去 AI 味不等于口语化，判据是「只有这位作者写得出」，来自作者本人的具体判断、具体数值与具体边界。

## 实测输出

用仓库自带的反例跑一遍。`examples/slop-sample.md` 是刻意写坏的中文样本：

```console
$ python3 code/check_phrasing.py examples/slop-sample.md
examples/slop-sample.md:5:1 [template-opener] 随着人工智能技术的快速发展（第 1 次出现，超过上限 0）
    → 以本题的具体矛盾、关键数字或经核实的文献切入，直入主题
examples/slop-sample.md:8:1 [formatting-slop] ## 模型效果 😀🚀✨（第 1 次出现，超过上限 0）
    → 删掉 emoji 与表情符号，标题用文字表达层级；强调靠事实与数据，不靠符号
examples/slop-sample.md:11:1 [fake-authority] 研究表明（第 1 次出现，超过上限 0）
    → 补上可核实的文献出处；找不到出处就删掉该论据（宁缺毋假）
examples/slop-sample.md:16:1 [colon-reveal] 最关键的一点：（第 1 次出现，超过上限 0）
    → 把结论前置，直接在主句里说出来
检查 1 个文件，命中 28 处（词表：21 条规则）
```

```console
$ python3 code/check_style.py examples/style-slop-sample.md
examples/style-slop-sample.md:5 [sentence-rhythm] 长句占比 59%（目标约 33%）
    → 拆分过长句、合并过短句，使长句占比落在 20%-50%
examples/style-slop-sample.md:7 [long-passive] 受限于样本规模，模型参数被反复调整而未能收敛到全局最优，该现象在数据稀疏时段尤为明显。
    → 拆成 2-3 个短句，主动语态优先
examples/style-slop-sample.md:11 [paragraph-rhythm] 相邻段落字数差异 2%（下限 20%）
    → 按内容需要拉开段落长短，重点段落展开、次要内容从简
检查 1 个文件，结构级命中 8 处；AI 痕迹风险：极高
```

两次都退出 1。命中处按输出里 `→` 之后的改法提示改写，改完复检，两个检查器都退出 0 才算过。

## 快速开始

### 安装

把本仓库放进 agent 的技能目录：

```
<project>/.trae/skills/deai-writing/
```

脚本只用 Python 标准库，PDF 模式额外需要 PyMuPDF（`pip install pymupdf`），不依赖宿主框架。已在 Python 3.13 与 3.14 上跑通全部自检。

### 跑三道关

```bash
python3 code/check_phrasing.py draft.md                # 词表级：命中即退出 1
python3 code/check_style.py draft.md                   # 结构级：命中即退出 1
python3 code/strip_invisible.py --clean draft.tex      # 字符级：就地清理并留 .bak
python3 code/check_phrasing.py --list-rules            # 查看词表规则与改法
python3 code/check_style.py --list-metrics             # 查看结构指标与阈值
```

带 `max_per_document` 的是频次上限，超出上限的部分才算命中。结构级风险等级为「高」或「极高」时不得交付。最终 PDF 与 Word 必须清理后复检，复检仍报 `CLEANED-RESIDUAL` 不得交付。

### 回归自检

```bash
python3 code/selfcheck.py                              # 12 项断言：正反例 + 规范文档自检 + 字符级闭环
```

改过词表、阈值或示例后必跑。

## 目录结构

```
deai-writing/
├── SKILL.md                       # 技能入口：定位、三道关、快速流程、强制项摘要、与其他技能的关系
├── README.md                      # 本文件（中文）：快速开始、目录结构、分类依据与扩展约定
├── README.en.md                   # 英文版 README：与 README.md 同构
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

## 与上游的关系

英文 slop 模式清单与句式分类参考 [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop)。本仓库在它之上做了三件事：

- 把清单整理成 21 条可执行的中英词表，加词只改 `code/phrasing-blacklist.json` 一处。
- 补上中文规则，以及结构级与字符级两道门禁，让「AI 味」从主观印象变成可复现的退出码。
- 把正反例固化成 `code/selfcheck.py` 的断言，原来靠人眼对照的「期望结果」现在写错就会失败。

## 分类依据

- **一级按内容类型分**：`code/` `docs/` `examples/`。这套目录词表在跨技能检索时语义不变，`code/` 恒为「可执行脚本与数据」，`docs/` 恒为「规范」，`examples/` 恒为「可复现示例」。
- **词表是数据不是代码**：`code/phrasing-blacklist.json` 既可被检查器读取，也可被第三方程序消费；加词只改这一处，`check_phrasing.py` 与 `docs/deai-rules.md` 随之生效。
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

## 致谢与许可

这个技能的规则体系建立在两个上游项目之上，各自取用的部分如下。

**petergyang/no-ai-slop**（MIT，作者 Peter Yang）

取用英文 slop 模式分类与编辑原则，包括二元对照、冒号揭晓、伪洞察铺陈、虚假深刻收尾、装饰性排版等类别。整理稿见 [`docs/no-ai-slop-reference.md`](docs/no-ai-slop-reference.md)，该文件保留上游 URL、commit `000650b156983f5159695b441477f4e63b25dc85` 与 MIT 声明全文。

**guillaumemeyer/watermarks-remover**（MIT）

取用不可见字符集与 IVD 保护逻辑，落在 `code/strip_invisible.py`，移植自上游 Layer A 的 `service/scripts/text_unicode.py`。该文件头部附有上游版权声明与 MIT 许可全文。

本仓库在上游之上的增量是中文词表规则、结构级与字符级两道门禁，以及把正反例固化成断言的 `code/selfcheck.py`。

**许可**：本仓库以 [MIT](LICENSE) 发布。再分发时请一并保留上游声明：上游 MIT 全文在 `docs/no-ai-slop-reference.md` 内，字符集相关的上游版权与许可全文在 `code/strip_invisible.py` 头部。
