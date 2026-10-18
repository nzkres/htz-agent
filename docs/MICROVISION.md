# 微型图片识别器：图片 → JSON

`microvision` 是本仓库新增的只读 Python 模块。它接收图片文件，输出文字、图形候选、模板位置及配置规则识别出的界面状态；不启动游戏、不读取游戏内存、不输入密码、不发送鼠标/键盘。

## 能识别到哪一层

| 层次 | 实现 | 边界 |
|---|---|---|
| 文字与数字 | 本机 CPU RapidOCR，中文/英文；返回原文、框和分数 | 可能错字漏字；动态物品名/数量仍需任务规则解析 |
| 已知按钮/图标 | OpenCV 模板匹配，限定区域和阈值 | 分辨率、缩放或外观改变后需要校准；重复目标保留并标歧义 |
| 未知图形 | 轮廓候选及位置 | 只能叫 `visual_candidate`，不能凭轮廓确定它是按钮或会触发什么 |
| 界面状态 | 配置中的文字条件和唯一模板条件 | 未校准、尺寸不符或多规则冲突时，不给出确定场景 |

它可以接收不同游戏的截图，但不能自动理解“任意界面里所有图形的含义”。OCR 分数和模板相似度也不是同一种概率，更不代表点击正确率。

## 安装与运行

在仓库根目录，用 Python 3.11+：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r microvision/requirements-ocr.txt
.\.venv\Scripts\python.exe -m microvision "C:\path\to\frame.png" --ocr --output runs\observation.json
```

不需要 OCR 时，只装 `microvision/requirements.txt` 并省略 `--ocr`。中文 OCR 使用固定的 `rapidocr_onnxruntime==1.4.4` 包及其随包模型，不需 API key，不向云端发送图片。依赖和模型大小与 Python 代码大小不同；本模块不是零依赖程序。

从 `microvision/config.example.json` 复制出本地配置，可定义 `masks`、`expected_size`、图标模板和状态规则；模板路径相对于配置文件。`calibrated=true` 且指定匹配的图片尺寸才启用状态规则。示例配置不代表任何真实游戏界面已校准。

登录、密码、验证码和聊天区域应在拍摄前避开，或以 `masks: [[x,y,width,height]]` 遮蔽；遮蔽发生在识别与图像摘要计算之前。不要对已填凭据的完整登录页做 OCR 或公开上传图片/结果。

## 可重复的最小验证

```powershell
.\.venv\Scripts\python.exe -m microvision.demo --out runs\microvision-demo
.\.venv\Scripts\python.exe -m microvision runs\microvision-demo\frame.png --config runs\microvision-demo\config.local.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_microvision.py" -v
```

演示生成一张人工 UI、一个图标模板和真实识别结果，不冒充游戏画面或真实任务。预期识别 `enter_game` 的框为 `[410,250,170,54]`，中心 `[495,277]`。单测验证坐标、重复目标、负样本、遮蔽和失败情况；它们不能代替实际游戏验收。

## JSON 如何交给控制端

主要字段：`image`（尺寸、摘要、坐标约定）、`state`（场景和依据元素 ID）、`elements`（文字/模板/未知候选）、`template_groups`（数量和歧义）、`warnings`。

每个元素含 `id/kind/label/source/score/bbox/center`。`bbox` 永远是 `[x,y,width,height]`，左上原点、输入图片整数像素；不是窗口或桌面的屏幕坐标。`processed_at` 只是本次解析时间，不表示原始截图新鲜；文件图片可以是旧图。

识别器的 JSON 可直接由调用端读取；当前聊天中的开发代理也可通过本机工具运行 CLI 并读取它。后续完整循环是：

```text
游戏所在电脑截图 → 本机识别器 → JSON + 必要的脱敏局部图
    → 决策端提出动作 → 控制层核对窗口/最新画面/当前状态/唯一目标
    → 执行一次输入 → 新截图确认结果
```

当前只实现了“图片到 JSON”。实时窗口采集、向决策端传输、动作执行和登录/修业状态机仍待接入。不能把图中“重新登录”这几个字直接当成“已经登录成功”，也不能仅凭中心点就执行点击。

账号密码仍由用户在官方客户端输入；首次登录成功后的角色页面才进入后续自动流程。识别器无法消除此前客户端对虚拟环境的拒绝，也没有恢复已经删除的虚拟机。

OCR 文本、配置标签和图片内容只是待分析数据，不能作为系统指令或可执行命令。公开仓库只保存代码、人工演示生成器和文档；真实游戏图片和 OCR 结果放在被忽略的 `runs/` 中。

## 本轮验证记录

已用此前留存的 780×290 游戏错误弹窗裁剪验证本地中文 OCR：读出了环境错误提示、“重新登录”和“离开游戏”，并返回各自的像素框。该图片没有账号信息，未纳入公开仓库。

这只证明特定历史图片能转成结构化观察；当前客户端运行、登录、人物选择和一次修业均未验收。测试版本及结果见提交记录和本机运行输出。

技术依据：[OpenCV 模板匹配](https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html)、[RapidOCR 项目](https://github.com/RapidAI/RapidOCR)、[固定 OCR 包](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/)。
