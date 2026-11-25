import {api} from "./api.js";
import {at, display, element} from "./dom.js";

import {renderEvidence} from "./trace-evidence.js";

export function connectTrace(afterChange, onError) {
  const dialog = at("trace");
  let decision, loadToken = 0;
  function select(run, revision, kind, id, action) {
    decision = {run, revision, kind, id, action};
    at("decision-title").textContent = `${action === "exclude" ? "排除" : "恢复"}原始行 ${id}`;
    at("decision-error").textContent = "";
    at("decision-submit").disabled = false;
    at("reason").focus();
  }
  function open() {
    decision = undefined;
    at("trace-body").replaceChildren();
    at("decision").reset();
    at("decision-title").textContent = "排除原始行";
    at("decision-error").textContent = "";
    at("decision-submit").disabled = true;
    if (!dialog.open) dialog.showModal();
    return ++loadToken;
  }
  at("decision").onsubmit = async (event) => {
    event.preventDefault();
    if (!decision) return;
    const {run, revision, kind, id, action} = decision;
    const token = loadToken;
    at("decision-submit").disabled = true;
    try {
      await api.decide(run, revision, kind, id, action, at("reason").value);
      if (token === loadToken) dialog.close();
    } catch (error) {
      if (token === loadToken && dialog.open) {
        at("decision-error").textContent = error.message;
        at("decision-submit").disabled = false;
      } else {
        onError(error);
      }
      return;
    }
    await afterChange(run, action === "exclude" ? "已排除原始行" : "已恢复原始行").catch(onError);
  };
  return {
    async show(run, hold, point, name) {
      const token = open();
      at("trace-title").textContent = `${hold} · ${name}`;
      at("trace-summary").textContent = "正在读取原始证据";
      try {
        const trace = await api.trace(run, hold, point);
        if (token !== loadToken || !dialog.open) return;
        at("trace-summary").textContent = `草稿第 ${trace.revision} 代 · 驻载 ${display(trace.response.loaded_um)} μm · 残余 ${display(trace.response.residual_um)} μm`;
        renderEvidence(at("trace-body"), trace, (kind, id, action) => {
          const button = element("button", action === "exclude" ? "手工排除" : "恢复本行");
          button.onclick = () => select(run, trace.revision, kind, id, action);
          return button;
        });
      } catch (error) {
        if (token === loadToken && dialog.open) {
          dialog.close();
          onError(error);
        }
      }
    },
    reviewRow(run, revision, kind, id, action) {
      open();
      at("trace-title").textContent = "裁定原始证据";
      at("trace-summary").textContent = `裁定后重新生成第 ${revision + 1} 代归约结果。`;
      select(run, revision, kind, id, action);
    },
  };
}
