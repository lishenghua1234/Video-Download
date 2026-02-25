/** 
 * script.js
 * 处理前端所有的业务逻辑，包含平台切换、表单提交和结果渲染
 */

document.addEventListener('DOMContentLoaded', () => {
    const urlInput = document.getElementById('video-url');
    const form = document.getElementById('download-form');
    const extractBtn = document.getElementById('extract-btn');
    const btnText = extractBtn.querySelector('span');
    const spinner = extractBtn.querySelector('.spinner');

    const resultContainer = document.getElementById('result-container');
    const errorMessage = document.getElementById('error-message');

    // 搜索框焦点事件优化
    urlInput.addEventListener('focus', () => {
        resultContainer.style.display = 'none';
        errorMessage.style.display = 'none';
    });

    // 表单提交逻辑
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const url = urlInput.value.trim();
        if (!url) return;

        // UI 状态更新为加载中
        setLoadingState(true);
        resultContainer.style.display = 'none';
        errorMessage.style.display = 'none';

        try {
            const response = await fetch('/api/extract', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: url
                })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.detail || data.error || 'Failed to extract video information.');
            }
            renderResult(data, url);

        } catch (error) {
            showError(error.message);
        } finally {
            setLoadingState(false);
        }
    });

    /**
     * 渲染查询结果
     * @param {Object} data - 后端返回的数据字典
     * @param {string} origUrl - 原始查询页面地址
     */
    function renderResult(data, origUrl) {
        // 设置标题
        document.getElementById('video-title').textContent = data.title;

        // 设置封面图与精致的兜底状态（加入图片实际加载能力的探测）
        const thumbnailEl = document.getElementById('video-thumbnail');

        // 设置渐变兜底背景（默认状态）
        const fallbackGradient = 'linear-gradient(135deg, rgba(30, 30, 40, 1) 0%, rgba(15, 15, 20, 1) 100%)';
        thumbnailEl.style.backgroundImage = fallbackGradient;
        thumbnailEl.style.backgroundRepeat = 'no-repeat';
        thumbnailEl.style.backgroundPosition = 'center center';
        thumbnailEl.style.backgroundSize = 'cover';

        if (data.thumbnail && data.thumbnail.trim() !== "") {
            // 对 Facebook 等有防盗链的平台，通过后端代理接口加载缩略图
            const needsProxy = ['facebook'].includes(data.platform);
            const proxyUrl = `/api/proxy_image?url=${encodeURIComponent(data.thumbnail)}`;
            // 优先尝试的 URL 列表：代理平台先试代理，其他平台先试原始
            const urlsToTry = needsProxy
                ? [proxyUrl, data.thumbnail]
                : [data.thumbnail, proxyUrl];

            // 用 Image 对象逐个探测，找到第一个可用的 URL
            function tryLoadThumb(urls, index) {
                if (index >= urls.length) return; // 全部失败，保持渐变兜底
                const img = new Image();
                img.onload = function () {
                    // 图片加载成功，设置为背景
                    thumbnailEl.style.backgroundImage = `url('${urls[index]}'), ${fallbackGradient}`;
                    thumbnailEl.style.backgroundRepeat = 'no-repeat, no-repeat';
                    thumbnailEl.style.backgroundPosition = 'center center, center center';
                    thumbnailEl.style.backgroundSize = 'cover, cover';
                };
                img.onerror = function () {
                    // 加载失败，尝试下一个 URL
                    tryLoadThumb(urls, index + 1);
                };
                img.src = urls[index];
            }
            tryLoadThumb(urlsToTry, 0);
        }

        // 渲染分辨率列表
        const formatsList = document.getElementById('formats-list');
        formatsList.innerHTML = '';

        if (!data.formats || data.formats.length === 0) {
            showError("No downloadable formats found for this video.");
            return;
        }

        data.formats.forEach(fmt => {
            const card = document.createElement('div');
            card.classList.add('format-card');

            // 构建徽章，有无音频和格式扩展名
            const audioBadge = fmt.has_audio
                ? `<span class="badge audio">Audio</span>`
                : `<span class="badge no-audio">No Audio</span>`;

            const extBadge = `<span class="badge">${fmt.ext.toUpperCase()}</span>`;

            card.innerHTML = `
                <div class="format-info">
                    <span class="resolution">${fmt.resolution}</span>
                    <div class="badges">
                        ${extBadge}
                        ${audioBadge}
                    </div>
                </div>
                <!-- 使用 fetch 获取二进制后触发 JS 下载，区分直连代理和服务端合成 -->
                <a href="javascript:void(0);" onclick="forceDownload('${fmt.url}', '${fmt.ext}', ${fmt.needs_merge || false}, '${fmt.format_id || ''}', '${origUrl}', this)" class="download-link">
                    Download
                </a>
            `;
            formatsList.appendChild(card);
        });

        // 显示结果容器
        resultContainer.style.display = 'block';
    }

    /**
     * 切换加载状态
     * @param {boolean} isLoading 
     */
    function setLoadingState(isLoading) {
        if (isLoading) {
            extractBtn.disabled = true;
            btnText.style.display = 'none';
            spinner.style.display = 'block';
        } else {
            extractBtn.disabled = false;
            btnText.style.display = 'block';
            spinner.style.display = 'none';
        }
    }

    /**
     * 展现错误信息
     * @param {string} msg 
     */
    function showError(msg) {
        errorMessage.textContent = msg;
        errorMessage.style.display = 'block';
    }
    /**
     * 实现彻底跨域下载，避免使用a标签引起浏览器无响应，并在失败时fallback到浏览器播放
     */
    window.forceDownload = async function (directUrl, ext, needsMerge, formatId, origUrl, btnElement) {
        const originalText = btnElement.innerText;
        btnElement.innerText = "Downloading...";
        btnElement.style.pointerEvents = "none";
        btnElement.style.opacity = "0.7";
        try {
            let apiEndpoint = '/api/download?url=' + encodeURIComponent(directUrl) + '&ext=' + encodeURIComponent(ext);
            if (needsMerge) {
                // 如果需要服务端合并，导向新接口，并传递原链接和轨道的 format_id
                apiEndpoint = '/api/download_merged?url=' + encodeURIComponent(origUrl) + '&format_id=' + encodeURIComponent(formatId);
            }

            const response = await fetch(apiEndpoint);
            if (!response.ok) {
                if (!needsMerge && directUrl) {
                    window.open(directUrl, '_blank');
                    throw new Error("Proxy error, opening in new tab");
                } else {
                    throw new Error("Server Merge Failed");
                }
            }
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = objectUrl;
            a.download = "downloaded_file." + (ext || "mp4");
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(objectUrl);
        } catch (err) {
            console.warn(err);
        } finally {
            btnElement.innerText = originalText;
            btnElement.style.pointerEvents = "auto";
            btnElement.style.opacity = "1";
        }
    }
});
