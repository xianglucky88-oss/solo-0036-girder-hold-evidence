import {api} from "./api.js";
import {at, element, reasonChips, status, table} from "./dom.js";

const phases = {before: "空载", loaded: "驻载", after: "撤载"};
const states = {
  active: ["参与归约", "good"],
  excluded: ["已排除", "warn"],
  outside: ["窗外留存", ""],
};
const readingHead = ["行号", "通道", "时刻 / s", "原值 / μm", "轮次", "时相"];
const positionHead = ["行号", "车轴", "车道", "轴距 / mm", "质量 / kg", "轮次"];

function cells(row, reading) {
  if (reading) {
    return [row.id, row.channel, row.tick, row.value_um, row.hold, phases[row.phase]];
  }
  return [row.id, row.axle, row.lane, row.station_mm, row.mass_kg, row.hold];
}

export function connectInventory(onReview, onError, onTicket) {
  const kindControl = at("inventory-kind");
  const stateControl = at("inventory-state");
  const search = at("inventory-match");
  let run, serial = 0, page = 1;
  let filter = {kind: "reading", state: "all", match: ""};
  const selected = new Map();

  function render(currentRun, payload) {
    const reading = payload.kind === "reading";
    const headers = ["选择", ...(reading ? readingHead : positionHead), "CSV 行", "状态", "生效理由", "手工裁定"];
    table(at("inventory-table"), headers, payload.rows.map((row) => {
      const manualActive = (row.reasons || []).some((item) => item.scope === "manual");
      const action = manualActive ? "restore" : "exclude";
      const button = element("button", action === "exclude" ? "手工排除" : "恢复本行");
      button.onclick = () => onReview(currentRun, payload.revision, payload.kind, row.id, action);
      const checkbox = element("input");
      checkbox.type = "checkbox";
      const key = `${payload.kind}/${row.id}`;
      checkbox.checked = selected.has(key);
      checkbox.onchange = () => {
        if (checkbox.checked) selected.set(key, {kind: payload.kind, row_id: row.id});
        else selected.delete(key);
      };
      const reasons = row.state === "excluded" ? reasonChips(row.reasons) : "—";
      return [checkbox, ...cells(row, reading), row.line, status(...states[row.state]), reasons, button];
    }), "没有符合条件的原始行");
    page = payload.page;
    at("inventory-page").textContent = `第 ${page} / ${payload.pages} 页 · ${payload.total} 行 · 已选 ${selected.size} 行`;
    at("inventory-prev").disabled = page <= 1;
    at("inventory-next").disabled = page >= payload.pages;
    at("ticket-file").disabled = selected.size === 0;
  }

  async function fetchPage(target) {
    const order = ++serial;
    const currentRun = run;
    at("inventory-prev").disabled = true;
    at("inventory-next").disabled = true;
    try {
      const data = await api.inventory(currentRun, {...filter, page: target});
      if (order === serial) render(currentRun, data);
    } catch (error) {
      if (order === serial) {
        at("inventory-table").replaceChildren();
        at("inventory-page").textContent = "读取失败";
        onError(error);
      }
    }
  }

  kindControl.onchange = () => {
    const outside = stateControl.querySelector('[value="outside"]');
    outside.disabled = kindControl.value !== "reading";
    if (outside.disabled && stateControl.value === "outside") stateControl.value = "all";
  };
  at("inventory-form").onsubmit = (event) => {
    event.preventDefault();
    filter = {kind: kindControl.value, state: stateControl.value, match: search.value};
    fetchPage(1);
  };
  at("inventory-prev").onclick = () => fetchPage(page - 1);
  at("inventory-next").onclick = () => fetchPage(page + 1);
  at("ticket-clear").onclick = () => {
    selected.clear();
    fetchPage(page);
  };
  at("ticket-file").onclick = () => onTicket(run, [...selected.values()], () => {
    selected.clear();
    return fetchPage(page);
  });
  return {show(currentRun) {
    const changed = run !== currentRun;
    run = currentRun;
    if (changed) selected.clear();
    return fetchPage(changed ? 1 : page);
  }};
}
