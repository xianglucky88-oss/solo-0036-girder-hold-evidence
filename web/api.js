async function request(path, data) {
  const options = data === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data),
  };
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("无法连接本地资料服务");
  }
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "操作失败");
  return payload;
}

export const api = {
  runs: () => request("/api/holds"),
  example: () => request("/example"),
  submit: (source) => request("/api/holds", source),
  draft: (run) => request(`/api/holds/${run}`),
  inventory: (run, query) => request(`/api/holds/${run}/inventory?${new URLSearchParams(query)}`),
  trace: (run, hold, point) => request(`/api/holds/${run}/trace?${new URLSearchParams({hold, point})}`),
  decide: (run, revision, kind, row_id, action, reason) => request(`/api/holds/${run}/review`, {revision, kind, row_id, action, reason}),
  ticket: (run, endpoint, payload) => request(`/api/holds/${run}/tickets/${endpoint}`, payload),
  release: (run, revision) => request(`/api/holds/${run}/release`, {revision}),
  editions: () => request("/api/editions"),
  edition: (id) => request(`/api/editions/${id}`),
  archivedTrace: (id, hold, point) => request(`/api/editions/${id}/trace?${new URLSearchParams({hold, point})}`),
  compare: (old, next) => request(`/api/diff/${old}/${next}`),
};
