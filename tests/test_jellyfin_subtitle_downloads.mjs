import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { after, before, test } from 'node:test';

import { getSubtitleFile, getSubtitleFilename } from '../apps/jellyfin/custom-cont-init.d/assets/subtitle-downloads.js';

let subtitleServer;
let serverUrl;

let requestedSubtitle;

let responseStatus = 200;
let subtitleContent = '1\n00:00:01,000 --> 00:00:02,000\nÇa marche.\n';

before(async () => {
    subtitleServer = createServer((request, response) => {
        requestedSubtitle = { url: request.url, authorization: request.headers.authorization, method: request.method };

        if (request.url.endsWith('/redirect')) {
            response.writeHead(302, { Location: `${serverUrl}followed` });
            response.end();

            return;
        }

        response.writeHead(responseStatus, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end(subtitleContent);
    });

    await new Promise((resolve) => subtitleServer.listen(0, '127.0.0.1', resolve));

    serverUrl = `http://127.0.0.1:${subtitleServer.address().port}/jellyfin/`;
});

after(() => subtitleServer.close());

test('fetches exact subtitle bytes using the viewer session and preserves a base path', async () => {
    const apiClient = {
        getUrl: (subtitlePath) => `${serverUrl}${subtitlePath}`,
        setRequestHeaders: (requestHeaders) => { requestHeaders.Authorization = 'MediaBrowser Token="test-viewer-session"'; }
    };

    const subtitleBlob = await getSubtitleFile({ apiClient, subtitleId: 'provider_srt-eng-123', pageUrl: serverUrl });

    assert.equal(await subtitleBlob.text(), subtitleContent);
    assert.deepEqual(requestedSubtitle, {
        url: '/jellyfin/Providers/Subtitles/Subtitles/provider_srt-eng-123',
        authorization: 'MediaBrowser Token="test-viewer-session"',
        method: 'GET'
    });
});

test('encodes subtitle identifiers instead of interpreting them as paths', async () => {
    const apiClient = { getUrl: (subtitlePath) => `${serverUrl}${subtitlePath}`, setRequestHeaders: () => {} };

    await getSubtitleFile({ apiClient, subtitleId: 'provider/../subtitle?token=wrong', pageUrl: serverUrl });

    assert.equal(requestedSubtitle.url,
        '/jellyfin/Providers/Subtitles/Subtitles/provider%2F..%2Fsubtitle%3Ftoken%3Dwrong');
});

test('does not send session credentials to a different origin', async () => {
    let requestedHeaders = false;
    const apiClient = {
        getUrl: () => 'https://another-server.example/subtitle',
        setRequestHeaders: () => { requestedHeaders = true; }
    };

    await assert.rejects(getSubtitleFile({ apiClient, subtitleId: 'subtitle', pageUrl: serverUrl }), /same server/);
    assert.equal(requestedHeaders, false);
});

test('rejects denied, throttled and failed downloads without saving error bodies', async () => {
    const apiClient = { getUrl: (subtitlePath) => `${serverUrl}${subtitlePath}`, setRequestHeaders: () => {} };

    for (const failureStatus of [401, 403, 429, 500]) {
        responseStatus = failureStatus;

        await assert.rejects(getSubtitleFile({ apiClient, subtitleId: 'subtitle', pageUrl: serverUrl }),
            new RegExp(String(failureStatus)));
    }

    responseStatus = 200;
});

test('rejects an empty subtitle file', async () => {
    const apiClient = { getUrl: (subtitlePath) => `${serverUrl}${subtitlePath}`, setRequestHeaders: () => {} };
    const originalSubtitleContent = subtitleContent;
    subtitleContent = '';

    await assert.rejects(getSubtitleFile({ apiClient, subtitleId: 'subtitle', pageUrl: serverUrl }), /empty/);

    subtitleContent = originalSubtitleContent;
});

test('does not follow redirects with the viewer session', async () => {
    const apiClient = {
        getUrl: (subtitlePath) => `${serverUrl}${subtitlePath}`,
        setRequestHeaders: (requestHeaders) => { requestHeaders.Authorization = 'MediaBrowser Token="test-viewer-session"'; }
    };

    await assert.rejects(getSubtitleFile({ apiClient, subtitleId: 'redirect', pageUrl: serverUrl }), TypeError);
    assert.equal(requestedSubtitle.url, '/jellyfin/Providers/Subtitles/Subtitles/redirect');
});

test('builds safe filenames while keeping the SRT extension and useful release name', () => {
    assert.equal(getSubtitleFilename('Film 2026 WEB-DL', 'eng'), 'Film 2026 WEB-DL.eng.srt');
    assert.equal(getSubtitleFilename('../../Film:<bad>\\name\u0000.srt', 'fra'), 'Film bad name.fra.srt');
    assert.equal(getSubtitleFilename('...<>:"/\\|?*', 'eng'), 'subtitles.eng.srt');
    assert.equal(getSubtitleFilename('Film', '../eng'), 'Film.eng.srt');
});
