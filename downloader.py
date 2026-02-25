import yt_dlp
import logging
import requests
import httpx
import re
import os
from urllib.parse import unquote

def strip_ansi(text: str) -> str:
    """清理 yt-dlp 等命令行工具输出中的 ANSI 颜色控制序列"""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

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
        "thumbnail": "/static/icon-192.png",
        "platform": platform,
        "formats": []
    }
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }
    
    try:
        if platform == 'facebook':
             result['error'] = "Facebook extraction requires valid User Cookies. Cannot be extracted directly without authentication."
             return result
             
        if platform == 'instagram':
             result['error'] = "Instagram extraction requires valid User Cookies to avoid rate limits or login walls. The downloader supports multiple resolutions once authenticated."
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

    elif platform == 'instagram':
        try:
            import subprocess
            import json
            import os
            
            # 使用 Node 环境调用用户要求的 instagram-url-direct
            node_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ig_node_module', 'index.js')
            # 必须传入包含引号的URL，在列表式驱动中 subprocess 自动处理引号转移但要注意避免 shell=True
            result_process = subprocess.run(['node', node_script, url], capture_output=True, text=True, timeout=60, encoding='utf-8')
            
            if result_process.returncode == 0 and (result_process.stdout or '').strip():
                try:
                    data = json.loads(result_process.stdout)
                    
                    media_list = data.get('media_details', [])
                    formats = []
                    
                    for m in media_list:
                        m_url = m.get('url')
                        if not m_url: continue
                        
                        formats.append({
                            "url": m_url,
                            "ext": "mp4",
                            "resolution": "Original",
                            "has_video": True,
                            "has_audio": True
                        })
                    
                    # 尝试从 post_info 获取 title 和全局的备用 thumbnail
                    post_info = data.get('post_info', {})
                    fallback_title = post_info.get('caption') or 'Instagram Video'
                    
                    fallback_thumb = '/static/icon-192.png'
                    if media_list and media_list[0].get('thumbnail'):
                        fallback_thumb = media_list[0].get('thumbnail')
                    
                    if formats:
                        return {
                            "success": True,
                            "platform": platform,
                            "original_url": url,
                            "title": fallback_title,
                            "thumbnail": fallback_thumb,
                            "formats": formats
                        }
                    else:
                        raise Exception("Media list parsing revealed no valid URLs.")
                        
                except json.JSONDecodeError:
                    raise Exception(f"Failed to parse node output: {result_process.stdout}")
            else:
                logger.error(f"Node IG extraction failed Error: {result_process.stderr}")
                return {
                    "success": False,
                    "error": f"Instagram API Extraction Failed: {(result_process.stderr or '').strip()}",
                    "platform": "instagram",
                    "formats": []
                }
        except Exception as e:
            logger.error(f"Instagram node extraction timeout or crashed: {e}")
            return {
                "success": False,
                "error": str(e),
                "platform": "instagram",
                "formats": []
            }


    ydl_opts: dict = {
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

            # 提取缩略图的深度容错
            raw_thumb = info_dict.get('thumbnail')
            if not raw_thumb and info_dict.get('thumbnails'):
                # 取第一个或最后一个有效图片
                raw_thumb = info_dict['thumbnails'][0].get('url')
            
            # 如果彻底没有获取到图片（比如 Instagram 无 Cookie 状态），给予一个默认占位符防止黑屏
            final_thumb = raw_thumb if raw_thumb else ''
            
            # 调试日志：追踪缩略图提取情况
            logger.info(f"[DEBUG-THUMB] platform={platform}, raw_thumb={raw_thumb}, final_thumb={final_thumb}")
            logger.info(f"[DEBUG-THUMB] thumbnails_list={info_dict.get('thumbnails')}")

            result = {
                "success": True,
                "title": info_dict.get('title', 'Unknown Title'),
                "thumbnail": final_thumb,
                "duration": info_dict.get('duration', 0),
                "platform": platform,
                "formats": []
            }
            
            formats = info_dict.get('formats', [])
            selected_formats = []
            
            # 先找最好的纯音频
            audio_formats = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
            best_audio = None
            if audio_formats:
                best_audio = sorted(audio_formats, key=lambda x: x.get('abr') or 0, reverse=True)[0]
                selected_formats.append({
                    "resolution": "Audio Only",
                    "height": -1, # 设置为负数保证排序在底部
                    "url": best_audio.get('url'),
                    "ext": best_audio.get('ext', 'm4a'),
                    "has_audio": True,
                    "has_video": False,
                    "needs_merge": False,
                    "format_id": best_audio.get('format_id')
                })
            
            for f in formats:
                if f.get('protocol') in ['m3u8_native', 'm3u8']:
                    continue  # 跳过不稳定的 m3u8，yt-dlp 会有更好的 format 代替
                
                vcodec = f.get('vcodec')
                acodec = f.get('acodec')
                height = f.get('height')
                
                # 跳过纯音频流 (已经在开头处理过了)
                if vcodec == 'none':
                    continue
                    
                # 过滤掉低于 360p 的画质
                if height is None or height < 360:
                    continue
                
                res = f"{height}p"
                video_url = f.get('url')
                ext = f.get('ext', 'mp4')
                format_id = f.get('format_id')
                
                # 判断是否有音频，或者是否需要合并
                has_audio = acodec != 'none'
                needs_merge = False
                
                # 如果只有画面没有声音，且我们存在最佳音频流，则标记为需要服务端合并
                if not has_audio and best_audio:
                    has_audio = True
                    needs_merge = True
                    format_id = f"{format_id}+{best_audio.get('format_id')}"
                
                selected_formats.append({
                    "resolution": res,
                    "height": height,
                    "url": video_url,
                    "ext": 'mp4' if needs_merge else ext, # 合成后固定输出 mp4
                    "has_audio": has_audio,
                    "needs_merge": needs_merge,
                    "format_id": format_id
                })

            selected_formats.sort(key=lambda x: x['height'], reverse=True)
            
            unique_resolutions = {}
            for sf in selected_formats:
                if sf['resolution'] == "Audio Only":
                    unique_resolutions["Audio Only"] = sf
                    continue
                    
                # 去重健：使用分辨率和是否有声音共同作为 Key，以此保障 1080p有声 和 1080p无声 能共存
                key = f"{sf['resolution']}_{sf['has_audio']}"
                if key not in unique_resolutions:
                    unique_resolutions[key] = sf
                    
            final_formats = []
            for key, fmt in unique_resolutions.items():
                if 'height' in fmt:
                    fmt.pop('height', None)
                
                # 如果没有设定 has_video，默认它且代表有视频
                if 'has_video' not in fmt:
                    fmt['has_video'] = True
                    
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
        
        # 针对失败做其他后备方案处理
        fallback_res = parse_douyin_fb_fallback(url, platform)
        if fallback_res.get('success'):
             return fallback_res
             
        return {
            "success": False,
            "error": strip_ansi(str(e))
        }
