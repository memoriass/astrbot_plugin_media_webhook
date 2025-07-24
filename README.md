# 媒体通知 Webhook 插件

用于 AstrBot 的媒体通知 Webhook 插件，支持接收来自各种媒体服务器的通知。

## 快速配置

### 1. 插件配置
```json
{
  "webhook_port": 60071,
  "group_id": "your-group-id",
  "tmdb_api_key": "your-tmdb-key"
}
```

### 2. 媒体服务器配置
设置 Webhook URL：
```
http://your-bot-server:60071/media-webhook
```

### 3. 测试命令
```
/webhook test        # 测试功能
/webhook status      # 查看状态
```


## 消息效果

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

## 主要配置

| 选项 | 说明 |
|------|------|
| `webhook_port` | Webhook 服务端口（默认：60071） |
| `group_id` | 目标群组 ID（必填） |
| `tmdb_api_key` | TMDB API 密钥（可选，用于数据丰富） |


插件支持为 **Jellyfin、Emby、Plex** 通过外部 API 获取更准确的剧集信息：

1. **TMDB 优先** - 有季数信息时使用 TMDB API
2. **BGM.TV 降级** - TMDB 失败时尝试 BGM.TV
3. **原始数据保底** - 两者都失败时使用原始数据

配置 `tmdb_api_key` 可获得更准确的剧情简介和剧集名称。

**支持平台**：Jellyfin、Emby、Plex 的剧集通知都会自动进行数据丰富处理。


## Ani-RSS 支持

完整支持 Ani-RSS 项目，详见 [ANI_RSS_COMPATIBILITY.md](ANI_RSS_COMPATIBILITY.md)

## 许可证

MIT License
