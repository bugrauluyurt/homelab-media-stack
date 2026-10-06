export function getSubtitleFilename(subtitleName, subtitleLanguage) {
    const releaseName = subtitleName.replace(/\.srt$/i, '')
        .replace(/[<>:"/\\|?*\u0000-\u001f]/g, ' ')
        .replace(/^[.\s]+|[.\s]+$/g, '')
        .replace(/\s+/g, ' ')
        .slice(0, 180) || 'subtitles';
    const languageCode = subtitleLanguage.replace(/[^a-z]/gi, '').slice(0, 3).toLowerCase() || 'und';

    return `${releaseName}.${languageCode}.srt`;
}

export async function getSubtitleFile({ apiClient, subtitleId, pageUrl = globalThis.location.href }) {
    const subtitlePath = `Providers/Subtitles/Subtitles/${encodeURIComponent(subtitleId)}`;
    const subtitleUrl = new URL(apiClient.getUrl(subtitlePath), pageUrl);

    if (subtitleUrl.origin !== new URL(pageUrl).origin) {
        throw new Error('Subtitles must come from the same server.');
    }

    const requestHeaders = {};
    apiClient.setRequestHeaders(requestHeaders);

    const subtitleResponse = await fetch(subtitleUrl, {
        headers: requestHeaders,
        redirect: 'error',
        signal: AbortSignal.timeout(30000)
    });

    if (!subtitleResponse.ok) {
        throw new Error(`Subtitle download failed (${subtitleResponse.status}).`);
    }

    const subtitleBlob = await subtitleResponse.blob();

    if (!subtitleBlob.size) {
        throw new Error('The subtitle file is empty.');
    }

    return subtitleBlob;
}

function addDownloadButtons() {
    if (!window.ApiClient?.getUrl || !window.ApiClient?.setRequestHeaders) {
        return;
    }

    for (const subtitleRow of document.querySelectorAll('.subtitleEditorDialog .subtitleResults .listItem[data-subid]')) {
        const providerHeading = subtitleRow.parentElement.previousElementSibling;
        const subtitleId = subtitleRow.dataset.subid;
        const subtitleLanguage = subtitleId.match(/^[a-f0-9]{32}_srt-([a-z]{2,3})-\d+(?:-(?:sdh|forced))*$/i)?.[1];
        const subtitleBody = subtitleRow.querySelector('.listItemBody');

        if (subtitleRow.tagName !== 'DIV' || providerHeading?.textContent.trim() !== 'Open Subtitles'
            || !subtitleLanguage || !subtitleBody || subtitleRow.querySelector('[data-subtitle-save]')) {
            continue;
        }

        const subtitleName = subtitleBody.firstElementChild?.textContent ?? 'subtitles';

        const downloadButton = document.createElement('button');
        downloadButton.type = 'button';
        downloadButton.className = 'listItemButton paper-icon-button-light';
        downloadButton.setAttribute('is', 'paper-icon-button-light');
        downloadButton.setAttribute('aria-label', 'Save subtitle to device');
        downloadButton.setAttribute('data-subtitle-save', '');
        downloadButton.title = 'Save to device';

        const downloadIcon = document.createElement('span');
        downloadIcon.className = 'material-icons';
        downloadIcon.setAttribute('aria-hidden', 'true');
        downloadIcon.textContent = 'download_for_offline';
        downloadButton.append(downloadIcon);

        const downloadStatus = document.createElement('div');
        downloadStatus.className = 'secondary listItemBodyText';
        downloadStatus.setAttribute('role', 'status');
        subtitleBody.append(downloadStatus);

        downloadButton.addEventListener('click', async (downloadEvent) => {
            downloadEvent.preventDefault();
            downloadEvent.stopPropagation();

            if (downloadButton.disabled) {
                return;
            }

            downloadButton.disabled = true;
            downloadStatus.textContent = 'Downloading subtitle...';

            try {
                const subtitleBlob = await getSubtitleFile({ apiClient: window.ApiClient, subtitleId });

                const subtitleObjectUrl = URL.createObjectURL(subtitleBlob);
                const downloadLink = document.createElement('a');
                downloadLink.href = subtitleObjectUrl;
                downloadLink.download = getSubtitleFilename(subtitleName, subtitleLanguage);
                document.body.append(downloadLink);

                downloadLink.click();
                downloadLink.remove();

                setTimeout(() => URL.revokeObjectURL(subtitleObjectUrl), 60000);

                downloadStatus.textContent = 'Download started.';
            } catch (downloadError) {
                downloadStatus.textContent = downloadError instanceof Error
                    ? downloadError.message : 'Unable to download subtitle. Try again.';
            } finally {
                downloadButton.disabled = false;
            }
        });

        subtitleRow.append(downloadButton);
    }
}

if (typeof document !== 'undefined') {
    const subtitleObserver = new MutationObserver(addDownloadButtons);
    subtitleObserver.observe(document.body, { childList: true, subtree: true });

    addDownloadButtons();
}
