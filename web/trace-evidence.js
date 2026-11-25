import {display, element, reasonChips, table} from "./dom.js";

const phaseNames = {before: "空载", loaded: "驻载", after: "撤载"};
const axleStates = {ambiguous: "多行冲突", missing: "缺行", lane: "车道不符", offset: "轴位超差", matched: "匹配"};
const gapReasons = {point_ambiguous: "测点多行冲突", reference_ambiguous: "参考多行冲突", reference_missing: "缺同刻参考"};

function group(body, name, headers, rows) {
  const section = element("section", undefined, "trace-group");
  const container = element("div", undefined, "table-wrap");
  section.append(element("h3", name), container);
  table(container, headers, rows);
  body.append(section);
}

function reasonFor(reasons, id) {
  const list = (reasons || {})[id];
  return list && list.length ? reasonChips(list) : "—";
}

function renderRows(body, title, headers, rows, action, kind, reasons) {
  const columns = [...headers, "生效理由", "手工裁定"];
  const values = rows.map(([id, ...rest]) => {
    const list = reasons[id] || [];
    const manualActive = list.some((item) => item.scope === "manual");
    const control = action ? action(kind, id, manualActive ? "restore" : "exclude") : "—";
    return [id, ...rest, reasonFor(reasons, id), control];
  });
  group(body, title, columns, values);
}

export function renderEvidence(body, trace, action) {
  body.replaceChildren();
  const reasons = trace.exclusion_reasons || {position: {}, reading: {}};
  group(body, "驻位核对", ["车轴", "状态", "实际偏移 / mm", "驻位行"], trace.placement.axles.map((row) => [
    row.axle, axleStates[row.state], row.offset_mm, row.evidence.join("、") || "—",
  ]));
  renderRows(body, "驻位原始行", ["行号", "车轴", "车道", "轴距 / mm", "质量 / kg", "CSV 行"], trace.positions.map((row) => [
    row.id, row.axle, row.lane, row.station_mm, row.mass_kg, row.line,
  ]), action, "position", reasons.position);
  for (const [key, phase] of Object.entries(phaseNames)) {
    const evidence = trace.response.phases[key];
    const rows = evidence.pairs.map((row) => [row.tick, row.point_row, row.reference_row, row.adjusted_um]);
    rows.push(...evidence.gaps.map((gap) => [
      gap.tick, gap.point_rows.join("、"), gap.reference_rows.join("、") || "—", gapReasons[gap.reason],
    ]));
    group(body, `${phase} · ${evidence.pair_count} 对 · 中值 ${display(evidence.median_um)} μm`,
          ["时刻 / s", "测点行", "参考行", "归一读数 / μm"], rows);
  }
  renderRows(body, "采样原始行", ["行号", "通道", "时刻 / s", "原值 / μm", "CSV 行"], trace.readings.map((row) => [
    row.id, row.channel, row.tick, row.value_um, row.line,
  ]), action, "reading", reasons.reading);
}
