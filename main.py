import static_ffmpeg
static_ffmpeg.add_paths()
from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import os
import httpx
from downloader import extract_video_info

app = FastAPI(title="Video Downloader API")

# 挂载静态资源目录
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

from typing import Optional

class ExtractRequest(BaseModel):
    url: str
    platform: Optional[str] = None

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/api/extract")
async def extract_video(request: ExtractRequest):
    if not request.url:
        raise HTTPException(status_code=400, detail="Missing url")
        
    url = request.url.lower()
    detected_platform = None
    
    if 'youtube.com' in url or 'youtu.be' in url:
        detected_platform = 'youtube'
    elif 'instagram.com' in url:
        detected_platform = 'instagram'
    elif 'facebook.com' in url or 'fb.watch' in url or 'fb.com' in url:
        detected_platform = 'facebook'
    elif 'tiktok.com' in url:
        detected_platform = 'tiktok'
    elif 'x.com' in url or 'twitter.com' in url:
        detected_platform = 'twitter'
        
    if not detected_platform:
        raise HTTPException(status_code=400, detail="Unsupported URL. Only YouTube, Instagram, Facebook, TikTok, and X (Twitter) are supported.")
        
    # 调用 yt-dlp/特定API 封装提取视频信息
    result = extract_video_info(request.url, detected_platform)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error extracting video"))
        
    return result

@app.get("/api/download")
async def download_video(url: str, ext: str = "mp4"):
    """
    通过流式代理解决跨域双击或只能在新标签页打开不能直接下载的问题
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")
        
    # 根据视频 CDN 域名动态注入对应平台的完整防盗链请求头
    # TikTok CDN (tiktokcdn.com) 和 tikwm CDN 以及 Instagram CDN 均对 Referer/Cookie 做强校验
    proxy_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity;q=1, *;q=0',
    }
    
    url_lower = url.lower()
    if 'tiktok' in url_lower or 'tiktokcdn' in url_lower:
        proxy_headers['Referer'] = 'https://www.tiktok.com/'
        proxy_headers['Cookie'] = 'tt_csrf_token=none; tt_webid=1'
    elif 'tikwm' in url_lower:
        proxy_headers['Referer'] = 'https://www.tikwm.com/'
    elif 'instagram' in url_lower or 'cdninstagram' in url_lower:
        proxy_headers['Referer'] = 'https://www.instagram.com/'
    elif 'facebook' in url_lower or 'fbcdn' in url_lower:
        proxy_headers['Referer'] = 'https://www.facebook.com/'
    elif 'youtube' in url_lower or 'googlevideo' in url_lower:
        proxy_headers['Referer'] = 'https://www.youtube.com/'
    
    client = httpx.AsyncClient(follow_redirects=True, headers=proxy_headers, timeout=60.0)
    
    request = client.build_request("GET", url)
    try:
        response = await client.send(request, stream=True)
        if response.status_code not in (200, 206):
            await response.aclose()
            await client.aclose()
            raise HTTPException(status_code=400, detail="Forbidden or Error from upstream")
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=400, detail=str(e))
        
    async def iterfile():
        try:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()
            
    media_type = "video/mp4" if ext == "mp4" else f"audio/{ext}" if ext in ["m4a", "mp3"] else "application/octet-stream"
                    
    return StreamingResponse(iterfile(), media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename=\"downloaded_file.{ext}\""
    })

@app.get("/api/proxy_image")
async def proxy_image(url: str):
    """
    专门用来突破 Instagram/Facebook 等平台对前端浏览器施加的图片防盗链和跨域拦截。
    服务器会在后台帮前端把缩略图拉好然后直接推流，对前端来说这就是同源的图。
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing image url")
        
    client = httpx.AsyncClient(follow_redirects=True, timeout=10.0, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    })
    
    # 根据目标 URL 的域名，智能补充 Referer 头来通过 CDN 防盗链检查
    referer_map = {
        'cdninstagram.com': 'https://www.instagram.com/',
        'instagram.com': 'https://www.instagram.com/',
        'fbcdn.net': 'https://www.facebook.com/',
        'facebook.com': 'https://www.facebook.com/',
    }
    for domain, referer in referer_map.items():
        if domain in url:
            client.headers['Referer'] = referer
            client.headers['Origin'] = referer.rstrip('/')
            break
    
    try:
        response = await client.get(url)
        if response.status_code != 200:
            await client.aclose()
            # 如果源网站都拒绝给代理图，返回 404 让前端走降级
            raise HTTPException(status_code=404, detail="Image not found")
            
        content_type = response.headers.get('content-type', 'image/jpeg')
        # 一定要关闭 client
        content = response.content
        await client.aclose()
        
        from fastapi import Response
        return Response(content=content, media_type=content_type, headers={
            "Cache-Control": "public, max-age=86400"
        })
        
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=404, detail="Proxy image failed")

import tempfile
import shutil
import asyncio
import subprocess
from fastapi.background import BackgroundTasks

@app.get("/api/download_merged")
def download_merged_video(url: str, format_id: str, background_tasks: BackgroundTasks):
    """
    专门针对高画质（音画分离）视频的服务端合成接口。
    会通过 yt-dlp 拉取并在服务器合并，之后回传给客户端并自动删除。
    """
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")
        
    temp_dir = tempfile.mkdtemp(prefix="video_merge_")
    out_path = os.path.join(temp_dir, "video.mp4")
    
    # 寻找 ffmpeg 的具体路径
    ffmpeg_exe, _ = get_or_fetch_platform_executables_else_raise()
    
    # 构建包含合并指令的 yt-dlp 进程
    cmd = [
        "yt-dlp",
        "-f", format_id,
        "--merge-output-format", "mp4",
        "--ffmpeg-location", ffmpeg_exe,
        "-o", out_path,
        url
    ]
    
    # 在 FastAPI 默认的同步路由中，代码会自动抛到线程池执行，不会阻塞主线程！
    process = subprocess.run(cmd, capture_output=True, text=True)
    
    if process.returncode != 0:
        # 合成失败时清理
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Merge failed on server: {process.stderr}")
        
    # 如果找不到预期的输出文件
    if not os.path.exists(out_path):
        # 也许 yt-dlp 输出了其他拓展名或者名字变了，尝试寻找里面的文件
        files = os.listdir(temp_dir)
        if files:
            out_path = os.path.join(temp_dir, files[0])
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Merged file not found on server")

    # 分配后台任务去删除临时目录
    def cleanup_temp_dir():
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    background_tasks.add_task(cleanup_temp_dir)
    
    return FileResponse(
        out_path, 
        media_type="video/mp4", 
        headers={"Content-Disposition": "attachment; filename=\"downloaded_merged_video.mp4\""}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
