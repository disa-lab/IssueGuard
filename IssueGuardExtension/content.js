// ============================================================================
// IssueGuard Content Script
// Real-time secret detection for GitHub issue forms
// ============================================================================

// State management
let debounceTimer = null;
let isChecking = false;
let currentIndicator = null;
let currentSpinner = null;
let currentTooltip = null;
let lastCheckedText = "";
const DEBOUNCE_DELAY_MS = 1000; // 1 second debounce delay (Grammarly-like behavior)
let currentHighlights = []; // Track all active highlights
let highlightObserver = null; // Intersection observer for scroll tracking

// ============================================================================
// PLATFORM DETECTION
// ============================================================================
// Detect whether we're on GitHub or GitLab
// ============================================================================

function detectPlatform() {
  const hostname = window.location.hostname;
  if (hostname.includes('gitlab')) return 'gitlab';
  return 'github';
}

// ============================================================================
// THEME CONFIGURATION
// ============================================================================
// Dynamically detect GitHub/GitLab light/dark mode
// ============================================================================

// Helper function to detect current theme (GitHub or GitLab)
function detectGitHubTheme() {
  const platform = detectPlatform();

  // GitLab-specific theme detection
  if (platform === 'gitlab') {
    // GitLab uses 'gl-dark' class on the html element for dark mode
    if (document.documentElement.classList.contains('gl-dark')) {
      return 'dark';
    }
    // Also check for theme classes
    if (document.documentElement.classList.contains('dark-mode') ||
      document.body.classList.contains('dark-mode')) {
      return 'dark';
    }
    return 'light';
  }

  // GitHub theme detection (existing logic)
  // Method 1: Check data-color-mode attribute on html or body
  const htmlColorMode = document.documentElement.getAttribute('data-color-mode');
  const bodyColorMode = document.body.getAttribute('data-color-mode');

  if (htmlColorMode === 'dark' || bodyColorMode === 'dark') {
    return 'dark';
  }
  if (htmlColorMode === 'light' || bodyColorMode === 'light') {
    return 'light';
  }

  // Method 2: Check for dark mode class on html or body
  if (document.documentElement.classList.contains('dark') ||
    document.documentElement.classList.contains('dark-theme') ||
    document.body.classList.contains('dark') ||
    document.body.classList.contains('dark-theme')) {
    return 'dark';
  }

  // Method 3: Check data-theme attribute
  const htmlTheme = document.documentElement.getAttribute('data-theme');
  const bodyTheme = document.body.getAttribute('data-theme');
  if (htmlTheme && htmlTheme.includes('dark')) return 'dark';
  if (bodyTheme && bodyTheme.includes('dark')) return 'dark';
  if (htmlTheme && htmlTheme.includes('light')) return 'light';
  if (bodyTheme && bodyTheme.includes('light')) return 'light';

  // Method 4: Check computed background color of body
  const bodyBgColor = window.getComputedStyle(document.body).backgroundColor;
  if (bodyBgColor) {
    // Parse RGB values
    const rgb = bodyBgColor.match(/\d+/g);
    if (rgb && rgb.length >= 3) {
      const brightness = (parseInt(rgb[0]) * 299 + parseInt(rgb[1]) * 587 + parseInt(rgb[2]) * 114) / 1000;
      // If brightness is less than 128, it's likely dark mode
      return brightness < 128 ? 'dark' : 'light';
    }
  }

  // Default to light if unable to detect
  return 'light';
}

// Helper function to get theme-appropriate inline styles
function getTooltipItemStyles() {
  const theme = detectGitHubTheme();
  if (theme === 'light') {
    return {
      background: 'rgba(0,0,0,0.08)',
      borderLeft: '3px solid rgba(0,0,0,0.3)'
    };
  }
  return {
    background: 'rgba(255,255,255,0.15)',
    borderLeft: '3px solid rgba(255,255,255,0.5)'
  };
}

function createIndicator() {
  const indicator = document.createElement("div");
  indicator.style.position = "absolute";
  indicator.style.right = "10px";
  indicator.style.top = "10px";
  indicator.style.width = "36px";
  indicator.style.height = "36px";
  indicator.style.borderRadius = "50%";
  indicator.style.border = "3px solid #e0e0e0";
  indicator.style.backgroundColor = "#667eea";
  indicator.style.boxShadow = "0 4px 16px rgba(102, 126, 234, 0.3)";
  indicator.style.cursor = "pointer";
  indicator.style.transition = "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)";
  indicator.style.zIndex = "9999";
  indicator.className = "secret-detector-indicator";
  indicator.style.display = "flex";
  indicator.style.alignItems = "center";
  indicator.style.justifyContent = "center";
  indicator.style.fontSize = "18px";
  indicator.innerHTML = "🛡️";

  // Add pulsing animation for initial state
  indicator.style.animation = "pulse 2s infinite";

  // Add hover effect
  indicator.addEventListener("mouseenter", () => {
    indicator.style.transform = "scale(1.15)";
    indicator.style.boxShadow = "0 6px 20px rgba(102, 126, 234, 0.5)";
  });

  indicator.addEventListener("mouseleave", () => {
    indicator.style.transform = "scale(1)";
    indicator.style.boxShadow = "0 4px 16px rgba(102, 126, 234, 0.3)";
  });

  return indicator;
}

function createSpinner() {
  const spinner = document.createElement("div");
  spinner.className = "secret-detector-spinner";
  spinner.style.position = "absolute";
  spinner.style.right = "55px";
  spinner.style.top = "14px";
  spinner.style.width = "28px";
  spinner.style.height = "28px";
  spinner.style.border = "3px solid rgba(102, 126, 234, 0.2)";
  spinner.style.borderTop = "3px solid #667eea";
  spinner.style.borderRadius = "50%";
  spinner.style.animation = "spin 0.6s linear infinite";
  spinner.style.display = "none";
  spinner.style.zIndex = "9999";
  return spinner;
}

// Add spinner animation and enhanced styles
const style = document.createElement('style');
style.innerHTML = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  
  @keyframes pulse {
    0% {
      box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3);
    }
    50% {
      box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3), 0 0 20px rgba(76, 175, 80, 0.6);
    }
    100% {
      box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3);
    }
  }
  
  @keyframes pulseRed {
    0% {
      box-shadow: 0 4px 16px rgba(244, 67, 54, 0.3);
    }
    50% {
      box-shadow: 0 4px 16px rgba(244, 67, 54, 0.3), 0 0 24px rgba(244, 67, 54, 0.8);
    }
    100% {
      box-shadow: 0 4px 16px rgba(244, 67, 54, 0.3);
    }
  }
  
  .secret-detector-tooltip {
    position: absolute;
    right: 55px;
    top: 10px;
    padding: 16px 20px;
    border-radius: 12px;
    font-size: 13px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    z-index: 10000;
    white-space: pre-line;
    max-width: 420px;
    max-height: 400px;
    overflow-y: auto;
    overflow-x: hidden;
    line-height: 1.6;
    animation: fadeIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    backdrop-filter: blur(10px);
    pointer-events: auto;
  }
  
  /* Dark theme styles */
  .secret-detector-tooltip.theme-dark {
    background: linear-gradient(135deg, #000000 0%, #1a1a1a 50%, #2d2d2d 100%);
    color: white;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(59, 130, 246, 0.3);
  }
  
  /* Light theme styles */
  .secret-detector-tooltip.theme-light {
    background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 50%, #e9ecef 100%);
    color: #1a1a1a;
    box-shadow: 0 8px 32px rgba(0,0,0,0.15), 0 0 0 1px rgba(59, 130, 246, 0.2);
  }
  
  /* Dark theme scrollbar */
  .secret-detector-tooltip.theme-dark::-webkit-scrollbar {
    width: 8px;
  }
  
  .secret-detector-tooltip.theme-dark::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 4px;
  }
  
  .secret-detector-tooltip.theme-dark::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.3);
    border-radius: 4px;
  }
  
  .secret-detector-tooltip.theme-dark::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.5);
  }
  
  /* Light theme scrollbar */
  .secret-detector-tooltip.theme-light::-webkit-scrollbar {
    width: 8px;
  }
  
  .secret-detector-tooltip.theme-light::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 4px;
  }
  
  .secret-detector-tooltip.theme-light::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
  }
  
  .secret-detector-tooltip.theme-light::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.3);
  }
  
  /* Dark theme arrow */
  .secret-detector-tooltip.theme-dark::after {
    content: '';
    position: absolute;
    right: -10px;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 0;
    border-style: solid;
    border-width: 10px 0 10px 10px;
    border-color: transparent transparent transparent #1a1a1a;
  }
  
  /* Light theme arrow */
  .secret-detector-tooltip.theme-light::after {
    content: '';
    position: absolute;
    right: -10px;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 0;
    border-style: solid;
    border-width: 10px 0 10px 10px;
    border-color: transparent transparent transparent #f8f9fa;
  }
  
  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateX(-15px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }
  
  /* Dark theme badges */
  .secret-badge.theme-dark {
    display: inline-block;
    background: rgba(244, 67, 54, 0.2);
    color: #ff6b6b;
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 11px;
    margin-right: 6px;
    letter-spacing: 0.5px;
    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
    border: 1px solid rgba(244, 67, 54, 0.3);
  }
  
  .safe-badge.theme-dark {
    display: inline-block;
    background: rgba(76, 175, 80, 0.2);
    color: #4ade80;
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 11px;
    margin-right: 6px;
    letter-spacing: 0.5px;
    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
    border: 1px solid rgba(76, 175, 80, 0.3);
  }
  
  /* Light theme badges */
  .secret-badge.theme-light {
    display: inline-block;
    background: rgba(244, 67, 54, 0.15);
    color: #d32f2f;
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 11px;
    margin-right: 6px;
    letter-spacing: 0.5px;
    text-shadow: none;
    border: 1px solid rgba(244, 67, 54, 0.4);
  }
  
  .safe-badge.theme-light {
    display: inline-block;
    background: rgba(76, 175, 80, 0.15);
    color: #2e7d32;
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 11px;
    margin-right: 6px;
    letter-spacing: 0.5px;
    text-shadow: none;
    border: 1px solid rgba(76, 175, 80, 0.4);
  }
  
  .secret-highlight {
    background-color: rgba(244, 67, 54, 0.3) !important;
    border-bottom: 2px solid #f44336 !important;
    border-radius: 3px;
    padding: 2px 0;
    position: relative;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }
  
  .secret-highlight:hover {
    background-color: rgba(244, 67, 54, 0.5) !important;
  }
  
  .secret-highlight-overlay {
    position: absolute;
    background-color: rgba(244, 67, 54, 0.3);
    border-bottom: 2px solid #f44336;
    border-radius: 3px;
    pointer-events: none;
    z-index: 1;
  }
