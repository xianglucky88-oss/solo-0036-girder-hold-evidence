import {at, display, element, fillOptions, status, table} from "./dom.js";

const responses = {valid: "证据齐全", coverage: "配对不足", placement: "驻位待复核"};

export function renderReview(draft, onTrace) {
  const {plan, report} = draft;
  const caseNames = new Map(plan.cases.map((item) => [item.id, item.label]));
  const pointNames = new Map(plan.points.map((item) => [item.id, item.label]));
  at("revision").textContent = draft.revision;
  at("placed").textContent = `${Object.values(report.placement).filter((item) => item.valid).length} / ${plan.holds.length}`;
  at("complete").textContent = `${report.responses.filter((row) => row.state === "valid").length} / ${report.responses.length}`;
  at("ready").replaceChildren(status(report.ready ? "可签出" : "待复核", report.ready ? "good" : "warn"));
  fillOptions(at("filter"), plan.holds.map((hold) => [hold.id, `${hold.id} · ${caseNames.get(hold.case)}`]), "全部轮次");
  const visible = () => {
    const holdFilter = at("filter").value;
    const holds = plan.holds.filter((hold) => !holdFilter || holdFilter === hold.id);
    at("rounds").replaceChildren(...holds.map(({id}) => {
      const item = report.placement[id];
      const chips = element("div", undefined, "round-chip");
      chips.append(element("strong", id), status(item.valid ? "驻位有效" : "驻位待复核", item.valid ? "good" : "warn"),
                   element("span", `${display(item.total_kg)} kg`, "number"));
      return chips;
    }));
    const rows = report.responses.filter((row) => !holdFilter || row.hold === holdFilter);
    table(at("response-table"), ["轮次", "工况", "测点", "证据", "驻载挠度 / μm", "残余 / μm", "复核线", "原始资料"], rows.map((row) => {
      const detail = element("button", "查看证据");
      detail.setAttribute("aria-label", `查看证据 ${row.hold} ${pointNames.get(row.point)}`);
      detail.onclick = () => onTrace(row.hold, row.point, pointNames.get(row.point));
      return [row.hold, caseNames.get(row.case), pointNames.get(row.point), status(responses[row.state], row.state === "valid" ? "good" : "warn"),
              row.loaded_um, row.residual_um, row.residual_review === null ? "—" : row.residual_review ? status("残余需复核", "warn") : "线内", detail];
    }));
  };
  at("filter").onchange = visible;
  visible();
}

export function renderJournal(draft, onRestore) {
  const latest = new Map(draft.journal.map((item) => [`${item.kind}/${item.row_id}`, item.revision]));
  table(at("journal"), ["代次", "类型", "行号", "裁定", "理由", "操作"], draft.journal.map((item) => {
    const canRestore = item.action === "exclude" && item.revision === latest.get(`${item.kind}/${item.row_id}`);
    const action = canRestore ? element("button", "恢复此行") : "—";
    if (canRestore) action.onclick = () => onRestore(item.kind, item.row_id);
    return [item.revision, item.kind === "reading" ? "采样" : "驻位", item.row_id, item.action === "exclude" ? "排除" : "恢复", item.reason, action];
  }));
}
