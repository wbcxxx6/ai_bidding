# 招标格式优先目录引擎设计

日期：2026-06-10

## 背景

当前 P0 主链路已经能完成上传、预分析、目录设计和章节生成，但目录设计仍带有原型阶段的问题：后端把“通用投标目录”当成默认骨架，再让模型补章节。这会导致一个关键业务错误：当招标文件中已经存在“响应性文件”“投标文件格式”“附件格式”“资格证明文件”“商务/技术响应文件”等明确格式要求时，系统仍可能改写章节标题、改变顺序、补入无关一级章，最终生成的投标文件不符合招标文件规定。

本设计将目录生成从“AI 自由规划目录”改为“招标格式解释 + 锁定目录构建 + AI 有边界补全”。系统必须先尊重招标文件原文格式，再在可写作章节内补充内容策略。

## 目标

- 从招标文件中识别响应性文件、投标文件格式、附件格式和投标文件组成等格式区域。
- 将招标文件明确规定的章节标题、顺序、模板和表格作为硬约束。
- 删除“通用 12 章兜底目录”作为默认行为。
- 将章节分为模板锁定、目录锁定、自由内容三类，后续生成按不同策略处理。
- 目录预览能展示章节是否锁定、来源片段和需要人工确认的问题。
- 当未识别到固定格式时，返回“未识别到固定投标文件格式”和轻量建议，不自动伪装成确定目录。

## 非目标

- 不在本次引入 PostgreSQL、PGVector、对象存储或完整异步任务系统。
- 不重做 Word 导出排版中心。
- 不实现复杂版面 OCR。当前仍基于已抽取文本做格式识别，扫描件质量问题只做提示。
- 不要求模型完全可靠。模型只能辅助理解和补充，不能覆盖锁定规则。

## 核心原则

### 1. 招标原文优先

目录来源优先级为：

1. 招标文件中的响应性文件、投标文件格式、附件格式、投标文件组成原文结构。
2. 用户在前端确认或修正后的格式结构。
3. AI 对可展开章节的写作建议。
4. 无固定格式时的人工确认建议。

只要上游识别到格式结构，一级章节标题和顺序默认锁定，AI 不得改写。

### 2. 锁定不是一刀切

章节按业务属性分为三类：

- `locked_template`：标题、顺序、格式和正文模板都应尽量与招标文件一致。典型章节包括投标函、法定代表人身份证明、授权委托书、承诺函、声明函、报价表、商务偏离表、技术偏离表、资格证明格式、附件表格。
- `locked_outline`：标题和顺序必须与招标文件一致，但内部可由系统补充写作小节。典型章节包括资格审查材料、商务响应文件、技术响应文件、服务方案、实施方案。
- `free_content`：招标文件未固定格式，只提出评分项或响应要求。AI 可以规划二三级结构，但必须引用评分项和需求来源。

### 3. 不确定就暴露给用户

格式识别没有把握时，系统不应补成看似确定的目录。返回结果必须包含 `needsReview` 和 `questions`，让用户确认章节归类、是否保持原题、是否允许展开。

## 后端设计

### 新模块

新增两个后端服务模块：

```text
services/tender_format_parser.py
services/outline_builder.py
```

`tender_format_parser.py` 负责从招标文件纯文本和预分析结果中提取格式结构，不负责生成最终目录。

`outline_builder.py` 负责把格式结构、用户确认结果和分析结果合成为目录 JSON，不直接调用模型。

旧的 `/api/bidding/chapter-design` 保留为兼容入口，但内部流程改为：

1. 读取 `bidding.file_id` 的招标文件文本。
2. 调用 `parse_tender_format(text, analysis_data)`。
3. 调用 `build_outline(format_plan, format_requirements, analysis_data)`。
4. 如果存在可展开章节，再调用模型补充该章节的写作说明和二三级结构。
5. 保存 `directory_structure`。
6. 返回目录、锁定信息、来源片段和人工确认问题。

### 格式识别输入

格式识别输入为：

```python
{
    "tender_text": "招标文件全文或已抽取文本",
    "analysis_data": {
        "bid_document_format": {
            "required_chapters": [],
            "format_notes": [],
            "document_composition": ""
        }
    }
}
```

识别优先扫描以下关键词附近的区域：

- 响应性文件
- 投标文件格式
- 响应文件格式
- 投标文件组成
- 响应文件组成
- 资格证明文件
- 商务响应文件
- 技术响应文件
- 附件格式
- 第六章、第七章、附件、附表

解析时保留标题原文、序号原文和来源片段。不得仅保留模型改写后的标题。

### 格式结构输出

`parse_tender_format` 返回：

```json
{
  "detected": true,
  "source": "tender_text",
  "confidence": 0.86,
  "formatSections": [
    {
      "heading": "第六章 响应文件格式",
      "sourceText": "第六章 响应文件格式...",
      "startOffset": 10240,
      "endOffset": 15880
    }
  ],
  "chapters": [
    {
      "title": "一、投标函",
      "rawTitle": "一、投标函",
      "orderLabel": "一",
      "type": "locked_template",
      "lockTitle": true,
      "lockOrder": true,
      "sourceText": "一、投标函\\n致：...",
      "sourceHeading": "第六章 响应文件格式",
      "confidence": 0.92
    }
  ],
  "formatNotes": [
    "响应文件应按本章格式编制并加盖公章。"
  ],
  "questions": []
}
```

如果没有识别到格式：

```json
{
  "detected": false,
  "source": "none",
  "confidence": 0,
  "chapters": [],
  "formatNotes": [],
  "questions": [
    "未在招标文件中识别到明确的投标文件格式，请确认是否需要手动创建目录。"
  ]
}
```

