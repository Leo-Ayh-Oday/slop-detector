// AI Slop Detector — Popup Logic v1.1

const MAX_FREE = 3;
let currentState = 'idle';
let abortController = null;
let serverReachable = false;

// ── Helpers ──

function $(id) { return document.getElementById(id); }

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

async function getState() {
  try {
    return await chrome.runtime.sendMessage({ action: 'getState' });
  } catch (e) {
    console.error('getState failed:', e);
    return { usageCount: 0, activated: false, serverUrl: 'http://localhost:8766' };
  }
}

async function getServerUrl() {
  const state = await getState();
  return state.serverUrl || 'http://localhost:8766';
}

async function getUsageInfo() {
  const state = await getState();
  return {
    used: state.usageCount ?? 0,
    remaining: Math.max(0, MAX_FREE - (state.usageCount ?? 0)),
    activated: state.activated ?? false,
  };
}

async function afterAnalysis() {
  try {
    const resp = await chrome.runtime.sendMessage({ action: 'incrementUsage' });
    return resp?.usageCount ?? 0;
  } catch (e) {
    return 0;
  }
}

async function setActivated() {
  try {
    await chrome.runtime.sendMessage({ action: 'activate' });
  } catch (e) {
    console.error('activate failed:', e);
  }
}

// ── UI ──

function showState(stateName) {
  document.querySelectorAll('.state').forEach(el => el.classList.remove('active'));
  const target = $(`state-${stateName}`);
  if (target) {
    target.classList.add('active');
    currentState = stateName;
  }
}

function setStatus(msg, isError) {
  const el = $('status-msg');
  if (el) {
    el.textContent = msg;
    el.style.color = isError ? 'var(--red)' : 'var(--text-muted)';
  }
}

// ── Server check ──

async function checkServer() {
  const indicator = $('server-indicator');
  const serverUrl = await getServerUrl();
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const resp = await fetch(`${serverUrl}/api/status`, { signal: controller.signal });
    clearTimeout(timer);
    if (resp.ok) {
      serverReachable = true;
      if (indicator) {
        indicator.textContent = 'Server: online';
        indicator.style.color = 'var(--green)';
      }
      return true;
    }
  } catch (e) {
    // offline
  }
  serverReachable = false;
  if (indicator) {
    indicator.textContent = 'Server: offline (run python server.py)';
    indicator.style.color = 'var(--red)';
  }
  return false;
}

// ── Pre-fill URL ──

async function prefillRepoUrl() {
  try {
    const resp = await chrome.runtime.sendMessage({ action: 'getActiveTabUrl' });
    const input = $('repo-url');
    if (input && resp?.url) {
      input.value = resp.url;
    }
  } catch (e) {
    console.error('prefillRepoUrl failed:', e);
  }
}

// ── Analysis ──

