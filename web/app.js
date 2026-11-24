import {api} from "./api.js";
import {at, fillOptions} from "./dom.js";
import {connectEditions} from "./editions.js";
import {connectIntake} from "./intake.js";
import {connectInventory} from "./inventory.js";
import {renderProfiles} from "./profiles.js";
import {renderJournal, renderReview} from "./review.js";
import {connectTrace} from "./trace.js";

let currentDraft, requestOrder = 0;
let activeView = "review";

function notice(message, error = false) {
  const panel = at("notice");
  panel.textContent = message;
  panel.classList.toggle("error", error);
  panel.hidden = !message;
}
const onError = (error) => notice(error.message, true);
const trace = connectTrace(async (run, message) => {
  if (currentDraft?.id === run) await refresh(run);
  notice(message);
}, onError);
const inventory = connectInventory(trace.reviewRow, onError);
const editions = connectEditions(notice, onError);

async function showView(view) {
  activeView = view;
  for (const button of document.querySelectorAll("[data-view]")) {
    const selected = button.dataset.view === view;
    button.setAttribute("aria-pressed", String(selected));
    at(button.dataset.view).hidden = !selected;
  }
  if (view === "raw" && currentDraft) await inventory.show(currentDraft.id);
  if (view === "editions" && currentDraft) await editions.show(currentDraft);
}

async function refresh(requested) {
  const order = ++requestOrder;
  const runs = await api.runs();
  const target = requested ?? runs[0]?.id;
  const draft = target ? await api.draft(target) : undefined;
  if (order !== requestOrder) return;
  fillOptions(at("run"), runs.map((row) => [row.id, `${row.label} · #${row.id}`]));
  at("run").disabled = !runs.length;
  at("empty").hidden = Boolean(draft);
  at("workbench").hidden = !draft;
  currentDraft = draft;
  if (!draft) return;
  at("run").value = draft.id;
  at("title").textContent = draft.plan.label;
  renderReview(draft, (hold, point, label) => trace.show(draft.id, hold, point, label));
  renderProfiles(draft);
  renderJournal(draft, (kind, id) => trace.reviewRow(draft.id, draft.revision, kind, id, "restore"));
  await showView(activeView);
}

at("run").onchange = () => {
  notice("");
  at("filter").value = "";
  at("diff").replaceChildren();
  refresh(Number(at("run").value)).catch(onError);
};
for (const button of document.querySelectorAll("[data-view]")) {
  button.onclick = () => showView(button.dataset.view).catch(onError);
}
for (const button of document.querySelectorAll("[data-close]")) {
  button.onclick = () => at(button.dataset.close).close();
}
connectIntake(async (result) => {
  await refresh(result.id);
  notice(result.created ? "资料已导入并完成归约" : "已打开同一份导入资料");
}, onError);
refresh().catch(onError);