### 目录输出

`build_outline` 返回：

```json
{
  "source": "tender_format_first",
  "needsReview": false,
  "chapters": [
    {
      "title": "一、投标函",
      "type": "locked_template",
      "lockTitle": true,
      "lockOrder": true,
      "sourceHeading": "第六章 响应文件格式",
      "sourceText": "一、投标函\\n致：...",
      "content": "本章应按招标文件模板填写，不进行自由扩写。",
      "target_words": 500,
      "sections": []
    },
    {
      "title": "三、技术响应文件",
      "type": "locked_outline",
      "lockTitle": true,
      "lockOrder": true,
      "sourceHeading": "第六章 响应文件格式",
      "content": "本章标题和顺序按招标文件锁定，内部内容可围绕技术要求和评分项展开。",
      "target_words": 3000,
      "sections": [
        {
          "title": "技术要求响应",
          "subsections": [
            {
              "title": "关键技术指标响应",
              "describe": "逐条对应招标文件技术要求和评分项，说明响应措施、实现方法、交付成果和证明材料。"
            }
          ]
        }
      ]
    }
  ],
  "questions": []
}
```

### 无固定格式行为

如果 `parse_tender_format.detected = false` 且用户没有传入格式要求，`/chapter-design` 不返回通用 12 章目录。它返回：

```json
{
  "source": "manual_review_required",
  "needsReview": true,
  "chapters": [],
  "suggestedChapters": [
    {
      "title": "技术响应",
      "reason": "招标文件存在技术评分项，但未发现固定章节格式。"
    }
  ],
  "questions": [
    "未识别到固定投标文件格式，是否基于评分项生成建议目录？"
  ]
}
```

前端应要求用户确认后，才把 `suggestedChapters` 转为正式目录。

## 生成策略

全文或单章生成必须按章节类型分流：

- `locked_template`：优先使用 `sourceText` 或 `template_contents`，只做占位符填充和待补充提示，不扩写正文。
- `locked_outline`：保留一级标题，允许补二三级结构，正文生成时必须引用招标要求和评分项。
- `free_content`：允许 AI 规划小节，但必须经过用户确认目录后才能生成。

生成 prompt 不再写“每章至少 3000 字”“必须 Mermaid”这类全局硬规则。字数、图表、引用和禁编造规则由章节类型和章节策略决定。

## 前端设计

目录预览页面需要展示：

- 章节标题。
- 章节类型：模板锁定、目录锁定、自由内容。
- 锁定状态：标题锁定、顺序锁定。
- 来源：例如“第六章 响应文件格式”。
- 来源片段查看入口。
- 需要人工确认的问题。

交互规则：

- `locked_template` 默认不可改标题，只允许查看来源和标记待补充字段。
- `locked_outline` 可新增二三级小节，但一级标题和顺序默认锁定。
- `free_content` 可编辑标题和顺序。
- 未识别到固定格式时，前端不直接进入生成，必须让用户确认建议目录。

## 测试策略

后端单元测试：

- 能从包含“第六章 响应文件格式”的文本中提取投标函、授权委托书、报价表等章节，并保持原顺序。
- 能识别投标函、授权委托书、承诺函、偏离表为 `locked_template`。
- 能识别技术响应文件、商务响应文件为 `locked_outline`。
- 有格式章节时不自动补通用 12 章。
- 无格式章节时返回 `manual_review_required`，不生成正式目录。
- 用户传入 `formatRequirements.required_chapters` 时，用户确认结果优先于自动识别结果。

接口测试：

- `/api/bidding/chapter-design` 在有响应文件格式时返回 `source=tender_format_first`。
- 返回结果包含 `lockTitle`、`lockOrder`、`sourceText` 或 `sourceHeading`。
- 模型失败不影响已识别格式目录返回。
- 无固定格式时返回 `needsReview=true`，不写入伪确定目录。

前端验证：

- 目录树能展示锁定状态和来源。
- `locked_template` 章节不能误导用户进入自由扩写。
- 未识别格式时出现人工确认提示。

## 验收标准

1. 上传包含“响应文件格式/投标文件格式”的招标文件后，目录一级标题与招标文件格式章节保持一致。
2. 投标函、授权委托书、报价表、偏离表等模板章节不被扩写成正文方案。
3. 技术响应、商务响应等可展开章节保留招标文件标题，并只在内部补二三级结构。
4. 目录生成不再默认追加通用 12 章。
5. 模型超时或失败时，已识别到的格式目录仍可返回。
6. 无固定格式时，系统提示人工确认，不直接生成确定目录。

## 迁移与兼容

- 保留旧接口路径 `/api/bidding/chapter-design`，避免前端大面积断裂。
- `directory_structure` 继续存 JSON，但 schema 增加 `source`、`needsReview`、`lockTitle`、`lockOrder`、`sourceText`、`sourceHeading`。
- 旧的 `services/outline_fallback.py` 应停止作为默认目录来源，后续只保留为“用户确认后生成建议目录”的辅助工具，或在实现完成后删除。
- `front/src/user/views/Generation.vue` 保持五步流程，但目录确认页需要理解新的锁定字段。

## 风险

- 纯文本解析对复杂 PDF 版面有限，可能漏掉表格边界。P0 先通过来源片段和人工确认补偿。
- 招标文件格式标题可能存在层级混乱，需要启发式规则和模型辅助共同处理。
- 某些招标文件把格式要求散落在多个章节，解析器必须允许多个 `formatSections`。
- 如果用户手动修改锁定标题，系统需要记录这是人工覆盖，后续生成和导出应使用用户确认结果。