`;
document.head.appendChild(style);

// Helper function to create highlight overlays for secret strings
function createHighlightOverlay(textarea, secretString) {
  const overlay = document.createElement('div');
  overlay.className = 'secret-highlight-overlay';
  overlay.setAttribute('data-secret', secretString);
  return overlay;
}

// Function to highlight secrets in contenteditable elements using CSS Custom Highlight API
// This API highlights text without modifying the DOM structure
function updateHighlightPositionsContentEditable(element, secretStrings) {
  // Check if CSS Custom Highlight API is supported
  if (!CSS.highlights) {
    console.log('[IssueGuard] CSS Custom Highlight API not supported, falling back to tooltip only');
    return;
  }

  // Clear any existing highlights
  CSS.highlights.delete('secret-highlight');

  const allRanges = [];

  // Use TreeWalker to find all text nodes
  const walker = document.createTreeWalker(
    element,
    NodeFilter.SHOW_TEXT,
    null,
    false
  );

  const textNodes = [];
  let node;
  while (node = walker.nextNode()) {
    if (node.textContent.trim().length > 0) {
      textNodes.push(node);
    }
  }

  console.log(`[IssueGuard] Found ${textNodes.length} text nodes, searching for ${secretStrings.length} secrets`);

  // For each secret string, find it in the text nodes and create ranges
  secretStrings.forEach(secretString => {
    textNodes.forEach(textNode => {
      const text = textNode.textContent;
      let startIndex = 0;
      let index;

      while ((index = text.indexOf(secretString, startIndex)) !== -1) {
        try {
          // Create a range for this occurrence
          const range = new Range();
          range.setStart(textNode, index);
          range.setEnd(textNode, Math.min(index + secretString.length, text.length));
          allRanges.push(range);
        } catch (e) {
          console.log('[IssueGuard] Error creating range:', e);
        }
        startIndex = index + 1;
      }
    });
  });

  // Create a Highlight object with all ranges and register it
  if (allRanges.length > 0) {
    const highlight = new Highlight(...allRanges);
    CSS.highlights.set('secret-highlight', highlight);
    console.log(`[IssueGuard] Created CSS highlight with ${allRanges.length} ranges`);
  }

  // Store reference for cleanup
  element._cssHighlightActive = true;
  element._highlightRanges = allRanges;
}

// Add CSS for the custom highlight (only once)
if (!document.querySelector('#issueguard-highlight-style')) {
  const highlightStyle = document.createElement('style');
  highlightStyle.id = 'issueguard-highlight-style';
  highlightStyle.textContent = `
    ::highlight(secret-highlight) {
      background-color: rgba(244, 67, 54, 0.35);
      color: inherit;
    }
  `;
  document.head.appendChild(highlightStyle);
}

// Function to position highlights based on text position in textarea
// Supports both textareas AND contenteditable elements (like GitLab's ProseMirror editor)
function updateHighlightPositions(textarea, secretStrings) {
  // Remove existing highlights
  removeHighlights(textarea);

  if (!secretStrings || secretStrings.length === 0) {
    return;
  }

  // Use CSS Custom Highlight API for contenteditable elements
  if (textarea.isContentEditable || textarea.getAttribute('contenteditable') === 'true' || textarea.tagName !== 'TEXTAREA') {
    console.log('[IssueGuard] Using CSS Custom Highlight API for contenteditable');
    updateHighlightPositionsContentEditable(textarea, secretStrings);
    return;
  }

  const text = getElementText(textarea);
  if (!text) return; // Safety check for empty/undefined text

  const highlights = [];

  // Create a mirror div to measure text positions
  const mirror = createMirrorDiv(textarea);

  // Get textarea's current scroll position and boundaries
  const textareaRect = textarea.getBoundingClientRect();
  const scrollTop = textarea.scrollTop;
  const scrollLeft = textarea.scrollLeft;

  // Get textarea's position relative to its parent
  const textareaOffsetLeft = textarea.offsetLeft;
  const textareaOffsetTop = textarea.offsetTop;

  secretStrings.forEach(secretString => {
    let startIndex = 0;
    let index;

    // Find all occurrences of this secret string
    while ((index = text.indexOf(secretString, startIndex)) !== -1) {
      // Check if the text still matches (hasn't been edited)
      const actualText = text.substring(index, index + secretString.length);
      if (actualText === secretString) {
        const position = getTextPosition(mirror, text, index, secretString.length, textarea);

        if (position) {
          const overlay = createHighlightOverlay(textarea, secretString);

          // Adjust position based on scroll and textarea offset within parent
          const adjustedLeft = textareaOffsetLeft + position.left - scrollLeft;
          const adjustedTop = textareaOffsetTop + position.top - scrollTop;

          overlay.style.left = adjustedLeft + 'px';
          overlay.style.top = adjustedTop + 'px';
          overlay.style.width = position.width + 'px';
          overlay.style.height = position.height + 'px';

          highlights.push({
            element: overlay,
            secretString: secretString,
            index: index,
            baseLeft: position.left,
            baseTop: position.top,
            width: position.width,
            height: position.height,
            textareaOffsetLeft: textareaOffsetLeft,
            textareaOffsetTop: textareaOffsetTop
          });

          // Append to textarea's parent
          if (textarea.parentElement) {
            textarea.parentElement.appendChild(overlay);
          }
        }
      }

      startIndex = index + 1;
    }
  });

  // Clean up mirror
  mirror.remove();

  // Store highlights reference
  textarea._highlights = highlights;
  currentHighlights = currentHighlights.concat(highlights);
}

// Create a mirror div that matches the textarea's styling
function createMirrorDiv(textarea) {
  const mirror = document.createElement('div');
  const computedStyle = window.getComputedStyle(textarea);

  // Copy relevant styles
  mirror.style.position = 'absolute';
  mirror.style.visibility = 'hidden';
  mirror.style.whiteSpace = 'pre-wrap';
  mirror.style.wordWrap = 'break-word';
  mirror.style.overflowWrap = 'break-word';
  mirror.style.fontFamily = computedStyle.fontFamily;
  mirror.style.fontSize = computedStyle.fontSize;
  mirror.style.fontWeight = computedStyle.fontWeight;
  mirror.style.lineHeight = computedStyle.lineHeight;
  mirror.style.letterSpacing = computedStyle.letterSpacing;
  mirror.style.padding = computedStyle.padding;
  mirror.style.border = computedStyle.border;
  mirror.style.boxSizing = computedStyle.boxSizing;
  mirror.style.width = textarea.scrollWidth + 'px';
  mirror.style.height = textarea.scrollHeight + 'px';
  mirror.style.left = '-9999px';
  mirror.style.top = '-9999px';
  mirror.style.overflow = 'hidden';

  document.body.appendChild(mirror);
  return mirror;
}

// Get the position of a substring within the textarea
function getTextPosition(mirror, fullText, startIndex, length, textarea) {
  try {
    const textBefore = fullText.substring(0, startIndex);
    const targetText = fullText.substring(startIndex, startIndex + length);

    // Set mirror scroll to match textarea (for accurate measurement)
    if (textarea) {
      mirror.scrollTop = 0;
      mirror.scrollLeft = 0;
    }

    // Create spans to measure position
    mirror.innerHTML = '';

    const beforeSpan = document.createElement('span');
    beforeSpan.textContent = textBefore;
    mirror.appendChild(beforeSpan);

    const targetSpan = document.createElement('span');
    targetSpan.textContent = targetText;
    targetSpan.style.backgroundColor = 'rgba(244, 67, 54, 0.3)';
    mirror.appendChild(targetSpan);

    const afterSpan = document.createElement('span');
    afterSpan.textContent = fullText.substring(startIndex + length);
    mirror.appendChild(afterSpan);

    // Get position relative to mirror (without scroll offset)
    const targetRect = targetSpan.getBoundingClientRect();
    const mirrorRect = mirror.getBoundingClientRect();

    // Calculate position within the mirror's content
    const relativeLeft = targetRect.left - mirrorRect.left + mirror.scrollLeft;
    const relativeTop = targetRect.top - mirrorRect.top + mirror.scrollTop;

    return {
      left: relativeLeft,
      top: relativeTop,
      width: targetRect.width,
      height: targetRect.height
    };
  } catch (error) {
    console.error('Error calculating text position:', error);
    return null;
  }
}

// Remove all highlights for a textarea
function removeHighlights(textarea) {
  if (textarea._highlights) {
    textarea._highlights.forEach(highlight => {
      if (highlight.element && highlight.element.parentElement) {
        highlight.element.remove();
      }
    });
    textarea._highlights = [];
  }

  // Also remove any orphaned highlights in the parent
  if (textarea.parentElement) {
    const orphanedHighlights = textarea.parentElement.querySelectorAll('.secret-highlight-overlay');
    orphanedHighlights.forEach(h => h.remove());
  }

  // For contenteditable: clean up CSS Custom Highlight API
  if (textarea._cssHighlightActive && CSS.highlights) {
    CSS.highlights.delete('secret-highlight');
    textarea._cssHighlightActive = false;
  }

  // Legacy: clean up body-appended overlays
  if (textarea._isContentEditable) {
    const bodyHighlights = document.body.querySelectorAll('.secret-highlight-overlay');
    bodyHighlights.forEach(h => h.remove());
  }

  // Clear from global tracking
  currentHighlights = currentHighlights.filter(h => h.element.parentElement);
}

// Set up scroll and input listeners to update highlights
function setupHighlightTracking(textarea) {
  // Update on scroll
  textarea.addEventListener('scroll', () => {
    if (textarea._highlights && textarea._highlights.length > 0) {
      // Update each highlight position based on scroll
      const scrollTop = textarea.scrollTop;
      const scrollLeft = textarea.scrollLeft;

      textarea._highlights.forEach(highlight => {
        if (highlight.element && highlight.element.parentElement) {
          const adjustedLeft = highlight.textareaOffsetLeft + highlight.baseLeft - scrollLeft;
          const adjustedTop = highlight.textareaOffsetTop + highlight.baseTop - scrollTop;

          highlight.element.style.left = adjustedLeft + 'px';
          highlight.element.style.top = adjustedTop + 'px';
        }
      });
    }
  });

  // Update on resize
  const resizeObserver = new ResizeObserver(() => {
    if (textarea._highlights && textarea._highlights.length > 0) {
      const secretStrings = textarea._highlights.map(h => h.secretString);
      const uniqueSecrets = [...new Set(secretStrings)];
      updateHighlightPositions(textarea, uniqueSecrets);
    }
  });

  resizeObserver.observe(textarea);
  textarea._resizeObserver = resizeObserver;
}

// Function to check the description and update the indicator
async function checkDescription(descriptionField, indicator, spinner) {
  // Prevent multiple simultaneous checks
  if (isChecking) {
    console.log("Check already in progress, skipping...");
    return;
  }

  isChecking = true;
  const description = getElementText(descriptionField).trim();

  try {
    spinner.style.display = "block";
    const response = await checkForSecrets(description);
    spinner.style.display = "none";

    console.log("Response received:", response);

    if (response && response.success) {
      if (response.secrets_detected > 0) {
        // Red indicator - secrets detected
        indicator.innerHTML = "⚠️";
        indicator.style.backgroundColor = "#f44336";
        indicator.style.border = "3px solid #d32f2f";
        indicator.style.boxShadow = "0 4px 16px rgba(244, 67, 54, 0.3)";
        indicator.style.animation = "pulseRed 2s infinite";

        // Filter to only secrets (not safe candidates)
        const secretCandidates = response.all_candidates.filter(c => c.is_secret);

        // Remove candidates that are substrings of other candidates
        const filteredSecrets = secretCandidates.filter((candidate, index, arr) => {
          return !arr.some((other, otherIndex) => {
            if (index === otherIndex) return false;
            return other.candidate_string.includes(candidate.candidate_string) &&
              other.candidate_string !== candidate.candidate_string;
          });
        });

        // Highlight the secret strings in the textarea
        const secretStrings = filteredSecrets.map(s => s.candidate_string);
        updateHighlightPositions(descriptionField, secretStrings);

        // Create detailed tooltip content
        const itemStyles = getTooltipItemStyles();
        let tooltipHTML = `<div style="font-weight: 700; margin-bottom: 12px; font-size: 15px;">⚠️ Secrets Detected</div>`;

        filteredSecrets.forEach((candidate, i) => {
          tooltipHTML += `<div style="margin: 10px 0; padding: 10px; background: ${itemStyles.background}; border-radius: 8px; border-left: ${itemStyles.borderLeft};">`;
          tooltipHTML += `<span class="secret-badge theme-${detectGitHubTheme()}">🔴 SECRET</span>`;
          tooltipHTML += `<div style="margin-top: 6px; font-size: 12px; font-weight: 600; word-break: break-all;">${escapeHtml(candidate.candidate_string.substring(0, 70))}${candidate.candidate_string.length > 70 ? '...' : ''}</div>`;
          tooltipHTML += `<div style="margin-top: 4px; font-size: 11px; opacity: 0.8;">Type: ${escapeHtml(candidate.secret_type)}</div>`;
          tooltipHTML += `</div>`;
        });

        indicator.setAttribute('data-tooltip', tooltipHTML);
      } else {
        // Green indicator - no secrets
        // Remove any existing highlights
        removeHighlights(descriptionField);

        indicator.innerHTML = "✅";
        indicator.style.backgroundColor = "#4caf50";
        indicator.style.border = "3px solid #388e3c";
        indicator.style.boxShadow = "0 4px 16px rgba(76, 175, 80, 0.3)";
        indicator.style.animation = "pulse 2s infinite";

        const tooltipHTML = `<div style="font-weight: 700; font-size: 15px;">✅ You're Safe!</div><div style="margin-top: 8px; opacity: 0.95; font-size: 13px;">No secrets detected in your text</div>`;
        indicator.setAttribute('data-tooltip', tooltipHTML);
      }
    } else {
      // Yellow indicator - error or invalid response
      indicator.innerHTML = "⚠️";
      indicator.style.backgroundColor = "#ff9800";
      indicator.style.border = "3px solid #f57c00";
      indicator.style.boxShadow = "0 4px 16px rgba(255, 152, 0, 0.3)";
      indicator.style.animation = "pulse 2s infinite";

      const tooltipHTML = `<div style="font-weight: 700; font-size: 15px;">⚠️ Connection Error</div><div style="margin-top: 8px; opacity: 0.95; font-size: 13px;">Unable to check for secrets. Please ensure the API is running.</div>`;
      indicator.setAttribute('data-tooltip', tooltipHTML);
    }
  } catch (error) {
    console.error("Error in checkDescription:", error);
    spinner.style.display = "none";

    indicator.innerHTML = "❌";
    indicator.style.backgroundColor = "#ff9800";
    indicator.style.border = "3px solid #f57c00";
    indicator.style.boxShadow = "0 4px 16px rgba(255, 152, 0, 0.3)";

    const tooltipHTML = `<div style="font-weight: 700; font-size: 15px;">❌ Error</div><div style="margin-top: 8px; opacity: 0.95; font-size: 13px;">An error occurred while checking</div>`;
    indicator.setAttribute('data-tooltip', tooltipHTML);
  } finally {
    isChecking = false;
  }
}

