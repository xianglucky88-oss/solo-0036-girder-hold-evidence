"""用演练样本在临时库和回环端口复核公开工作流。"""
import copy
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from girder.httpd import Server
from girder.jsonwire import fingerprint
from girder.store import Store


@contextmanager
def temporary_server():
    with tempfile.TemporaryDirectory(prefix="girder-") as folder:
        with Server(("127.0.0.1", 0), Store(Path(folder) / "workflow.sqlite")) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                yield f"http://127.0.0.1:{server.server_port}"
            finally:
                server.shutdown()
                worker.join()


def request(base, path, body=None, expected=200):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        response = urlopen(req, timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        if response.status != expected:
            raise RuntimeError(f"{path}: HTTP {response.status}；预期 {expected}。{raw[:200]!r}")
        value = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
        return value, response.headers


def check(condition, label):
    if not condition:
        raise RuntimeError(f"工作流核对失败：{label}")
    print(f"通过  {label}")


def exercise(url):
    get = lambda path: request(url, path)[0]
    post = lambda path, body, expected=200: request(url, path, body, expected)[0]
    check(b"/web/app.js" in get("/") and b"export" in get("/web/api.js"), "native-ui 浏览器入口")
    sample = get("/example")
    bad = copy.deepcopy(sample)
    bad["plan"]["holds"][0]["loaded"] = [0, 3]
    post("/api/holds", bad, 400)
    check(get("/api/holds") == [], "intake-invalid 输入冲突无落库")
    created = post("/api/holds", sample)
    run = f"/api/holds/{created['id']}"
    again = post("/api/holds", dict(sample, plan=json.dumps(sample["plan"])))
    check(created["created"] and not again["created"] and len(get("/api/holds")) == 1 and again["id"] == created["id"],
          "intake 合法资料导入和幂等")
    draft = get(run)
    result = draft["report"]
    check(result["placement"]["H1"]["total_kg"] == 18000 and result["placement"]["H1"]["valid"], "placement 逐轴后核对总质量")
    result_rows = {(row["hold"], row["point"]): row for row in result["responses"]}
    inner = result_rows["H1", "MID_I"]
    check(inner["phases"]["loaded"]["pairs"][0]["reference_row"] == "REF_A-21" and result["unassigned_readings"] == ["Q1-90"],
          "pairing 同刻配对及窗外留证")
    check(inner["loaded_um"] == -119 and inner["residual_um"] == 4 and result_rows["H1", "MID_O"]["residual_review"],
          "responses 驻载位移与撤载残余")
    found = next(row for row in result["repeats"] if row["case"] == "CENTER" and row["point"] == "MID_I")
    check(found["spread_um"] == 16 and found["review"], "repeats 同工况重复差")
    check(result["envelopes"][1]["low"]["value_um"] == -150 and result["envelopes"][1]["low"]["evidence"][0]["hold"] == "H3",
          "envelopes 有符号包络和控制证据")
    trace = get(f"{run}/trace?hold=H1&point=MID_I")
    check({item["id"] for item in trace["positions"]} == {"P11", "P12"} and len(trace["readings"]) == 18,
          "trace 回查原始行")
    outside = get(f"{run}/inventory?kind=reading&state=outside")
    page_two = get(f"{run}/inventory?kind=reading&page=2")
    check(outside["total"] == 1 and outside["rows"][0]["id"] == "Q1-90" and page_two["page"] == 2
          and page_two["rows"][0]["line"] > 51, "inventory 窗外行筛选及实源分页")
    first = post(f"{run}/release", {"revision": 0})
    check(first == post(f"{run}/release", {"revision": 0}), "release 同一代次签出幂等")
    change = dict(revision=0, kind="reading", row_id="REF_A-21", action="exclude", reason="演练排除参考行")
    post(f"{run}/review", change)
    post(f"{run}/review", change, 409)
    second = post(f"{run}/release", {"revision": 1})
    check(len(get(run)["journal"]) == 1 and first["id"] != second["id"], "review 附理由排除及旧代次冲突")
    post(f"{run}/review", dict(change, row_id="REF_A-24", revision=1))
    broken = get(run)["report"]
    blocked = {(row["hold"], row["point"]) for row in broken["responses"] if row["state"] == "coverage"}
    post(f"{run}/release", {"revision": 2}, 409)
    check(blocked == {("H1", "MID_I"), ("H1", "Q1")} and not broken["envelopes"][0]["complete"],
          "coverage 共享参考影响及缺证据阻断签出")
    post(f"{run}/review", dict(change, revision=2, row_id="REF_A-24", action="restore"))
    check(get(run)["report"]["ready"], "restore 恢复原始读数并重算")
    diff = get(f"/api/diff/{first['id']}/{second['id']}")
    check(next(row for row in diff["rows"] if row["hold"] == "H1" and row["point"] == "MID_I")["change"]["loaded_um"] == 1
          and len(get("/api/editions")) == 2, "compare 版本证据与数值差异")
    frozen_trace = get(f"/api/editions/{first['id']}/trace?hold=H1&point=MID_I")
    revised_trace = get(f"/api/editions/{second['id']}/trace?hold=H1&point=MID_I")
    check(frozen_trace["response"]["loaded_um"] == -119 and revised_trace["response"]["loaded_um"] == -118
          and "REF_A-21" in {row["id"] for row in frozen_trace["readings"]}
          and "REF_A-21" not in {row["id"] for row in revised_trace["readings"]}, "archive 签出版追溯使用相应代次的原始配对")
    edition, headers = request(url, f"/api/editions/{first['id']}/download")
    check(edition["digest"] == fingerprint(edition["document"]) == first["digest"] and edition["document"]["journal"] == []
          and headers["Content-Disposition"].startswith("attachment"), "download 历史版本独立下载及摘要")


def main():
    with temporary_server() as url:
        exercise(url)


if __name__ == "__main__":
    main()
