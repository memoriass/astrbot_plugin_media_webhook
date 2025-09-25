# 媒体通知 Webhook 插件

为 AstrBot 提供媒体服务器通知功能。原始逻辑来自 @CikeyQi

**媒体服务器设置**：
```
Webhook URL: http://your-bot-server:60071/media-webhook
```


## 使用说明

1. **在媒体服务器中设置 Webhook URL**
   ```
   http://your-bot-server:60071/media-webhook
   ```
2. **插件会自动接收并推送通知到指定群组**
   - 自动选择最佳适配器
   - 支持合并转发，避免刷屏
   - 包含图片和详细信息

## 📊 状态查看

使用指令查看插件状态：
```
/webhook status
```

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
