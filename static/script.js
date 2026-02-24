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
                // 如果后端提取失败并且是 Instagram，我们在这个 try 块外面的 catch 里拦截进行 fallback
                if (/(?:https?:\/\/)?(?:www\.)?instagram\.com\S+/.test(url)) {
                    throw new Error("IG_FALLBACK");
                } else {
                    throw new Error(data.detail || data.error || 'Failed to extract video information.');
                }
            }
            renderResult(data);

        } catch (error) {
            if (error.message === "IG_FALLBACK" || (/(?:https?:\/\/)?(?:www\.)?instagram\.com\S+/.test(url))) {
                console.log("Backend blocked by IG firewall. Executing distributed client-side extractions...");
                try {
                    // Try Cobalt free instance via browser
                    const cbRes = await fetch("https://cobalt.kwiatektv.com/api/json", {
                        method: "POST",
                        headers: { "Accept": "application/json", "Content-Type": "application/json" },
                        body: JSON.stringify({ url: url, isAudioOnly: false })
                    });
                    const cbData = await cbRes.json();

                    if (cbData && cbData.url) {
                        const fallbackResult = {
                            success: true,
                            title: "Instagram Reel (Client Tunnel)",
                            thumbnail: "",
                            platform: "instagram",
                            formats: [{
                                resolution: "Original HD",
                                url: cbData.url,
                                ext: "mp4",
                                has_audio: true
                            }]
                        };
                        renderResult(fallbackResult);
                        return; // 成功解析后截止
                    } else {
                        throw new Error("Client Tunnel also failed: " + JSON.stringify(cbData));
                    }
                } catch (cbErr) {
                    console.warn(cbErr);
                    showError("Instagram extraction failed. Please check the URL or Try later.");
                }
            } else {
                showError(error.message);
            }
        } finally {
            setLoadingState(false);
        }
    });

    /**
     * 渲染查询结果
     * @param {Object} data - 后端返回的数据字典
     */
    function renderResult(data) {
        // 设置标题
        document.getElementById('video-title').textContent = data.title;

        // 设置封面图
        const thumbnailEl = document.getElementById('video-thumbnail');
        if (data.thumbnail) {
            thumbnailEl.style.backgroundImage = `url('${data.thumbnail}')`;
        } else {
            thumbnailEl.style.backgroundImage = 'none';
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
                <!-- 使用 fetch 获取二进制后触发 JS 下载，消除双击失灵以及跨域被阻隔的问题 -->
                <a href="javascript:void(0);" onclick="forceDownload('${fmt.url}', this)" class="download-link">
                    Download
                </a>
                <!-- 保留原链接的新标签页播放 -->
                <a href="${fmt.url}" class="download-link" style="margin-top: 5px; background: transparent; color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4);" target="_blank" rel="noopener noreferrer">
                    Play in Browser
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
    window.forceDownload = async function (url, btnElement) {
        const originalText = btnElement.innerText;
        btnElement.innerText = "Downloading...";
        btnElement.style.pointerEvents = "none";
        btnElement.style.opacity = "0.7";
        try {
            const response = await fetch('/api/download?url=' + encodeURIComponent(url));
            if (!response.ok) {
                // 如果代理失败或对方拒绝，自动Fallback降级：直接开启新标签页供用户预览保存
                window.open(url, '_blank');
                throw new Error("Proxy error, opening in new tab");
            }
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = objectUrl;
            a.download = "video.mp4";
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
