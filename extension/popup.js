// AI Slop 检测器 — 弹窗逻辑 v1.2

const MAX_FREE = 3;
let currentState = 'idle';
let abortController = null;

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
    return { usageCount: 0, activated: false, serverUrl: 'http://localhost:8766' };
  }
}

async function getServerUrl() {
  const s = await getState();
  return s.serverUrl || 'http://localhost:8766';
}

async function getUsageInfo() {
  const s = await getState();
  return {
    used: s.usageCount ?? 0,
    remaining: Math.max(0, MAX_FREE - (s.usageCount ?? 0)),
    activated: s.activated ?? false,
  };
}

async function afterAnalysis() {
  try {
    const r = await chrome.runtime.sendMessage({ action: 'incrementUsage' });
    return r?.usageCount ?? 0;
  } catch (e) { return 0; }
}

async function setActivated() {
  try { await chrome.runtime.sendMessage({ action: 'activate' }); } catch (e) {}
}

function showState(name) {
  document.querySelectorAll('.state').forEach(el => el.classList.remove('active'));
  const t = $(`state-${name}`);
  if (t) { t.classList.add('active'); currentState = name; }
}

function setStatus(msg, isError) {
  const el = $('status-msg');
  if (el) { el.textContent = msg; el.style.color = isError ? 'var(--red)' : 'var(--text-muted)'; }
}

// ── 服务器检查 ──

async function checkServer() {
  const indicator = $('server-indicator');
  const url = await getServerUrl();
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 3000);
    const r = await fetch(`${url}/api/status`, { signal: ctrl.signal });
    clearTimeout(t);
    if (r.ok) {
      if (indicator) { indicator.textContent = '服务器：已连接'; indicator.style.color = 'var(--green)'; }
      return true;
    }
  } catch (e) {}
  if (indicator) { indicator.textContent = '服务器：离线（请先运行 python server.py）'; indicator.style.color = 'var(--red)'; }
  return false;
}

// ── 预填 URL ──

async function prefillRepoUrl() {
  try {
    const r = await chrome.runtime.sendMessage({ action: 'getActiveTabUrl' });
    const input = $('repo-url');
    if (input && r?.url) input.value = r.url;
  } catch (e) {}
}

// ── 分析 ──

