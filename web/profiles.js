import {at, element, status, table} from "./dom.js";

function toNumber(value) {
  const [a, b = 1] = String(value).split("/").map(Number);
  return a / b;
}

function drawRange(low, high, bounds) {
  const chart = element("canvas");
  chart.width = 480;
  chart.height = 44;
  chart.setAttribute("aria-hidden", "true");
  const context = chart.getContext("2d");
  const toX = (value) => 10 + 460 * (value - bounds[0]) / (bounds[1] - bounds[0] || 1);
  context.fillStyle = "#e4dced";
  context.fillRect(10, 21, 460, 2);
  const zero = toX(0);
  context.fillStyle = "#9282a3";
  context.fillRect(zero, 8, 1, 28);
  if (low && high) {
    const start = toX(toNumber(low.value_um));
    const end = toX(toNumber(high.value_um));
    context.fillStyle = "#7547a3";
    context.fillRect(start, 17, Math.max(2, end - start), 10);
    for (const x of [start, end]) {
      context.beginPath();
      context.arc(x, 22, 7, 0, Math.PI * 2);
      context.fill();
    }
  }
  return chart;
}

export function renderProfiles(draft) {
  const {plan, report} = draft;
  const values = report.envelopes.flatMap(({low, high}) => low ? [toNumber(low.value_um), toNumber(high.value_um)] : []);
  const bounds = [Math.min(0, ...values), Math.max(0, ...values)];
  at("envelopes").replaceChildren(...report.envelopes.map(({station_mm, low, high, complete, missing}) => {
    const row = element("div", undefined, "envelope");
    const block = element("div");
    block.append(element("strong", `${station_mm / 1000} m`), document.createTextNode(" "),
                 status(complete ? "齐全" : `缺 ${missing.length} 项`, complete ? "good" : "warn"));
    const details = element("details", undefined, "muted");
    details.append(element("summary", low ? `${low.value_um} 至 ${high.value_um} μm` : "暂无可用区间"));
    for (const [label, edge] of [["下界", low], ["上界", high]]) {
      if (edge) details.append(element("p", `${label}：${edge.evidence.map((entry) => `${entry.hold}/${entry.point}`).join("、")}`));
    }
    if (missing.length) details.append(element("p", `缺项：${missing.map((entry) => `${entry.hold}/${entry.point}`).join("、")}`));
    row.append(block, drawRange(low, high, bounds), details);
    return row;
  }));
  const names = new Map(plan.cases.map(({id, label}) => [id, label]));
  table(at("repeats"), ["工况", "测点", "轮次", "状态", "差值 / μm", "漏项"], report.repeats.map((row) => [
    names.get(row.case), plan.points.find((point) => point.id === row.point).label, row.holds.join("、"),
    row.state === "incomplete" ? status("待补齐", "warn") : row.state === "single" ? "仅一轮" : row.review ? status("差值需复核", "warn") : "线内",
    row.spread_um, row.missing.join("、") || "—",
  ]));
}
