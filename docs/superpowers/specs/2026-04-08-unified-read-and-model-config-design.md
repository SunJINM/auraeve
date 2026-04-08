# 统一 Read 入口与模型配置重构设计

## 背景

AuraEve 当前的文件与多媒体处理能力分散在多处：

- 文件读取由 `Read` 工具、附件提取、`media_understanding` 预处理共同承担
- 主模型配置仍以单个 `LLM_MODEL` 为核心，无法显式声明多模型能力
- 图片降级、音频转写、附件预处理的职责边界不清晰
- WebUI 中模型与语音配置缺少统一的卡片化编辑体验

这导致系统在“主模型不支持图片输入但用户上传了图片”这类场景下，行为路径隐含、配置分散、维护成本偏高。

## 目标

本次重构目标如下：

1. `Read` 成为所有文件类型的唯一读取入口
2. 完全移除 `media_understanding`
3. 引入多模型注册表配置，支持同时配置多个模型，并手动声明能力
4. 主模型只能有一个，但任意模型都可以通过能力标记参与降级链路
5. 当主模型不支持图片输入时，`Read` 自动选择支持图片输入的模型将图片转成文字
6. 音频统一走独立 ASR 配置与转写链路
7. WebUI 提供卡片化模型配置与 ASR 配置编辑体验

## 非目标

- 不做旧配置结构兼容
- 不做自动能力识别，能力标记全部由用户手动勾选
- 不引入基于“用途”的模型路由配置；模型卡片只声明能力，不声明角色
- 不在本次设计中扩展视频理解

---

## 方案设计

### 1. 总体架构

系统收敛为三条明确链路：

1. **模型配置链路**
   统一由 `LLM_MODELS` 管理所有模型定义、主模型标记和能力标记。

2. **文件读取链路**
   统一由 `Read` 进入，内部根据文件类型调度文本读取、图片转文字、PDF 提取、notebook 解析、音频转写。

3. **语音转写链路**
   统一由独立 `ASR` 配置管理，不再属于 `media_understanding`。

### 2. 配置结构

新的核心配置结构如下：

```json
{
  "LLM_MODELS": [
    {
      "id": "main",
      "label": "主模型",
      "enabled": true,
      "isPrimary": true,
      "model": "gpt-5.4-mini",
      "apiBase": null,
      "apiKey": "",
      "extraHeaders": {},
      "maxTokens": 8192,
      "temperature": 0.7,
      "thinkingBudgetTokens": 0,
      "capabilities": {
        "imageInput": true,
        "audioInput": false,
        "documentInput": true,
        "toolCalling": true,
        "streaming": true
      }
    }
  ],
  "READ_ROUTING": {
    "imageFallbackEnabled": true,
    "failWhenNoImageModel": true,
    "imageToTextPrompt": "你是图片理解器。请提取主体、关键文字、与用户问题相关结论，保持简洁。"
  },
  "ASR": {
    "enabled": true,
    "defaultLanguage": "zh-CN",
    "timeoutMs": 15000,
    "maxConcurrency": 4,
    "retryCount": 1,
    "failoverEnabled": true,
    "cacheEnabled": true,
    "cacheTtlSeconds": 600,
    "providers": []
  }
}
```

### 3. 模型注册表

新增统一的模型注册表层，负责：

- 加载 `LLM_MODELS`
- 校验只有一个 `isPrimary=true` 的主模型
- 校验至少存在一个主模型
- 过滤 `enabled=true` 的模型
- 按能力筛选候选模型，例如查找 `imageInput=true` 的模型

模型卡片上的能力仅作为系统路由依据，不参与自动推断。

### 4. `Read` 作为唯一文件入口

`Read` 需要明确成为所有文件类型的统一入口，支持以下文件类型：

- 文本文件
- 图片文件
- PDF
- notebook
- 音频文件

它的职责是：

- 识别文件类型
- 统一返回结构
- 调用对应处理器
- 在主模型不支持某种输入模态时执行显式降级

### 5. 图片读取与降级策略

图片文件处理遵循以下规则：

1. `Read` 读取到图片文件
2. 查询当前主模型的 `capabilities.imageInput`
3. 若主模型支持图片输入，则直接返回图片输入块给主模型
4. 若主模型不支持图片输入，则：
   - 从已启用模型中寻找 `capabilities.imageInput=true` 的模型
   - 使用该模型将图片转换成文字描述
   - 结果以文本形式返回给主模型

图片转文字结果建议统一结构化为以下内容：

- `summary`
- `ocr_text`
- `key_objects`
- `relevance_to_user_request`
- `uncertainties`

若没有可用的图片能力模型，则：

- `Read` 返回明确错误
- 不允许静默吞图

### 6. PDF 处理策略

PDF 读取顺序如下：

1. 优先抽取文本
2. 若文本足够，则直接返回文本
3. 若为扫描件或文本极少，则渲染页面为图片
4. 渲染结果复用图片降级链路

这样 PDF 不再拥有独立的隐式多媒体处理系统，而是统一纳入 `Read` 的显式调度。

### 7. Notebook 处理策略

`.ipynb` 由 `Read` 统一解析，输出 cell 内容与关键输出结果，保持现有 notebook 读取能力，但不依赖 `media_understanding`。

### 8. 音频处理策略

音频文件统一走 ASR，不再让主模型决定是否原生消费音频。

处理规则：

1. `Read` 识别到音频文件
2. 调用 `ASR` 配置对应的转写运行时
3. 返回转写文本

