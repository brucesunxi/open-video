# 本地启动与优云智算迁移

## 现在在本地运行

要求 Python 3.11–3.13、uv、Node.js 20.19+ 或 22.12+、npm。建议 Node.js 22 LTS。项目路径包含空格，终端中保留引号。

```bash
cd "/Users/jianrong/Projects/open talking"
uv sync --frozen
npm ci
npm run build
bash scripts/start-local.sh
```

浏览器打开 `http://127.0.0.1:8010`。第一次点“体验示例课堂”，或创建老师。示例老师是虚构人物，资料为水的三态示例。浏览器声音不是声音克隆。

开发时可以分别运行 `.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8010` 与 `npm run dev`，界面地址为 `http://127.0.0.1:5173`。前端 `/api` 代理到后台。日常体验建议使用构建后的一体启动方式。

数据保存在 `data/studio.sqlite3` 与 `data/assets`，不会随着网页刷新丢失。`.env` 配置在根目录，修改后重启后端。停止前台服务使用 Ctrl+C。

## 优云智算部署顺序

以下是应用架构的部署步骤。尚未在新云实例上执行；GPU 模型安装将在读取当前服务器版本和老师素材后单独锁定，避免再次混装 TensorRT。

1. 保留已跑通的旧服务和模型备份，新建独立目录，例如 `/workspace/teacher-studio`，将源代码、`uv.lock`、`package-lock.json`、脚本和文档上传。不要上传本机 `.venv`、`node_modules` 或 macOS 缓存。
2. 选择稳定 GPU 实例，4090 24GB 作为单用户测试起点。卡通渲染在浏览器，GPU 主要留给 TTS/ASR；真人模型显存另测。不要据此承诺并发数。
3. 持久化目录挂载到云盘，设置 `DATA_DIR=/workspace/teacher-data`。应用环境与 Qwen、FasterLivePortrait 环境分别安装和锁定。
4. 安装本项目依赖并构建前端。创建 `.env`，设置 `APP_HOST=0.0.0.0`、`APP_PORT=8010`、至少 24 位随机 `APP_TOKEN`，以及模型服务配置。启动器在外网监听但没有强令牌时拒绝启动。
5. 使用平台 HTTP 端口映射或反向代理接入 **8010**，外部地址必须使用 HTTPS。TTS/ASR 同机只监听 127.0.0.1，例如 8020/8030，不配置为公共 WebUI 端口。
6. 接入模型适配服务，协议见 `docs/model-services.md`。`TTS_BASE_URL=http://127.0.0.1:8020`，`ASR_BASE_URL=http://127.0.0.1:8030`。设置老师声音档案 ID 后选择“老师克隆声音”。
7. 如果采用真人流，再配置 WebRTC/TURN；卡通界面不依赖 TURN。不要复用历史实例的公网 IP、端口或 PID。
8. 使用 systemd/supervisor 或容器重启策略守护业务与模型服务。执行一次整机重启，验证课程、素材、声音配置和进度恢复。

### 容器方式

仓库提供 CPU 业务容器 `Dockerfile` 与 `compose.yaml`，模型仍在独立 GPU 服务中。容器方式尚未在此 Mac 上构建测试。

```bash
cp .env.example .env
# 编辑 .env，设置 APP_TOKEN 和模型地址
docker compose up -d --build
docker compose logs -f studio
```

Compose 默认仅映射主机 `127.0.0.1:8010`，适合本机反向代理；若优云智算映射需要监听容器外网，明确调整宿主端口绑定，并保留令牌和 HTTPS。容器内的 `127.0.0.1` 是容器自身，独立模型容器用容器服务名，宿主模型用适当的网关地址。不要直接照抄宿主 loopback 地址。

## 迁移与备份

```bash
.venv/bin/python scripts/backup.py /你的备份目录
```

脚本要求先停止应用，复制 SQLite 与上传资产，输出带时间戳的压缩包。不包含 `.env` 密钥、GPU 权重或第三方模型环境。配置需单独安全保存。恢复时停服务，把压缩包内目录展开到新的 DATA_DIR，再启动并检查教师、知识库和课程。不要覆盖唯一一份正在使用的数据。

## 目前的部署边界

- 单管理员访问令牌模式，不是多人账号、租户权限或公网 SaaS 完整认证。
- SQLite 本地存储、同步文档导入和 PPT 导出适合原型与小规模验证；生产需队列、配额、审计和持久化对象存储。
- 知识库目前是 jieba + BM25 原文引用；接入 LLM 后有逐字引文校验，但还不是自动事实正确性证明。语义检索、重排和系统性课程测试仍需开发。
- 本地浏览器朗读依赖系统声音，不承诺音色与超长音频连续性；GPU 服务接入后再做延迟和连续课堂验收。
- 原始视频已可保存，自动提取声音与建模流水线尚未完成。

## 故障定位

| 现象 | 检查 |
| --- | --- |
| 网页不能打开 | 8010 是否启动、前端是否 `npm run build`，云平台是否映射 HTTP 端口 |
| 401 | APP_TOKEN 是否一致；重新输入访问令牌 |
| 查询没结果 | 资料是否属于当前老师、是否审核、问题关键词是否命中；课程内只查课程固定资料 |
| 声音没播放 | 查看声音模式；浏览器是否允许播放；GPU 模式检查服务与 voice_profile_id |
| PPT 导出失败 | Node.js、npm 依赖、exports 目录权限；不在 Python 环境安装 PPT 模型 |
| 视频无真人动画 | 当前参考图为静态；尚需接入并验收 OpenTalking 真人适配器 |
| 下载模型网络失败 | 检查代理与访问源；不要关闭 TLS 校验 |
