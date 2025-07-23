# BGM.TV 集成功能说明

## 功能概述

媒体通知 Webhook 插件现在集成了 BGM.TV API，可以获取真实的动画剧集数据用于测试。

## 新增功能

### 1. BGM.TV 数据获取
- 从 BGM.TV 搜索 API 随机获取动画作品
- 获取作品的详细信息（名称、年份、简介、图片等）
- 自动转换为插件需要的数据格式

### 2. 增强的测试命令
原来的 `/webhook_test` 命令现在支持多种参数组合：

#### 基础用法
```
/webhook_test                    # 使用静态数据，不包含图片
/webhook_test_simple            # 纯文本测试（保持不变）
```

#### 数据源选择
```
/webhook_test static            # 使用静态测试数据
/webhook_test bgm               # 使用 BGM.TV 真实数据
/webhook_test bangumi           # 同 bgm，别名
```

#### 图片控制
```
/webhook_test static yes        # 静态数据 + 默认图片
/webhook_test static no         # 静态数据，无图片
/webhook_test bgm yes           # BGM 数据 + 强制包含图片
/webhook_test bgm no            # BGM 数据，无图片
/webhook_test bgm auto          # BGM 数据，自动判断（默认）
```

## 数据转换示例

### BGM.TV 原始数据
```json
{
  "id": 360341,
  "name": "呪い・アニメ-アニメ・制作スタジオ怪談",
  "name_cn": "诅咒・动画-动画・制作室怪谈",
  "air_date": "2023-10-01",
  "summary": "198X年――下請け専門のアニメ・スタジオが乱立していた時代...",
  "images": {
    "large": "https://lain.bgm.tv/pic/cover/l/37/9d/360341_1b4Qw.jpg"
  },
  "eps": 6
}
```

### 转换后的测试数据
```json
{
  "item_type": "Episode",
  "series_name": "诅咒・动画-动画・制作室怪谈",
  "year": "2023",
  "item_name": "第2话",
  "season_number": 1,
  "episode_number": 2,
  "overview": "198X年――下請け専門のアニメ・スタジオが乱立していた時代...",
  "runtime": "28分钟",
  "image_url": "https://lain.bgm.tv/pic/cover/l/37/9d/360341_1b4Qw.jpg"
}
```

## 生成的消息示例

```
📺 新单集上线

剧集名称: 诅咒・动画-动画・制作室怪谈 (2023)
集号: S01E02
集名称: 第2话

剧情简介:
198X年――下請け専門のアニメ・スタジオが乱立していた時代に映画の専門学校を卒業した省三は、人手不足に喘ぐアニメ業界に就職する。過酷な労働環境の中、会社に泊まり込みで作業をする省三が、仮眠中に心霊現象に遭遇してしまう...

时长: 28分钟
```

## 技术实现

### API 调用流程
1. 调用 BGM.TV 搜索 API：`https://api.bgm.tv/search/subject/动画`
2. 从结果中随机选择一个作品
3. 调用详细信息 API：`https://api.bgm.tv/v0/subjects/{id}`
4. 转换数据格式并生成测试消息

### 错误处理
- API 请求超时（10秒）
- 网络连接失败
- 数据格式错误
- 自动回退到静态测试数据

### 随机化元素
- 随机选择作品
- 随机生成季数（1-3）
- 随机生成集数（1-24）
- 随机生成时长（20-30分钟）

## 使用建议

### 推荐的测试流程
1. **快速测试** - 使用 `/webhook_test_simple` 验证基本功能
2. **功能测试** - 使用 `/webhook_test static` 测试消息格式
3. **真实数据测试** - 使用 `/webhook_test bgm` 测试完整流程
4. **图片测试** - 使用 `/webhook_test bgm yes` 测试图片功能

### 网络环境要求
- 能够访问 `api.bgm.tv`
- 能够访问 `lain.bgm.tv`（图片CDN）
- 建议配置合适的 User-Agent

## 注意事项

1. **API 限制** - BGM.TV API 可能有访问频率限制
2. **网络依赖** - BGM 功能需要稳定的网络连接
3. **数据质量** - 部分作品可能缺少某些信息（如年份、简介）
4. **图片大小** - BGM.TV 图片可能较大，注意网络流量

## 故障排除

### 常见问题
- **API 超时** - 检查网络连接，尝试使用静态数据
- **图片加载失败** - 检查图片URL访问权限
- **数据格式错误** - 插件会自动回退到默认数据

### 调试方法
- 查看插件日志中的 BGM.TV API 调用信息
- 使用 `/webhook_test static` 对比测试
- 检查网络防火墙设置
