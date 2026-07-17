let openedSubagentPanelId = null;
let openedSubagentButtonId = null;

function toggleDetail(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById(id + '-arrow');
  if (!el) return;
  const hidden = el.style.display === 'none';
  el.style.display = hidden ? 'block' : 'none';
  if (arrow) arrow.textContent = hidden ? '▼' : '▶';
}

function toggleSubagentPanel(panelId, buttonId) {
  const panel = document.getElementById(panelId);
  const btn = document.getElementById(buttonId);
  if (!panel || !btn) return;

  if (openedSubagentPanelId && openedSubagentPanelId !== panelId) {
    const prevPanel = document.getElementById(openedSubagentPanelId);
    const prevBtn = openedSubagentButtonId ? document.getElementById(openedSubagentButtonId) : null;
    if (prevPanel) prevPanel.style.display = 'none';
    if (prevBtn) prevBtn.textContent = '詳細を開く';
  }

  const willOpen = panel.style.display === 'none';
  panel.style.display = willOpen ? 'block' : 'none';
  btn.textContent = willOpen ? '詳細を閉じる' : '詳細を開く';

  openedSubagentPanelId = willOpen ? panelId : null;
  openedSubagentButtonId = willOpen ? buttonId : null;
}