这使音频链路和图片链路职责更清晰：

- 图片依赖“支持图片输入的模型”
- 音频依赖“独立 ASR 服务”

### 9. 缓存策略

图片转文字与音频转写都建议引入缓存，缓存 key 至少包含：

- 文件内容 hash
- 所使用的模型或 ASR provider
- 相关 prompt 或配置版本

目的：

- 避免重复读取同一图片或音频时重复计费
- 保证结果与当前配置版本对应

### 10. WebUI 模型卡片设计

WebUI 的模型配置区改为卡片列表，每张卡片表示一个模型实例。

折叠态展示：

- 模型名称
- 自定义标签
- 是否启用
- 是否主模型
- 能力标签

展开态可编辑：

- `id`
- `label`
- `model`
- `apiBase`
- `apiKey`
- `extraHeaders`
- `maxTokens`
- `temperature`
- `thinkingBudgetTokens`
- 能力勾选项

交互约束：

- 主模型只能有一个
- 若删除主模型，则必须先指定新的主模型才能保存
- 若没有任何已启用的 `imageInput=true` 模型，则显示图片降级风险提示

### 11. WebUI ASR 卡片设计

新增独立的“语音转文本”配置卡片。

顶层配置：

- 是否启用
- 默认语言
- 超时
- 最大并发
- 重试次数
- 故障转移
- 缓存开关
- 缓存 TTL

下方提供 ASR provider 列表卡片，支持：

- OpenAI 兼容 ASR
- `whisper-cli`
- `funasr-local`

展开态编辑各 provider 的参数。

### 12. 模块边界

建议新增或重构以下模块：

- `model_registry`
  统一提供主模型查找、按能力筛选、配置校验

- `read_router`
  作为 `Read` 的内部调度层，按文件类型分发

- `image_to_text_service`
  专门负责通过支持图片输入的模型将图片转为文字

- `asr_runtime`
  继续独立承担音频转写

- `webui config schema`
  前后端统一使用新的配置结构

### 13. 删除项

以下内容从本次实现中彻底移除：

- `MEDIA_UNDERSTANDING` 配置块
- `media_understanding` 运行时
- 所有依赖 `media_understanding` 的预处理调用路径

### 14. 错误处理

关键失败场景处理如下：

- 没有主模型：配置校验失败
- 有多个主模型：配置校验失败
- 主模型不支持图片且不存在可用视觉模型：`Read` 明确报错
- ASR provider 全部失败：`Read` 明确报错
- PDF 渲染失败：返回具体渲染错误，不静默忽略

---

## 数据流

### 图片文件

```text
用户/工具请求 Read(file)
  -> Read 识别为图片
  -> model_registry 获取主模型
  -> 主模型支持 imageInput ?
     -> yes: 返回图片块
     -> no:
        -> 从已启用模型中挑选 imageInput=true 的模型
        -> image_to_text_service 转文字
        -> 返回文本结果给主模型
```

### 音频文件

```text
用户/工具请求 Read(file)
  -> Read 识别为音频
  -> asr_runtime 按 ASR 配置执行转写
  -> 返回文本结果给主模型
```

### PDF 文件

```text
用户/工具请求 Read(file)
  -> 优先抽文本
  -> 文本足够: 返回文本
  -> 文本不足: 渲染为图片
  -> 复用图片链路
```

---

## 改动范围

### 后端

- 替换现有单模型配置读取逻辑
- 新增模型注册表
- 新增 `Read` 内部路由层
- 删除 `media_understanding`
- 改造图片、PDF、音频文件读取链路

### 前端

- 重构模型配置页面为模型卡片列表
- 新增 ASR 配置卡片
- 增加主模型唯一性校验与能力标签展示

### 测试

- 配置校验测试
- `Read` 文件类型路由测试
- 图片降级测试
- 音频转写测试
- WebUI 卡片保存与校验测试

---

## 测试重点

1. 只能存在一个主模型
2. 没有主模型时无法保存配置
3. 主模型支持图片时，图片走原生输入
4. 主模型不支持图片时，自动选取支持图片的模型转文字
5. 没有图片能力模型时，图片读取明确失败
6. 音频文件统一走 ASR
7. PDF 文本型与扫描型分支都正确工作
8. WebUI 模型卡片与 ASR 卡片的增删改查和校验正确

---

## 风险与权衡

### 优点

- 结构统一，用户心智简单
- `Read` 成为唯一文件入口，链路可预测
- 主模型与能力模型职责清晰
- 前端配置体验更一致

### 风险

- 本次改动会涉及配置、运行时、WebUI 三层联动
- 由于不做旧配置兼容，切换到新结构需要一次性完成
- 若 `Read` 内部边界设计不清晰，容易重新长成“隐式媒体中台”

### 风险缓解

- 通过 `model_registry`、`read_router`、`image_to_text_service`、`asr_runtime` 明确职责边界
- 保持 `Read` 只做调度，不直接承担所有具体实现

---

## 结论

本次重构的核心，不是简单删除 `media_understanding`，而是将其职责拆分并显式化：

- 多模型能力声明收口到 `LLM_MODELS`
- 图片降级收口到 `Read + image_to_text_service`
- 音频转写收口到 `Read + ASR`
- WebUI 围绕新的配置结构提供卡片化编辑体验

最终效果是：主模型只负责最终推理，`Read` 负责统一文件入口，能力模型和 ASR 服务负责把非兼容输入转换成主模型可消费的文本或原生块。
