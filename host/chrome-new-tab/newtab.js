// Chrome keeps the cursor in the address bar on an overridden new tab page, so
// Lab's search box couldn't take focus. A tab opened with a URL gets page focus:
// open Lab in this tab's place and close this one.
chrome.tabs.getCurrent((tab) => {
  chrome.tabs.create({ url: "http://YOUR_HOSTNAME:3005/lab", index: tab.index });
  chrome.tabs.remove(tab.id);
});
