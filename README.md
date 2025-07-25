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
  "fanart_api_key": "your-fanart-key"
}
```

**媒体服务器设置**：
```
Webhook URL: http://your-bot-server:60071/media-webhook
```


## 使用说明

1. 配置插件参数
2. 在媒体服务器中设置 Webhook URL
3. 插件会自动接收并推送通知到指定群组

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
