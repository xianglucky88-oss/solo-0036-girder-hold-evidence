import {api} from "./api.js";
import {at, element, status, table} from "./dom.js";

const phases = {before: "空载", loaded: "驻载", after: "撤载"};
const states = {
  active: ["参与归约", "good"],
  excluded: ["已排除", "warn"],
  outside: ["窗外留存", ""],
};
const readingHead = ["行号", "通道", "时刻 / s", "原值 / μm", "轮次", "时相"];
const positionHead = ["行号", "轮次", "车号", "车轴", "车道", "轴距 / mm", "质量 / kg"];

function cells(row, reading, vehicleContract = false) {
  if (reading) {
    return [row.id, row.channel, row.tick, row.value_um, row.hold, phases[row.phase]];
  }
  const vehicle = row.vehicle || (vehicleContract ? "待推断" : "—");
  return [row.id, row.hold, vehicle, row.axle, row.lane, row.station_mm, row.mass_kg];
}

export function connectInventory(onReview, onError) {
  const kindControl = at("inventory-kind");
  const stateControl = at("inventory-state");
  const search = at("inventory-match");
  let run, serial = 0, page = 1;
  let filter = {kind: "reading", state: "all", match: ""};

  function render(currentRun, payload) {
    const reading = payload.kind === "reading";
    const headers = [...(reading ? readingHead : positionHead), "CSV 行", "状态", "裁定"];
    table(at("inventory-table"), headers, payload.rows.map((row) => {
      const action = row.state === "excluded" ? "restore" : "exclude";
      const button = element("button", action === "exclude" ? "排除" : "恢复");
      button.onclick = () => onReview(currentRun, payload.revision, payload.kind, row.id, action);
      return [...cells(row, reading, payload.vehicle_contract), row.line, status(...states[row.state]), button];
    }), "没有符合条件的原始行");
    page = payload.page;
    at("inventory-page").textContent = `第 ${page} / ${payload.pages} 页 · ${payload.total} 行`;
    at("inventory-prev").disabled = page <= 1;
    at("inventory-next").disabled = page >= payload.pages;
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
  return {show(currentRun) {
    const changed = run !== currentRun;
    run = currentRun;
    return fetchPage(changed ? 1 : page);
  }};
}
