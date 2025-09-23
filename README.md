# 媒体通知 Webhook 插件

为 AstrBot 提供媒体服务器通知功能。原始逻辑来自 @CikeyQi


## 配置

```json
{
  "webhook_port": 60071,
  "group_id": "your-group-id",
  "platform_name": "aiocqhttp",
  "batch_min_size": 3,
  "batch_interval_seconds": 300,
  "cache_ttl_seconds": 300,
  "tmdb_api_key": "your-tmdb-key",
  "fanart_api_key": "your-fanart-key",
  "adapter_type": null,
  "sender_id": "10000",
  "sender_name": "媒体服务器"
}
```

### 新增配置项

- **`adapter_type`**: 手动指定适配器类型（可选）
  - `null`: 自动根据平台选择
  - `"aiocqhttp"`: 使用优化的aiocqhttp适配器
  - `"napcat"`: 使用NapCat适配器
  - `"llonebot"`: 使用LLOneBot适配器
  - `"generic"`: 使用通用适配器

- **`sender_id`**: 合并转发消息的发送者QQ号（默认: "10000"）
- **`sender_name`**: 合并转发消息的发送者昵称（默认: "媒体服务器"）

**媒体服务器设置**：
```
Webhook URL: http://your-bot-server:60071/media-webhook
```


## 使用说明

1. **配置插件参数**
   - 设置 `platform_name` 为你的协议端类型（如 `aiocqhttp`、`llonebot`、`napcat`）
   - 配置 `group_id` 为目标群组ID
   - 可选：设置 `adapter_type` 手动指定适配器类型

2. **在媒体服务器中设置 Webhook URL**
   ```
   http://your-bot-server:60071/media-webhook
   ```

3. **插件会自动接收并推送通知到指定群组**
   - 自动选择最佳适配器
   - 支持合并转发，避免刷屏
   - 包含图片和详细信息

## 🔧 故障排除

### LLOneBot 协议端收不到消息
- ✅ **已修复**：更新了转发节点格式，使用标准的 `uin`/`name` 字段
- ✅ **已修复**：统一了API调用方式，使用 `bot_client.api.call_action`

### 其他常见问题
- **消息发送失败**：检查 `platform_name` 配置是否正确
- **适配器选择错误**：可手动设置 `adapter_type` 参数
- **图片显示异常**：检查媒体服务器的图片URL是否可访问

## 📊 状态查看

使用指令查看插件状态：
```
/webhook status
```

显示信息包括：
- 当前使用的适配器类型
- 支持的功能特性
- 配置参数状态

- **协议端适配**:
  - **aiocqhttp**: 支持合并转发
  - **其他协议**: 自动降级为单独发送

**消息格式优化**：
- **Ani-RSS**: 直接发送原始数据，不进行转换
- **其他来源**: 紧凑排列，只显示第一段简介
- **智能截断**: 自动限制文本长度，避免消息过长


## 消息示例

```
🤖 📺 新剧集更新 [Jellyfin]

剧集名称: 进击的巨人 (2023)
集号: S04E28
集名称: 最终话

剧情简介:
艾伦·耶格尔的故事迎来最终章节...

时长: 24分钟
✨ 数据来源: TMDB
```

## 许可证

MIT License
