(() => {
    const properties = [
        '--color-primary', '--color-positive', '--color-negative',
        '--color-widget-background', '--color-widget-background-highlight',
        '--color-widget-content-border', '--color-text-base', '--color-text-subdue',
    ];
    const probe = document.createElement('span');
    probe.hidden = true;
    document.body.append(probe);

    function sendTheme(frame) {
        const colors = {};
        for (const property of properties) {
            probe.style.color = `var(${property})`;
            colors[property] = getComputedStyle(probe).color;
        }
        frame.contentWindow.postMessage({type: 'meeting-theme', colors, scheme: document.documentElement.dataset.scheme}, new URL(frame.src).origin);
    }

    function frames() {
        return [...document.querySelectorAll('iframe[src]')].filter(frame => {
            const url = new URL(frame.src);
            return url.protocol === 'http:' && url.port === '4536';
        });
    }

    window.addEventListener('message', event => {
        if (event.data?.type !== 'meeting-theme-ready') return;
        const frame = frames().find(frame => frame.contentWindow === event.source && new URL(frame.src).origin === event.origin);
        if (frame) sendTheme(frame);
    });

    const observer = new MutationObserver(() => frames().forEach(sendTheme));
    observer.observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme', 'data-scheme', 'style']});
    const themeStyle = document.getElementById('theme-style');
    if (themeStyle) observer.observe(themeStyle, {childList: true, characterData: true, subtree: true});
})();
