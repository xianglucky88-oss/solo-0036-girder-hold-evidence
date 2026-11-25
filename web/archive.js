import {api} from "./api.js";
import {at, display, fillOptions} from "./dom.js";
import {renderEvidence} from "./trace-evidence.js";

export function connectArchive(onError) {
  const dialog = at("archive");
  const select = at("archive-coordinate");
  const picker = at("archive-picker");
  const summary = at("archive-response");
  const body = at("archive-body");
  let requestOrder = 0;

  function current(order) {
    return dialog.open && order === requestOrder;
  }

  async function loadTrace(edition, response) {
    const order = ++requestOrder;
    summary.textContent = "正在读取签出版证据";
    body.replaceChildren();
    try {
      const trace = await api.archivedTrace(edition, response.hold, response.point);
      if (!current(order)) return;
      summary.textContent = trace.graded !== undefined
        ? `分级 ${trace.graded} · 整次残余 ${display(trace.response.residual_um)} μm`
        : `驻载 ${display(trace.response.loaded_um)} μm · 残余 ${display(trace.response.residual_um)} μm`;
      renderEvidence(body, trace);
    } catch (error) {
      if (current(order)) summary.textContent = error.message;
    }
  }

  return async function open(edition) {
    const order = ++requestOrder;
    at("archive-title").textContent = `第 ${edition} 版 · 签出证据`;
    at("archive-meta").textContent = "";
    summary.textContent = "正在读取签出版";
    body.replaceChildren();
    picker.hidden = true;
    if (!dialog.open) dialog.showModal();
    try {
      const {digest, document} = await api.edition(edition);
      if (!current(order)) return;
      at("archive-meta").textContent = `草稿代次 ${document.revision} · 摘要 ${digest.slice(0, 12)}…`;
      const responses = [...document.report.responses];
      if (document.report.graded) {
        for (const row of document.report.graded.workorder) {
          responses.push({hold: document.report.graded.id, point: row.point,
                          loaded_um: row.difference_um, residual_um: row.residual_um});
        }
      }
      fillOptions(select, responses.map((row, index) => [index, `${row.hold} · ${row.point}`]));
      select.onchange = () => loadTrace(edition, responses[Number(select.value)]);
      picker.hidden = false;
      await loadTrace(edition, responses[Number(select.value)]);
    } catch (error) {
      if (current(order)) {
        dialog.close();
        onError(error);
      }
    }
  };
}
