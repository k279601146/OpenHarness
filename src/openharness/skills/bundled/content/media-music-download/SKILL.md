---
name: media-music-download
description: 媒体与音乐解析下载技能。全量支持 BugPk API 平台提供的全部 40 个在线接口（涵盖网易云音乐SVIP、酷我音乐、汽水音乐、QQ音乐、音乐聚合，抖音原画/实况/图集/主页、快手、小红书、哔哩哔哩、微信视频号、微博、今日头条、皮皮虾、皮皮搞笑、最右、豆包AI视频与对话图、即梦AI、千问AI、影视解析、蓝奏云直链、闲鱼商品，以及城市天气、IP归属、快递物流、手机号归属、ICP备案等实用工具）。基于 short_videos 源码与线上服务，严格适配各媒体不同的请求参数与《视频解析统一JSON格式3.0》规范。
version: 1.2.0
---

# 媒体与音乐全量解析下载技能 (Media & Music Universal Download Skill)

本技能基于 `D:\workspace\short_videos` 开源项目以及部署于 `https://api.bugpk.com` 的服务构建。全面收录并支持您提供的**全部 40 个在线接口**，无任何遗漏。

针对各媒体**请求参数不一致**、**返回结构差异**以及**防盗链下载**等问题，技能内建参数隔离规则与自动化驱动脚本 [`scripts/parse_and_download.py`](scripts/parse_and_download.py)。

---

## 🔒 核心操作规范（必读规则）

### 1. 严格直连原则（禁止使用代理）
- **禁止使用任何 HTTP/HTTPS 网络代理**，必须采用完全直连方式请求接口。
- **cURL 调用规范**: 所有命令行 `curl` 请求必须添加 `--noproxy "*"` 参数：
  ```bash
  curl -s --noproxy "*" "https://api.bugpk.com/api/..."
  ```
