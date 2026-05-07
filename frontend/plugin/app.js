const API_BASE = "http://172.27.3.6:8080";

function renderFindings(payload) {
  const root = document.getElementById("result");
  root.innerHTML = "";

  const summary = document.createElement("div");
  summary.className = "muted";
  summary.textContent = `任务 ${payload.task_id} | 风险分 ${payload.risk_score}`;
  root.appendChild(summary);

  (payload.findings || []).forEach((item) => {
    const card = document.createElement("div");
    card.className = `card ${(item.severity || "LOW").toLowerCase()}`;
    card.innerHTML = `
      <div><strong>${item.risk_type}</strong> (${item.severity})</div>
      <div class="muted">原文：${item.original_text}</div>
      <div>建议：${item.suggestion}</div>
      <button>采纳</button>
    `;

    const btn = card.querySelector("button");
    btn.addEventListener("click", () => {
      if (window.Asc && window.Asc.plugin) {
        window.Asc.plugin.executeMethod("ReplaceTextSmart", [item.suggestion]);
      }
    });

    root.appendChild(card);
  });
}

document.getElementById("startBtn").addEventListener("click", async () => {
  const contractId = document.getElementById("contractId").value.trim();
  if (!contractId) return;

  const resp = await fetch(`${API_BASE}/api/review/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id: contractId }),
  });

  if (!resp.ok) {
    document.getElementById("result").textContent = `请求失败: ${resp.status}`;
    return;
  }

  const data = await resp.json();
  renderFindings(data);
});
