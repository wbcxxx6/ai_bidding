# Task Plan: 本地带图片标书 MVP

## Goal
为 Mac M1 本地环境规划一个能从产品 PDF 手册抽取图片、检索匹配素材、生成带图片 Word 标书的最小可用 MVP。

## Phases
- [x] Phase 1: 识别现有项目结构
- [x] Phase 2: 梳理 MVP 技术路线
- [x] Phase 3: 输出编码设计与实施步骤
- [ ] Phase 4: 后续按规划实现代码

## Key Questions
1. 是否需要重构现有项目？
2. 图片插入链路应该走多模态 RAG 还是结构化素材检索？
3. Mac M1 本地优先用哪些依赖？

## Decisions Made
- 沿用现有 Flask + SQLite + ChromaDB 原型：当前项目已有上传、文本向量化、通义调用、Markdown 转 Word 能力，MVP 不需要重构为 FastAPI/PostgreSQL。
- 图片检索先用结构化元数据 + 周边文本 embedding：营业执照、产品图、手册插图是确定性素材，多模态检索作为后续增强。
- PDF 图片抽取优先用 PyMuPDF：Mac M1 安装简单，能抽文字、图片、页码和图片位置，适合最小闭环。
- Word 插图通过扩展 md_to_word.py 支持 Markdown 图片语法：生成阶段输出 `![图注](本地图片路径)`，导出阶段插入真实图片。

## Errors Encountered
- None.

## Status
**Planning complete** - 已输出 `local_image_bid_mvp_design.md`，下一步可按该设计实现代码。