async function startAnalysis() {
  console.log('startAnalysis called');
  const url = ($('repo-url').value || '').trim();

  if (!url) {
    // Try to manually enter URL
    setStatus('Enter a GitHub repo URL (e.g. https://github.com/user/repo)', true);
    return;
  }

  if (!url.includes('github.com')) {
    setStatus('Only GitHub repositories are supported.', true);
    return;
  }

  // Check free tier
  const { remaining, activated } = await getUsageInfo();
  console.log('Usage:', { remaining, activated });
  if (!activated && remaining <= 0) {
    showState('paywall');
    return;
  }

  // Check server
  const online = await checkServer();
  console.log('Server online:', online);
  if (!online) {
    showState('error');
    $('error-title').textContent = 'Server Unreachable';
    $('error-msg').textContent = 'Cannot connect to localhost:8766. Make sure the server is running.';
    return;
  }

  showState('loading');
  $('loading-status').textContent = 'Cloning repository...';
  setStatus('');

  abortController = new AbortController();
  const serverUrl = await getServerUrl();

  // Progress simulation
  const progressTimer = setTimeout(() => {
    $('loading-status').textContent = 'Scanning files for slop patterns...';
  }, 3000);

  try {
    // Manual timeout wrapper (compatible with older Chrome/Edge)
    const timeoutId = setTimeout(() => abortController.abort(), 25000);

    const resp = await fetch(`${serverUrl}/api/slop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_url: url, branch: 'main' }),
      signal: abortController.signal,
    });

    clearTimeout(timeoutId);
    clearTimeout(progressTimer);

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(errText || `Server returned ${resp.status}`);
    }

    const report = await resp.json();
    console.log('Report:', report);

    // Increment usage
    let usageInfo;
    if (!activated) {
      await afterAnalysis();
      usageInfo = await getUsageInfo();
    } else {
      usageInfo = await getUsageInfo();
    }

    renderResults(report, url, usageInfo);
    showState('results');
  } catch (e) {
    clearTimeout(progressTimer);
    if (e.name === 'AbortError') {
      showState('idle');
      setStatus('Analysis timed out (repo too large?)', true);
    } else {
      console.error('Analysis error:', e);
      $('error-title').textContent = 'Analysis Failed';
      $('error-msg').textContent = e.message || 'Unknown error';
      showState('error');
    }
  } finally {
    abortController = null;
  }
}

function cancelAnalysis() {
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
}

// ── Render results ──

function renderResults(report, repoUrl, usageInfo) {
  const repoName = repoUrl.replace('https://github.com/', '').replace(/\/$/, '');
  $('result-repo-name').textContent = repoName;

  const score = report.score;
  const verdict = report.verdict;
  const verdictLabels = { clean: 'Clean', suspicious: 'Suspicious', likely_slop: 'Likely AI Slop' };
  const verdictClasses = { clean: 'verdict-clean', suspicious: 'verdict-suspicious', likely_slop: 'verdict-slop' };
  const fillClasses = { clean: 'fill-clean', suspicious: 'fill-suspicious', likely_slop: 'fill-slop' };
  const scoreColor = score >= 80 ? 'var(--green)' : score >= 40 ? 'var(--amber)' : 'var(--red)';

  $('result-verdict-text').textContent = `${report.red_flags.length} red flag(s) detected`;

  // Score card
  $('score-card').innerHTML = `
    <div class="score-header">
      <span class="score-number" style="color:${scoreColor}">${score}</span>
      <div class="score-label">
        <span class="score-verdict ${verdictClasses[verdict]}">${verdictLabels[verdict]}</span>
        <div style="margin-top:4px">out of 100</div>
      </div>
    </div>
    <div class="score-bar">
      <div class="score-bar-fill ${fillClasses[verdict]}" style="width:${score}%"></div>
    </div>
    <div class="score-stats">
      <span>Files: ${report.stats.total_source_files ?? '?'}</span>
      <span>Commits: ${report.stats.total_commits ?? '?'}</span>
      <span>Contributors: ${report.stats.contributors ?? '?'}</span>
    </div>
  `;

  // Red flags
  const flagsList = $('flags-list');
  if (report.red_flags && report.red_flags.length > 0) {
    let html = '<div class="flags-title">Red Flags</div>';
    for (const flag of report.red_flags) {
      const evidenceText = (flag.evidence || []).map(escapeHtml).join('\n');
      html += `
        <div class="flag-item" title="${escapeHtml(evidenceText)}">
          <span class="flag-severity sev-${flag.severity}"></span>
          <span class="flag-name">${escapeHtml(flag.label)}</span>
          <span class="flag-score">${flag.score}/10</span>
        </div>
      `;
    }
    flagsList.innerHTML = html;
  } else {
    flagsList.innerHTML = '';
  }

  // Recommendations
  const recs = $('recommendations');
  if (report.recommendations && report.recommendations.length > 0) {
    let html = '<div class="recs-title">Recommendations</div>';
    for (const rec of report.recommendations) {
      html += `<div class="rec-item">${escapeHtml(rec)}</div>`;
    }
    recs.innerHTML = html;
  } else {
    recs.innerHTML = '';
  }

  // Usage counter
  const counter = $('usage-counter-2');
  if (counter) {
    if (!usageInfo.activated) {
      counter.innerHTML = `Free analyses: <strong>${usageInfo.remaining}</strong> remaining`;
    } else {
      counter.innerHTML = 'Unlimited analyses (activated)';
    }
  }
}

// ── Activation ──

async function activateCode() {
  const code = ($('activation-code').value || '').trim();
  const statusEl = $('activate-status');

  if (!code) {
    statusEl.textContent = 'Enter an activation code.';
    return;
  }

  const serverUrl = await getServerUrl();
  try {
    const resp = await fetch(`${serverUrl}/api/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activation_code: code }),
    });
    const data = await resp.json();
    if (data.valid) {
      await setActivated();
      statusEl.style.color = 'var(--green)';
      statusEl.textContent = data.message;
      setTimeout(() => {
        showState('idle');
        setStatus('Activated! Unlimited analyses unlocked.', false);
      }, 1500);
    } else {
      statusEl.style.color = 'var(--red)';
      statusEl.textContent = data.message;
    }
  } catch (e) {
    statusEl.style.color = 'var(--red)';
    statusEl.textContent = 'Cannot reach server. Is it running?';
  }
}

// ── Init ──

async function init() {
  console.log('AI Slop Detector popup init');
  try {
    await prefillRepoUrl();
    await checkServer();

    const { remaining, activated } = await getUsageInfo();
    if (activated) {
      $('usage-counter').innerHTML = 'Unlimited analyses <strong>(activated)</strong>';
    } else {
      $('remaining-count').textContent = remaining;
    }

    // Focus input
    setTimeout(() => {
      const input = $('repo-url');
      if (input) input.focus();
    }, 150);

    console.log('Init complete');
  } catch (e) {
    console.error('Init error:', e);
  }
}

document.addEventListener('DOMContentLoaded', init);

// Enter key handlers
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && currentState === 'idle') {
    e.preventDefault();
    startAnalysis();
  } else if (e.key === 'Enter' && currentState === 'paywall') {
    e.preventDefault();
    activateCode();
  }
});
