import {display, element, table} from "./dom.js";

const phaseNames = {before: "空载", loaded: "驻载", after: "撤载"};
const axleStates = {ambiguous: "多行冲突", missing: "缺行", lane: "车道不符", offset: "轴位超差", matched: "匹配"};
const gapReasons = {point_ambiguous: "测点多行冲突", reference_ambiguous: "参考多行冲突", reference_missing: "缺同刻参考"};
const directionNames = {up: "去程", peak: "峰值", back: "回程"};
const contrastStates = {valid: "已采用", coverage: "配对不足", mass: "总质量超限", placement: "驻位待复核"};

function group(body, name, headers, rows) {
  const section = element("section", undefined, "trace-group");
  const container = element("div", undefined, "table-wrap");
  section.append(element("h3", name), container);
  table(container, headers, rows);
  body.append(section);
}

function renderRows(body, title, headers, rows, action, kind) {
  const columns = action ? [...headers, "裁定"] : headers;
  const values = rows.map(([id, ...rest]) => action ? [id, ...rest, action(kind, id)] : [id, ...rest]);
  group(body, title, columns, values);
}

function renderPlacement(body, axles, action) {
  group(body, "驻位核对", ["车轴", "状态", "实际偏移 / mm", "驻位行"], axles.map((row) => [
    row.axle, axleStates[row.state], row.offset_mm, row.evidence.join("、") || "—",
  ]));
}

function renderSamples(body, readings, action) {
  renderRows(body, "采样原始行", ["行号", "通道", "时刻 / s", "原值 / μm", "CSV 行"], readings.map((row) => [
    row.id, row.channel, row.tick, row.value_um, row.line,
  ]), action, "reading");
}

function renderPositions(body, positions, action) {
  renderRows(body, "驻位原始行", ["行号", "车轴", "车道", "轴距 / mm", "质量 / kg", "CSV 行"], positions.map((row) => [
    row.id, row.axle, row.lane, row.station_mm, row.mass_kg, row.line,
  ]), action, "position");
}

function renderPhase(body, title, evidence) {
  const rows = evidence.pairs.map((row) => [row.tick, row.point_row, row.reference_row, row.adjusted_um]);
  rows.push(...evidence.gaps.map((gap) => [
    gap.tick, gap.point_rows.join("、"), gap.reference_rows.join("、") || "—", gapReasons[gap.reason],
  ]));
  group(body, `${title} · ${evidence.pair_count} 对 · 中值 ${display(evidence.median_um)} μm`,
        ["时刻 / s", "测点行", "参考行", "归一读数 / μm"], rows);
}

function renderGraded(body, trace, action) {
  group(body, "整次残余", ["测点", "首空载中值 / μm", "撤净中值 / μm", "整次残余 / μm", "状态"], [[
    trace.point, trace.response.first_empty_um, trace.response.final_empty_um, trace.response.residual_um,
    contrastStates[trace.response.state] ?? trace.response.state,
  ]]);
  renderPhase(body, "首空载公共窗", trace.first_empty.phases);
  for (const step of trace.steps) {
    renderPlacement(body, step.placement.axles, action);
    renderPhase(body, `${step.id} · ${directionNames[step.direction] ?? step.direction} · ${step.level}`, step.phases);
  }
  renderPhase(body, "末段撤净公共窗", trace.final_empty.phases);
  group(body, "同级去回对照", ["级别", "去程台阶", "回程台阶", "总质量差 / kg", "对照容差 / kg", "去程位移 / μm", "回程位移 / μm", "有符号回程差 / μm", "采用"],
        trace.contrasts.map((row) => [
          row.level_label ?? row.level, row.forward, row.back, row.mass_delta_kg, row.contrast_tolerance_kg,
          row.forward_displacement_um, row.back_displacement_um, row.difference_um,
          row.adopted ? "已采用" : contrastStates[row.state] ?? row.state,
        ]));
  renderPositions(body, trace.positions, action);
  renderSamples(body, trace.readings, action);
}

export function renderEvidence(body, trace, action) {
  body.replaceChildren();
  if (trace.graded !== undefined) {
    renderGraded(body, trace, action);
    return;
  }
  renderPlacement(body, trace.placement.axles, action);
  renderPositions(body, trace.positions, action);
  for (const [key, phase] of Object.entries(phaseNames)) {
    renderPhase(body, phase, trace.response.phases[key]);
  }
  renderSamples(body, trace.readings, action);
}