- **Python / 代码调用规范**: 自动清空代理环境变量 (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`) 并设置 `trust_env = False` 与 `proxies = {"http": None, "https": None}`，彻底杜绝代理干扰。

### 2. 大文件保护策略（超限不主动下载）
- 设定默认大文件安全阈值为 **50MB**（可通过 `--max-size <MB>` 调整）。
- 解析后获取文件尺寸（通过 API 返回的 `data.size` 或流探测 `Content-Length`）：
  - **文件大小 ≤ 50MB**: 正常执行自动化流式直连下载，保存到指定目录。
  - **文件大小 > 50MB**: **严禁主动帮用户下载**，避免长时间占用磁盘与网络带宽；系统会自动提取该媒体文件的直链（Direct Download URL）、画质信息与精确文件大小，以 Markdown 链接形式直接提供给用户，由用户自行点击或使用外部下载器下载。

---

## 📋 全量 40 接口全景清单 (严格对应无遗漏)

| 序号 | 接口名称 | 接口路径 | 类别 | 核心请求参数 | 说明与返回 |
| :---: | :--- | :--- | :---: | :--- | :--- |
| **1** | 网易云音乐SVIP解析 | `/api/163_music` | 音乐解析 | `type` (必填), `url`/`ids`, `level` | 支持单曲直链、多档音质、歌词、搜歌、歌单 |
| **2** | 酷我音乐解析 | `/api/kuwo` | 音乐解析 | `url` (必填) | 酷我歌曲直链与动态歌词（仅传 url 参数） |
| **3** | 汽水音乐解析[官方接口] | `/api/qsmusic` | 音乐解析 | `url` (必填) | 汽水音乐官方长短链接直链解析 |
| **4** | QQ音乐解析 | `/api/qqmusic` | 音乐解析 | `url` (必填), 可选 `type`, `name` | 歌曲解析、MV 及关键词搜歌 |
| **5** | 音乐解析聚合 | `/api/music` | 音乐解析 | `id`, `media`, `type` (均必填) | 网易云/QQ音乐聚合直链提取 |
| **6** | 抖音无水印解析【原画】 | `/api/douyin` | 短视频/图文 | `url` (必填) | 原画直链(`quality=original`)、图集、实况、BGM |
| **7** | 抖音主页解析 | `/api/dyzy` | 短视频/图文 | `url` 或 `id` (必填), `page` | 抖音用户主页作品批量列表提取 |
| **8** | bilibili解析 | `/api/bilibili` | 短视频/图文 | `url` (必填) | B站 1080P 视频直链（需带 B 站 Referer） |
| **9** | 快手聚合解析【支持实况】 | `/api/ksjx` | 短视频/图文 | `url` (必填) | 快手视频、图集、实况 Live Photo 解析 |
| **10** | 快手解析 | `/api/kuaishou` | 短视频/图文 | `url` (必填) | 快手短视频去水印基础解析 |
| **11** | 小红书聚合 | `/api/xhsjx` | 短视频/图文 | `url` (必填) | 小红书综合解析（视频、图集、实况统一契约） |
| **12** | 小红书解析 | `/api/xhs` | 短视频/图文 | `url` (必填) | 小红书短视频无水印解析 |
| **13** | 小红书图文解析 | `/api/xhsimg` | 短视频/图文 | `url` (必填) | 小红书多图高清无水印图集原图提取 |
| **14** | 微信视频号视频解析 | `/api/wxsph` | 短视频/图文 | `url` (必填) | 视频号无水印直链提取 |
| **15** | 微博短视频解析[官方接口] | `/api/weibo` | 短视频/图文 | `url` (必填) | 微博短视频官方接口版无水印解析 |
| **16** | 微博去水印解析 | `/api/weibo_v` | 短视频/图文 | `url` (必填) | 微博短视频爬虫版解析（备用） |
| **17** | 今日头条去水印解析 | `/api/toutiao` | 短视频/图文 | `url` (必填) | 今日头条短视频去水印与背景音乐提取 |
| **18** | 皮皮虾去水印解析 | `/api/pipixia` | 短视频/图文 | `url` (必填) | 皮皮虾视频与图集去水印解析 |
| **19** | 皮皮搞笑去水印解析 | `/api/pipigx` | 短视频/图文 | `url` (必填) | 皮皮搞笑视频去水印解析 |
| **20** | 最右解析 | `/api/zuiyou` | 短视频/图文 | `url` (必填) | 最右视频无水印解析 |
| **21** | 豆包视频去水印解析 | `/api/dbvideos` | AI生成解析 | `url` (必填) | 豆包 AI 生成短视频无水印直链提取 |
| **22** | 豆包对话图片无水印提取 | `/api/dbduihua` | AI生成解析 | `url` (必填) | 豆包对话分享链接生成的无水印高清图提取 |
| **23** | 即梦去水印解析 | `/api/jimengai` | AI生成解析 | `url` (必填) | 即梦 AI 视频去水印，支持未发布作品 |
| **24** | 千问图片/视频去水印 | `/api/qianwenimg` | AI生成解析 | `url` (必填) | 通义千问生成图片与视频无水印直链提取 |
| **25** | 短视频去水印解析【聚合】 | `/api/short_videos` | 聚合入口 | `url` (必填) | 聚合入口1：智能分发 20+ 短视频平台 |
| **26** | 短视频解析聚合2 | `/api/svparse` | 聚合入口 | `url` (必填) | 聚合入口2：支持抖音、小红书、ins等 |
| **27** | 影视解析(非凡去广告) | `/api/videosjx` | 影视/网盘 | `url` (必填) | 爱优腾芒播放页去广告 m3u8 提取 |
| **28** | 蓝奏云直链解析 | `/api/lanzou` | 影视/网盘 | `url` (必填), 可选 `pwd`, `type=down` | 网盘真实文件直链提取，支持 302 下载 |
| **29** | 闲鱼商品信息解析 | `/api/xydetail` | 电商解析 | `url` (必填) | 闲鱼商品分享链接详情提取（含商品 ID） |
| **30** | 城市天气id | `/api/citywid` | 实用工具 | `city` (必填) | 查询城市对应的国家天气城市 ID 列表 |
| **31** | 城市天气查询 | `/api/weather` | 实用工具 | `city` (必填) | 查询指定城市实时天气及预报 |
| **32** | ip查询【本地数据库】 | `/api/ipinfo` | 实用工具 | 可选 `ip` | 本地数据库快速定位 IP（空则取客户端IP） |
| **33** | Ip归属地查询 | `/api/ipquery` | 实用工具 | `ip` (必填) | 在线查询 IP 地理位置与网络运营商 |
| **34** | 快递查询 | `/api/kuaidi` | 实用工具 | `mail_no` (必填) | 快递运单号全流程物流追踪轨迹 |
| **35** | QQ信息查询 | `/api/qq_info` | 实用工具 | `qq` (必填) | 查询 QQ 号公开昵称、头像图片直链 |
| **36** | 号码归属地查询 | `/api/tel` | 实用工具 | `tel` (必填) | 查询手机号码归属地省市与运营商 |
| **37** | icp备案查询 | `/api/icp` | 实用工具 | `search` (必填) | 工信部域名 ICP 备案信息查询 |
| **38** | 随机评论 | `/api/random_comments` | 实用工具 | 无必填参数 | 随机获取一条网络热门神评 |
| **39** | 随机一言 | `/api/yiyan` | 实用工具 | 无必填参数 | 随机输出一句中英文哲理金句 |
| **40** | zepp绑定手环接口 | `/api/zeppbind` | 实用工具 | `access`, `username` (必填) | Zepp 运动手环设备账号绑定接口 |

---

## 🛠️ 各媒体请求参数的关键差异规则

1. **必须传 `type` 的接口**:
   - `/api/163_music` (网易云音乐): 缺少 `type` 会直接报错 `400`。解析单曲必须传 `type=json`（含歌词、音质、直链）；搜歌必须传 `type=search&keywords=...`；仅需播放直链传 `type=url`。
2. **严禁带多余参数的接口**:
   - `/api/kuwo` (酷我音乐): **仅接收 `url` 参数**。如果向其附加 `type=json` 或 `level=standard`，服务端会进行 URL 校验或重定向，导致无法返回 JSON。
   - `/api/qsmusic` (汽水音乐): **仅接收 `url` 参数**。
3. **聚合解析接口**:
   - `/api/music`: 需要三个必填参数 `id`（歌曲ID）、`media`（`netease` 或 `tencent`）、`type`（`song`/`mv`/`url`）。
4. **防盗链特别处理**:
   - `/api/bilibili`: B 站视频直链下载必须带请求头 `Referer: https://www.bilibili.com/`，否则返回 403。

---

## 💻 驱动脚本与直连调用指南

技能内置脚本 [`scripts/parse_and_download.py`](scripts/parse_and_download.py) 已经完全固化了**直连无代理**和**大文件保护**机制：

### 1. 媒体与音乐解析 (`parse`)
```bash
# 解析网易云音乐（直连无代理）
python scripts/parse_and_download.py parse "https://music.163.com/song?id=186016" --level lossless

# 解析酷我音乐（严格按仅 url 参数发起直连请求）
python scripts/parse_and_download.py parse "https://www.kuwo.cn/play_detail/123456"

# 解析抖音（支持直接粘贴整段含文案的分享文本）
python scripts/parse_and_download.py parse "7.79 复制打开抖音... https://v.douyin.com/eEEfBw-3-pQ/ 看看这个"
```

### 2. 下载与大文件保护 (`download`)
```bash
# 正常下载（默认阈值 50MB，文件超限将自动跳过下载并输出直链）
python scripts/parse_and_download.py download "https://www.kuwo.cn/play_detail/123456" --dir ~/Downloads/Music

# 自定义安全阈值（例如限制 30MB）
python scripts/parse_and_download.py download "https://v.douyin.com/eEEfBw-3-pQ/" --max-size 30 --dir ~/Downloads/Douyin

# 仅下载背景音乐 (BGM)
python scripts/parse_and_download.py download "https://v.douyin.com/eEEfBw-3-pQ/" --media-type music --dir ~/Downloads/BGM
```

> **大文件超限返回结构示例**：
> ```json
> {
>   "too_large_count": 1,
>   "too_large_files": [
>     {
>       "type": "video",
>       "filename": "作者_标题.mp4",
>       "url": "https://.../video.mp4",
>       "size": 114833620,
>       "size_label": "109.51MB",
>       "message": "文件大小 (109.51MB) 超过设定的上限 (50.00MB)，已跳过主动下载，请使用提供的直链手动下载"
>     }
>   ]
> }
> ```

### 3. 直连 cURL 示例 (`curl -s --noproxy '*'`)
```bash
# 查天气
curl -s --noproxy "*" "https://api.bugpk.com/api/weather?city=北京"

# 查手机号归属地
curl -s --noproxy "*" "https://api.bugpk.com/api/tel?tel=13800138000"

# 查快递物流
curl -s --noproxy "*" "https://api.bugpk.com/api/kuaidi?mail_no=SF1234567890"

# 酷我音乐解析
curl -s --noproxy "*" "https://api.bugpk.com/api/kuwo?url=https%3A%2F%2Fwww.kuwo.cn%2Fplay_detail%2F123456"

# 网易云音乐直连解析
curl -s --noproxy "*" "https://api.bugpk.com/api/163_music?type=json&url=https%3A%2F%2Fmusic.163.com%2Fsong%3Fid%3D186016"
```

---

## 📚 详细参考文档

- [统一 JSON 格式 3.0 规范契约](references/unified-format-3.0.md)
- [BugPk API 全量 40 接口技术规格与接入白皮书](references/api-specs.md)
