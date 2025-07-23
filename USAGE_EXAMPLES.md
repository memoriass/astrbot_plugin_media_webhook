# 使用示例

## 消息格式示例

### 🤖 QQ 群 (aiocqhttp) + Jellyfin

**配置**：
```json
{
  "platform_name": "aiocqhttp",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

**消息效果**：
```
🤖 📺 新单集上线 [Jellyfin]

剧集名称: 进击的巨人 最终季 (2023)
集号: S04E28
集名称: 最终话

剧情简介:
艾伦·耶格尔的故事迎来最终章节，所有的真相即将揭晓。在这个充满战争与牺牲的世界中，每个人都必须面对自己的选择和命运...

时长: 24分钟
```

### ✈️ Telegram + Plex

**配置**：
```json
{
  "platform_name": "telegram",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

**消息效果**：
```
✈️ 🎬 新电影上线 [Plex]

电影名称: 阿凡达：水之道 (2022)

剧情简介:
杰克·萨利与奈蒂莉组建了家庭，他们的孩子也逐渐成长。然而危机未曾消散，萨利一家不得不彼此保护，为了生存而战，并承受随之而来的痛苦...

时长: 192分钟
```

### 💬 微信群 (gewechat) + Emby

**配置**：
```json
{
  "platform_name": "gewechat",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

**消息效果**：
```
💬 📺 新单集上线 [Emby]

剧集名称: 三体 (2023)
集号: S01E08
集名称: 古筝行动

剧情简介:
面对三体文明的威胁，人类开始了前所未有的应对行动。古筝行动的实施将决定人类文明的未来走向...

时长: 45分钟
```

### 🎮 Discord + Sonarr

**配置**：
```json
{
  "platform_name": "discord",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

**消息效果**：
```
🎮 📺 新单集上线 [Sonarr]

剧集名称: 鬼灭之刃 锻刀村篇 (2023)
集号: S03E11
集名称: 与上弦的邂逅

剧情简介:
炭治郎在锻刀村遇到了前所未有的强敌，上弦之鬼的出现让整个村子陷入危机...

时长: 24分钟
```

## 不同配置下的效果对比

### 完整信息显示
```json
{
  "show_platform_prefix": true,
  "show_source_info": true
}
```
**效果**：`🤖 📺 新单集上线 [Jellyfin]`

### 仅显示平台前缀
```json
{
  "show_platform_prefix": true,
  "show_source_info": false
}
```
**效果**：`🤖 📺 新单集上线`

### 仅显示来源信息
```json
{
  "show_platform_prefix": false,
  "show_source_info": true
}
```
**效果**：`📺 新单集上线 [Jellyfin]`

### 最简洁模式
```json
{
  "show_platform_prefix": false,
  "show_source_info": false
}
```
**效果**：`📺 新单集上线`

## 多媒体服务器环境

### 家庭媒体中心示例

**环境**：Jellyfin + Sonarr + Radarr + Overseerr

**消息流**：
```
🤖 📺 新单集上线 [Sonarr]
剧集名称: 星球大战：安道尔 (2022)
集号: S01E12
集名称: 里克斯路

🤖 🎬 新电影上线 [Radarr]  
电影名称: 壮志凌云：独行侠 (2022)

🤖 📺 新单集上线 [Jellyfin]
剧集名称: 权力的游戏 (2019)
集号: S08E06
集名称: 铁王座
```

### 企业环境示例

**环境**：Plex + 企业微信

**配置**：
```json
{
  "platform_name": "wecom",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

**消息效果**：
```
💼 📺 新单集上线 [Plex]

剧集名称: 公司培训视频系列 (2023)
集号: S01E05
集名称: 网络安全培训

时长: 30分钟
```

## 测试命令示例

### 使用 BGM.TV 真实数据测试
```
/webhook test
```

**可能的输出**：
```
🔄 正在从 BGM.TV 获取随机剧集数据...
✅ 成功获取 BGM.TV 数据

[动画封面图片]
🤖 📺 新单集上线 [Jellyfin]

剧集名称: 葬送的芙莉莲 (2023)
集号: S01E15
集名称: 第15话

剧情简介:
在魔王被打倒后的世界，精灵法师芙莉莲踏上了新的冒险旅程。这一次，她将与新的伙伴们一起面对未知的挑战...

时长: 24分钟
```

### 简单文本测试
```
/webhook test simple
```

**输出**：
```
📢 📺 新单集上线

剧集名称: 测试剧集 (2024)
集号: S01E01
集名称: 测试集名称

剧情简介:
这是一个测试剧情简介

时长: 45分钟
```

### 查看状态
```
/webhook status
```

**输出**：
```
📊 Media Webhook 状态
🌐 服务地址: http://localhost:60071/media-webhook
🎯 目标群组: 123456789
🔗 消息平台: aiocqhttp
📤 发送策略: 智能发送（支持合并转发）
🔀 合并转发支持: ✅

📋 队列消息数: 0
🗂️ 缓存请求数: 5
⚙️ 批量发送阈值: 3
⏰ 处理间隔: 300秒
```

## 实际使用场景

### 🏠 个人家庭影院
- **平台**：QQ 群
- **服务器**：Jellyfin + Sonarr + Radarr
- **效果**：家庭成员能清楚知道新内容来源和获取方式

### 👥 朋友分享群
- **平台**：微信群
- **服务器**：Plex
- **效果**：朋友们能及时了解新增的影视内容

### 🎮 游戏社区
- **平台**：Discord
- **服务器**：Jellyfin
- **效果**：社区成员获得游戏相关视频更新通知

### 💼 企业培训
- **平台**：企业微信
- **服务器**：Plex
- **效果**：员工及时收到培训视频更新通知

## 配置建议

### 🎯 推荐配置

**标准配置**（推荐）：
```json
{
  "platform_name": "aiocqhttp",
  "show_platform_prefix": true,
  "show_source_info": true,
  "batch_min_size": 3,
  "force_individual_send": false
}
```

**简洁配置**：
```json
{
  "platform_name": "telegram",
  "show_platform_prefix": false,
  "show_source_info": false,
  "batch_min_size": 5,
  "force_individual_send": false
}
```

**调试配置**：
```json
{
  "platform_name": "aiocqhttp",
  "show_platform_prefix": true,
  "show_source_info": true,
  "batch_min_size": 1,
  "force_individual_send": true
}
```
