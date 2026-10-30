# 桌面端交接（2026-10-19）

## 当前状态

- M0–M5 已完成：PySide6 无边框外壳、三关体检、改写闭环、学术翻译、目录版 exe。
- 目录版已构建并验证：`desktop/build/dist/deai/deai.exe`，整个目录约 94 MB；
  exe 自检 5/5 通过，窗口能启动、加载样本并正常退出。
- 单文件版尚未构建；没有用真实供应商密钥联调过。
- 门禁：桌面端 206 项测试通过；引擎自检 12/12。
- 本轮改动（自检入口、根 README 同步、交接更新）尚未提交。

## 运行、自检与门禁

```bash
cd desktop
python3 -m deai_app                      # 源码运行
python3 -m deai_app --smoke              # 源码自检
PYTHONIOENCODING=utf-8 python3 -m unittest discover -s tests -t .
cd .. && python3 code/selfcheck.py       # 12 项断言
```

windowed exe 没有 stdout，自检结果要写文件：

```bash
desktop/build/dist/deai/deai.exe --smoke --out smoke.txt
```

本轮实测输出：

```
deai 0.1.0 · frozen
[PASS] 词表级 · 21 条规则 · 反例命中 3 处
[PASS] 结构级 · 反例 1 处（风险 中） · 正例 0 处
[PASS] 字符级 · 检出 1 个 · 清理后 0 个
[PASS] 主题 · 26 色值 · 6 字号 · 3 个必需段
[PASS] 示例配置 · 6 个示例供应商
结论：全部通过（5/5）
```

## 打包

清单只在 `desktop/build/bundle.py` 写一次：引擎取自 `bridge.engine_files()`，
资源保持 `deai_app/assets` 相对位置；`paths.py` 在 frozen 模式下按同一位置取它们，
`tests/test_packaging.py` 钉住这条对应关系。

```bash
cd desktop
python3 build/build.py --dry-run        # 只打印命令
python3 build/build.py                  # 目录版：build/dist/deai/deai.exe
python3 build/build.py --onefile        # 单文件版：build/dist/deai.exe，冷启动要先解包
```

`build/dist/`、`build/work/` 与 PyInstaller 生成的 spec 已被 `.gitignore` 忽略。

## 后续（按优先级）

1. **单文件版**：构建一次，测冷启动、体积与杀软误报；目录版已验证，单文件版没有。
2. **真实供应商联调**：至少用一家远程供应商填 key，跑改写与中译英，
   核对 401/404/429/超时的文案、流式增量与取消。
3. **长文策略**：当前把全文直接放进提示词；超过上下文会由供应商报错，
   需要分段、截断或提示用户拆稿。
4. **译后去 AI 失败的回退**：两阶段切换时会清空翻译稿，第二段失败只剩错误提示；
   目标是不交付未去 AI 的译文，但可以保留译文草稿供重试。
5. 可选：应用图标、代码签名、安装器、依赖体积裁剪（排除项已在 `bundle.py`）。

## 已知约束与既定决策

- `code/` 是公开路径契约，目录名与调用方式不能改；桌面端只读调用，不复制规则。
- 用户配置与密钥在 `%APPDATA%\deai\`，仓库里只有不含密钥的 `providers.example.json`；
  界面与测试输出都不带出密钥原文。
- 翻译默认必须再过降 AI；`Settings.auto_deai_after_translate` 默认 True，界面没有关闭开关。
- 本地供应商绕过系统代理（Windows 注册表代理会把 `127.0.0.1` 接管成 502）。
- 改写/翻译结果在「整段」视图展示；复制与保存始终取纯文本，不取报告 HTML。
- 全项目不写 emoji 字面量，`tests/test_ui_contract.py` 扫全树；规则覆盖用码点构造样本。
- 所有模型调用只用标准库 `urllib` 手写 SSE；运行时第三方依赖只有 PySide6-Essentials。

## 本轮改动清单

- `desktop/deai_app/core/selftest.py`：无界面自检五项（词表、结构、字符、主题、示例配置）。
- `desktop/deai_app/__main__.py`：新增 `--smoke` 与 `--out`；`--checkup`/`--version` 也支持写文件。
- `desktop/tests/test_selftest.py`：7 项测试，含负向对照、stdout=None 与子进程落盘。
- `README.md`、`README.en.md`：补 `desktop/` 目录树与桌面应用说明，分类依据同步。
- `desktop/README.md`：打包一节补 exe 自检命令与目录版体积。
- 实际构建产物在 `desktop/build/dist/`，已被忽略，不随仓库提交。
