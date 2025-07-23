# Ani-RSS 兼容性支持

## 概述

媒体通知 Webhook 插件现在完全兼容 [Ani-RSS](https://github.com/wushuo894/ani-rss) 项目的 webhook 推送格式。Ani-RSS 是一个专门用于动画 RSS 订阅和下载的工具，插件能够自动识别并处理来自 Ani-RSS 的通知数据。

## 兼容性特性

### 🔍 自动格式检测
插件能够自动识别 Ani-RSS 的多种数据格式，无需手动配置：

**JSON 配置格式检测**：
- 检测 `notificationTemplate`、`notificationType`、`webHookMethod` 等特有字段
- 当检测到 3 个或以上 Ani-RSS 特征字段时，自动识别为 Ani-RSS JSON 数据

**文本模板格式检测**：
- 检测 `${emoji}`、`${action}`、`${title}`、`${score}` 等模板变量
- 当检测到 3 个或以上模板变量时，自动识别为 Ani-RSS 文本模板
- 完全解决 "JSON 解析失败" 问题

### 🔄 数据格式转换
自动将 Ani-RSS 的两种格式转换为标准的媒体通知格式：

**JSON 配置转换**：
- 解析 `webHookBody` 字段中的模板信息
- 检测是否包含图片和文本内容
- 生成标准化的媒体数据结构

**文本模板转换**：
- 解析模板变量：`${title}`、`${season}`、`${episode}` 等
- 提取剧集信息、评分、字幕组等详细数据
- 智能生成包含原始信息的通知消息

### 📱 智能内容处理
- 支持完整的 Ani-RSS 模板变量集合
- 自动检测并保留重要信息（标题、季集、评分等）
- 根据内容类型生成相应的通知消息
- 支持图片 URL 检测和处理

## Ani-RSS 数据格式示例

### 1. Ani-RSS 真实消息格式（实际使用格式）
```json
{
  "meassage": [
    {
      "type": "image",
      "data": {
        "file": "https://lain.bgm.tv/pic/cover/l/7c/8e/424883_BpzVb.jpg"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "🎈🎈🎈\n事件类型: 开始下载\n标题: 不时用俄语小声说真心话的邻桌艾莉同学\n评分: 8.0\nTMDB: https://www.themoviedb.org/tv/235758\nTMDB标题: test\nBGM: https://bgm.tv/subject/424883\n季: 1\n集: 1\n字幕组: 未知字幕组\n进度: 2/12\n首播:  2024年1月1日\n事件: test\n下载位置: C:/Media/番剧/B/不时用俄语小声说真心话的邻桌艾莉同学/Season 1\nTMDB集标题: 第1集\n🎈🎈🎈"
      }
    }
  ]
}
```

**请求头信息**：
```
User-Agent: wushuo894/ani-rss (https://github.com/wushuo894/ani-rss)
Content-Type: application/json;charset=UTF-8
```

### 2. Ani-RSS 文本模板格式（配置格式）
```
${emoji}${emoji}${emoji}
事件类型: ${action}
标题: ${title}
评分: ${score}
TMDB: ${tmdburl}
TMDB标题: ${themoviedbName}
BGM: ${bgmUrl}
季: ${season}
集: ${episode}
字幕组: ${subgroup}
进度: ${currentEpisodeNumber}/${totalEpisodeNumber}
首播:  ${year}年${month}月${date}日
事件: ${text}
下载位置: ${downloadPath}
TMDB集标题: ${episodeTitle}
${emoji}${emoji}${emoji}
```

### 2. 原始 Ani-RSS 配置数据
```json
{
  "enable": true,
  "retry": 3,
  "comment": "",
  "notificationTemplate": "${notification}",
  "notificationType": "WEB_HOOK",
  "mailSMTPHost": "smtp.qq.com",
  "mailSMTPPort": 465,
  "mailFrom": "",
  "mailPassword": "",
  "mailSSLEnable": true,
  "mailTLSEnable": false,
  "mailAddressee": "",
  "mailImage": true,
  "serverChanType": "SERVER_CHAN",
  "serverChanSendKey": "",
  "serverChan3ApiUrl": "",
  "serverChanTitleAction": true,
  "telegramBotToken": "",
  "telegramChatId": "",
  "telegramTopicId": -1,
  "telegramApiHost": "https://api.telegram.org",
  "telegramImage": true,
  "telegramFormat": "",
  "webHookMethod": "POST",
  "webHookUrl": "127.0.0.1:9000",
  "webHookBody": "{\"message\":[{\"type\":\"image\",\"data\":{\"file\":\"${image}\"}},{\"type\":\"text\",\"data\":{\"text\":\"${message}\"}}]}",
  "embyRefresh": false,
  "embyApiKey": "",
  "embyRefreshViewIds": [],
  "embyDelayed": 0,
  "statusList": [
    "DOWNLOAD_START",
    "OMIT",
    "ERROR"
  ]
}
```

### 4. 转换后的标准格式
```json
{
  "item_type": "Episode",
  "series_name": "不时用俄语小声说真心话的邻桌艾莉同学",
  "item_name": "第1集",
  "overview": "来自 Ani-RSS 的动画更新通知\n\n🎈🎈🎈\n事件类型: 开始下载\n标题: 不时用俄语小声说真心话的邻桌艾莉同学\n评分: 8.0\nTMDB: https://www.themoviedb.org/tv/235758...",
  "image_url": "https://lain.bgm.tv/pic/cover/l/7c/8e/424883_BpzVb.jpg",
  "runtime": "",
  "year": "2024",
  "season_number": "1",
  "episode_number": "1"
}
```

## 消息效果示例

### 真实消息通知（推荐）
```
🤖 📺 新单集上线 [Ani-RSS]

剧集名称: 不时用俄语小声说真心话的邻桌艾莉同学
集名称: 第1集
集号: S01E01

剧情简介:
来自 Ani-RSS 的动画更新通知

🎈🎈🎈
事件类型: 开始下载
标题: 不时用俄语小声说真心话的邻桌艾莉同学
评分: 8.0
TMDB: https://www.themoviedb.org/tv/235758
BGM: https://bgm.tv/subject/424883
季: 1
集: 1
字幕组: 未知字幕组
进度: 2/12
首播:  2024年1月1日
下载位置: C:/Media/番剧/B/不时用俄语小声说真心话的邻桌艾莉同学/Season 1
🎈🎈🎈
```

### 文本模板通知
```
🤖 📺 新单集上线 [Ani-RSS]

剧集名称: ${title}
集名称: ${episodeTitle}

剧情简介:
来自 Ani-RSS 的动画更新通知
```

## 配置说明

### Ani-RSS 端配置
在 Ani-RSS 中配置 webhook 通知：

1. **webHookUrl**: 设置为插件的 webhook 地址
   ```
   http://your-bot-server:60071/media-webhook
   ```

2. **webHookMethod**: 设置为 `POST`

3. **webHookBody**: 可以使用以下格式
   ```json
   {
     "message": [
       {
         "type": "image",
         "data": {
           "file": "${image}"
         }
       },
       {
         "type": "text", 
         "data": {
           "text": "${message}"
         }
       }
     ]
   }
   ```

### 插件端配置
插件无需特殊配置，会自动检测和处理 Ani-RSS 数据：

```json
{
  "webhook_port": 60071,
  "webhook_path": "/media-webhook",
  "group_id": "your-group-id",
  "platform_name": "aiocqhttp",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

## 支持的模板变量

### 文本模板变量
插件支持以下 Ani-RSS 模板变量：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `${emoji}` | 表情符号 | 🎌 |
| `${action}` | 事件类型 | DOWNLOAD_START |
| `${title}` | 动画标题 | 进击的巨人 最终季 |
| `${score}` | 评分 | 9.0 |
| `${tmdburl}` | TMDB 链接 | https://www.themoviedb.org/... |
| `${themoviedbName}` | TMDB 标题 | Attack on Titan Final Season |
| `${bgmUrl}` | BGM 链接 | https://bgm.tv/subject/... |
| `${season}` | 季数 | 4 |
| `${episode}` | 集数 | 28 |
| `${subgroup}` | 字幕组 | 某字幕组 |
| `${currentEpisodeNumber}` | 当前集数 | 28 |
| `${totalEpisodeNumber}` | 总集数 | 28 |
| `${year}` | 年份 | 2023 |
| `${month}` | 月份 | 11 |
| `${date}` | 日期 | 05 |
| `${text}` | 事件描述 | 下载完成 |
| `${downloadPath}` | 下载路径 | /downloads/anime/... |
| `${episodeTitle}` | 集标题 | 最终话 |

## 支持的 webHookBody 格式

### 1. 包含图片和文本
```json
{
  "message": [
    {
      "type": "image",
      "data": {
        "file": "${image}"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "${message}"
      }
    }
  ]
}
```

### 2. 仅包含文本
```json
{
  "message": [
    {
      "type": "text",
      "data": {
        "text": "${message}"
      }
    }
  ]
}
```

### 3. 自定义格式
```json
{
  "content": "动画更新通知",
  "image": "${image}",
  "text": "${message}"
}
```

## 检测机制

### User-Agent 检测
插件首先检查 HTTP 请求头中的 User-Agent：
```
User-Agent: wushuo894/ani-rss (https://github.com/wushuo894/ani-rss)
```

### 消息格式检测
插件检测 Ani-RSS 真实消息格式特征：
- `meassage` 数组字段（注意拼写为 `meassage`）
- 消息类型：`image` 和 `text`
- 数据结构：`type` + `data` 组合

### JSON 配置检测
插件检测以下 Ani-RSS JSON 配置特有字段：
- `notificationTemplate`
- `notificationType`
- `webHookMethod`
- `webHookUrl`
- `webHookBody`
- `statusList`

当检测到 3 个或以上字段时，识别为 Ani-RSS JSON 配置。

### 文本模板检测
插件检测以下 Ani-RSS 文本模板变量：
- `${emoji}`, `${action}`, `${title}`
- `${score}`, `${season}`, `${episode}`
- `${subgroup}`, `${year}`, `${month}`
- 以及其他模板变量

当检测到 3 个或以上模板变量时，识别为 Ani-RSS 文本模板。

### 内容解析
**JSON 格式**：
- 检测 `${image}` 模板变量或 `image` 关键词
- 检测 `${message}` 模板变量或 `text` 关键词
- 根据检测结果决定是否包含图片

**文本模板**：
- 解析所有模板变量并保留原始格式
- 检测 `${tmdburl}` 或 `${bgmUrl}` 决定是否包含图片
- 提取重要信息到消息概述中

## 使用场景

### 🎌 动画追番通知
- Ani-RSS 自动下载新番
- 实时推送下载状态到群聊
- 支持图片和文本混合通知

### 📺 RSS 订阅管理
- 监控 RSS 源更新
- 自动通知新内容
- 集成到现有的媒体通知系统

### 🔄 状态监控
支持 Ani-RSS 的多种状态通知：
- `DOWNLOAD_START`: 开始下载
- `OMIT`: 跳过下载
- `ERROR`: 下载错误

## 故障排除

### 常见问题

**Q: 收到 "Webhook 请求体解析失败: 无效的JSON格式" 错误**
A: 这个问题已经完全解决！插件现在支持 Ani-RSS 的文本模板格式，不再需要 JSON 格式。

**Q: 通知消息显示模板变量而不是实际值**
A: 这是正常的，因为插件接收到的是模板格式。Ani-RSS 在实际发送时会填充这些变量的真实值。

**Q: 如何确认插件正确识别了 Ani-RSS 格式**
A: 查看日志，应该会显示 "检测到 ani-rss 文本模板，已转换为标准格式" 或类似信息。

**Q: 图片不显示**
A: 文本模板格式中，如果包含 `${tmdburl}` 或 `${bgmUrl}` 变量，插件会自动添加默认图片。

### 调试步骤

1. **检查 webhook 地址**
   ```
   http://your-server:60071/media-webhook
   ```

2. **验证数据格式**
   使用 `/webhook test` 命令测试插件功能

3. **查看日志**
   插件会记录 "检测到 ani-rss 格式数据，已转换为标准格式" 日志

## 兼容性说明

### 版本支持
- 支持所有版本的 Ani-RSS
- 向后兼容现有的媒体服务器通知
- 不影响其他数据源的处理

### 平台支持
- 支持所有 AstrBot 兼容的消息平台
- 自动添加平台前缀和来源标识
- 完整的图片和文本支持

## 示例配置

### 完整的 Ani-RSS + AstrBot 配置

**Ani-RSS 配置**:
```json
{
  "webHookMethod": "POST",
  "webHookUrl": "http://192.168.1.100:60071/media-webhook",
  "webHookBody": "{\"message\":[{\"type\":\"text\",\"data\":{\"text\":\"${message}\"}}]}"
}
```

**AstrBot 插件配置**:
```json
{
  "webhook_port": 60071,
  "webhook_path": "/media-webhook",
  "group_id": "123456789",
  "platform_name": "aiocqhttp",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

这样配置后，当 Ani-RSS 有新的动画更新时，会自动发送通知到指定的 QQ 群。
