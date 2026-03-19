// Background service worker for GitHub Secret Detector Extension
console.log("GitHub Secret Detector Extension loaded");

// Listen for extension installation or updates
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Extension installed for the first time');
  } else if (details.reason === 'update') {
    console.log('Extension updated to version:', chrome.runtime.getManifest().version);
  }
});

// Keep service worker alive (optional, for debugging)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Message received:', message);
  
  if (message.action === 'ping') {
    sendResponse({ status: 'alive' });
  }
  
  return true; // Keep the message channel open for async response
});

// Log when content script is active on a GitHub page
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('github.com')) {
    console.log('GitHub page loaded:', tab.url);
  }
});
