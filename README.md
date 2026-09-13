# 知课 Teacher Studio

基于解决方案文档落地的本地开发版。CPU 业务后台 + 浏览器课堂 + 独立 GPU 模型接口。当前可以先完成资料与课程流程，再在优云智算接入老师声音和真人模型。

## 启动

```bash
uv sync --frozen
npm ci
npm run build
bash scripts/start-local.sh
```

打开 http://127.0.0.1:8010 。没有真实素材时点击“体验示例课堂”。使用“静音阅读”可以在没有系统语音的环境验证课堂、翻页、提问与续讲。

## 实时对话

互动课堂顶部可切换「讲课与插问 / 实时对话」。点击开始实时对话，允许麦克风；说完一句自动发送，老师回答后继续聆听。回答期间可点「打断并说话」，也可发送文字。离开模式会停止收音与播放。

浏览器识别依赖浏览器支持和厂商网络服务，失败时页面会提示；GPU 识别连接后支持录音静音分句。当前是轮流说话和按钮打断，不是全双工或流式语音模型；老师克隆音色仍需部署。连续轮次保存在独立会话中，目前每轮按问题检索，省略主题的追问理解仍待增强。

## 已实现

- 教师档案、教学特点、授权确认；视频、声音、图片和 VRM 资产上传与存储。
- TXT / Markdown / DOCX / 文字 PDF 导入；预览、审核、teacher_id 隔离；jieba + rank-bm25 检索和原文引用。
- 可选 DeepSeek/OpenAI-compatible JSON 调用，引用必须包含有效来源与逐字原文；无效格式退回原文检索，服务失败明确提示。
- 资料整理为逐页课程草稿、编辑讲稿、审核发布、版本冻结、复制新版本。
- 课堂暂停、翻页、插问、显式继续；revision 比较防止取消后迟到回答覆盖当前课堂；SQLite 持久化进度。
- PptxGenJS 导出可编辑 PPTX，讲稿和资料依据写入演讲者备注。
- 浏览器演示声音；TTS/ASR HTTP 适配；three-vrm 加载用户 VRM、基础动作和说话节奏动画。
- 响应式中文界面、单管理员令牌、端到端测试、启动脚本、备份与迁移说明。

## 尚未完成或验证

老师声音克隆模型与权重部署、自动视频转声音档案、真人 WebRTC 适配、精确中文口型、语义检索/重排、AI 长篇教案生成、多用户权限、生产并发与 30 分钟 GPU 稳定性验收。配置地址不代表这些能力已经验收。详见 `docs/model-services.md` 与 `docs/deployment.md`。

## 工程结构

```text
web/                  React + TypeScript 课堂与管理页面
server/app.py         FastAPI 路由、授权、课程与会话协调
server/store.py       SQLite 持久化与会话 revision CAS
server/knowledge.py   文档解析、分段与中文 BM25
server/providers.py   LLM / TTS / ASR 服务适配
scripts/              启动、PPTX 导出、备份和浏览器测试
tests/                后台流程、隔离、取消、恢复和模型协议测试
docs/                 模型协议、部署和第三方集成说明
data/                 本地数据，已 gitignore
```

## 开发与验证

```bash
.venv/bin/python -m pytest -q
npm run build
# 另开终端启动独立测试服务（不要用真实素材数据库）
DATA_DIR=/tmp/teacher-studio-ui APP_PORT=8011 .venv/bin/python scripts/start.py
npm run test:ui
```

浏览器测试默认使用 macOS Chrome；其他系统设置 `CHROME_PATH`。测试截图和 PPT 写入 `test-results/`。API 文档在 `/docs`，但公网部署应由网关统一保护；业务 `/api` 路由受访问令牌保护。

现阶段是单管理员本地应用，不要直接作为多人公网平台发布。最终上云前会根据实际模型版本生成独立 GPU 安装与启动配置。

### 自动语音识别兜底

默认选择「优先浏览器 · GPU 自动兜底」。浏览器不支持、启动异常、网络/服务错误，或检测到说话后长时间无识别结果，会切到已配置的 GPU ASR。启动等待超时为 20 秒，说话等待为 20 秒，临时结果等待最终结果为 15 秒。无声事件不会触发切换。麦克风权限拒绝或采集错误会提示授权/设备检查，不尝试绕过权限。

切换时丢弃迟到浏览器结果，同一对话保持 GPU 路由；用户重新点击开始时再尝试浏览器。丢失的浏览器音频不能恢复，需重新说一遍。GPU 未配置或识别失败时暂停并保留文字输入。配置 `ASR_BASE_URL` 后重启后台即可启用现有 `/transcribe` 协议；配置不代表服务健康，需 GPU 实测。

运行 `node scripts/fallback-smoke.mjs` 可测试六种自动切换情形，使用模拟音频及 GPU 响应。
