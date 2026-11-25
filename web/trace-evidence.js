import {display, element, table} from "./dom.js";

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

function renderRows(body, title, headers, rows, action, kind) {
  const columns = action ? [...headers, "裁定"] : headers;
  const values = rows.map(([id, ...rest]) => {
    const meta = rest[rest.length - 1];
    const payload = rest.slice(0, -1);
    return action ? [id, ...payload, action(kind, id, meta || {})] : [id, ...payload];
  });
  group(body, title, columns, values);
}

export function renderEvidence(body, trace, action) {
  body.replaceChildren();
  group(body, "驻位核对", ["车轴", "状态", "实际偏移 / mm", "驻位行"], trace.placement.axles.map((row) => [
    row.axle, axleStates[row.state], row.offset_mm, row.evidence.join("、") || "—",
  ]));
  renderRows(body, "驻位原始行", ["行号", "车轴", "车道", "轴距 / mm", "质量 / kg", "CSV 行"], trace.positions.map((row) => [
    row.id, row.axle, row.lane, row.station_mm, row.mass_kg, row.line,
    {scope: row.scope || "base", retest_id: row.retest_id || null},
  ]), action, "position");
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
    {scope: row.scope || "base", retest_id: row.retest_id || null},
  ]), action, "reading");
}
