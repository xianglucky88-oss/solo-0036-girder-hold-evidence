import {api} from "./api.js";
import {at, element, status, table} from "./dom.js";

function ticketEvents(journal) {
  // 故障单事件按代次分组（同一代次的多行属于同一次整组操作）。
  const groups = new Map();
  for (const item of journal) {
    if (item.scope !== "ticket") continue;
    if (!groups.has(item.revision)) groups.set(item.revision, []);
    groups.get(item.revision).push(item);
  }
  return [...groups.entries()].map(([revision, events]) => ({
    revision,
    ticket: events[0].ticket,
    action: events[0].action,
    reason: events[0].reason,
    members: events.map((event) => ({kind: event.kind, row_id: event.row_id})),
  }));
}

export function connectTickets(afterChange, onError) {
  const dialog = at("ticket-dialog");
  let context;

  function openFile(run, members, done) {
    context = {mode: "exclude", run, members, done};
    at("ticket-dialog-title").textContent = `按故障单整组排除 · ${members.length} 行`;
    at("ticket-id-row").hidden = false;
    at("ticket-revoke-hint").hidden = true;
    at("ticket-members").replaceChildren(...members.map((member) =>
      element("li", `${member.kind === "reading" ? "采样" : "驻位"} · ${member.row_id}`)));
    at("ticket-form").reset();
    at("ticket-error").textContent = "";
    dialog.showModal();
  }

  function openRevoke(run, ticket, reason) {
    context = {mode: "revoke", run, ticket};
    at("ticket-dialog-title").textContent = `整单撤销故障单 ${ticket}`;
    at("ticket-id-row").hidden = true;
    at("ticket-revoke-hint").hidden = false;
    at("ticket-revoke-hint").textContent = `该单当前理由：${reason}。撤销只解除本故障单的理由，手工裁定和其他故障单继续生效。`;
    at("ticket-members").replaceChildren();
    at("ticket-form").reset();
    at("ticket-error").textContent = "";
    dialog.showModal();
  }

  at("ticket-form").onsubmit = async (event) => {
    event.preventDefault();
    if (!context) return;
    const button = at("ticket-submit");
    button.disabled = true;
    try {
      if (context.mode === "exclude") {
        await api.ticket(context.run, "exclude", {
          revision: Number(at("ticket-revision").value),
          ticket: at("ticket-id").value.trim(),
          reason: at("ticket-reason").value,
          rows: context.members,
        });
      } else {
        await api.ticket(context.run, "revoke", {
          revision: Number(at("ticket-revision").value),
          ticket: context.ticket,
          reason: at("ticket-reason").value,
        });
      }
      dialog.close();
      const done = context.done;
      await afterChange(context.run, context.mode === "exclude" ? "已按故障单整组排除" : "已整单撤销故障单");
      if (done) await done();
    } catch (error) {
      if (dialog.open) {
        at("ticket-error").textContent = error.message;
        button.disabled = false;
      } else {
        onError(error);
      }
    }
  };

  function renderJournal(draft, onChanged) {
    const groups = ticketEvents(draft.journal);
    const active = new Map();
    for (const group of groups) {
      if (group.action === "exclude") active.set(group.ticket, group);
      else active.delete(group.ticket);
    }
    table(at("ticket-journal"), ["代次", "故障单", "操作", "成员", "理由", "操作"], groups.map((group) => {
      const memberText = group.members
        .map((member) => `${member.kind === "reading" ? "采样" : "驻位"} ${member.row_id}`).join("、");
      let actionCell = "—";
      if (group.action === "exclude" && active.get(group.ticket)?.revision === group.revision) {
        const button = element("button", "整单撤销");
        button.onclick = () => openRevoke(draft.id, group.ticket, group.reason);
        actionCell = button;
      }
      return [group.revision, group.ticket,
              status(group.action === "exclude" ? "整组排除" : "整单撤销", group.action === "exclude" ? "warn" : "good"),
              memberText, group.reason, actionCell];
    }), "暂无故障单裁定");
    at("ticket-revision").value = draft.revision;
  }

  return {openFile, renderJournal};
}
