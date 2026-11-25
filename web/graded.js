import {at, display, element, status, table} from "./dom.js";

const directionNames = {up: "去程", peak: "峰值", back: "回程"};
const contrastStates = {valid: "已采用", coverage: "配对不足", mass: "总质量超限", placement: "驻位待复核"};

export function renderGraded(draft, onTrace) {
  const graded = draft.report.graded;
  const panel = at("graded-panel");
  panel.hidden = !graded;
  if (!graded) return;

  at("graded-summary").textContent =
    `${graded.label} · 首空载 ${graded.first_empty_window[0]}–${graded.first_empty_window[1]} s`
    + ` · 末段撤净 ${graded.final_empty_window[0]}–${graded.final_empty_window[1]} s · 状态 `
    + (graded.ready ? "可签出" : `待补齐 ${graded.missing.length} 项`);

  table(at("graded-steps"), ["台阶", "级别", "方向", "窗口 / s", "总质量 / kg", "驻位"], graded.steps.map((step) => {
    const placement = step.placement;
    return [step.id, step.level, directionNames[step.direction] ?? step.direction,
            `${step.window[0]}–${step.window[1]}`, display(placement.total_kg),
            status(placement.valid ? "驻位有效" : "驻位待复核", placement.valid ? "good" : "warn")];
  }));

  const points = new Map(draft.plan.points.map((point) => [point.id, point.label]));
  table(at("graded-workorder"), ["级别", "测点", "采用台阶", "首空载 / μm", "去程位移 / μm", "回程位移 / μm",
    "有符号回程差 / μm", "整次残余 / μm", "采用", "证据"], graded.workorder.map((row) => {
    const detail = element("button", "查看证据");
    detail.setAttribute("aria-label", `查看分级证据 ${graded.id} ${points.get(row.point)}`);
    detail.onclick = () => onTrace(graded.id, row.point, points.get(row.point));
    return [row.level_label ?? row.level, points.get(row.point) ?? row.point,
            `${row.forward} / ${row.back}`, display(row.first_empty_um), display(row.forward_displacement_um),
            display(row.back_displacement_um), display(row.difference_um), display(row.residual_um),
            status(contrastStates[row.state] ?? row.state, row.state === "valid" ? "good" : "warn"), detail];
  }));
}