// Helper function to escape HTML
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Helper function to get text content from any element (textarea or contenteditable)
function getElementText(element) {
  if (!element) return '';

  // For textareas and inputs, use .value
  if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
    return element.value || '';
  }

  // For contenteditable elements (ProseMirror, etc.), use textContent
  if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') {
    return element.textContent || element.innerText || '';
  }

  // For elements with .value property (some custom elements)
  if ('value' in element) {
    return element.value || '';
  }

  // Fallback to textContent
  return element.textContent || element.innerText || '';
}

function startChecking(descriptionField) {
  // Check if already monitoring this field AND the indicator is still in the DOM
  // If the indicator was removed (e.g., modal closed), we need to reinitialize
  if (descriptionField._secretDetectorHandler) {
    const existingIndicator = descriptionField.parentElement?.querySelector('.secret-detector-indicator');
    if (existingIndicator) {
      console.log("[IssueGuard] Field already being monitored with indicator present, skipping...");
      return;
    } else {
      console.log("[IssueGuard] Handler exists but indicator missing - cleaning up and reinitializing...");
      // Reset lastCheckedText so the same content will trigger a new scan
      lastCheckedText = "";
      // Clean up the stale handler
      if (descriptionField._contentObserver) {
        descriptionField._contentObserver.disconnect();
        delete descriptionField._contentObserver;
      }
      descriptionField.removeEventListener('input', descriptionField._secretDetectorHandler);
      delete descriptionField._secretDetectorHandler;
    }
  }

  // Clean up any existing global elements
  if (currentIndicator && currentIndicator.parentElement) {
    console.log("[IssueGuard] Cleaning up existing global elements...");
    currentIndicator.remove();
    currentIndicator = null;
  }
  if (currentSpinner && currentSpinner.parentElement) {
    currentSpinner.remove();
    currentSpinner = null;
  }


  const indicator = createIndicator();
  const spinner = createSpinner();

  // Store references for cleanup
  currentIndicator = indicator;
  currentSpinner = spinner;

  descriptionField.parentElement.style.position = "relative";
  descriptionField.parentElement.appendChild(indicator);
  descriptionField.parentElement.appendChild(spinner);

  // Set up highlight tracking for scroll and resize
  setupHighlightTracking(descriptionField);

  // Tooltip hide timer
  let tooltipHideTimer = null;

  // Function to show tooltip
  const showTooltip = () => {
    // Clear any existing hide timer
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
      tooltipHideTimer = null;
    }

    const tooltipHTML = indicator.getAttribute('data-tooltip');
    if (tooltipHTML && !currentTooltip) {
      currentTooltip = document.createElement("div");
      currentTooltip.className = `secret-detector-tooltip theme-${detectGitHubTheme()}`;
      currentTooltip.innerHTML = tooltipHTML;
      descriptionField.parentElement.appendChild(currentTooltip);

      // Add event listeners to tooltip to keep it visible when hovering
      currentTooltip.addEventListener("mouseenter", () => {
        if (tooltipHideTimer) {
          clearTimeout(tooltipHideTimer);
          tooltipHideTimer = null;
        }
      });

      currentTooltip.addEventListener("mouseleave", () => {
        hideTooltipWithDelay();
      });
    }
  };

  // Function to hide tooltip with delay
  const hideTooltipWithDelay = () => {
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
    }

    tooltipHideTimer = setTimeout(() => {
      if (currentTooltip) {
        currentTooltip.remove();
        currentTooltip = null;
      }
      tooltipHideTimer = null;
    }, 300); // 300ms delay before hiding
  };

  // Show tooltip on hover
  indicator.addEventListener("mouseenter", showTooltip);

  // Hide tooltip on mouse leave with delay
  indicator.addEventListener("mouseleave", hideTooltipWithDelay);

  console.log("[IssueGuard] Starting secret detection...");

  // Perform an IMMEDIATE check if there's existing content (critical for modal reopen)
  const initialText = getElementText(descriptionField).trim();
  console.log(`[IssueGuard] Initial text length: ${initialText.length}, content: "${initialText.substring(0, 50)}..."`);
  if (initialText.length > 0) {
    console.log('[IssueGuard] Triggering immediate check for existing content...');
    // Show spinner immediately so user knows scan is in progress
    spinner.style.display = "block";
    lastCheckedText = initialText;
    checkDescription(descriptionField, indicator, spinner);
  }

  // Check if this is a ProseMirror/contenteditable element (GitLab rich text editor)
  const isContentEditable = descriptionField.isContentEditable ||
    descriptionField.getAttribute('contenteditable') === 'true' ||
    descriptionField.classList.contains('ProseMirror');

  // Debounced handler for content changes
  const handleContentChange = () => {
    const currentText = getElementText(descriptionField).trim();

    // Clear existing timer
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }

    // IMMEDIATE: Update highlight positions as user types (for real-time positioning)
    if (descriptionField._highlights && descriptionField._highlights.length > 0) {
      const text = getElementText(descriptionField);
      const secretStrings = [...new Set(descriptionField._highlights.map(h => h.secretString))];

      // Check if all secrets still exist in the text
      const allSecretsStillExist = secretStrings.every(secret => text.includes(secret));

      if (allSecretsStillExist) {
        // Update positions immediately to follow the text
        updateHighlightPositions(descriptionField, secretStrings);
      } else {
        // Some secrets were removed/edited, remove all highlights
        removeHighlights(descriptionField);
      }
    }

    // Only check if text has actually changed
    if (currentText === lastCheckedText) {
      return;
    }

    // Set up new debounced check
    debounceTimer = setTimeout(() => {
      console.log("[IssueGuard] Running debounced check after content change...");
      lastCheckedText = currentText;
      checkDescription(descriptionField, indicator, spinner);
    }, DEBOUNCE_DELAY_MS);
  };

  // Force immediate check (bypasses debounce)
  const forceImmediateCheck = () => {
    const currentText = getElementText(descriptionField).trim();
    if (currentText !== lastCheckedText && currentText.length > 0) {
      console.log('[IssueGuard] Forcing immediate check...');
      // Clear any pending debounce timer
      if (debounceTimer) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
      }
      lastCheckedText = currentText;
      checkDescription(descriptionField, indicator, spinner);
    }
  };

  // For ProseMirror/contenteditable: use MutationObserver to detect ALL changes
  // This catches typing, pasting, drag-drop, undo/redo, and any programmatic changes
  if (isContentEditable) {
    console.log('[IssueGuard] Setting up MutationObserver for ProseMirror/contenteditable...');

    const contentObserver = new MutationObserver((mutations) => {
      // Check if any mutation actually changed the text content
      let hasContentChange = false;
      for (const mutation of mutations) {
        if (mutation.type === 'characterData' ||
          mutation.type === 'childList' ||
          (mutation.type === 'attributes' && mutation.target.nodeType === Node.TEXT_NODE)) {
          hasContentChange = true;
          break;
        }
      }

      if (hasContentChange) {
        console.log('[IssueGuard] ProseMirror content change detected via MutationObserver');
        handleContentChange();
      }
    });

    contentObserver.observe(descriptionField, {
      childList: true,
      subtree: true,
      characterData: true,
      characterDataOldValue: true
    });

    // Store for cleanup
    descriptionField._contentObserver = contentObserver;

    // Also listen for paste on contenteditable (may fire before mutation)
    descriptionField.addEventListener('paste', () => {
      console.log('[IssueGuard] Paste event on contenteditable, scheduling immediate check...');
      setTimeout(forceImmediateCheck, 150);
    });

    // Listen for drop events (drag and drop)
    descriptionField.addEventListener('drop', () => {
      console.log('[IssueGuard] Drop event detected, scheduling immediate check...');
      setTimeout(forceImmediateCheck, 150);
    });
  } else {
    // For regular textareas: use input event
    descriptionField.addEventListener('input', handleContentChange);

    // Attach paste listener - triggers IMMEDIATE check
    descriptionField.addEventListener('paste', () => {
      console.log('[IssueGuard] Paste event on textarea, scheduling immediate check...');
      setTimeout(forceImmediateCheck, 100);
    });
  }

  // Store the handler for cleanup
  descriptionField._secretDetectorHandler = handleContentChange;
}

