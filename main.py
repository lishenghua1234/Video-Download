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
async def download_video(url: str):
    """
    通过流式代理解决跨域双击或只能在新标签页打开不能直接下载的问题
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")
        
    client = httpx.AsyncClient(follow_redirects=True, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    })
    
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
                    
    return StreamingResponse(iterfile(), media_type="video/mp4", headers={
        "Content-Disposition": "attachment; filename=\"downloaded_video.mp4\""
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
