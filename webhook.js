import express from 'express';
import crypto from 'crypto';

const
    GROUP_ID = '609113519', // 替换为实际的群组ID
    BOT_ID = '2659908767', // 替换为实际的机器人ID
    PORT = 60071, // 监听端口
    CACHE_TTL_SECONDS = 300, // 重复请求的缓存过期时间 (秒), 默认5分钟
    BATCH_INTERVAL_SECONDS = 300, // 批量发送任务的执行间隔 (秒), 默认5分钟
    BATCH_MIN_SIZE = 3 // 触发合并转发的最小消息数, 默认3条


const REDIS_QUEUE_KEY = `media-notification-queue:${BOT_ID}`;

const app = express();
app.use(express.text({ type: '*/*' }));

const MEDIA_TYPE_MAP = {
    Movie: "电影", Series: "剧集", Season: "剧季",
    Episode: "单集", Album: "专辑", Song: "歌曲", Video: "视频",
};
const TYPE_EMOJI_MAP = { Season: '🎬', Episode: '📺', Default: '🌟' };

const decodeHtmlEntities = (text) => {
    if (!text) return "";
    return text.replace(/&#(\d+);/g, (match, dec) => {
        return String.fromCharCode(dec);
    });
};

const calculateBodyHash = (body) => {
    try {
        const bodyForHash = { ...body };
        delete bodyForHash.image_url;
        const bodyString = JSON.stringify(bodyForHash, Object.keys(bodyForHash).sort());
        return crypto.createHash('md5').update(bodyString).digest('hex');
    } catch (e) {
        console.error('MD5 哈希计算失败', e);
        return null;
    }
};

const generateMainSection = (data) => {
    const sections = [];
    const { series_name, year, item_type, item_name, season_number, episode_number } = data;
    if (series_name) sections.push(`剧集名称: ${series_name} ${year ? `(${year})` : ''}`);
    switch (item_type) {
        case 'Season':
            if (item_name) sections.push(`季名称: ${item_name}`);
            if (season_number) sections.push(`季号: ${season_number}`);
            break;
        case 'Episode':
            if (season_number && episode_number) sections.push(`集号: S${String(season_number).padStart(2, '0')}E${String(episode_number).padStart(2, '0')}`);
            if (item_name) sections.push(`集名称: ${item_name}`);
            break;
        default:
            if (item_name) sections.push(`名称: ${item_name}`);
            if (year) sections.push(`年份: ${year}`);
            break;
    }
    return sections.join('\n');
};

const generateMessageText = (data) => {
    const cnType = MEDIA_TYPE_MAP[data.item_type] || data.item_type;
    const emoji = TYPE_EMOJI_MAP[data.item_type] || TYPE_EMOJI_MAP.Default;
    const messageParts = [
        `${emoji} 新${cnType}上线`,
        generateMainSection(data)
    ];
    if (data.overview) {
        const decodedOverview = decodeHtmlEntities(data.overview);
        messageParts.push(`\n剧情简介:\n${decodedOverview}`);
    }
    if (data.runtime) messageParts.push(`\n时长: ${data.runtime}`);
    return messageParts.join('\n\n');
};

async function processMessageQueue() {
    const rawMessages = await redis.lRange(REDIS_QUEUE_KEY, 0, -1);
    if (rawMessages.length === 0) {
        return;
    }

    await redis.del(REDIS_QUEUE_KEY);

    const messages = rawMessages.map(m => JSON.parse(m)).reverse();
    console.log(`[任务执行] 从队列中取出 ${messages.length} 条待发消息。`);

    try {
        if (messages.length >= BATCH_MIN_SIZE) {
            console.log(`消息数量达到 ${BATCH_MIN_SIZE} 条，准备合并发送。`);
            const forwardNodes = messages.map(msg => ({
                message: [
                    segment.image(msg.imageUrl),
                    msg.messageText
                ]
            }));
            const forwardMsg = await Bot.makeForwardMsg(forwardNodes);
            await Bot[BOT_ID].pickGroup(GROUP_ID).sendMsg(forwardMsg);
            console.log(`成功发送 ${messages.length} 条合并消息。`);
        } else {
            console.log(`消息数量不足 ${BATCH_MIN_SIZE} 条，准备单独发送。`);
            for (const msg of messages) {
                await Bot[BOT_ID].pickGroup(GROUP_ID).sendMsg([
                    segment.image(msg.imageUrl),
                    msg.messageText
                ]);
            }
            console.log(`成功发送 ${messages.length} 条单独消息。`);
        }
    } catch (error) {
        console.error('发送消息时出错:', error.stack);
    }
}

app.post('/media-webhook', async (req, res) => {
    let mediaData;
    try {
        mediaData = JSON.parse(req.body);
    } catch (error) {
        console.error('Webhook 请求体解析失败:', error);
        return res.status(400).send("无效的 JSON 格式。");
    }

    const requestHash = calculateBodyHash(mediaData);

    try {
        if (requestHash) {
            const cacheHit = await redis.get(requestHash);
            if (cacheHit) {
                console.warn(`检测到重复请求，已忽略。 [hash: ${requestHash}]`);
                return res.status(202).send("重复请求已被忽略。");
            }
            await redis.set(requestHash, 'true', { EX: CACHE_TTL_SECONDS });
        }

        const messagePayload = {
            imageUrl: mediaData.image_url,
            messageText: generateMessageText(mediaData)
        };

        await redis.lPush(REDIS_QUEUE_KEY, JSON.stringify(messagePayload));

        console.log(`新 ${mediaData.item_type} 通知已加入队列。 [hash: ${requestHash}]`);
        res.status(200).send("消息已加入队列。");

    } catch (error) {
        console.error('Webhook 处理出错:', error.stack);
        res.status(500).send("处理消息时发生内部错误。");
    }
});

app.listen(PORT, () => {
    console.info(`- Media WebHook 服务已启动`);
    console.info(`- 监听端口: ${PORT}`);
    console.info(`- 访问地址: http://localhost:${PORT}/media-webhook`);

    setInterval(processMessageQueue, BATCH_INTERVAL_SECONDS * 1000);
});