// Clean up previous elements to prevent memory leaks
function cleanupPreviousElements() {
  // Clear debounce timer
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }

  // Remove event listener from description field (supports both GitHub and GitLab)
  const descriptionField = document.querySelector('textarea[aria-label="Markdown value"]') ||
    document.querySelector('textarea[name="issue[body]"]') ||
    document.querySelector('textarea[aria-label="Comment body"]') ||
    document.querySelector('#issue-description') ||
    document.querySelector('textarea[name="issue[description]"]') ||
    document.querySelector('.js-gfm-input') ||
    document.querySelector('.ProseMirror');

  if (descriptionField) {
    if (descriptionField._secretDetectorHandler) {
      descriptionField.removeEventListener('input', descriptionField._secretDetectorHandler);
      delete descriptionField._secretDetectorHandler;
    }

    // Clean up MutationObserver for ProseMirror/contenteditable
    if (descriptionField._contentObserver) {
      descriptionField._contentObserver.disconnect();
      delete descriptionField._contentObserver;
    }

    // Clean up highlights
    removeHighlights(descriptionField);

    // Clean up resize observer
    if (descriptionField._resizeObserver) {
      descriptionField._resizeObserver.disconnect();
      delete descriptionField._resizeObserver;
    }
  }


  if (currentIndicator && currentIndicator.parentElement) {
    currentIndicator.remove();
    currentIndicator = null;
  }

  if (currentSpinner && currentSpinner.parentElement) {
    currentSpinner.remove();
    currentSpinner = null;
  }

  if (currentTooltip && currentTooltip.parentElement) {
    currentTooltip.remove();
    currentTooltip = null;
  }

  // Clear global highlights
  currentHighlights.forEach(h => {
    if (h.element && h.element.parentElement) {
      h.element.remove();
    }
  });
  currentHighlights = [];

  // Reset last checked text
  lastCheckedText = "";
  isChecking = false;

  // Cleanup all comment field monitors
  cleanupAllCommentFields();
}

