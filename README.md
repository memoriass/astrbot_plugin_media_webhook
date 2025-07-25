# 媒体通知 Webhook 插件

为 AstrBot 提供媒体服务器通知功能。原始逻辑来自 @CikeyQi

## 功能特性

- 🎬 **多平台支持** - Jellyfin、Emby、Plex、Ani-RSS 等媒体服务器
- 📱 **智能消息** - 自动格式化，包含剧集信息和封面图片
- 🔄 **智能去重** - 基于哈希值防止重复通知，支持不同数据源
- 📦 **批量发送** - 支持消息缓存和合并转发
- 🤖 **协议适配** - 自动适配 aiocqhttp 等协议端
- 🔧 **智能检测** - 自动检测通知来源并转换数据格式
- 🛠️ **容错处理** - 支持 Ani-RSS 不完整 JSON 修复

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
  "fanart_api_key": "your-fanart-key"
}
```

**媒体服务器设置**：
```
Webhook URL: http://your-bot-server:60071/media-webhook
```

**测试命令**：
```
/webhook test    # 测试功能
/webhook status  # 查看状态
```

## 使用说明

1. 配置插件参数
2. 在媒体服务器中设置 Webhook URL
3. 插件会自动接收并推送通知到指定群组

**智能缓存发送策略**：
- **纯缓存机制**: 消息加入队列后等待批量缓存时间
- **智能发送选择**:
  - 不大于 `batch_min_size`: 使用单独发送
  - 超过 `batch_min_size` 且支持合并转发: 使用合并转发
- **协议端适配**:
  - **aiocqhttp**: 支持合并转发
  - **其他协议**: 自动降级为单独发送


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
