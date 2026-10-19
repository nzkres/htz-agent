# htz-agent：源码审计与一次修业最小方案

本仓库保留 [Lixiuxiu559/htz-agent](https://github.com/Lixiuxiu559/htz-agent) 的源码和历史，补充对 Windows 电脑版《幻唐志》的复用分析及实施清单。

**已完成源码审计和只读 `microvision` 图片识别原型；尚未实现或验收“登录 → 选人物 → 完成一次修业”。上游脚本不能直接当成可用成品运行。**

- 审计日期：2026-10-19（Asia/Shanghai）。
- 上游基线：`fdb352c6acb360d69641d64cc644080cc59b92fc`，提交于 2026-04-25 21:05:57 +08:00。
- 未导入或运行上游 `core/tasks`、未操作游戏账号、未修改上游 Python 代码。新增 `microvision` 独立安装必要的图像依赖并完成离线验证。
- 已删除的 Windows 实验虚拟机不会因下载本项目而恢复。此前客户端拒绝虚拟环境的问题仍是执行环境的前置限制。

## 阅读入口

| 文件 | 内容 |
|---|---|
| [长期目标与路线](docs/LONG_TERM_GOAL.md) | 成品标准、成本、V0/V1 验证及后续阶段 |
| [三种小电脑路线](docs/HARDWARE_ROUTES.md) | N100/N150、M920x RX560 和小机箱组装的步骤、试机门槛与共同验收 |
| [玩法覆盖清单](docs/PLAYBOOKS.csv) | 六项日常及其他玩法的待核验范围 |
| [微型识别器](docs/MICROVISION.md) | 可运行的图片 → JSON CLI、中文 OCR、模板识别与验证方法 |
| [代码复用与缺口](docs/CODE_REVIEW.md) | 按模块和函数说明真实实现、缺陷、优先级及复用条件 |
| [最小实现与验收](docs/MINIMUM_PLAN.md) | 登录、选人物、一次物资修业的状态、文件计划及验收证据 |
| [任务列表](TASKS.csv) | 依赖、建议负责人、交付物和完成条件；可分配实施 |
| [源码来源](docs/PROVENANCE.md) | 上游版本、归属、发布范围与许可证状态 |
| [静态审计数据](docs/audit.json) | 源文件哈希、行数、函数清单和缺失文件；由只读扫描产生 |

## 复用结论

优先复用 `ScreenCapture` 的 Windows 截图、`Executor.click/key_press` 的输入基础，以及配置和受限 OCR；先统一窗口、坐标、前台校验和识别失败停止规则。

另写一个短的单次状态流程，读取当前修业要求、核对背包物资、交付并验证游戏内完成次数变化。上游 `ShiMenTask` 的占位分支与计数逻辑不适合作为验收基础。

第一版限制为单窗口、单角色、固定客户端尺寸，一次“收集物资并交付”任务。账号密码由用户直接在官方客户端输入；脚本等待登录后的明确状态。未覆盖的任务或缺物必须停止并显示原因。自动采购、战斗、六项日常和无人值守重登在后续范围。

## 验收边界

语法通过、窗口截图正常、点击已发送、本地计数增加，均不能证明修业已完成。只有完成“识别本次任务 → 实际执行 → 实际交付 → 游戏内完成确认”并留存脱敏证据，才能登记一次成功。

运行日志、登录画面、账号信息和真实游戏截图应只保留在本机，不随本仓库发布。仓库内原有 `SPEC.md`、`SKILL.md`、`CLAUDE.md` 和 `agents.md` 是上游内容，其能力描述和路线图不代表本次验证结果。

## 运行只读识别原型

```powershell
.\.venv\Scripts\python.exe -m pip install -r microvision/requirements-ocr.txt
.\.venv\Scripts\python.exe -m microvision.demo
.\.venv\Scripts\python.exe -m microvision frame.png --ocr --output runs\observation.json
```

需要先创建 Python 虚拟环境；完整说明见 [MICROVISION.md](docs/MICROVISION.md)。原型不包含窗口采集和输入执行器，未校准场景保持 `unknown`。

当前预算：新增现金支出上限 **0 元**。服务器/硬件购买、游戏充值、新购付费减负和新增计费 API 均不在当前路线内；真实游戏验证仍需免费、获准且兼容的运行环境。详见长期目标文档。