async function checkForSecrets(description) {
  try {
    if (!description || description.length === 0) {
      return { success: true, secrets_detected: 0, all_candidates: [] };
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

    const response = await fetch("http://localhost:8000/detect", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text: description }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    console.log("Result from backend:", result);
    return result;
  } catch (error) {
    if (error.name === 'AbortError') {
      console.error("Request timeout:", error);
    } else {
      console.error("Error checking for secrets:", error);
    }
    return { success: false, error: error.message };
  }
}


function handleNewIssuePage() {
  const platform = detectPlatform();
  let descriptionField;

  if (platform === 'gitlab') {
    // GitLab issue description selectors
    // GitLab uses various editor types: plain textarea, rich text editor (ProseMirror/Tiptap), or markdown
    descriptionField = document.querySelector('#issue-description') ||
      document.querySelector('textarea[name="issue[description]"]') ||
      document.querySelector('.js-gfm-input') ||
      document.querySelector('textarea[data-testid="issue-description"]') ||
      document.querySelector('textarea[placeholder*="Write a comment"]') ||
      document.querySelector('textarea[placeholder*="Write or drag"]') ||
      document.querySelector('.ProseMirror') ||
      document.querySelector('[contenteditable="true"][data-placeholder]') ||
      document.querySelector('.gl-editor textarea') ||
      document.querySelector('.md-area textarea') ||
      document.querySelector('.js-vue-markdown-field textarea');
  } else {
    // GitHub issue description selectors
    descriptionField = document.querySelector('textarea[aria-label="Markdown value"]');
  }

  console.log(`[${platform}] Description field found:`, !!descriptionField);

  if (descriptionField) {
    startChecking(descriptionField);
  } else {
    console.log("Description field not found, setting up observer...");

    // Set a timeout to prevent infinite observation
    let observerTimeout;

    const observer = new MutationObserver((mutationsList, obs) => {
      let newDescriptionField;

      if (platform === 'gitlab') {
        newDescriptionField = document.querySelector('#issue-description') ||
          document.querySelector('textarea[name="issue[description]"]') ||
          document.querySelector('.js-gfm-input') ||
          document.querySelector('textarea[data-testid="issue-description"]') ||
          document.querySelector('textarea[placeholder*="Write a comment"]') ||
          document.querySelector('textarea[placeholder*="Write or drag"]') ||
          document.querySelector('.ProseMirror') ||
          document.querySelector('[contenteditable="true"][data-placeholder]') ||
          document.querySelector('.gl-editor textarea') ||
          document.querySelector('.md-area textarea') ||
          document.querySelector('.js-vue-markdown-field textarea');
      } else {
        newDescriptionField = document.querySelector('textarea[aria-label="Markdown value"]');
      }

      if (newDescriptionField) {
        obs.disconnect();
        clearTimeout(observerTimeout);
        startChecking(newDescriptionField);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Stop observing after 10 seconds to prevent memory issues
    observerTimeout = setTimeout(() => {
      observer.disconnect();
      console.log("Observer timeout - field not found");
    }, 10000);
  }
}

function handleEditIssuePage() {
  const platform = detectPlatform();
  let descriptionField;

  if (platform === 'gitlab') {
    // GitLab issue body/comment selectors (multiple editor types)
    descriptionField = document.querySelector('#issue-description') ||
      document.querySelector('textarea[name="issue[description]"]') ||
      document.querySelector('.js-gfm-input') ||
      document.querySelector('#note_note') ||
      document.querySelector('textarea[name="note[note]"]') ||
      document.querySelector('textarea[data-testid="issue-description"]') ||
      document.querySelector('textarea[placeholder*="Write a comment"]') ||
      document.querySelector('textarea[placeholder*="Write or drag"]') ||
      document.querySelector('.ProseMirror') ||
      document.querySelector('[contenteditable="true"][data-placeholder]') ||
      document.querySelector('.gl-editor textarea') ||
      document.querySelector('.md-area textarea') ||
      document.querySelector('.js-vue-markdown-field textarea');
  } else {
    // GitHub issue body/comment selectors
    descriptionField = document.querySelector('textarea[name="issue[body]"]') ||
      document.querySelector('textarea[aria-label="Comment body"]') ||
      document.querySelector('textarea[aria-label="Markdown value"]');
  }

  console.log(`[${platform}] Edit page - Description field found:`, !!descriptionField);

  if (descriptionField && !descriptionField._secretDetectorHandler) {
    startChecking(descriptionField);
  }

  // Set up persistent observer for issue body edits
  if (!window._issueBodyObserver) {
    console.log("Setting up persistent issue body observer...");

    const observer = new MutationObserver((mutationsList) => {
      // Look for newly appeared or modified textareas (supports both platforms)
      let allTextareas;

      if (platform === 'gitlab') {
        allTextareas = document.querySelectorAll('#issue-description, textarea[name="issue[description]"], .js-gfm-input, #note_note, textarea[name="note[note]"], .js-note-text, textarea[placeholder*="Write a comment"], textarea[placeholder*="Write or drag"], .ProseMirror, [contenteditable="true"][data-placeholder], .gl-editor textarea, .md-area textarea, .js-vue-markdown-field textarea');
      } else {
        allTextareas = document.querySelectorAll('textarea[name="issue[body]"], textarea[aria-label="Comment body"], textarea[aria-label="Markdown value"]');
      }

      allTextareas.forEach(textarea => {
        // Only attach if not already monitoring
        if (textarea && !textarea._secretDetectorHandler && textarea.offsetParent !== null) {
          console.log("New or modified issue body textarea detected, starting detection...");
          startChecking(textarea);
        }
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['readonly', 'disabled', 'style', 'class']
    });

    window._issueBodyObserver = observer;
  }

  // Also monitor comment fields on issue pages
  monitorCommentFields();

  // Watch for edit button clicks
  watchForEditButtons();
}

// Watch for edit button clicks on issue pages
function watchForEditButtons() {
  console.log("Setting up edit button watcher...");

  // Use event delegation to catch edit button clicks
  document.body.addEventListener('click', (event) => {
    const target = event.target;

    // Check if it's an edit button or contains edit text
    const isEditButton = target.matches('button[aria-label*="dit" i], button[title*="dit" i], .js-comment-edit-button, [data-edit-text]') ||
      target.closest('button[aria-label*="dit" i], button[title*="dit" i], .js-comment-edit-button, [data-edit-text]');

    if (isEditButton) {
      console.log("Edit button clicked, waiting for textarea to appear...");

      // Wait a bit for the textarea to appear after clicking edit
      setTimeout(() => {
        // Try to find the textarea that appeared
        const allTextareas = document.querySelectorAll('textarea[name="issue[body]"], textarea[aria-label="Comment body"], textarea[aria-label="Markdown value"], textarea[placeholder*="comment" i]');

        allTextareas.forEach(textarea => {
          // Check if this textarea is visible and not already monitored
          if (textarea && !textarea._secretDetectorHandler && textarea.offsetParent !== null) {
            console.log("Found newly editable textarea after edit button click");

            // Check if it's an issue body or a comment
            if (textarea.name === 'issue[body]' || textarea.getAttribute('aria-label') === 'Markdown value') {
              startChecking(textarea);
            } else {
              // It's a comment field
              const existingMonitor = activeCommentMonitors.get(textarea);
              if (!existingMonitor) {
                console.log("Starting monitoring for newly editable comment field");
                const fieldIndex = activeCommentMonitors.size;
                startCheckingCommentField(textarea, fieldIndex);
              }
            }
          }
        });
      }, 300);
    }
  }, true); // Use capture phase to catch the event early
}

// Track all active comment field monitors
const activeCommentMonitors = new Map();

function monitorCommentFields() {
  console.log("Setting up comment field monitoring...");

  const platform = detectPlatform();
  let commentFields;

  if (platform === 'gitlab') {
    // GitLab comment field selectors
    commentFields = document.querySelectorAll('#note_note, textarea[name="note[note]"], .js-note-text, textarea[placeholder*="Write a comment"], textarea[placeholder*="Write or drag"]');
  } else {
    // GitHub comment field selectors
    commentFields = document.querySelectorAll('textarea[placeholder*="Use Markdown to format your comment"], textarea[placeholder*="comment" i]');
  }

  console.log(`[${platform}] Found ${commentFields.length} comment fields`);

  commentFields.forEach((commentField, index) => {
    // Skip if already monitoring this field or if it's not visible
    if (activeCommentMonitors.has(commentField) || commentField.offsetParent === null) {
      console.log(`Comment field ${index} already being monitored or not visible`);
      return;
    }

    console.log(`Starting monitoring for comment field ${index}`);
    startCheckingCommentField(commentField, index);
  });

  // Set up observer to watch for new comment fields (when user clicks "Add a comment", etc.)
  if (!window._commentFieldObserver) {
    const commentObserver = new MutationObserver((mutations) => {
      let newCommentFields;

      if (platform === 'gitlab') {
        newCommentFields = document.querySelectorAll('#note_note, textarea[name="note[note]"], .js-note-text, textarea[placeholder*="Write a comment"], textarea[placeholder*="Write or drag"]');
      } else {
        newCommentFields = document.querySelectorAll('textarea[placeholder*="Use Markdown to format your comment"], textarea[placeholder*="comment" i]');
      }

      newCommentFields.forEach((field, index) => {
        // Only start monitoring if not already monitored and field is visible
        if (!activeCommentMonitors.has(field) && field.offsetParent !== null) {
          console.log(`New comment field detected, starting monitoring for field ${index}`);
          startCheckingCommentField(field, index);
        }
      });
    });

    commentObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style', 'class', 'readonly', 'disabled']
    });

    // Store observer for cleanup
    window._commentFieldObserver = commentObserver;
  }
}

function startCheckingCommentField(commentField, fieldIndex) {
  const indicator = createIndicator();
  const spinner = createSpinner();

  // Store references for this specific field
  const fieldData = {
    indicator,
    spinner,
    tooltip: null,
    debounceTimer: null,
    lastCheckedText: "",
    isChecking: false,
    inputHandler: null,
    highlights: []
  };

  activeCommentMonitors.set(commentField, fieldData);

  // Ensure parent has relative positioning
  commentField.parentElement.style.position = "relative";
  commentField.parentElement.appendChild(indicator);
  commentField.parentElement.appendChild(spinner);

  // Set up highlight tracking for scroll and resize
  setupHighlightTracking(commentField);

  // Tooltip hide timer
  let tooltipHideTimer = null;

  // Function to show tooltip
  const showTooltip = () => {
    // Clear any existing hide timer
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
      tooltipHideTimer = null;
    }

    const tooltipHTML = indicator.getAttribute('data-tooltip');
    if (tooltipHTML && !fieldData.tooltip) {
      fieldData.tooltip = document.createElement("div");
      fieldData.tooltip.className = `secret-detector-tooltip theme-${detectGitHubTheme()}`;
      fieldData.tooltip.innerHTML = tooltipHTML;
      commentField.parentElement.appendChild(fieldData.tooltip);

      // Add event listeners to tooltip to keep it visible when hovering
      fieldData.tooltip.addEventListener("mouseenter", () => {
        if (tooltipHideTimer) {
          clearTimeout(tooltipHideTimer);
          tooltipHideTimer = null;
        }
      });

      fieldData.tooltip.addEventListener("mouseleave", () => {
        hideTooltipWithDelay();
      });
    }
  };

  // Function to hide tooltip with delay
  const hideTooltipWithDelay = () => {
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
    }

    tooltipHideTimer = setTimeout(() => {
      if (fieldData.tooltip) {
        fieldData.tooltip.remove();
        fieldData.tooltip = null;
      }
      tooltipHideTimer = null;
    }, 300); // 300ms delay before hiding
  };

  // Show tooltip on hover
  indicator.addEventListener("mouseenter", showTooltip);

  // Hide tooltip on mouse leave with delay
  indicator.addEventListener("mouseleave", hideTooltipWithDelay);

  // Perform an immediate check if there's existing content
  const initialText = getElementText(commentField).trim();
  if (initialText.length > 0) {
    fieldData.lastCheckedText = initialText;
    checkCommentField(commentField, fieldData);
  }

  // Debounced input listener
  const handleInput = () => {
    const currentText = getElementText(commentField).trim();

    // Clear existing timer
    if (fieldData.debounceTimer) {
      clearTimeout(fieldData.debounceTimer);
    }

    // Check if any highlighted strings no longer exist in the text
    if (commentField._highlights && commentField._highlights.length > 0) {
      const stillValid = commentField._highlights.filter(h => {
        const text = getElementText(commentField);
        return text.includes(h.secretString);
      });

      // If some highlights are no longer valid, remove all and let backend re-check
      if (stillValid.length !== commentField._highlights.length) {
        removeHighlights(commentField);
      }
    }

    // Only check if text has actually changed
    if (currentText === fieldData.lastCheckedText) {
      return;
    }

    // Set up new debounced check
    fieldData.debounceTimer = setTimeout(() => {
      console.log(`Running debounced check for comment field ${fieldIndex}...`);
      fieldData.lastCheckedText = currentText;
      checkCommentField(commentField, fieldData);
    }, DEBOUNCE_DELAY_MS);
  };

  // Attach input listener
  commentField.addEventListener('input', handleInput);

  // Attach paste listener - triggers IMMEDIATE check after paste content is inserted (GitLab fix)
  commentField.addEventListener('paste', () => {
    // Wait for paste content to be inserted, then force immediate check
    setTimeout(() => {
      const currentText = getElementText(commentField).trim();
      if (currentText !== fieldData.lastCheckedText && currentText.length > 0) {
        console.log('[IssueGuard] Paste detected in comment field, triggering immediate check...');
        // Clear any pending debounce timer
        if (fieldData.debounceTimer) {
          clearTimeout(fieldData.debounceTimer);
          fieldData.debounceTimer = null;
        }
        fieldData.lastCheckedText = currentText;
        checkCommentField(commentField, fieldData);
      }
    }, 100);
  });

  fieldData.inputHandler = handleInput;

  // Watch for field removal
  const removalObserver = new MutationObserver((mutations) => {
    if (!document.contains(commentField)) {
      console.log(`Comment field ${fieldIndex} removed, cleaning up...`);
      cleanupCommentField(commentField);
      removalObserver.disconnect();
    }
  });

  removalObserver.observe(document.body, { childList: true, subtree: true });
  fieldData.removalObserver = removalObserver;
}

async function checkCommentField(commentField, fieldData) {
  // Prevent multiple simultaneous checks
  if (fieldData.isChecking) {
    console.log("Check already in progress for this comment field, skipping...");
    return;
  }

  fieldData.isChecking = true;
  const text = getElementText(commentField).trim();

  try {
    fieldData.spinner.style.display = "block";
    const response = await checkForSecrets(text);
    fieldData.spinner.style.display = "none";

    console.log("Response received for comment field:", response);

    if (response && response.success) {
      if (response.secrets_detected > 0) {
        // Red indicator - secrets detected
        fieldData.indicator.innerHTML = "⚠️";
        fieldData.indicator.style.backgroundColor = "#f44336";
        fieldData.indicator.style.border = "3px solid #d32f2f";
        fieldData.indicator.style.boxShadow = "0 4px 16px rgba(244, 67, 54, 0.3)";
        fieldData.indicator.style.animation = "pulseRed 2s infinite";

        // Filter to only secrets (not safe candidates)
        const secretCandidates = response.all_candidates.filter(c => c.is_secret);

        // Remove candidates that are substrings of other candidates
        const filteredSecrets = secretCandidates.filter((candidate, index, arr) => {
          return !arr.some((other, otherIndex) => {
            if (index === otherIndex) return false;
            return other.candidate_string.includes(candidate.candidate_string) &&
              other.candidate_string !== candidate.candidate_string;
          });
        });

        // Highlight the secret strings in the textarea
        const secretStrings = filteredSecrets.map(s => s.candidate_string);
        updateHighlightPositions(commentField, secretStrings);

        // Create detailed tooltip content
        const itemStyles = getTooltipItemStyles();
        let tooltipHTML = `<div style="font-weight: 700; margin-bottom: 12px; font-size: 15px;">⚠️ Secrets Detected</div>`;

        filteredSecrets.forEach((candidate, i) => {
          tooltipHTML += `<div style="margin: 10px 0; padding: 10px; background: ${itemStyles.background}; border-radius: 8px; border-left: ${itemStyles.borderLeft};">`;
          tooltipHTML += `<span class="secret-badge theme-${detectGitHubTheme()}">🔴 SECRET</span>`;
          tooltipHTML += `<div style="margin-top: 6px; font-size: 12px; font-weight: 600; word-break: break-all;">${escapeHtml(candidate.candidate_string.substring(0, 70))}${candidate.candidate_string.length > 70 ? '...' : ''}</div>`;
          tooltipHTML += `<div style="margin-top: 4px; font-size: 11px; opacity: 0.8;">Type: ${escapeHtml(candidate.secret_type)}</div>`;
          tooltipHTML += `</div>`;
        });

        fieldData.indicator.setAttribute('data-tooltip', tooltipHTML);
      } else {
        // Green indicator - no secrets
        // Remove any existing highlights
        removeHighlights(commentField);

        fieldData.indicator.innerHTML = "✅";
        fieldData.indicator.style.backgroundColor = "#4caf50";
        fieldData.indicator.style.border = "3px solid #388e3c";
        fieldData.indicator.style.boxShadow = "0 4px 16px rgba(76, 175, 80, 0.3)";
        fieldData.indicator.style.animation = "pulse 2s infinite";

        const tooltipHTML = `<div style="font-weight: 700; font-size: 15px;">✅ You're Safe!</div><div style="margin-top: 8px; opacity: 0.95; font-size: 13px;">No secrets detected in your comment</div>`;
        fieldData.indicator.setAttribute('data-tooltip', tooltipHTML);
      }
    } else {
      // Yellow indicator - error or invalid response
      fieldData.indicator.innerHTML = "⚠️";
      fieldData.indicator.style.backgroundColor = "#ff9800";
      fieldData.indicator.style.border = "3px solid #f57c00";
      fieldData.indicator.style.boxShadow = "0 4px 16px rgba(255, 152, 0, 0.3)";
      fieldData.indicator.style.animation = "pulse 2s infinite";

      const tooltipHTML = `<div style="font-weight: 700; font-size: 15px;">⚠️ Connection Error</div><div style="margin-top: 8px; opacity: 0.95; font-size: 13px;">Unable to check for secrets. Please ensure the API is running.</div>`;
      fieldData.indicator.setAttribute('data-tooltip', tooltipHTML);
    }
  } catch (error) {
    console.error("Error in checkCommentField:", error);
    fieldData.spinner.style.display = "none";

    fieldData.indicator.innerHTML = "❌";
    fieldData.indicator.style.backgroundColor = "#ff9800";
    fieldData.indicator.style.border = "3px solid #f57c00";
    fieldData.indicator.style.boxShadow = "0 4px 16px rgba(255, 152, 0, 0.3)";

    const tooltipHTML = `<div style="font-weight: 700; font-size: 15px;">❌ Error</div><div style="margin-top: 8px; opacity: 0.95; font-size: 13px;">An error occurred while checking</div>`;
    fieldData.indicator.setAttribute('data-tooltip', tooltipHTML);
  } finally {
    fieldData.isChecking = false;
  }
}

function cleanupCommentField(commentField) {
  const fieldData = activeCommentMonitors.get(commentField);

  if (!fieldData) return;

  // Clear debounce timer
  if (fieldData.debounceTimer) {
    clearTimeout(fieldData.debounceTimer);
  }

  // Remove event listener
  if (fieldData.inputHandler) {
    commentField.removeEventListener('input', fieldData.inputHandler);
  }

  // Remove highlights
  removeHighlights(commentField);

  // Clean up resize observer
  if (commentField._resizeObserver) {
    commentField._resizeObserver.disconnect();
    delete commentField._resizeObserver;
  }

  // Remove DOM elements
  if (fieldData.indicator && fieldData.indicator.parentElement) {
    fieldData.indicator.remove();
  }

  if (fieldData.spinner && fieldData.spinner.parentElement) {
    fieldData.spinner.remove();
  }

  if (fieldData.tooltip && fieldData.tooltip.parentElement) {
    fieldData.tooltip.remove();
  }

  // Disconnect removal observer
  if (fieldData.removalObserver) {
    fieldData.removalObserver.disconnect();
  }

  // Remove from active monitors
  activeCommentMonitors.delete(commentField);
}

function cleanupAllCommentFields() {
  console.log("Cleaning up all comment field monitors...");

  // Cleanup all active monitors
  activeCommentMonitors.forEach((fieldData, commentField) => {
    cleanupCommentField(commentField);
  });

  // Clear the map
  activeCommentMonitors.clear();

  // Disconnect the comment observer
  if (window._commentFieldObserver) {
    window._commentFieldObserver.disconnect();
    window._commentFieldObserver = null;
  }

  // Disconnect the issue body observer
  if (window._issueBodyObserver) {
    window._issueBodyObserver.disconnect();
    window._issueBodyObserver = null;
  }
}

function checkCurrentPage() {
  const pathname = window.location.pathname;
  const platform = detectPlatform();

  // GitHub URL patterns
  const githubNewIssuePattern = /\/[^/]+\/[^/]+\/issues\/new\/?$/;
  const githubEditIssuePattern = /\/[^/]+\/[^/]+\/issues\/\d+$/;

  // GitLab URL patterns (uses /-/ in the path)
  // GitLab new issue can be accessed via /issues/new OR via modal from /issues list page
  const gitlabNewIssuePattern = /-\/issues\/new\/?$/;
  const gitlabEditIssuePattern = /-\/issues\/\d+$/;
  const gitlabIssuesListPattern = /-\/issues\/?$/;  // Issues list page (can have new issue modal)

  let isNewIssuePage = false;
  let isEditIssuePage = false;

  if (platform === 'gitlab') {
    isNewIssuePage = gitlabNewIssuePattern.test(pathname) || gitlabIssuesListPattern.test(pathname);
    isEditIssuePage = gitlabEditIssuePattern.test(pathname);
  } else {
    isNewIssuePage = githubNewIssuePattern.test(pathname);
    isEditIssuePage = githubEditIssuePattern.test(pathname);
  }

  console.log(`Platform: ${platform}, Path: ${pathname}, IsNew: ${isNewIssuePage}, IsEdit: ${isEditIssuePage}`);

  if (isNewIssuePage) {
    console.log("On new issue page, starting detection");
    // Small delay to ensure DOM is ready
    setTimeout(() => {
      handleNewIssuePage();
    }, 500);
  } else if (isEditIssuePage) {
    console.log("On issue view/edit page, starting detection");
    // Small delay to ensure DOM is ready
    setTimeout(() => {
      handleEditIssuePage();
    }, 500);
  } else {
    console.log("Not on issue creation or edit page");
    cleanupPreviousElements();
  }
}

function init() {
  console.log("Secret Detector Extension initialized");

  // Check initial page load
  checkCurrentPage();

  // Modern approach: Use both popstate and custom event for SPAs
  let lastUrl = location.href;

  // Listen for URL changes (works with GitHub's SPA navigation)
  const urlObserver = new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
      lastUrl = url;
      console.log("URL changed to:", url);
      checkCurrentPage();
    }
  });

  urlObserver.observe(document, { subtree: true, childList: true });

  // Also listen for popstate (browser back/forward)
  window.addEventListener('popstate', () => {
    console.log("Popstate event detected");
    setTimeout(() => checkCurrentPage(), 100);
  });

  // Listen for pushState/replaceState (SPA navigation)
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;

  history.pushState = function () {
    originalPushState.apply(this, arguments);
    console.log("pushState detected");
    setTimeout(() => checkCurrentPage(), 100);
  };

  history.replaceState = function () {
    originalReplaceState.apply(this, arguments);
    console.log("replaceState detected");
    setTimeout(() => checkCurrentPage(), 100);
  };
}

