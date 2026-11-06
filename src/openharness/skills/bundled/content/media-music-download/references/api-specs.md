# BugPk API 全量 40 接口技术规格与接入白皮书

> 源码目录：`D:\workspace\short_videos`  
> 线上服务基址：`https://api.bugpk.com`  
> 本文档详尽记录您提供的全部 40 个在线接口的完整参数协议、请求方式与数据契约，杜绝任何媒体遗漏。

---

## 🔒 核心调用原则 (直连与大文件保护)

1. **强制直连原则（严禁使用代理）**:
   - 所有的请求统一使用直连方式进行，禁止使用代理。
   - 使用 `curl` 请求时必须强制追加 `--noproxy "*"`：
     `curl -s --noproxy "*" "https://api.bugpk.com/api/..."`
   - 使用代码请求时必须清除环境代理变量，使用无代理 Session 直连。

2. **大文件下载保护机制**:
   - 设定默认大文件安全阈值为 **50MB**。
   - 若解析得到的音视频文件大小超过 50MB，系统**不主动帮用户下载**，而是提取该媒体文件的直链（Direct Download URL）、清晰度档位及文件大小，直接提供给用户手动下载。

---

## 目录索引 (全量 40 接口)

1. [音乐解析接口 (5个)](#一音乐解析接口-5个)
   - 1.1 网易云音乐SVIP解析 (`/api/163_music`)
   - 1.2 酷我音乐解析 (`/api/kuwo`)
   - 1.3 汽水音乐解析[官方接口] (`/api/qsmusic`)
   - 1.4 QQ音乐解析 (`/api/qqmusic`)
   - 1.5 音乐解析聚合 (`/api/music`)
2. [短视频与图文去水印接口 (15个)](#二短视频与图文去水印接口-15个)
   - 2.1 抖音无水印解析【原画】 (`/api/douyin`)
   - 2.2 抖音主页解析 (`/api/dyzy`)
   - 2.3 bilibili解析 (`/api/bilibili`)
   - 2.4 快手聚合解析【支持实况】 (`/api/ksjx`)
   - 2.5 快手解析 (`/api/kuaishou`)
   - 2.6 小红书聚合 (`/api/xhsjx`)
   - 2.7 小红书解析 (`/api/xhs`)
   - 2.8 小红书图文解析 (`/api/xhsimg`)
   - 2.9 微信视频号视频解析 (`/api/wxsph`)
   - 2.10 微博短视频解析[官方接口] (`/api/weibo`)
   - 2.11 微博去水印解析 (`/api/weibo_v`)
   - 2.12 今日头条去水印解析 (`/api/toutiao`)
   - 2.13 皮皮虾去水印解析 (`/api/pipixia`)
   - 2.14 皮皮搞笑去水印解析 (`/api/pipigx`)
   - 2.15 最右解析 (`/api/zuiyou`)
3. [AI 生成内容与对话提取 (4个)](#三ai-生成内容与对话提取-4个)
   - 3.1 豆包视频去水印解析 (`/api/dbvideos`)
   - 3.2 豆包对话图片无水印提取 (`/api/dbduihua`)
   - 3.3 即梦去水印解析 (`/api/jimengai`)
   - 3.4 千问图片/视频去水印 (`/api/qianwenimg`)
4. [聚合解析入口 (2个)](#四聚合解析入口-2个)
   - 4.1 短视频去水印解析【聚合】 (`/api/short_videos`)
   - 4.2 短视频解析聚合2 (`/api/svparse`)
5. [影视与网盘直链 (2个)](#五影视与网盘直链-2个)
   - 5.1 影视解析(非凡去广告) (`/api/videosjx`)
   - 5.2 蓝奏云直链解析 (`/api/lanzou`)
6. [电商商品信息解析 (1个)](#六电商商品信息解析-1个)
   - 6.1 闲鱼商品信息解析 (`/api/xydetail`)
7. [实用查询与日常工具接口 (11个)](#七实用查询与日常工具接口-11个)
   - 7.1 城市天气id (`/api/citywid`)
   - 7.2 城市天气查询 (`/api/weather`)
   - 7.3 ip查询【本地数据库】 (`/api/ipinfo`)
   - 7.4 Ip归属地查询 (`/api/ipquery`)
   - 7.5 快递查询 (`/api/kuaidi`)
   - 7.6 QQ信息查询 (`/api/qq_info`)
   - 7.7 号码归属地查询 (`/api/tel`)
   - 7.8 icp备案查询 (`/api/icp`)
   - 7.9 随机评论 (`/api/random_comments`)
   - 7.10 随机一言 (`/api/yiyan`)
   - 7.11 zepp绑定手环接口 (`/api/zeppbind`)

---

## 一、音乐解析接口 (5个)

### 1.1 网易云音乐SVIP解析
- **URL**: `https://api.bugpk.com/api/163_music`
- **源码对应**: `api/wyy.py`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `type`: (必填) `json`(完整信息), `url`(音频直链), `song`(详情), `lyric`(歌词), `search`(搜索), `playlist`(歌单), `album`(专辑), `down`(302下载)
  - `url`: (可选) 网易云音乐分享链接（`music.163.com` 或 `163cn.tv` 短链）
  - `ids` / `id`: (可选) 歌曲 ID
  - `level`: (可选) 音质等级：`standard`, `exhigh`, `lossless`, `hires`, `sky`, `jyeffect`, `jymaster`
  - `keywords` / `s`: (搜索时必填) 搜歌关键词
  - `limit`: (可选) 搜索返回数量 (默认 20)
- **响应示例 (`type=json`)**:
  ```json
  {
    "status": 200,
    "name": "晴天",
    "ar_name": "周杰伦",
    "al_name": "叶惠美",
    "pic": "https://p3.music.126.net/...",
    "url": "https://music.163.com/song/media/outer/url?id=186016.mp3",
    "size": "0B",
    "level": "标准音质",
    "lyric": "[00:00.000] 作词 : 周杰伦...",
    "tlyric": "..."
  }
  ```

### 1.2 酷我音乐解析
- **URL**: `https://api.bugpk.com/api/kuwo`
- **请求方式**: `GET`
- **请求参数**:
  - `url`: (必填) 酷我音乐播放页地址（如 `https://www.kuwo.cn/play_detail/123456`，内含歌曲 ID）
  - **切勿传递额外参数**（如 `type` 或 `level`），否则可能触发网关重定向。
- **响应示例**:
  ```json
  {
    "code": 200,
    "msg": "成功",
    "data": {
      "song_id": "123456",
      "title": "Happy Valentine",
      "artist": "曹格",
      "album": "Naughty Gentleman",
      "pic": "https://img3.kuwo.cn/star/albumcover/500/...",
      "releaseDate": "2005-12-23",
      "songTimeMinutes": "04:44",
      "music_url": "https://kw-lv.kuwo.cn/.../M800000doCGp4DpqiE.mp3",
      "lyrics_url": "[00:00.000]Happy Valentine - 曹格..."
    }
  }
  ```

### 1.3 汽水音乐解析[官方接口]
- **URL**: `https://api.bugpk.com/api/qsmusic`
- **请求方式**: `GET`
- **请求参数**:
  - `url`: (必填) 汽水音乐分享链接（如 `https://qishui.douyin.com/s/ia2T2aMo/`）
- **返回**: 歌曲名、作者、音频 MP3 直链。

### 1.4 QQ音乐解析
- **URL**: `https://api.bugpk.com/api/qqmusic`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) QQ音乐歌曲链接
  - `type`: (可选) `song` / `mv` / `search`
  - `name`: (可选) 搜索歌名
  - `n`, `page`, `count`: (可选) 序号与分页

### 1.5 音乐解析聚合
- **URL**: `https://api.bugpk.com/api/music`
- **请求方式**: `GET`
- **请求参数**:
  - `id`: (必填) 歌曲 ID
  - `media`: (必填) 平台标识 `tencent` / `netease`
  - `type`: (必填) `song` / `mv` / `url`

---

## 二、短视频与图文去水印接口 (15个)

*注：以下接口均严格遵循《视频解析统一JSON格式3.0》规范输出。*

### 2.1 抖音无水印解析【原画】
- **URL**: `https://api.bugpk.com/api/douyin`
- **源码对应**: `api/douyin/douyin.php` + `api/douyin/DouyinParser.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 抖音分享短链或包含分享文案的完整字符串（系统自动正则提取 `https://v.douyin.com/...`）
- **返回字段**: `data.url` (原画直链 `quality="original"`), `data.video_backup` (多码率备选), `data.images` (原图列表), `data.live_photo` (实况图文微视频对), `data.music` (背景音乐).

### 2.2 抖音主页解析
- **URL**: `https://api.bugpk.com/api/dyzy`
- **源码对应**: `api/douyin-home/home.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url` / `id`: (必填，二选一) 用户主页链接或 `sec_uid`
  - `page`: (可选) 页码，默认 `1`
  - `page_size`: (可选) 每页数量，默认 `10`

### 2.3 bilibili解析
- **URL**: `https://api.bugpk.com/api/bilibili`
- **源码对应**: `api/bilibili/bilibili.php`
- **请求方式**: `GET`
- **请求参数**:
  - `url`: (必填) B站视频链接（`https://b23.tv/...` 或 `https://www.bilibili.com/video/BV...`）
- **防盗链提醒**: 下载直链时请求头必须带 `Referer: https://www.bilibili.com/`。

### 2.4 快手聚合解析【支持实况】
- **URL**: `https://api.bugpk.com/api/ksjx`
- **源码对应**: `api/kuaishou/ksjx.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 快手分享链接，支持图集、短视频与实况 Live Photo 解析。

### 2.5 快手解析
- **URL**: `https://api.bugpk.com/api/kuaishou`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 快手视频分享链接。

### 2.6 小红书聚合
- **URL**: `https://api.bugpk.com/api/xhsjx`
- **源码对应**: `api/xiaohongshu/xhsjx.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 小红书笔记链接（支持 `http://xhslink.com/...`），综合输出单视频、多图原图与实况。

### 2.7 小红书解析
- **URL**: `https://api.bugpk.com/api/xhs`
- **请求方式**: `GET`
- **请求参数**:
  - `url`: (必填) 小红书短视频笔记链接。

### 2.8 小红书图文解析
- **URL**: `https://api.bugpk.com/api/xhsimg`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 小红书多图图文笔记链接。

### 2.9 微信视频号视频解析
- **URL**: `https://api.bugpk.com/api/wxsph`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 微信视频号分享链接（如 `https://weixin.qq.com/sph/AYznnccv9H`）。

### 2.10 微博短视频解析[官方接口]
- **URL**: `https://api.bugpk.com/api/weibo`
- **源码对应**: `api/weibo.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 微博视频分享链接。

### 2.11 微博去水印解析
- **URL**: `https://api.bugpk.com/api/weibo_v`
- **源码对应**: `api/weibo_v.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 微博短视频链接（爬虫版备用）。

### 2.12 今日头条去水印解析
- **URL**: `https://api.bugpk.com/api/toutiao`
- **源码对应**: `api/toutiao.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 今日头条视频或微头条链接。

### 2.13 皮皮虾去水印解析
- **URL**: `https://api.bugpk.com/api/pipixia`
- **源码对应**: `api/ppxia.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 皮皮虾分享链接。

### 2.14 皮皮搞笑去水印解析
- **URL**: `https://api.bugpk.com/api/pipigx`
- **源码对应**: `api/pipigx.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 皮皮搞笑分享链接。

### 2.15 最右解析
- **URL**: `https://api.bugpk.com/api/zuiyou`
- **源码对应**: `api/zuiyou.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 最右 App 帖子视频分享链接。

---

## 三、AI 生成内容与对话提取 (4个)

### 3.1 豆包视频去水印解析
- **URL**: `https://api.bugpk.com/api/dbvideos`
- **源码对应**: `api/doubao/video/api.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 豆包 AI 生成短视频链接。

### 3.2 豆包对话图片无水印提取
- **URL**: `https://api.bugpk.com/api/dbduihua`
- **源码对应**: `api/doubao/duihua/duihua.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 豆包对话分享链接（如 `https://www.doubao.com/thread/...`）。

### 3.3 即梦去水印解析
- **URL**: `https://api.bugpk.com/api/jimengai`
- **源码对应**: `api/jimengai/index.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 即梦 AI 视频链接（支持隐藏或未发布作品）。

### 3.4 千问图片/视频去水印
- **URL**: `https://api.bugpk.com/api/qianwenimg`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 通义千问分享链接。

---

## 四、聚合解析入口 (2个)

### 4.1 短视频去水印解析【聚合】
- **URL**: `https://api.bugpk.com/api/short_videos`
- **源码对应**: `api/sv.php`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 支持抖音、快手、小红书、B站、油管、TikTok、西瓜等 20+ 平台，自动平台特征识别并分发。

### 4.2 短视频解析聚合2
- **URL**: `https://api.bugpk.com/api/svparse`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 聚合备选入口 2。

---

## 五、影视与网盘直链 (2个)

### 5.1 影视解析(非凡去广告)
- **URL**: `https://api.bugpk.com/api/videosjx`
- **请求方式**: `GET`
- **请求参数**:
  - `url`: (必填) 腾讯视频、爱奇艺、优酷、芒果等正版视频播放页 URL。
- **返回**: 影片名称、剧集、封面及无广告 m3u8 高清播放地址。

### 5.2 蓝奏云直链解析
- **URL**: `https://api.bugpk.com/api/lanzou`
- **请求方式**: `GET`
- **请求参数**:
  - `url`: (必填) 蓝奏云分享链接（如 `https://jiuhunwl.lanzouw.com/...`）
  - `pwd`: (可选) 访问密码提取码
  - `type`: (可选) 填 `down` 为直接 302 重定向下载文件；不填返回 JSON 元数据。

---

## 六、电商商品信息解析 (1个)

### 6.1 闲鱼商品信息解析
- **URL**: `https://api.bugpk.com/api/xydetail`
- **请求方式**: `GET` / `POST`
- **请求参数**:
  - `url`: (必填) 闲鱼商品详情分享链接（需包含商品 ID）。

---

## 七、实用查询与日常工具接口 (11个)

### 7.1 城市天气id
- **URL**: `https://api.bugpk.com/api/citywid`
- **请求方式**: `GET` / `POST`
- **请求参数**: `city` (必填，如 `北京`、`朝阳`)
- **返回**: 城市对应的国家天气 ID 列表。

### 7.2 城市天气查询
- **URL**: `https://api.bugpk.com/api/weather`
- **请求方式**: `GET` / `POST`
- **请求参数**: `city` (必填，城市名称或天气 ID)
- **返回**: 当前温度、湿度、风向、空气质量及多日天气预报。

### 7.3 ip查询【本地数据库】
- **URL**: `https://api.bugpk.com/api/ipinfo`
- **请求方式**: `GET`
- **请求参数**: `ip` (可选，不填默认取当前客户端 IP)
- **返回**: 本地离线数据库快速定位。

### 7.4 Ip归属地查询
- **URL**: `https://api.bugpk.com/api/ipquery`
- **请求方式**: `GET`
- **请求参数**: `ip` (必填，如 `114.114.114.114`)
- **返回**: 国家、省份、城市、运营商。

### 7.5 快递查询
- **URL**: `https://api.bugpk.com/api/kuaidi`
- **请求方式**: `GET` / `POST`
- **请求参数**: `mail_no` (必填，快递运单号)
- **返回**: 快递公司、运单状态及物流全流程轨迹。

### 7.6 QQ信息查询
- **URL**: `https://api.bugpk.com/api/qq_info`
- **请求方式**: `GET` / `POST`
- **请求参数**: `qq` (必填，QQ号码)
- **返回**: QQ昵称、头像图片直链等公开信息。

### 7.7 号码归属地查询
- **URL**: `https://api.bugpk.com/api/tel`
- **请求方式**: `GET` / `POST`
- **请求参数**: `tel` (必填，手机号码)
- **返回**: 省市、邮编、区号、运营商。

### 7.8 icp备案查询
- **URL**: `https://api.bugpk.com/api/icp`
- **请求方式**: `GET` / `POST`
- **请求参数**: `search` (必填，待查询的网站主域名)
- **返回**: 主办单位名称、性质、备案号、审核时间。

### 7.9 随机评论
- **URL**: `https://api.bugpk.com/api/random_comments`
- **请求方式**: `GET`
- **请求参数**: 无
- **返回**: 随机网络热门幽默神评纯文本。

### 7.10 随机一言
- **URL**: `https://api.bugpk.com/api/yiyan`
- **请求方式**: `GET`
- **请求参数**: 无
- **返回**: 中英文对照励志哲理金句文本。

### 7.11 zepp绑定手环接口
- **URL**: `https://api.bugpk.com/api/zeppbind`
- **请求方式**: `GET` / `PUT`
- **请求参数**: `access` (必填，登录 Token), `username` (必填，账号), `displayName` (可选，设备名)
- **返回**: 绑定状态与关联信息。
