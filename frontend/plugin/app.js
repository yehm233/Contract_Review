const apiBase = "http://172.27.3.6:8080";

function severityClass(severity) {
  return (severity || "low").toLowerCase();
}

function renderFindings(findings) {
  const result = document.getElementById("result");
  result.innerHTML = "";

  findings.forEach((item) => {
    const card = document.createElement("div");
    card.className = `card ${severityClass(item.severity)}`;
    card.innerHTML = `
      <div><strong>风险类型：</strong>${item.risk_type}</div>
      <div><strong>级别：</strong>${item.severity}</div>
      <div><strong>原文：</strong>${item.original_text}</div>
      <div><strong>建议：</strong>${item.suggestion}</div>
      <button class="adopt-btn">采纳</button>
    `;

    card.querySelector(".adopt-btn").addEventListener("click", () => {
      window.Asc.plugin.executeMethod("ReplaceTextSmart", [item.suggestion]);
    });

    result.appendChild(card);
  });
}

document.getElementById("startReviewBtn").addEventListener("click", async () => {
  const contractId = document.getElementById("contractId").value.trim();
  if (!contractId) {
    alert("请输入 contract_id");
    return;
  }

  const resp = await fetch(`${apiBase}/api/review/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id: contractId }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    alert(`审查失败: ${text}`);
    return;
  }

  const data = await resp.json();
  renderFindings(data.findings || []);
});
