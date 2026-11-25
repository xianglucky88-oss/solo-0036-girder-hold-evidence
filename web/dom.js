export const at = (id) => document.getElementById(id);

export function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content instanceof Node) node.append(content);
  else if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}

export const display = (value) => value ?? "—";

export function status(text, tone = "") {
  return element("span", text, `status ${tone}`);
}

export function table(container, headers, rows, empty = "暂无记录") {
  if (!rows.length) {
    container.replaceChildren(element("p", empty, "empty-row"));
    return;
  }
  const grid = element("table");
  const head = grid.createTHead().insertRow();
  for (const title of headers) {
    const cell = element("th", title);
    cell.scope = "col";
    head.append(cell);
  }
  const body = grid.createTBody();
  for (const values of rows) {
    const row = body.insertRow();
    for (const value of values) row.append(element("td", display(value)));
  }
  container.replaceChildren(grid);
}

export function fillOptions(select, options, empty) {
  const previous = select.value;
  const nodes = options.map(([value, label]) => new Option(label, String(value)));
  select.replaceChildren(...(empty === undefined ? nodes : [new Option(empty, ""), ...nodes]));
  if (Array.from(select.options).some((option) => option.value === previous)) select.value = previous;
}

export function reasonChips(reasons) {
  const wrap = element("div", undefined, "reason-list");
  for (const item of reasons || []) {
    const source = item.scope === "ticket" ? `故障单 ${item.ticket ?? ""}` : "手工裁定";
    const chip = element("span", `${source}：${item.reason}`, `reason-chip ${item.scope}`);
    chip.title = `第 ${item.revision} 代生效`;
    wrap.append(chip);
  }
  return wrap;
}
