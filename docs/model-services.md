# 模型服务接入协议

业务服务不导入 torch、TensorRT 或 Qwen。CPU 后台通过 HTTP 调用独立进程；本地未配置时，知识问答使用原文检索，声音由浏览器演示。页面不会把未接入的服务标记为已经成功推理。

## 已实现的适配器

| 能力 | 本地代码 | 云端约定 |
| --- | --- | --- |
| 大模型 | `server/providers.py` | OpenAI-compatible `POST /chat/completions`，支持 JSON response_format；默认 DeepSeek |
| 声音合成 | `server/providers.py` | `POST /synthesize` 返回 WAV/MP3 音频 |
| 语音识别 | `server/providers.py` | `POST /transcribe` 接收 multipart 文件，返回 `{ "text": "…" }` |
| 卡通形象 | `web/Avatar.tsx` | 浏览器内 three-vrm 加载用户上传的 VRM；不需要云端逐帧生成 |
| 真人视频 | 尚待整合 | 将已有 OpenTalking 会话 / OmniRT / WebRTC 协议适配为播放器事件，不能只填写 URL 就完成 |

这里的 `/synthesize` 与 `/transcribe` 是本项目的适配接口，**不是声称 Qwen 官方 WebUI 原生提供这些接口**。部署 Qwen3-TTS Base、Qwen3-ASR 时，要用包装服务把模型调用转换为下面的协议。GPU 环境和权重选型在拿到实际老师素材后完成验证；不在本地下载大模型。

## 声音服务

业务后台调用示例：

```http
POST /synthesize
Authorization: Bearer <TTS_API_KEY>
Content-Type: application/json

{"text":"这节课我们来了解水的三态。","voice_profile_id":"teacher-lin-v1","format":"wav"}
```

成功返回 `200 Content-Type: audio/wav` 与完整音频字节，或 `audio/mpeg`。单段上限 2000 字、30MB、90 秒请求超时；第一版是分段整段音频返回，不是首包流式 TTS。流式 PCM 与精确音素时间戳是后续协议扩展。

云端维护 `voice_profile_id → 经过审核的参考音频、转写文本、模型和版本`。声音档案由 GPU 服务创建；在教师资料中填入 ID。业务后台只传 ID，不能允许客户端提交任意云端文件路径。参考声音版本应保持不可变，替换时创建新 ID。

老师视频和参考声音现在可以上传保存，但尚未自动执行：视频分离、说话人确认、音频质量检查、声音建档或微调。实现这些任务时加入任务队列和人工确认步骤。

## 语音识别服务

```http
POST /transcribe
Authorization: Bearer <ASR_API_KEY>
Content-Type: multipart/form-data

file=<浏览器录音>
```

返回 `{"text":"蒸发是什么意思？"}`。包装服务需支持浏览器录音格式（通常 WebM/Opus，Safari 可能 MP4/AAC），用 FFmpeg 转换到模型要求的采样率。当前界面录音最长 60 秒、15MB；完成后先填入问题框，让用户检查再发送。

## 真人服务与现有 OpenTalking

本地没有克隆旧服务器仓库，也没有用未知版本冒充已接入。下一步在 GPU 服务器读取实际 OpenTalking/OmniRT 版本及会话协议后，独立实现真人适配器：

1. 由教师资产选取已授权的头像和声音。
2. 把本系统的讲稿/问答语音送入驱动服务，或接入其支持的文本驱动模式。
3. 通过真实 WebRTC offer/answer 建立视频流，并验证 TURN 端口。
4. 把 pause、cancel、turn_id 对齐，只有一处播放音频。
5. 对三分钟讲课和连续插问做音画与取消测试。

现有服务器已经验证的 TensorRT 8.6 环境应保持独立，不在其中安装新的 Qwen 模型依赖。

## 卡通动作的当前精度

已经接入 three-vrm loader、角色更新、眨眼、基础点头与抬臂。没有角色素材时显示自行绘制的程序化示例角色；PNG/JPG 只显示参考图。当前 VRM 口型按说话状态做节奏动画，**不是音素级同步**。后续通过 TTS 时间戳或 HeadAudio 输出接入表情权重，再验证中文口型和动作自然度。未使用第三方示例角色，上传 VRM 时需要持有角色许可。

## 接入与故障测试

先在服务所在机器验证合成一条短音频，再配置本项目 `.env`。TTS 或 ASR 的 API 密钥只留在后台。不要把没有 TLS 的模型端口直接暴露公网；同服务器用 loopback，分服务器用专网或 SSH 隧道。

`tests/test_providers.py` 用模拟 HTTP 响应验证请求格式与错误处理；这不等于实际 GPU 模型已经验收。

## 已实现的 GPU 包装服务（2026-09-11）

gpu/asr_service.py 和 gpu/tts_service.py 已部署到新实例，仅监听 loopback。实测记录见 cloud-status.md。声音注册接口 POST /profiles 接收 file、transcript、consent，返回 voice_profile_id；业务接口 POST /api/teachers/{id}/voice-profile 根据该老师的声音素材建立档案并自动保存 ID。网页已接入。视频自动分离与真人驱动仍待完成。参考录音仅限 3–30 秒、15MB。
