#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BugPk API 全媒体与音乐解析下载工具 (Universal Media & Music Parse & Download Tool)
严格遵循：
1. 直连请求：禁用任何网络代理 (curl -s --noproxy '*' / requests trust_env=False)
2. 大文件保护：超过设定阈值（默认 50MB）不主动下载，提供直链由用户自行下载
3. 覆盖全量 40 个在线接口与 short_videos 源码
"""

import os
import sys
import re
import json
import argparse
import urllib.parse
import requests

# 确保控制台 UTF-8 输出
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

API_BASE = "https://api.bugpk.com/api"

# 默认大文件阈值 (MB)
DEFAULT_MAX_SIZE_MB = 50

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# ==================== 1. 强制直连 (禁用任何代理) ====================
# 清空所有代理相关的环境变量
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
for p in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(p, None)

# 构建无代理直连 Session
direct_session = requests.Session()
direct_session.trust_env = False  # 忽略系统代理
direct_session.proxies = {"http": None, "https": None}  # 强制无代理

# 全量 40 个接口的完整元数据配置表
ALL_ENDPOINTS = {
    # 一、音乐解析接口 (5)
    "163_music": {
        "name": "网易云音乐SVIP解析",
        "category": "音乐解析",
        "path": "/api/163_music",
        "method": "GET/POST",
        "required_params": ["type"],
        "optional_params": ["url", "ids", "id", "level", "keywords", "s", "limit", "offset"],
        "desc": "支持单曲完整信息(type=json)、直链(type=url)、歌词(type=lyric)、搜索(type=search&keywords=...)及音质切换"
    },
    "kuwo": {
        "name": "酷我音乐解析",
        "category": "音乐解析",
        "path": "/api/kuwo",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "酷我歌曲播放页直链与歌词提取（仅接收 url 参数）"
    },
    "qsmusic": {
        "name": "汽水音乐解析[官方接口]",
        "category": "音乐解析",
        "path": "/api/qsmusic",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "汽水音乐官方直链提取，支持长短分享链接"
    },
    "qqmusic": {
        "name": "QQ音乐解析",
        "category": "音乐解析",
        "path": "/api/qqmusic",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": ["type", "name", "n", "page", "count"],
        "desc": "QQ音乐单曲解析与关键词搜歌(type=search&name=...)"
    },
    "music": {
        "name": "音乐解析聚合",
        "category": "音乐解析",
        "path": "/api/music",
        "method": "GET",
        "required_params": ["id", "media", "type"],
        "optional_params": [],
        "desc": "网易云与QQ音乐聚合直链提取 (media: tencent/netease, type: song/mv/url)"
    },

    # 二、短视频与图文去水印接口 (15)
    "douyin": {
        "name": "抖音无水印解析【原画】",
        "category": "短视频与图文",
        "path": "/api/douyin",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "免Cookie解析，支持原画直链(quality=original)、备选直链、图集原图、实况LivePhoto与背景音乐"
    },
    "dyzy": {
        "name": "抖音主页解析",
        "category": "短视频与图文",
        "path": "/api/dyzy",
        "method": "GET/POST",
        "required_params": ["url" or "id"],
        "optional_params": ["page", "page_size"],
        "desc": "抖音个人主页作品批量列表"
    },
    "bilibili": {
        "name": "bilibili解析",
        "category": "短视频与图文",
        "path": "/api/bilibili",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "B站短视频及合集 1080P 直链解析（下载需附带 B 站 Referer）"
    },
    "kuaishou": {
        "name": "快手解析",
        "category": "短视频与图文",
        "path": "/api/kuaishou",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "快手去水印视频与图片提取"
    },
    "ksjx": {
        "name": "快手聚合解析【支持实况】",
        "category": "短视频与图文",
        "path": "/api/ksjx",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "快手去水印聚合解析，支持图集、短视频、实况 Live Photo"
    },
    "xhs": {
        "name": "小红书解析",
        "category": "短视频与图文",
        "path": "/api/xhs",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "无水印解析小红书视频"
    },
    "xhsimg": {
        "name": "小红书图文解析",
        "category": "短视频与图文",
        "path": "/api/xhsimg",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "提取小红书无水印高清多图图集"
    },
    "xhsjx": {
        "name": "小红书聚合",
        "category": "短视频与图文",
        "path": "/api/xhsjx",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "小红书综合解析，自动识别单视频、图集、实况并输出统一契约"
    },
    "wxsph": {
        "name": "微信视频号视频解析",
        "category": "短视频与图文",
        "path": "/api/wxsph",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "微信视频号分享链接无水印直链提取"
    },
    "weibo": {
        "name": "微博短视频解析[官方接口]",
        "category": "短视频与图文",
        "path": "/api/weibo",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "微博短视频官方接口版无水印解析"
    },
    "weibo_v": {
        "name": "微博去水印解析",
        "category": "短视频与图文",
        "path": "/api/weibo_v",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "微博短视频爬虫版无水印解析"
    },
    "toutiao": {
        "name": "今日头条去水印解析",
        "category": "短视频与图文",
        "path": "/api/toutiao",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "今日头条短视频去水印与背景音乐提取"
    },
    "pipixia": {
        "name": "皮皮虾去水印解析",
        "category": "短视频与图文",
        "path": "/api/pipixia",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "无水印解析皮皮虾视频与图集"
    },
    "pipigx": {
        "name": "皮皮搞笑去水印解析",
        "category": "短视频与图文",
        "path": "/api/pipigx",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "皮皮搞笑视频去水印解析"
    },
    "zuiyou": {
        "name": "最右解析",
        "category": "短视频与图文",
        "path": "/api/zuiyou",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "无水印解析最右短视频与帖子视频"
    },

    # 三、AI 生成内容解析 (4)
    "dbvideos": {
        "name": "豆包视频去水印解析",
        "category": "AI生成解析",
        "path": "/api/dbvideos",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "豆包 AI 生成短视频无水印原画直链提取"
    },
    "dbduihua": {
        "name": "豆包对话图片无水印提取",
        "category": "AI生成解析",
        "path": "/api/dbduihua",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "提取豆包对话分享链接中生成的无水印高清图片"
    },
    "jimengai": {
        "name": "即梦去水印解析",
        "category": "AI生成解析",
        "path": "/api/jimengai",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "即梦 AI 视频去水印，支持隐藏与未发布作品"
    },
    "qianwenimg": {
        "name": "千问图片/视频去水印",
        "category": "AI生成解析",
        "path": "/api/qianwenimg",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "千问大模型生成图片与视频无水印直链提取"
    },

    # 四、聚合分发入口 (2)
    "short_videos": {
        "name": "短视频去水印解析【聚合】",
        "category": "聚合入口",
        "path": "/api/short_videos",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "聚合入口1：自动分发至20+平台单平台解析接口"
    },
    "svparse": {
        "name": "短视频解析聚合2",
        "category": "聚合入口",
        "path": "/api/svparse",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "聚合入口2：支持抖音、小红书、ins、即梦ai等"
    },

    # 五、影视与网盘直链 (2)
    "videosjx": {
        "name": "影视解析(非凡去广告)",
        "category": "影视与网盘",
        "path": "/api/videosjx",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "全网主流视频播放页去广告 m3u8 与影片信息解析"
    },
    "lanzou": {
        "name": "蓝奏云直链解析",
        "category": "影视与网盘",
        "path": "/api/lanzou",
        "method": "GET",
        "required_params": ["url"],
        "optional_params": ["pwd", "type"],
        "desc": "蓝奏云分享链接提取真实下载直链 (支持 pwd 提取码与 type=down 302下载)"
    },

    # 六、电商商品解析 (1)
    "xydetail": {
        "name": "闲鱼商品信息解析",
        "category": "电商解析",
        "path": "/api/xydetail",
        "method": "GET/POST",
        "required_params": ["url"],
        "optional_params": [],
        "desc": "闲鱼商品分享链接详情提取（需带商品 ID）"
    },

    # 七、实用查询与日常工具 (11)
    "citywid": {
        "name": "城市天气id",
        "category": "实用工具",
        "path": "/api/citywid",
        "method": "GET/POST",
        "required_params": ["city"],
        "optional_params": [],
        "desc": "查询指定城市的天气城市 ID (city: 城市名称)"
    },
    "weather": {
        "name": "城市天气查询",
        "category": "实用工具",
        "path": "/api/weather",
        "method": "GET/POST",
        "required_params": ["city"],
        "optional_params": [],
        "desc": "查询指定城市实时与预报天气 (city: 城市名或城市ID)"
    },
    "ipinfo": {
        "name": "ip查询【本地数据库】",
        "category": "实用工具",
        "path": "/api/ipinfo",
        "method": "GET",
        "required_params": [],
        "optional_params": ["ip"],
        "desc": "基于本地数据库查询 IP 归属地（为空则自动取客户端 IP）"
    },
    "ipquery": {
        "name": "Ip归属地查询",
        "category": "实用工具",
        "path": "/api/ipquery",
        "method": "GET",
        "required_params": ["ip"],
        "optional_params": [],
        "desc": "在线查询 IP 地理位置与运营商信息"
    },
    "kuaidi": {
        "name": "快递查询",
        "category": "实用工具",
        "path": "/api/kuaidi",
        "method": "GET/POST",
        "required_params": ["mail_no"],
        "optional_params": [],
        "desc": "根据快递单号查询物流追踪轨迹"
    },
    "qq_info": {
        "name": "QQ信息查询",
        "category": "实用工具",
        "path": "/api/qq_info",
        "method": "GET/POST",
        "required_params": ["qq"],
        "optional_params": [],
        "desc": "查询 QQ 昵称、头像等公开信息"
    },
    "tel": {
        "name": "号码归属地查询",
        "category": "实用工具",
        "path": "/api/tel",
        "method": "GET/POST",
        "required_params": ["tel"],
        "optional_params": [],
        "desc": "查询手机号码归属省市与运营商"
    },
    "icp": {
        "name": "icp备案查询",
        "category": "实用工具",
        "path": "/api/icp",
        "method": "GET/POST",
        "required_params": ["search"],
        "optional_params": [],
        "desc": "查询域名的工业和信息化部 ICP 备案信息 (search: 域名)"
    },
    "random_comments": {
        "name": "随机评论",
        "category": "实用工具",
        "path": "/api/random_comments",
        "method": "GET",
        "required_params": [],
        "optional_params": [],
        "desc": "随机获取一条网络热门神评"
    },
    "yiyan": {
        "name": "随机一言",
        "category": "实用工具",
        "path": "/api/yiyan",
        "method": "GET",
        "required_params": [],
        "optional_params": [],
        "desc": "随机返回一句哲理名言金句"
    },
    "zeppbind": {
        "name": "zepp绑定手环接口",
        "category": "实用工具",
        "path": "/api/zeppbind",
        "method": "GET/PUT",
        "required_params": ["access", "username"],
        "optional_params": ["displayName"],
        "desc": "Zepp 运动手环账号绑定逻辑接口"
    }
}

def extract_first_url(text: str) -> str:
    """从文本中提取首个 http/https 链接"""
    match = re.search(r'https?://[^\s"\'<>]+', text)
    if match:
        return match.group(0).rstrip('\'"，。；,.;')
    return text.strip()

def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120] if name else "media_file"

def format_size_label(size_bytes: int) -> str:
    """字节大小转换为人类可读标签"""
    if size_bytes <= 0:
        return "未知大小"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f}PB"

def identify_platform(url: str):
    """
    根据 URL 识别所属平台类型
    返回 (platform_key, endpoint_url)
    """
    url_lower = url.lower()
    
    # 音乐平台
    if "music.163.com" in url_lower or "163cn.tv" in url_lower:
        return "163_music", f"{API_BASE}/163_music"
    if "kuwo.cn" in url_lower:
        return "kuwo", f"{API_BASE}/kuwo"
    if "qishui.douyin.com" in url_lower or "qishui" in url_lower:
        return "qsmusic", f"{API_BASE}/qsmusic"
    if "y.qq.com" in url_lower:
        return "qqmusic", f"{API_BASE}/qqmusic"
        
    # 视频/图文平台
    if "douyin.com" in url_lower or "iesdouyin.com" in url_lower:
        if "/user/" in url_lower or "douyin.com/user" in url_lower:
            return "dyzy", f"{API_BASE}/dyzy"
        return "douyin", f"{API_BASE}/douyin"
    if "kuaishou.com" in url_lower or "gifshow.com" in url_lower or "chenzhongtech.com" in url_lower:
        return "ksjx", f"{API_BASE}/ksjx"
    if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        return "xhsjx", f"{API_BASE}/xhsjx"
    if "bilibili.com" in url_lower or "b23.tv" in url_lower:
        return "bilibili", f"{API_BASE}/bilibili"
    if "weixin.qq.com/sph" in url_lower:
        return "wxsph", f"{API_BASE}/wxsph"
    if "weibo.com" in url_lower or "weibo.cn" in url_lower:
        return "weibo", f"{API_BASE}/weibo"
    if "toutiao.com" in url_lower or "toutiaoimg.com" in url_lower:
        return "toutiao", f"{API_BASE}/toutiao"
    if "pipix.com" in url_lower:
        return "pipixia", f"{API_BASE}/pipixia"
    if "ippzone.com" in url_lower or "pipigx.com" in url_lower:
        return "pipigx", f"{API_BASE}/pipigx"
    if "izuiyou.com" in url_lower or "xiaochuankeji.cn" in url_lower:
        return "zuiyou", f"{API_BASE}/zuiyou"
    if "doubao.com" in url_lower:
        if "/thread/" in url_lower:
            return "dbduihua", f"{API_BASE}/dbduihua"
        return "dbvideos", f"{API_BASE}/dbvideos"
    if "jimeng.jianying.com" in url_lower or "jimeng" in url_lower:
        return "jimengai", f"{API_BASE}/jimengai"
    if "qianwen.com" in url_lower:
        return "qianwenimg", f"{API_BASE}/qianwenimg"
    if "lanzou" in url_lower:
        return "lanzou", f"{API_BASE}/lanzou"
    if "v.qq.com" in url_lower or "iqiyi.com" in url_lower or "youku.com" in url_lower or "mgtv.com" in url_lower:
        return "videosjx", f"{API_BASE}/videosjx"
    if "m.tb.cn" in url_lower or "2.taobao.com" in url_lower or "goofish.com" in url_lower:
        return "xydetail", f"{API_BASE}/xydetail"
        
    # 默认使用通用短视频聚合分发
    return "short_videos", f"{API_BASE}/short_videos"

def call_raw_api(endpoint_key: str, params: dict = None) -> dict:
    """直接调用任意 40 个在线接口之一（强制直连、无代理）"""
    if endpoint_key not in ALL_ENDPOINTS:
        return {"ok": False, "error": f"未知的接口 key: {endpoint_key}"}
        
    meta = ALL_ENDPOINTS[endpoint_key]
    url = f"{API_BASE}/{endpoint_key}"
    params = params or {}
    
    try:
        resp = direct_session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=20)
        resp.encoding = "utf-8"
        try:
            data = resp.json()
        except Exception:
            return {
                "ok": True,
                "endpoint_key": endpoint_key,
                "name": meta["name"],
                "status_code": resp.status_code,
                "raw_text": resp.text
            }
            
        return {
            "ok": True,
            "endpoint_key": endpoint_key,
            "name": meta["name"],
            "status_code": resp.status_code,
            "response": data
        }
    except Exception as e:
        return {
            "ok": False,
            "endpoint_key": endpoint_key,
            "name": meta["name"],
            "error": str(e)
        }

def parse_media(raw_input: str, custom_params: dict = None) -> dict:
    """
    通用媒体解析函数：根据各媒体的请求参数规范组织请求（强制直连、无代理）
    """
    clean_url = extract_first_url(raw_input)
    platform, endpoint = identify_platform(clean_url)
    custom = custom_params or {}
    req_params = {}
    
    if platform == "163_music":
        req_params["type"] = custom.get("type", "json")
        req_params["level"] = custom.get("level", "standard")
        if "id" in custom:
            req_params["id"] = custom["id"]
        elif "ids" in custom:
            req_params["ids"] = custom["ids"]
        else:
            req_params["url"] = clean_url
            
    elif platform == "kuwo":
        # 酷我音乐：严禁附加多余参数
        req_params["url"] = clean_url
        
    elif platform == "qsmusic":
        req_params["url"] = clean_url
        
    elif platform == "qqmusic":
        req_params["url"] = clean_url
        if "type" in custom: req_params["type"] = custom["type"]
        if "name" in custom: req_params["name"] = custom["name"]
        
    elif platform == "music":
        if "id" in custom: req_params["id"] = custom["id"]
        req_params["media"] = custom.get("media", "netease")
        req_params["type"] = custom.get("type", "song")
        
    elif platform == "dyzy":
        if "id" in custom:
            req_params["id"] = custom["id"]
        else:
            req_params["url"] = clean_url
        if "page" in custom: req_params["page"] = custom["page"]
        if "page_size" in custom: req_params["page_size"] = custom["page_size"]
        
    elif platform == "lanzou":
        req_params["url"] = clean_url
        if "pwd" in custom: req_params["pwd"] = custom["pwd"]
        if "type" in custom: req_params["type"] = custom["type"]
        
    elif platform == "videosjx":
        req_params["url"] = clean_url
        
    elif platform == "xydetail":
        req_params["url"] = clean_url
        
    else:
        req_params["url"] = clean_url

    try:
        resp = direct_session.get(endpoint, params=req_params, headers=DEFAULT_HEADERS, timeout=25)
        resp.encoding = "utf-8"
        try:
            data = resp.json()
        except Exception:
            return {
                "ok": False,
                "platform": platform,
                "endpoint": endpoint,
                "params": req_params,
                "error": f"API 返回非 JSON 响应 (HTTP {resp.status_code})",
                "raw_body": resp.text[:400]
            }
            
        return {
            "ok": True,
            "platform": platform,
            "endpoint": endpoint,
            "params": req_params,
            "response": data
        }
    except Exception as e:
        return {
            "ok": False,
            "platform": platform,
            "endpoint": endpoint,
            "params": req_params,
            "error": str(e)
        }

def search_music(keyword: str, platform: str = "163_music", limit: int = 10):
    """搜索音乐（强制直连、无代理）"""
    if platform == "163_music":
        url = f"{API_BASE}/163_music"
        params = {"type": "search", "keywords": keyword, "limit": limit}
        r = direct_session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
        r.encoding = "utf-8"
        return r.json()
    elif platform == "qqmusic":
        url = f"{API_BASE}/qqmusic"
        params = {"type": "search", "name": keyword, "count": limit}
        r = direct_session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
        r.encoding = "utf-8"
        return r.json()
    else:
        raise ValueError(f"暂不支持平台的搜索: {platform}")

# ==================== 2. 大文件保护与直连流式下载 ====================
def download_file_with_size_limit(url: str, output_path: str, max_size_bytes: int, referer: str = None) -> dict:
    """
    带大小限制的直连流式下载：
    如果文件大小超过阈值，不主动帮用户下载，而是返回直链让用户自己下载。
    """
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
        
    try:
        # 先以 stream=True 发起连接，通过响应头校验大小
        resp = direct_session.get(url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()
        
        content_length = int(resp.headers.get('content-length', 0))
        
        # 尺寸超出阈值检测
        if content_length > max_size_bytes:
            resp.close()
            return {
                "downloaded": False,
                "reason": "too_large",
                "url": url,
                "size": content_length,
                "size_label": format_size_label(content_length),
                "max_size_label": format_size_label(max_size_bytes),
                "message": f"文件大小 ({format_size_label(content_length)}) 超过设定的上限 ({format_size_label(max_size_bytes)})，已跳过主动下载，请使用提供的直链手动下载"
            }
            
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        downloaded = 0
        with open(output_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > max_size_bytes:
                        # 极端情况：无 Content-Length 头但实际下载超出上限
                        f.close()
                        os.remove(output_path)
                        resp.close()
                        return {
                            "downloaded": False,
                            "reason": "too_large",
                            "url": url,
                            "size": downloaded,
                            "size_label": format_size_label(downloaded),
                            "max_size_label": format_size_label(max_size_bytes),
                            "message": f"实际流大小超过设定的上限 ({format_size_label(max_size_bytes)})，已停止下载"
                        }
                    f.write(chunk)
                    
        return {
            "downloaded": True,
            "path": output_path,
            "size": os.path.getsize(output_path),
            "size_label": format_size_label(os.path.getsize(output_path))
        }
    except Exception as e:
        return {
            "downloaded": False,
            "reason": "error",
            "url": url,
            "error": str(e)
        }

def download_parsed_media(parsed_result: dict, out_dir: str = "~/Downloads", media_type: str = "all", max_size_mb: int = DEFAULT_MAX_SIZE_MB) -> dict:
    """
    根据解析结果提取实际媒体文件，根据大文件限制策略进行下载或输出直链
    """
    out_dir = os.path.expanduser(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if not parsed_result.get("ok"):
        return {"ok": False, "error": parsed_result.get("error", "解析失败")}
        
    platform = parsed_result.get("platform")
    res_data = parsed_result.get("response", {})
    
    download_targets = []
    title = "media"
    author = "unknown"
    
    # 1. 网易云音乐结构 (163_music)
    if platform == "163_music":
        if "status" in res_data and res_data["status"] == 200:
            title = res_data.get("name", "163_music")
            author = res_data.get("ar_name", "artist")
            music_url = res_data.get("url")
            base_name = sanitize_filename(f"{author} - {title}")
            if music_url:
                download_targets.append({
                    "url": music_url,
                    "filename": f"{base_name}.mp3",
                    "type": "audio"
                })
            lyric = res_data.get("lyric")
            if lyric:
                lrc_path = os.path.join(out_dir, f"{base_name}.lrc")
                with open(lrc_path, "w", encoding="utf-8") as lf:
                    lf.write(lyric)
                download_targets.append({
                    "url": None,
                    "filename": f"{base_name}.lrc",
                    "path": lrc_path,
                    "type": "lyric"
                })
        elif "data" in res_data and isinstance(res_data["data"], list) and len(res_data["data"]) > 0:
            item = res_data["data"][0]
            music_url = item.get("url")
            song_id = item.get("id", "song")
            if music_url:
                download_targets.append({
                    "url": music_url,
                    "filename": f"netease_{song_id}.mp3",
                    "type": "audio"
                })
                
    # 2. 酷我音乐结构 (kuwo)
    elif platform == "kuwo":
        data = res_data.get("data", {})
        if data and isinstance(data, dict):
            title = data.get("title", "kuwo_song")
            author = data.get("artist", "artist")
            music_url = data.get("music_url")
            base_name = sanitize_filename(f"{author} - {title}")
            if music_url:
                download_targets.append({
                    "url": music_url,
                    "filename": f"{base_name}.mp3",
                    "type": "audio"
                })
            lyrics = data.get("lyrics_url")
            if lyrics and isinstance(lyrics, str) and "[" in lyrics:
                lrc_path = os.path.join(out_dir, f"{base_name}.lrc")
                with open(lrc_path, "w", encoding="utf-8") as lf:
                    lf.write(lyrics)
                download_targets.append({
                    "url": None,
                    "filename": f"{base_name}.lrc",
                    "path": lrc_path,
                    "type": "lyric"
                })

    # 3. 聚合音乐 / 汽水 / QQ音乐
    elif platform in ["music", "qsmusic", "qqmusic"]:
        data = res_data.get("data", {})
        if isinstance(data, dict):
            title = data.get("title") or data.get("name") or "song"
            author = data.get("author") or data.get("artist") or "artist"
            music_url = data.get("url") or data.get("music_url") or data.get("play_url")
            base_name = sanitize_filename(f"{author} - {title}")
            if music_url:
                download_targets.append({
                    "url": music_url,
                    "filename": f"{base_name}.mp3",
                    "type": "audio"
                })

    # 4. 视频解析统一 JSON 格式 3.0 (短视频/图文/实况)
    else:
        data = res_data.get("data", {})
        if isinstance(data, dict):
            title = data.get("title") or data.get("desc") or "video"
            author_obj = data.get("author", {})
            author = author_obj.get("name", "author") if isinstance(author_obj, dict) else str(author_obj)
            base_name = sanitize_filename(f"{author}_{title}")
            
            # 主视频直链
            video_url = data.get("url")
            reported_size = data.get("size", 0)
            if video_url and (media_type in ["all", "video"]):
                download_targets.append({
                    "url": video_url,
                    "filename": f"{base_name}.mp4",
                    "type": "video",
                    "reported_size": reported_size,
                    "referer": "https://www.bilibili.com/" if platform == "bilibili" else None
                })
                
            # 图集原图 (images)
            images = data.get("images", [])
            if images and isinstance(images, list) and (media_type in ["all", "image", "images"]):
                for idx, img_url in enumerate(images):
                    download_targets.append({
                        "url": img_url,
                        "filename": f"{base_name}_{idx+1}.jpg",
                        "type": "image"
                    })
                    
            # 实况 Live Photo (live_photo)
            live_photo = data.get("live_photo", [])
            if live_photo and isinstance(live_photo, list) and (media_type in ["all", "live"]):
                for idx, lp in enumerate(live_photo):
                    if isinstance(lp, dict):
                        lp_img = lp.get("image")
                        lp_vid = lp.get("video")
                        if lp_img:
                            download_targets.append({
                                "url": lp_img,
                                "filename": f"{base_name}_live_{idx+1}.jpg",
                                "type": "image"
                            })
                        if lp_vid:
                            download_targets.append({
                                "url": lp_vid,
                                "filename": f"{base_name}_live_{idx+1}.mp4",
                                "type": "video"
                            })
                            
            # 背景音乐 (music)
            music_obj = data.get("music", {})
            if isinstance(music_obj, dict) and music_obj.get("url") and (media_type in ["all", "music", "audio"]):
                m_url = music_obj.get("url")
                m_title = sanitize_filename(music_obj.get("title", f"{base_name}_bgm"))
                download_targets.append({
                    "url": m_url,
                    "filename": f"{m_title}.mp3",
                    "type": "audio"
                })

    # 执行下载并判定大文件保护
    downloaded_files = []
    too_large_files = []
    
    for item in download_targets:
        if item.get("path"):
            downloaded_files.append({
                "type": item["type"],
                "path": item["path"],
                "size": os.path.getsize(item["path"]),
                "size_label": format_size_label(os.path.getsize(item["path"]))
            })
            continue
            
        file_url = item.get("url")
        if not file_url:
            continue
            
        # 若 API 元数据中已明确标明超过阈值，直接跳过并提供直链
        reported_size = item.get("reported_size", 0)
        if reported_size > max_size_bytes:
            too_large_files.append({
                "type": item["type"],
                "filename": item["filename"],
                "url": file_url,
                "size": reported_size,
                "size_label": format_size_label(reported_size),
                "message": f"文件大小超过 {max_size_mb}MB 上限，已提供直链请自行下载"
            })
            continue
            
        dest_path = os.path.join(out_dir, item["filename"])
        res = download_file_with_size_limit(file_url, dest_path, max_size_bytes=max_size_bytes, referer=item.get("referer"))
        
        if res.get("downloaded"):
            downloaded_files.append({
                "type": item["type"],
                "path": res["path"],
                "size": res["size"],
                "size_label": res["size_label"]
            })
        elif res.get("reason") == "too_large":
            too_large_files.append({
                "type": item["type"],
                "filename": item["filename"],
                "url": res["url"],
                "size": res.get("size", 0),
                "size_label": res.get("size_label", "未知"),
                "message": res.get("message")
            })

    return {
        "ok": len(downloaded_files) > 0 or len(too_large_files) > 0,
        "platform": platform,
        "title": title,
        "author": author,
        "out_dir": out_dir,
        "max_size_limit_mb": max_size_mb,
        "downloaded_count": len(downloaded_files),
        "downloaded_files": downloaded_files,
        "too_large_count": len(too_large_files),
        "too_large_files": too_large_files
    }

def main():
    parser = argparse.ArgumentParser(description="BugPk 全量 40 接口媒体与音乐解析下载工具（强制直连无代理、大文件防护）")
    subparsers = parser.add_subparsers(dest="action", help="执行操作")
    
    # 1. list 指令
    parser_list = subparsers.add_parser("list", help="列出全部 40 个支持的接口及参数规范")
    
    # 2. call 指令
    parser_call = subparsers.add_parser("call", help="直接直连调用指定的 API 接口")
    parser_call.add_argument("endpoint", help="接口名称 (例如 weather, 163_music, douyin, kuaidi, tel 等)")
    parser_call.add_argument("params", nargs="*", help="键值对参数，例如 city=北京 或 url=https://...")
    
    # 3. parse 指令
    parser_parse = subparsers.add_parser("parse", help="仅解析媒体并输出格式化元数据（直连无代理）")
    parser_parse.add_argument("url", help="待解析的链接或分享文本")
    parser_parse.add_argument("--level", choices=["standard", "exhigh", "lossless", "hires", "sky", "jyeffect", "jymaster"], help="网易云音质")
    parser_parse.add_argument("--type", choices=["json", "url", "song", "lyric", "down"], help="网易云解析类型")
    
    # 4. download 指令
    parser_down = subparsers.add_parser("download", help="解析并下载对应媒体/音乐文件（带大文件防护）")
    parser_down.add_argument("url", help="待解析的链接或分享文本")
    parser_down.add_argument("--dir", default="~/Downloads", help="本地保存目录，默认 ~/Downloads")
    parser_down.add_argument("--media-type", default="all", choices=["all", "video", "image", "live", "music", "audio"], help="需要下载的内容类型")
    parser_down.add_argument("--level", help="网易云音乐音质")
    parser_down.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE_MB, help=f"最大自动下载限制(MB)，超过此大小不主动下载并提供直链，默认 {DEFAULT_MAX_SIZE_MB}MB")
    
    # 5. search 指令
    parser_search = subparsers.add_parser("search", help="搜索音乐（直连无代理）")
    parser_search.add_argument("keyword", help="搜索关键词")
    parser_search.add_argument("--platform", default="163_music", choices=["163_music", "qqmusic"], help="音乐平台")
    parser_search.add_argument("--limit", type=int, default=10, help="返回数量")

    args = parser.parse_args()
    
    if args.action == "list":
        print(f"=== BugPk API 全量 40 接口清单 (共 {len(ALL_ENDPOINTS)} 个，全部采用直连无代理调用) ===")
        categories = {}
        for k, v in ALL_ENDPOINTS.items():
            cat = v["category"]
            categories.setdefault(cat, []).append((k, v))
        for cat, items in categories.items():
            print(f"\n【{cat}】({len(items)} 个):")
            for k, meta in items:
                req = ", ".join(meta["required_params"]) if meta["required_params"] else "无"
                print(f"  • {k:15} | {meta['name']} | 必填参数: [{req}] | {meta['desc']}")
                
    elif args.action == "call":
        param_dict = {}
        for p in args.params:
            if "=" in p:
                k, v = p.split("=", 1)
                param_dict[k.strip()] = v.strip()
        res = call_raw_api(args.endpoint, param_dict)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.action == "parse":
        custom = {}
        if args.level: custom["level"] = args.level
        if args.type: custom["type"] = args.type
        res = parse_media(args.url, custom)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.action == "download":
        custom = {}
        if args.level: custom["level"] = args.level
        parsed = parse_media(args.url, custom)
        if not parsed.get("ok"):
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
            sys.exit(1)
        res = download_parsed_media(parsed, out_dir=args.dir, media_type=args.media_type, max_size_mb=args.max_size)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.action == "search":
        res = search_music(args.keyword, platform=args.platform, limit=args.limit)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
