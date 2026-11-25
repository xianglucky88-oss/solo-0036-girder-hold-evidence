import {display, element, table} from "./dom.js";

const phaseNames = {before: "空载", loaded: "驻载", after: "撤载"};
const axleStates = {ambiguous: "多行冲突", missing: "缺行", lane: "车道不符", offset: "轴位超差", matched: "匹配"};
const gapReasons = {
  point_ambiguous: "测点读数竞争，缺唯一候选",
  reference_ambiguous: "参考读数竞争，缺唯一候选",
  reference_missing: "缺合格参考（超时差或无候选）",
};
const syncStates = {shared_clock: "共用试验时钟", synced: "已按同步观测换算", no_sync_evidence: "无同步证据"};

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

export function renderEvidence(body, trace, action) {
  body.replaceChildren();
  group(body, "驻位核对", ["车轴", "状态", "实际偏移 / mm", "驻位行"], trace.placement.axles.map((row) => [
    row.axle, axleStates[row.state], row.offset_mm, row.evidence.join("、") || "—",
  ]));
  renderRows(body, "驻位原始行", ["行号", "车轴", "车道", "轴距 / mm", "质量 / kg", "CSV 行"], trace.positions.map((row) => [
    row.id, row.axle, row.lane, row.station_mm, row.mass_kg, row.line,
  ]), action, "position");
  for (const [key, phase] of Object.entries(phaseNames)) {
    const evidence = trace.response.phases[key];
    const rows = evidence.pairs.map((row) => [
      row.tick, row.point_row, row.reference_row, row.adjusted_um, "唯一候选成对",
    ]);
    rows.push(...evidence.gaps.map((gap) => [
      gap.tick, gap.point_rows.join("、"), gap.reference_rows.join("、") || "—", gapReasons[gap.reason], "未成对",
    ]));
    group(body, `${phase} · ${evidence.pair_count} 对 · 中值 ${display(evidence.median_um)} μm`,
          ["试验时刻 / s", "测点行", "参考行", "归一读数 / μm", "配对说明"], rows);
  }
  if (trace.sync_observations?.length) {
    group(body, "同步观测（相邻观测间匀速钟差，端点有效）", ["观测行", "采集机", "本机时刻 / s", "试验时刻 / s", "CSV 行"],
          trace.sync_observations.map((row) => [row.id, row.device, row.local_tick, row.test_tick, row.line]));
  }
  renderRows(body, "采样原始行", ["行号", "通道", "采集机", "本机时刻 / s", "试验时刻 / s", "原值 / μm", "时钟状态", "CSV 行"],
             trace.readings.map((row) => [
               row.id, row.channel, row.device ?? "共用时钟", row.local_tick ?? "—", row.tick, row.value_um,
               syncStates[row.sync_state] || row.sync_state, row.line,
             ]), action, "reading");
}
