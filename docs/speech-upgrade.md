# 语音与口型升级（2026-09-11）

## 实现

- TTS：保留 Qwen3-TTS-12Hz-1.7B-Base 和现有参考录音，使用 Faster Qwen3-TTS v0.3.0 的 CUDA Graph 解码。服务启动时捕获计算图、缓存最近四位已授权老师的参考提示并预热一次解码，健康检查就绪后才接收请求。回退可设置 `TTS_ENGINE=standard`。
- 嘴型：MuseTalk 1.5 读取同一份合成音频的 Whisper 特征，以 25 FPS 生成脸部嘴型，不再使用 RMS 音量控制嘴部开合。保留 LivePortrait 产生的轻微头部动作和眨眼；每个头像提前生成 100 帧模板，VAE 潜变量缓存复用，段落间继续模板帧位置。
- 输出：H.264/AAC 同一个 MP4，由同一个 video 元素播放。CPU veryfast/CRF25 压缩代替旧版 ultrafast 高码率输出。视频仍按短句返回，并非 WebRTC 帧流。
- 前端：首段最多 16 字，后续最多 20 字，优先在第 10 字之后按标点断句，避免过短问候后接长段落。只预取下一段，避免队列拥塞，保留取消逻辑。服务启动时预备最多两个已授权老师头像；实时课堂打开后再次调用幂等头像预备接口，覆盖新上传的照片。`/api/speech` 添加 Server-Timing 分别记录 TTS 与画面耗时。新增 `/api/speech/stream` 使用一次 SSE 连接连续传送分段 MP4/WAV（base64 数据），避免每段重新建立公网请求；每段携带索引、类型和耗时。客户端仅解码预取下一段，校验序号与完整性，取消会中断 fetch；服务端在断开后停止后续分段。当前 GPU 已执行的计算仍可能需要短暂完成。

## 固定版本与许可

- [Faster Qwen3-TTS](https://github.com/andimarafioti/faster-qwen3-tts)，v0.3.0 提交 `8034dcefbd42f6c0cbf1e37ec06c5655bb235684`，MIT。固定旧版是为了兼容当前 Transformers 4.57.3 / qwen-tts 0.1.1，不能直接升级为要求 Transformers 5 的最新版。
- [MuseTalk](https://github.com/TMElyralab/MuseTalk)，提交 `0a89dec45a0192b824e3cf4daf96c239440c5ed8`，代码 MIT；[权重卡](https://huggingface.co/TMElyralab/MuseTalk) 标记 CreativeML Open RAIL-M，并说明可商用，使用时仍需遵守该权重许可。
- [SD VAE](https://huggingface.co/stabilityai/sd-vae-ft-mse) 遵循其 OpenRAIL 许可；[Whisper tiny](https://huggingface.co/openai/whisper-tiny) 为 Apache-2.0。模型许可证不应与代码 MIT 混为一谈。
- LivePortrait 仍使用原固定版本；不下载或使用 InsightFace 检测权重，也未导入 MuseTalk 的 S3FD/DWPose/人脸解析依赖。仅使用 OpenCV Haar 检测单人正面照片，稳定框与软边嘴部融合。

## 复现安装

在有 Git 的部署电脑创建两个源码包，上传至 `/workspace/teacher-deploy/`：

```sh
git -C /path/to/faster-qwen3-tts archive v0.3.0 faster_qwen3_tts LICENSE pyproject.toml README.md | gzip > faster-qwen-v030.tar.gz
tar -czf musetalk-core.tar.gz -C /path/to/MuseTalk musetalk/models musetalk/utils/audio_processor.py LICENSE
```

GPU 主机用现有 TTS Python 运行 `scripts/prepare-speech-upgrade.py`，仅添加 diffusers==0.30.2（不升级原 torch），下载 MuseTalk V1.5、SD VAE、Whisper tiny。源码分别在 `vendor/faster-qwen` 和 `avatar/MuseTalk`，权重位于 `models/MuseTalk`。
`gpu/musetalk_service.py` 与 `gpu/avatar_service.py` 均需放到实际运行的 `gpu/` 目录。`deploy/services.py` 让 avatar 使用新入口、TTS 使用 cuda-graph。

## 实测和限制

同一老师音色、同一 19 字测试句：原服务 6.802 秒生成 4.08 秒音频；加速引擎预热后 1.263 秒生成 4.72 秒音频。采样产生的语速/时长会变化，不是确定性逐采样对比。
候选端到端实测：4.32 秒语音合成 1.18 秒；128/108 帧视频各对应 5.12/4.32 秒声音，时长误差为零，渲染 2.389/2.044 秒。两句合成音频经 ASR 完整还原。首次头像模板准备 5.4 秒，可复用。

这些是服务器内部实测，不含大模型回复、公网传输、浏览器缓存/解码。口型模型输出仍需视觉验收；帧数、ASR 和时长检查不能证明所有音素都完美同步。照片输入目前限正面人像，卡通图、全身手势与真实双向同时讲话尚未验收。不同 GPU 的速度和显存占用需要重新测量。

公网 SSE 验收（首版 24 字分段）：首句 9.939 秒；第一、第二段衔接分别 15/20 毫秒，无播放错误。该实测证明平台没有把整个响应缓冲到结束才返回。随后缩短首段继续降低初始等待，最终值见 cloud-status.md。

最终 16/20 字分段公网验收：发送到首段播放 8.629 秒；前两次段间衔接为 22/19 毫秒，无播放错误。与同次调优前约 6–7 秒段间停顿相比，连续推送改善明显。首句还不是秒回，网络和大模型等待仍占用时间；该单次 Chrome 实测不是所有终端的延迟承诺。
