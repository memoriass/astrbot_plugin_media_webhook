# 命令使用指南

## 概述

媒体通知 Webhook 插件提供了简洁易用的命令接口，支持真实数据测试和灵活的配置选项。

## 命令列表

### `/webhook test` - 主要测试命令

**默认行为**（推荐）：
```
/webhook test
```
- 🎯 使用 BGM.TV 真实动画数据
- 🖼️ 自动包含封面图片
- 🎲 每次获取不同的随机作品

**指定数据源**：
```
/webhook test bgm        # 明确使用 BGM.TV 数据
/webhook test static     # 使用静态测试数据
/webhook test bangumi    # 同 bgm，别名
```

**控制图片**：
```
/webhook test bgm yes    # BGM 数据 + 强制包含图片
/webhook test bgm no     # BGM 数据 + 不包含图片
/webhook test static yes # 静态数据 + 默认图片
/webhook test static no  # 静态数据 + 不包含图片
```

### `/webhook test simple` - 快速测试

```
/webhook test simple
```
- 📝 纯文本测试，不包含图片
- ⚡ 快速验证基本功能
- 🔧 适合调试和故障排除

### `/webhook status` - 状态查看

```
/webhook status
```
- 📊 显示插件运行状态
- 🔗 显示当前平台和发送策略
- 📋 显示队列和缓存信息
- ⚙️ 显示配置参数

## 使用场景

### 🎯 日常测试（推荐）
```bash
/webhook test
```
**效果**：获取真实的动画数据和封面图片，体验完整功能

**示例输出**：
```
🔄 正在从 BGM.TV 获取随机剧集数据...
✅ 成功获取 BGM.TV 数据

[封面图片]
📺 新单集上线

剧集名称: 葬送的芙莉莲 (2023)
集号: S01E15
集名称: 第15话

剧情简介:
在魔王被打倒后的世界，精灵法师芙莉莲踏上了新的冒险旅程...

时长: 24分钟
```

### ⚡ 快速验证
```bash
/webhook test simple
```
**效果**：快速验证插件基本功能，不依赖网络

**示例输出**：
```
📺 新单集上线

剧集名称: 测试剧集 (2024)
集号: S01E01
集名称: 测试集名称

剧情简介:
这是一个测试剧情简介

时长: 45分钟
```

### 🔧 调试测试
```bash
/webhook test bgm no
```
**效果**：使用真实数据但不包含图片，适合网络受限环境

### 📊 状态监控
```bash
/webhook status
```
**效果**：查看插件运行状态和配置信息

**示例输出**：
```
📊 Media Webhook 状态
🌐 服务地址: http://localhost:60071/media-webhook
🎯 目标群组: 123456789
🔗 消息平台: aiocqhttp
📤 发送策略: 智能发送（支持合并转发）
🔀 合并转发支持: ✅

📋 队列消息数: 0
🗂️ 缓存请求数: 3
⚙️ 批量发送阈值: 3
⏰ 处理间隔: 300秒
```

## 参数说明

### data_source（数据源）
- **`bgm`** / **`bangumi`** - 从 BGM.TV 获取真实动画数据（默认）
- **`static`** - 使用预设的静态测试数据

### include_image（图片设置）
- **`auto`** - 自动判断，默认包含图片（默认）
- **`yes`** / **`y`** / **`true`** / **`1`** - 强制包含图片
- **`no`** / **`n`** / **`false`** / **`0`** - 不包含图片

## 最佳实践

### 🎯 推荐工作流程

1. **日常使用**：
   ```bash
   /webhook test
   ```
   获取真实数据，体验完整功能

2. **快速检查**：
   ```bash
   /webhook test simple
   ```
   验证基本功能是否正常

3. **状态监控**：
   ```bash
   /webhook status
   ```
   定期检查插件状态

### 🔧 故障排除

1. **网络问题**：
   ```bash
   /webhook test static    # 使用静态数据
   /webhook test simple    # 纯文本测试
   ```

2. **图片加载失败**：
   ```bash
   /webhook test bgm no    # 不包含图片
   ```

3. **功能验证**：
   ```bash
   /webhook status         # 检查配置
   /webhook test static    # 基础功能测试
   ```

## 命令变更历史

### v2.0 更新
- ✅ 命令名称简化：移除下划线，使用空格
- ✅ 默认使用 BGM.TV 真实数据
- ✅ 默认包含图片，提供完整测试体验
- ✅ 保持向后兼容性

### 命令对照表
| 旧命令 | 新命令 | 说明 |
|--------|--------|------|
| `/webhook_test` | `/webhook test` | 主要测试命令 |
| `/webhook_status` | `/webhook status` | 状态查看命令 |
| `/webhook_test_simple` | `/webhook test simple` | 简单测试命令 |

## 常见问题

### Q: 为什么默认使用 BGM.TV 数据？
A: BGM.TV 提供真实的动画数据，包括封面图片、剧情简介等，能够更好地测试插件的完整功能。

### Q: 如果 BGM.TV 无法访问怎么办？
A: 插件会自动回退到静态数据，或者可以手动使用 `/webhook test static`。

### Q: 如何减少网络依赖？
A: 使用 `/webhook test simple` 进行纯文本测试，或使用 `/webhook test static no` 使用静态数据且不包含图片。

### Q: 命令支持哪些缩写？
A: 图片参数支持多种格式：`yes/y/true/1` 表示包含，`no/n/false/0` 表示不包含。