// ============================================================================
// GITLAB MODAL WATCHER
// ============================================================================
// Watch for GitLab modal open/close/reopen to reinitialize the extension
// This fixes the issue where closing and reopening the new issue modal
// causes the extension functionality to disappear
function setupGitLabModalWatcher() {
  if (detectPlatform() !== 'gitlab') return;

  console.log('[IssueGuard] Setting up GitLab modal watcher...');

  // Debounce timer to prevent rapid re-initialization
  let initDebounceTimer = null;
  let lastInitTime = 0;
  const MIN_INIT_INTERVAL = 500; // Minimum 500ms between initializations

  // Function to safely initialize the extension for GitLab
  const safeInitialize = () => {
    const now = Date.now();

    // Prevent too-frequent reinitializations
    if (now - lastInitTime < MIN_INIT_INTERVAL) {
      console.log('[IssueGuard] Skipping init - too soon after last init');
      return;
    }

    // Check if ProseMirror editor exists and needs monitoring
    // IMPORTANT: Check for VISIBILITY to ensure we don't attach to hidden/closed editors
    const allProseMirrors = document.querySelectorAll('.ProseMirror');
    const allDescriptions = document.querySelectorAll('#issue-description, textarea[name="issue[description]"], .js-gfm-input');

    let editorField = null;

    // Find first visible ProseMirror
    for (const el of allProseMirrors) {
      if (el.offsetParent !== null) {
        editorField = el;
        break;
      }
    }

    // If no ProseMirror, check descriptions
    if (!editorField) {
      for (const el of allDescriptions) {
        if (el.offsetParent !== null) {
          editorField = el;
          break;
        }
      }
    }

    if (editorField) {
      // Check if already being monitored AND indicator exists
      // If indicator is gone (modal was closed/reopened), we need to reinitialize
      const existingIndicator = editorField.parentElement?.querySelector('.secret-detector-indicator');
      if (editorField._secretDetectorHandler && existingIndicator) {
        console.log('[IssueGuard] Editor already being monitored with indicator present');

        // Even if monitored, check if there's content that needs scanning in case it was just restored
        const text = getElementText(editorField).trim();
        if (text.length > 0 && text !== lastCheckedText) {
          console.log('[IssueGuard] Content changed/restored, forcing scan...');
          // Force reset lastCheckedText to ensure scan runs
          lastCheckedText = "";
          const spinner = editorField.parentElement?.querySelector('.secret-detector-spinner');
          if (spinner) spinner.style.display = "block";
          checkDescription(editorField, existingIndicator, spinner);
        }
        return;
      }

      console.log('[IssueGuard] Found visible editor, initializing...');
      lastInitTime = now;

      // Reset global state to ensure clean start
      lastCheckedText = "";

      // Start monitoring - startChecking will handle cleanup if needed
      startChecking(editorField);

      // POLLING: Schedule multiple checks to catch content that loads asynchronously
      // This is critical for when GitLab restores draft content after the editor appears
      let checkCount = 0;
      const maxChecks = 5;

      const pollContent = () => {
        checkCount++;
        const text = getElementText(editorField).trim();
        console.log(`[IssueGuard] Polling check ${checkCount}/${maxChecks}: length=${text.length}`);

        if (text.length > 0) {
          // If we have text and haven't scanned it yet (or last scan was empty)
          if (text !== lastCheckedText) {
            console.log('[IssueGuard] Polling found new content, triggering scan...');
            const indicator = editorField.parentElement?.querySelector('.secret-detector-indicator');
            const spinner = editorField.parentElement?.querySelector('.secret-detector-spinner');

            if (indicator && spinner) {
              spinner.style.display = "block";
              lastCheckedText = text; // Update this BEFORE calling to prevent loops if logic changes
              checkDescription(editorField, indicator, spinner);
            }
            return; // Stop polling if successful
          }
        }

        // Continue polling if no text found or text hasn't changed
        if (checkCount < maxChecks) {
          setTimeout(pollContent, 500);
        }
      };

      // Start polling after a short delay
      setTimeout(pollContent, 500);
    }
  };

  // Watch for new modals/drawers being added that contain editors
  const modalObserver = new MutationObserver((mutations) => {
    // Only process if we're actually on a GitLab issues page
    const pathname = window.location.pathname;
    if (!pathname.includes('issues')) return;

    let shouldCheck = false;

    for (const mutation of mutations) {
      // Check for added nodes that might contain an editor
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          // Check if this node or its children contain editor elements
          const hasProseMirror = node.classList?.contains('ProseMirror') ||
            node.querySelector?.('.ProseMirror');
          const hasIssueForm = node.querySelector?.('#issue-description') ||
            node.querySelector?.('textarea[name="issue[description]"]') ||
            node.querySelector?.('.js-gfm-input') ||
            node.classList?.contains('issue-form') ||
            node.classList?.contains('gl-modal') ||
            node.classList?.contains('gl-drawer');

          if (hasProseMirror || hasIssueForm) {
            shouldCheck = true;
            break;
          }
        }
      }
      if (shouldCheck) break;
    }

    if (shouldCheck) {
      console.log('[IssueGuard] Modal/editor mutation detected...');

      // Debounce the initialization
      if (initDebounceTimer) {
        clearTimeout(initDebounceTimer);
      }

      initDebounceTimer = setTimeout(() => {
        safeInitialize();
      }, 300);
    }
  });

  modalObserver.observe(document.body, {
    childList: true,
    subtree: true
  });

  // Store reference for potential cleanup
  window._gitlabModalObserver = modalObserver;

  // Also check immediately in case modal is already open
  setTimeout(safeInitialize, 500);
}


