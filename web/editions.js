import {connectArchive} from "./archive.js";
import {api} from "./api.js";
import {at, element, fillOptions, table} from "./dom.js";

export function connectEditions(onNotice, onError) {
  const openArchive = connectArchive(onError);
  async function browse() {
    const editions = await api.editions();
    table(at("edition-list"), ["版号", "试验资料", "代次", "摘要", "归档证据", "证据包"], editions.map((row) => {
      const download = element("a", "下载 JSON");
      download.href = `/api/editions/${row.id}/download`;
      const digest = element("code", `${row.digest.slice(0, 12)}…`);
      digest.title = row.digest;
      const open = element("button", "查看");
      open.onclick = () => openArchive(row.id);
      return [row.id, row.label, row.revision, digest, open, download];
    }));
    const options = editions.map((row) => [row.id, `第 ${row.id} 版 · ${row.label} / 代次 ${row.revision}`]);
    fillOptions(at("before"), options, "选择对照版");
    fillOptions(at("after"), options, "选择目标版");
    at("diff-form").hidden = editions.length === 0;
  }
  at("diff-form").onsubmit = async (event) => {
    event.preventDefault();
    const button = at("diff-form").querySelector("button");
    button.disabled = true;
    at("diff").replaceChildren();
    try {
      const result = await api.compare(at("before").value, at("after").value);
      table(at("diff"), ["轮次", "测点", "驻载变化 / μm", "残余变化 / μm", "证据变化"], result.rows.map((row) => [
        row.hold, row.point, row.change.loaded_um, row.change.residual_um, row.evidence_changed ? "已变化" : "相同",
      ]));
    } catch (error) {
      onError(error);
    } finally {
      button.disabled = false;
    }
  };
  return {async show(draft) {
    const button = at("release");
    button.disabled = !draft.report.ready;
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await api.release(draft.id, draft.revision);
        await browse();
        onNotice(`已签出第 ${result.id} 版`);
      } catch (error) {
        onError(error);
      } finally {
        if (at("release").onclick === releaseCurrent) button.disabled = !draft.report.ready;
      }
    };
    const releaseCurrent = button.onclick;
    return browse();
  }};
}
