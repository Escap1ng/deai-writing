# 桌面端交接（2026-10-19 起，2026-11-01 更新）

## 当前状态

- M0–M5 已完成：PySide6 无边框外壳、三关体检、改写闭环、学术翻译、目录版与单文件版 exe；
  译后降 AI 失败已可保留译文草稿并整段重试，超长输入有了按供应商上下文的前置拦截（2026-10-30 补）。
- 界面使用优化已接通（2026-11-01 补）：失败与指引长文案进可换行提示条（状态行留摘要）、
  供应商切换与翻译方向前置到主界面、输入栏支持拖放载入、窗口几何记忆、
  生成期间动作按钮禁用并显示脉冲点。
- 目录版已构建并验证（2026-11-01 重打，含长文拦截与界面优化）：`desktop/build/dist/deai/deai.exe`，
  约 94 MB；exe 自检 5/5、退出码 0；窗口 0.94 s 出现，WM_CLOSE 后退出码 0。
- 单文件版已构建并验证（同日重打）：`desktop/build/dist/deai.exe`，38,560,734 字节（约 37 MB）；
  三次 `--smoke` 均 5/5、退出码 0，全程 1.5–1.9 秒；窗口 1.62 秒出现，WM_CLOSE 后
  引导与解包子进程都已退出（子进程退出码探针侧没取到，同口径目录版为 0）。杀软误报尚未实测。
- 没有用真实供应商密钥联调过。
- 门禁：桌面端 266 项测试通过；引擎自检 12/12。

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

验证口径（2026-11-01 实测固定）：目录版/单文件版各跑 `--smoke --out`（单文件连跑三次取区间），
再各自过一次窗口探针——启动后轮询出现的可见顶层窗口（单文件版是「引导父进程 + 解包子进程」
双进程，窗口属子进程，要按进程名找属主而不是 Start-Process 拿到的 PID）、发 WM_CLOSE、
等「属主退出 + 8 秒内全部退出」；中途发现进程残留就先优雅收尾，绝不按映像名杀。
探针动的是 `%APPDATA%\deai\window.json`，先备份再还原；临时探针脚本放系统 Temp，不进仓库。

## 后续（按优先级）

1. **真实供应商联调**（唯一没走过的面，需要远程供应商 key）。验收点：
   - 改写与中译英各跑一遍：流式增量逐段上屏、逐轮复检、生成中「停止生成」能中断；
   - 401 / 404 / 429 / 超时的文案与实际错误一致，不泄露 key；
   - 译后降 AI 失败：草稿保留、界面标「未过降 AI」、「重试降 AI」只重跑该段；
   - 长文拦截：给供应商填 `context_tokens` 后，超长输入在发出前被拦，
     提示条完整展示拆稿指引；不填则不检查；
   - 供应商下拉与翻译方向切换后重启应用，选择仍保留。
2. **长文第二层（未设计）**：`context_tokens` 只做发送前拒绝；分段、截断或按章节拆稿
   的策略还没有设计，属于后续议题。
3. **可选项**：应用图标、代码签名、安装器、单文件版杀软误报实测、
   依赖体积裁剪（排除项已在 `bundle.py`）。

已完成、已收档：M0–M5、译后回退（失败/取消保草稿、重试只跑降 AI 段）、
长文第一层（`core/limits.py` 发前拦截）、界面使用优化（2026-11-01）、两版 exe 重打包。

## 已知约束与既定决策

- `code/` 是公开路径契约，目录名与调用方式不能改；桌面端只读调用，不复制规则。
- 用户配置与密钥在 `%APPDATA%\deai\`，仓库里只有不含密钥的 `providers.example.json`；
  界面与测试输出都不带出密钥原文。
- 翻译默认必须再过降 AI；`Settings.auto_deai_after_translate` 默认 True，界面没有关闭开关。
- 本地供应商绕过系统代理（Windows 注册表代理会把 `127.0.0.1` 接管成 502）。
- 改写/翻译结果在「整段」视图展示；复制与保存始终取纯文本，不取报告 HTML。
- 全项目不写 emoji 字面量，`tests/test_ui_contract.py` 扫全树；规则覆盖用码点构造样本。
- 所有模型调用只用标准库 `urllib` 手写 SSE；运行时第三方依赖只有 PySide6-Essentials。
- 消息路由只有一条路：一切状态文案经 `_say()`；状态行是单行摘要通道，
  失败与指引类（`banner=True`）进可换行提示条，56 字长度阈值只兜底。
- 窗口几何（含最大化标记）单独存 `%APPDATA%\deai\window.json`，不与模型配置混档；
  越屏位置恢复时丢弃。

## 最近一次功能批（2026-11-01）：界面使用优化

- `desktop/deai_app/ui/app.py`：`split_message()` 消息路由（56 字阈值兜底，
  失败/指引类以 `banner=True` 显式挂条）+ 双栏下方可换行提示条；
  工具栏供应商下拉（切换即写回 `active_provider` 并落盘）、
  输入栏头的学术翻译方向分段（`translate_target` 即时落盘）；
  `_prepare_generation` / `_on_worker_finished` 统一开合锁与脉冲点；
  窗口几何读写（`%APPDATA%\deai\window.json`，含最大化标记，越屏位置丢弃）。
- `desktop/deai_app/ui/panes.py`：动作按钮收进引用表与 `set_actions_enabled()`；
  拖放（`first_loadable_url` 挑后缀、dragEnter/Move/Leave/drop 四态 + dragOver 高亮的 properties 选择器）。
- `desktop/deai_app/ui/segmented.py`：mouse/key 事件增加 `isEnabled()` 防线。
- `desktop/deai_app/ui/style.py`：`#banner`、`#busyDot`、`#pane[dragOver="true"]`。
- 测试：`test_rewrite_ui.py` 路由/快控/拖放几何/生成锁四组 +22 项，
  `test_qt_shell.py` 最窄宽度契约改（按钮保 sizeHint，状态行保可见下限），
  `test_rewrite_e2e.py` 失败指引断言移到提示条；桌面端门禁 266 项；引擎自检 12/12。
