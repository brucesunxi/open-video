# 成熟项目整合记录

本轮直接使用的组件如下。源码包中的许可证应随分发保留；npm 与 Python 环境中的依赖许可不能被本项目品牌覆盖。版本以 lockfile 为准。

| 组件 | 用途 | 当前版本 / 许可 |
| --- | --- | --- |
| React | 工作台界面 | 19.3.0 / MIT |
| Three.js + three-vrm | 用户 VRM 角色渲染 | 0.180.0 + 3.5.5 / MIT |
| PptxGenJS | 可编辑 PPTX 与讲稿备注 | 3.12.0 / MIT |
| FastAPI | CPU 业务 API | 0.141.1 / MIT |
| jieba + rank-bm25 | 中文分词与资料检索 | 0.42.1 MIT + 0.2.2 Apache-2.0 |
| python-docx / pypdf | 导入教学文档 | 1.2.0 MIT / 6.18.0 BSD-3-Clause |

尚未将 OpenTalking/FasterLivePortrait 的代码复制进这个仓库。现有 GPU 服务作为独立后端保留，真人流适配在后续 GPU 接入阶段实现。Qwen3-TTS/ASR 仅预留并测试 HTTP 协议，不包含权重，不声称已经产生老师克隆音频。Amica、TalkingHead、HeadAudio 保留为后续效果对比候选，不把候选项目写成已实现功能。

## 已知依赖审计事项

2026-09-11 的 `npm audit` 报告 PptxGenJS 间接依赖 `image-size` 的图片解析拒绝服务风险（GHSA-w3rx-r6r6-pgpr、GHSA-5p2g-fcmc-qvqq），当前查询的 registry 最新 image-size 仍为 2.0.2。自动修复建议会把 PptxGenJS 降为旧版本，未执行。

本轮 PPT 导出只生成文字，不调用图片尺寸解析，不把用户图片传给 PPT 图片处理链路。该审计项仍未消除；若增加图片导出或开放公网批量导出，必须先核对上游修复或替换图片解析组件，再重新审计。不把当前审计结果宣称为零漏洞。

## 官方实现参考

- https://github.com/pixiv/three-vrm
- https://gitbrent.github.io/PptxGenJS/docs/quick-start/
- https://gitbrent.github.io/PptxGenJS/docs/speaker-notes/
- https://fastapi.tiangolo.com/tutorial/request-files/
- https://api-docs.deepseek.com/
- 老师声音与真人模型的候选、权重许可边界见根目录解决方案文档。
