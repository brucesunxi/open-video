# 照片头肩动画

当前部署已升级为 MuseTalk 1.5 语音内容驱动口型，详见 [语音与口型升级](speech-upgrade.md)。以下保留首版背景，音量驱动方式已不再用于线上照片对话。

## 首版实现记录

当前实现使用 LivePortrait 核心神经网络渲染，音频包络控制嘴部开合，程序控制轻微头部姿态和眨眼。不是音素级口型，也不生成全身手势；卡通图尚未验收，首版要求可检测的单人正面照片。声音与画面封装为同一 MP4，由同一媒体元素播放；分段预取沿用声音播放流程。

上游：https://github.com/KlingAIResearch/LivePortrait 。源码许可保留在服务器 avatar/LivePortrait/LICENSE。只下载 liveportrait/base_models 和 retargeting_models；不下载 InsightFace 检测权重。检测采用 OpenCV 自带 Haar 人脸检测器。上游许可证明确要求商用替换 InsightFace 检测模型；本适配器不导入 InsightFace。

服务：gpu/avatar_service.py，127.0.0.1:8040，复用 tts Python 环境，增加 opencv-python-headless==4.11.0.86，不改变 torch。代码放在 /workspace/teacher-deploy/avatar/LivePortrait；权重位于 /workspace/teacher-deploy/models/LivePortrait。
业务配置 AVATAR_BASE_URL=http://127.0.0.1:8040。deploy/services.py 管理 avatar 服务。

POST /api/speech 的 animate 默认为 false，音色试听仍返回 WAV；课堂请求 animate=true，且当前老师选择图片时返回 MP4。图片所有权和授权在业务端验证，渲染服务仅监听回环。输入限制图片 15MB、音频 10MB / 30 秒；图像特征内存缓存 3 个，不保存生成视频。渲染在独立线程锁下串行，忙碌有界重试。

此模式增加视频渲染等待，不是流式帧输出。尚需继续优化延迟、跨句动作连续性、口型精度以及卡通输入支持。
