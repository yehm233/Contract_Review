const API_BASE = "http://172.27.3.6:8080";

const $ = id => document.getElementById(id);

// OnlyOffice plugin init
window.Asc && window.Asc.plugin && window.Asc.plugin.init && window.Asc.plugin.init();

// Review button
$('startBtn').addEventListener('click', async () => {
  const text = $('contractText').value.trim();
  if (!text) return;

  const btn = $('startBtn');
  const status = $('statusMsg');
  const result = $('result');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 审查中...';
  status.textContent = 'AI 正在分析合同，请稍候...';
  result.innerHTML = '';

  try {
    const contractId = 'plugin-' + Date.now();
    const resp = await fetch(`${API_BASE}/api/review/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contract_id: contractId, contract_text: text }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || '请求失败');
    }

    const data = await resp.json();
    status.textContent = '审查完成';
    renderFindings(data);
  } catch (e) {
    status.textContent = '';
    result.innerHTML = `<div style="color:#b91c1c;font-size:12px;padding:10px;background:#fef2f2;border-radius:8px;border:1px solid #fecaca;">&#9888; ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>&#128269;</span> 开始审查';
  }
});

function renderFindings(payload) {
  const root = $('result');
  root.innerHTML = '';

  // Summary
  const summary = payload.summary || {};
  const overallRisk = (summary.overall_risk || 'LOW').toUpperCase();
  const findings = payload.findings || [];

  const summaryBlock = document.createElement('div');
  summaryBlock.className = 'summary-block';
  summaryBlock.innerHTML = `
    <div class="risk-overall">
      <span style="font-size:12px;font-weight:600;">&#128202; 审查摘要</span>
      <span class="severity-tag ${overallRisk.toLowerCase()}">${overallRisk}</span>
    </div>
    <div class="desc">${summary.review_summary || '暂无摘要'}</div>
    <div style="margin-top:6px;font-size:11px;color:#94a3b8;">
      风险评分: ${payload.risk_score || 0} | 风险项: ${findings.length} 个
    </div>
  `;
  root.appendChild(summaryBlock);

  // Findings
  if (!findings.length) {
    root.innerHTML += '<div class="empty-state"><p>未发现风险点</p></div>';
    return;
  }

  const container = document.createElement('div');
  container.className = 'findings-container';

  findings.forEach((item, idx) => {
    const sev = (item.severity || 'LOW').toLowerCase();
    const card = document.createElement('div');
    card.className = `card ${sev}`;
    card.innerHTML = `
      <div class="card-header">
        <span class="card-title">${item.risk_type || '未知风险'}</span>
        <span class="severity-tag ${sev}">${(item.severity || 'LOW').toUpperCase()}</span>
      </div>
      <div class="card-body">
        <div class="field"><span class="label">原文：</span>${item.original_text || '-'}</div>
        <div class="field"><span class="label">依据：</span>${item.legal_basis || '-'}</div>
        <div class="field"><span class="label">建议：</span>${item.suggestion || '-'}</div>
        ${item.proposed_clause ? `<div class="field" style="margin-top:6px;padding:6px 8px;background:#f0fdf4;border-radius:6px;border:1px solid #bbf7d0;"><span class="label" style="color:#15803d;">替代条款：</span><br>${item.proposed_clause}</div>` : ''}
      </div>
      ${(item.proposed_clause || item.suggestion) ? `
        <div class="card-action">
          <button class="btn-adopt" data-idx="${idx}" data-text="${encodeURIComponent(item.proposed_clause || item.suggestion)}">
            &#9997; 采纳此建议
          </button>
        </div>` : ''}
    `;
    container.appendChild(card);
  });

  // Bind adopt buttons
  container.querySelectorAll('.btn-adopt').forEach(btn => {
    btn.addEventListener('click', () => {
      const textToInsert = decodeURIComponent(btn.dataset.text);
      adoptClause(textToInsert, btn);
    });
  });

  root.appendChild(container);
}

function adoptClause(text, btn) {
  if (!window.Asc || !window.Asc.plugin) {
    // Not in OnlyOffice environment, copy to clipboard
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = '&#10003; 已复制到剪贴板';
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = '&#9997; 采纳此建议';
        btn.disabled = false;
      }, 2000);
    }).catch(() => {
      alert('复制失败，请手动复制：\n\n' + text);
    });
    return;
  }

  // In OnlyOffice: insert text at cursor position
  try {
    window.Asc.plugin.executeMethod("PasteText", [text]);
    btn.textContent = '&#10003; 已插入文档';
    btn.disabled = true;
  } catch (e) {
    // Fallback: try ReplaceTextSmart
    try {
      window.Asc.plugin.executeMethod("ReplaceTextSmart", [[{ text: text, replaceWith: text }]]);
      btn.textContent = '&#10003; 已插入文档';
      btn.disabled = true;
    } catch (e2) {
      alert('插入失败：' + e2.message);
    }
  }
}
