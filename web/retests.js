import {api} from "./api.js";
import {at, element, status, table} from "./dom.js";

export function connectRetests(onNotice, onError) {
  const form = at("retest-form");

  function obligationRows(draft) {
    const {report, plan} = draft;
    if (report.contract !== "hold-reduction-v2") return [];
    const names = new Map(plan.cases.map((item) => [item.id, item.label]));
    const obligations = report.obligations;
    const confirmed = new Map(obligations.confirmed.map((item) => [item.hold, item]));
    const broken = new Set(obligations.broken_confirmations || []);
    return obligations.missing.map(({hold, case: caseId}) => {
      const confirmation = confirmed.get(hold);
      const forced = obligations.forced[hold];
      const candidates = obligations.eligible_edges[hold] || [];
      let state;
      if (confirmation && broken.has(hold)) state = status(`归属失效：${confirmation.retest_id}`, "warn");
      else if (confirmation) state = status(`已由 ${confirmation.retest_id} 替补`, "good");
      else if (forced) state = status(`归属唯一：${forced}`, "good");
      else if (candidates.length) state = status("归属待确认", "warn");
      else state = status("无合格补测", "warn");
      const action = confirmation && !broken.has(hold) ? "—" : confirmButton(draft, hold, forced, candidates.length > 0);
      return [hold, names.get(caseId), candidates.join("、") || "—", state, action];
    });
  }

  function confirmButton(draft, hold, forced, hasCandidates) {
    if (!forced || !hasCandidates) return element("span", "—", "muted");
    const button = element("button", `确认由 ${forced} 替补`);
    button.onclick = async () => {
      const reason = window.prompt(`确认补测轮 ${forced} 替补原轮 ${hold} 的理由`, "负责人确认唯一归属");
      if (reason === null) return;
      button.disabled = true;
      try {
        await api.confirmSubstitution(draft.id, draft.revision, hold, forced, reason);
        onNotice(`已确认 ${forced} 替补 ${hold}`);
      } catch (error) {
        onError(error);
      }
    };
    return button;
  }

  function render(draft) {
    const {report} = draft;
    if (report.contract !== "hold-reduction-v2") {
      at("retest-obligations").replaceChildren(element("p", "当前资料尚无补测登记。登记补测后，这里显示缺证义务与替补归属。", "empty-row"));
      at("retest-rounds").replaceChildren(element("p", "暂无补测轮", "empty-row"));
      return;
    }
    const obligations = report.obligations;
    table(at("retest-obligations"), ["缺证原轮", "工况", "合格补测候选", "归属状态", "替补确认"], obligationRows(draft));
    const summary = element("p", `最多可补齐 ${obligations.max_fill} 项；仍缺 ${obligations.outstanding.length} 项义务。`
      + (obligations.forced && Object.keys(obligations.forced).length ? " 可确认的强制归属已在下方标出。" : " 当前无归属唯一的安排。"),
      "muted");
    at("retest-obligations").prepend(summary);

    table(at("retest-rounds"), ["补测轮", "工况", "整轮资格", "采用状态", "可替义务"], report.retests.map((item) => {
      const adopted = item.adopted ? status("已采用", "good") : status("未采用", "");
      const canReplace = (obligations.eligible_edges &&
        Object.entries(obligations.eligible_edges).filter(([, list]) => list.includes(item.retest_id))
          .map(([hold]) => hold).join("、")) || "—";
      return [item.retest_id, item.case,
              item.qualified ? status("整轮合格", "good") : status("未达整轮合格", "warn"),
              adopted, canReplace];
    }), "暂无补测轮");
  }

  form.onsubmit = async (event) => {
    event.preventDefault();
    const run = Number(at("run").value);
    const revision = Number(at("retest-revision").value);
    const readFiles = async (id) => (await Promise.all([...at(id).files].map((file) => file.text()))).join("");
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const payload = {
        revision,
        id: at("retest-id").value.trim(),
        label: at("retest-label").value.trim(),
        case: at("retest-case").value,
        before: [Number(at("retest-before-start").value), Number(at("retest-before-end").value)],
        loaded: [Number(at("retest-loaded-start").value), Number(at("retest-loaded-end").value)],
        after: [Number(at("retest-after-start").value), Number(at("retest-after-end").value)],
        positions: await readFiles("retest-positions"),
        readings: await readFiles("retest-readings"),
      };
      const result = await api.registerRetest(run, payload);
      form.reset();
      onNotice(`补测 ${result.retest_id} 已登记，当前代次 ${result.revision}`);
    } catch (error) {
      onError(error);
    } finally {
      button.disabled = false;
    }
  };

  return {render};
}