async function startAnalysis() {
  const url = ($('repo-url').value || '').trim();

  if (!url) { setStatus('请输入 GitHub 仓库地址，如 https://github.com/user/repo', true); return; }
  if (!url.includes('github.com')) { setStatus('仅支持 GitHub 仓库', true); return; }

  const { remaining, activated } = await getUsageInfo();
  if (!activated && remaining <= 0) { showState('paywall'); return; }

  const online = await checkServer();
  if (!online) {
    showState('error');
    $('error-title').textContent = '无法连接服务器';
    $('error-msg').textContent = '请先启动本地服务器：python server.py';
    return;
  }

  showState('loading');
  $('loading-status').textContent = '正在克隆仓库...';
  setStatus('');

  abortController = new AbortController();
  const serverUrl = await getServerUrl();

  const progressTimer = setTimeout(() => {
    $('loading-status').textContent = '正在扫描代码...';
  }, 3000);

  try {
    const timeoutId = setTimeout(() => abortController.abort(), 30000);
    const resp = await fetch(`${serverUrl}/api/slop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_url: url, branch: 'main' }),
      signal: abortController.signal,
    });
    clearTimeout(timeoutId);
    clearTimeout(progressTimer);

    if (!resp.ok) throw new Error((await resp.text()) || `服务器返回 ${resp.status}`);

    const report = await resp.json();

    if (!activated) { await afterAnalysis(); }
    const usageInfo = await getUsageInfo();

    renderResults(report, url, usageInfo);
    showState('results');
  } catch (e) {
    clearTimeout(progressTimer);
    if (e.name === 'AbortError') {
      showState('idle');
      setStatus('分析超时（仓库太大？）', true);
    } else {
      $('error-title').textContent = '分析失败';
      $('error-msg').textContent = e.message || '未知错误';
      showState('error');
    }
  } finally {
    abortController = null;
  }
}

function cancelAnalysis() {
  if (abortController) { abortController.abort(); abortController = null; }
}

// ── 渲染结果 ──

function renderResults(report, repoUrl, usageInfo) {
  const repoName = repoUrl.replace('https://github.com/', '').replace(/\/$/, '');
  $('result-repo-name').textContent = repoName;

  const score = report.score;
  const verdict = report.verdict;
  const verdictLabels = { '干净': '干净', '可疑': '可疑', '极可能 AI 生成': '极可能 AI 生成' };
  const verdictCssMap = { '干净': 'clean', '可疑': 'suspicious', '极可能 AI 生成': 'slop' };
  const cssKey = verdictCssMap[verdict] || 'suspicious';
  const scoreColor = score >= 80 ? 'var(--green)' : score >= 40 ? 'var(--amber)' : 'var(--red)';

  $('result-verdict-text').textContent = `发现 ${report.red_flags.length} 个红旗信号`;

  // 评分卡
  $('score-card').innerHTML = `
    <div class="score-header">
      <span class="score-number" style="color:${scoreColor}">${score}</span>
      <div class="score-right">
        <span class="score-verdict verdict-${cssKey}">${verdictLabels[verdict]}</span>
        <div style="margin-top:4px;font-size:10px;color:var(--text-muted)">满分 100</div>
      </div>
    </div>
    <div class="score-bar">
      <div class="score-bar-fill fill-${cssKey}" style="width:${score}%"></div>
    </div>
    <div class="score-stats">
      <span>文件：<strong>${report.stats.total_source_files ?? '?'}</strong></span>
      <span>提交：<strong>${report.stats.total_commits ?? '?'}</strong></span>
      <span>贡献者：<strong>${report.stats.contributors ?? '?'}</strong></span>
    </div>
  `;

  // 红旗信号
  const flagsList = $('flags-list');
  if (report.red_flags && report.red_flags.length > 0) {
    let html = '<div class="flags-title">红旗信号</div>';
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

  // 改进建议
  const recs = $('recommendations');
  if (report.recommendations && report.recommendations.length > 0) {
    let html = '<div class="recs-title">改进建议</div>';
    for (const rec of report.recommendations) {
      html += `<div class="rec-item">${escapeHtml(rec)}</div>`;
    }
    recs.innerHTML = html;
  } else {
    recs.innerHTML = '';
  }

  // 使用次数
  const counter = $('usage-counter-2');
  if (counter) {
    if (usageInfo.activated) {
      counter.innerHTML = '无限次（已激活）';
    } else {
      counter.innerHTML = `免费次数：<strong>${usageInfo.remaining}</strong> 次`;
    }
  }
}

// ── 激活 ──

async function activateCode() {
  const code = ($('activation-code').value || '').trim();
  const statusEl = $('activate-status');
  if (!code) { statusEl.textContent = '请输入激活码'; return; }

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
        setStatus('激活成功！无限次已解锁', false);
      }, 1500);
    } else {
      statusEl.style.color = 'var(--red)';
      statusEl.textContent = data.message;
    }
  } catch (e) {
    statusEl.style.color = 'var(--red)';
    statusEl.textContent = '连接失败，服务器在跑吗？';
  }
}

// ── 初始化 ──

async function init() {
  try {
    await prefillRepoUrl();
    await checkServer();
    const { remaining, activated } = await getUsageInfo();
    if (activated) {
      $('usage-counter').innerHTML = '无限次 <strong>（已激活）</strong>';
    } else {
      $('remaining-count').textContent = remaining;
    }
    setTimeout(() => { const input = $('repo-url'); if (input) input.focus(); }, 150);
  } catch (e) {}
}

document.addEventListener('DOMContentLoaded', init);

// Enter 快捷键
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && currentState === 'idle') { e.preventDefault(); startAnalysis(); }
  if (e.key === 'Enter' && currentState === 'paywall') { e.preventDefault(); activateCode(); }
});
