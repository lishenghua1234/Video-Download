import yt_dlp
import logging
import requests
import httpx
import re
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_douyin_fb_fallback(url: str, platform: str) -> dict:
    """
    针对 yt-dlp 容易受到风控限制的抖音和 Facebook，提供自研的简易Fallback爬虫或者第三方接入。
    实际生产环境中可以接入稳定的付费API接口。
    """
    result = {
        "success": False,
        "title": f"{platform.capitalize()} Video",
        "thumbnail": "",
        "platform": platform,
        "formats": []
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    }
    
    try:
        # FB 不再使用粗暴的模拟返回，由于我们前面已完善了 TikWM 等解析，
        # 如果走到此后备流程，只处理 Facebook的特殊提示或异常捕获。
        if platform == 'facebook':
             result['error'] = "Facebook extraction requires valid User Cookies. Cannot be extracted directly without authentication."
             return result
             result['error'] = "Facebook extraction requires valid User Cookies. Returning simulated result for testing UI."
             return result

    except Exception as e:
        logger.error(f"Fallback Error for {platform}: {e}")
        
    return result

def extract_video_info(url: str, platform: str) -> dict:

    if platform == 'tiktok':
        try:
            api_url = 'https://www.tikwm.com/api/'
            resp = requests.post(api_url, data={'url': url, 'hd': 1}, timeout=15)
            data = resp.json()
            if data.get('code') == 0:
                vid_data = data.get('data', {})
                result = {
                    "success": True,
                    "title": vid_data.get('title', f"{platform.capitalize()} Video"),
                    "thumbnail": vid_data.get('cover', ''),
                    "platform": platform,
                    "formats": []
                }
                
                play_url = vid_data.get('play')
                hdplay_url = vid_data.get('hdplay')
                
                if hdplay_url:
                    result['formats'].append({
                        "resolution": "HD",
                        "url": hdplay_url,
                        "ext": "mp4",
                        "has_audio": True
                    })
                if play_url:
                    result['formats'].append({
                        "resolution": "SD",
                        "url": play_url,
                        "ext": "mp4",
                        "has_audio": True
                    })
                    
                if result['formats']:
                    return result
        except Exception as e:
            logger.error(f"Tikwm extraction failed for {platform}: {e}")

    # 清洗 URL：去除可能引发短时间内触发唯一无缓存请求导致 Rate-limit 的各种追踪后缀
    if platform == 'instagram' and '?' in url:
        url = url.split('?')[0]

    ydl_opts = {
        'skip_download': True,
        'extract_flat': False,
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True
    }

    try:
        # 尝试标准 yt-dlp 解析
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info_dict = ydl.extract_info(url, download=False)
            except Exception as extract_err:
                 raise extract_err

            result = {
                "success": True,
                "title": info_dict.get('title', 'Unknown Title'),
                "thumbnail": info_dict.get('thumbnail', ''),
                "duration": info_dict.get('duration', 0),
                "platform": platform,
                "formats": []
            }
            
            formats = info_dict.get('formats', [])
            selected_formats = []
            
            for f in formats:
                if f.get('protocol') in ['m3u8_native', 'm3u8']:
                    pass
                elif f.get('protocol') == 'http_dash_segments':
                    continue
                
                height = f.get('height')
                # 过滤掉没有视频流或没有音频流的静音文件！
                # acodec = none 代表纯视频，vcodec = none 代表纯音频，我们都需要过滤
                if f.get('vcodec') == 'none' or f.get('acodec') == 'none' or height is None:
                    continue
                
                res = f"{height}p"
                video_url = f.get('url')
                ext = f.get('ext', 'mp4')
                
                selected_formats.append({
                    "resolution": res,
                    "height": height,
                    "url": video_url,
                    "ext": ext,
                    "has_audio": True,
                    "format_id": f.get('format_id')
                })

            selected_formats.sort(key=lambda x: x['height'], reverse=True)
            
            unique_resolutions = {}
            for sf in selected_formats:
                res = sf['resolution']
                if res not in unique_resolutions:
                    unique_resolutions[res] = sf
                    
            final_formats = []
            for res, fmt in unique_resolutions.items():
                del fmt['height']
                final_formats.append(fmt)
                
            result['formats'] = final_formats
            
            if not result['formats'] and info_dict.get('url'):
                 result['formats'].append({
                     "resolution": "Best",
                     "url": info_dict.get('url'),
                     "ext": info_dict.get('ext', 'mp4'),
                     "has_audio": True
                 })

            # 如果没有提到有视频的解析，认为是失败了
            if not result['formats']:
                raise RuntimeError("No downloadable video formats found.")
            
            return result

    except Exception as e:
        logger.error(f"Error extracting video info via yt-dlp for {url}: {e}")
        # 针对失败做后备方案处理
        fallback_res = parse_douyin_fb_fallback(url, platform)
        if fallback_res.get('success'):
             return fallback_res
             
        return {
            "success": False,
            "error": str(e)
        }