// ============================================================================
// THEME CHANGE OBSERVER
// ============================================================================
// Watch for GitHub theme changes and update tooltip themes dynamically
function setupThemeObserver() {
  const themeObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' &&
        (mutation.attributeName === 'data-color-mode' ||
          mutation.attributeName === 'data-theme' ||
          mutation.attributeName === 'class')) {
        console.log('GitHub theme changed, updating tooltips...');

        // Update all existing tooltips
        const currentTheme = detectGitHubTheme();

        // Update main tooltip if exists
        if (currentTooltip) {
          currentTooltip.className = `secret-detector-tooltip theme-${currentTheme}`;
        }

        // Update all comment field tooltips
        activeCommentMonitors.forEach((fieldData) => {
          if (fieldData.tooltip) {
            fieldData.tooltip.className = `secret-detector-tooltip theme-${currentTheme}`;
          }
        });
      }
    });
  });

  // Observe both html and body elements for theme changes
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-color-mode', 'data-theme', 'class']
  });

  themeObserver.observe(document.body, {
    attributes: true,
    attributeFilter: ['data-color-mode', 'data-theme', 'class']
  });

  console.log('Theme observer initialized');
}

// Cleanup when extension is unloaded
window.addEventListener('beforeunload', () => {
  cleanupPreviousElements();
});

init();
setupThemeObserver();
setupGitLabModalWatcher();
