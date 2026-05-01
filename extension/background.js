// AI Slop Detector — Background Service Worker
// Manages storage: usage count, activation state, server URL

const STORAGE_KEYS = {
  USAGE_COUNT: 'usageCount',
  ACTIVATED: 'activated',
  SERVER_URL: 'serverUrl',
};

const DEFAULTS = {
  USAGE_COUNT: 0,
  ACTIVATED: false,
  SERVER_URL: 'http://127.0.0.1:8766',
};

// Initialize storage on install
chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get(Object.values(STORAGE_KEYS));
  const toSet = {};
  for (const [key, storageKey] of Object.entries(STORAGE_KEYS)) {
    if (stored[storageKey] === undefined) {
      toSet[storageKey] = DEFAULTS[key];
    }
  }
  if (Object.keys(toSet).length > 0) {
    await chrome.storage.local.set(toSet);
  }
});

// Handle messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  switch (request.action) {
    case 'getState':
      chrome.storage.local.get(Object.values(STORAGE_KEYS), (result) => {
        sendResponse({
          usageCount: result[STORAGE_KEYS.USAGE_COUNT] ?? DEFAULTS.USAGE_COUNT,
          activated: result[STORAGE_KEYS.ACTIVATED] ?? DEFAULTS.ACTIVATED,
          serverUrl: result[STORAGE_KEYS.SERVER_URL] ?? DEFAULTS.SERVER_URL,
        });
      });
      return true; // Keep channel open for async

    case 'incrementUsage':
      chrome.storage.local.get([STORAGE_KEYS.USAGE_COUNT], (result) => {
        const newCount = (result[STORAGE_KEYS.USAGE_COUNT] ?? 0) + 1;
        chrome.storage.local.set({ [STORAGE_KEYS.USAGE_COUNT]: newCount }, () => {
          sendResponse({ usageCount: newCount });
        });
      });
      return true;

    case 'activate':
      chrome.storage.local.set({ [STORAGE_KEYS.ACTIVATED]: true }, () => {
        sendResponse({ success: true });
      });
      return true;

    case 'setServerUrl':
      chrome.storage.local.set({ [STORAGE_KEYS.SERVER_URL]: request.url }, () => {
        sendResponse({ success: true });
      });
      return true;

    case 'getActiveTabUrl':
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const url = tabs[0]?.url || '';
        // Extract repo URL if on a GitHub repo page
        const match = url.match(/^https:\/\/github\.com\/([^/]+\/[^/]+)/);
        sendResponse({ url: match ? `https://github.com/${match[1]}` : '' });
      });
      return true;

    default:
      sendResponse({ error: 'Unknown action' });
      return false;
  }
});
