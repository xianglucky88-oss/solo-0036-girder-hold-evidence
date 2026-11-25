import {api} from "./api.js";
import {at} from "./dom.js";

async function readFiles() {
  const files = ["plan-file", "positions-file", "readings-file", "sync-file"].map((id) => at(id).files[0]);
  const [plan, positions, readings, sync] = await Promise.all(files.map((file) => (file ? file.text() : "")));
  const payload = {plan, positions, readings};
  if (sync) payload.sync = sync;
  return payload;
}

export function connectIntake(onImported, onError) {
  at("open-intake").onclick = () => {
    at("intake-error").textContent = "";
    at("intake").showModal();
  };
  const form = at("intake-form");
  form.onsubmit = async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit], button:not([type])");
    button.disabled = true;
    try {
      const result = await api.submit(await readFiles());
      at("intake").close();
      form.reset();
      await onImported(result);
    } catch (error) {
      if (at("intake").open) at("intake-error").textContent = error.message;
      else onError(error);
    } finally {
      button.disabled = false;
    }
  };
  const importSample = async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await onImported(await api.submit(await api.example()));
    } catch (error) {
      onError(error);
    } finally {
      button.disabled = false;
    }
  };
  at("sample").onclick = importSample;
  at("empty-sample").onclick = importSample;
}
