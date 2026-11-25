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


def exercise_graded(url):
    get = lambda path: request(url, path)[0]
    post = lambda path, body, expected=200: request(url, path, body, expected)[0]

    sample = get("/example-graded")
    created = post("/api/holds", sample)
    run = f"/api/holds/{created['id']}"
    draft = get(run)
    report = draft["report"]
    graded = report["graded"]
    check(graded is not None and graded["id"] == "G1" and len(graded["steps"]) == 5,
          "graded 连续分级过程登记")
    check([point["first_empty_um"] for point in graded["points"]] == [2, 2, 2]
          and [point["final_empty_um"] for point in graded["points"]] == [3, 3, 3]
          and [point["residual_um"] for point in graded["points"]] == [1, 1, 1],
          "graded 共用零点与整次残余")
    low = next(row for row in graded["contrasts"] if row["level"] == "LOW")
    high = next(row for row in graded["contrasts"] if row["level"] == "HIGH")
    check(low["forward"] == "L_UP" and low["back"] == "L_BACK"
          and low["contrast_tolerance_kg"] == 200 and low["mass_delta_kg"] == 200 and low["state"] == "valid",
          "graded 同级指定去回台阶与对照容差")
    low_row = next(row for row in low["points"] if row["point"] == "MID_I")
    check(low_row["forward_displacement_um"] == 16 and low_row["back_displacement_um"] == 19
          and low_row["difference_um"] == 3 and low_row["residual_um"] == 1,
          "graded 有符号回程差与整次残余")
    check(all(row["difference_um"] == 4 for row in high["points"]) and report["ready"],
          "graded 高级回程差")
    check(report["step_placement"]["L_UP"]["total_kg"] == 19900
          and report["step_placement"]["L_BACK"]["total_kg"] == 20100,
          "graded 去回实测总质量")

    trace = get(f"{run}/trace?hold=G1&point=MID_I")
    check(trace["graded"] == "G1" and len(trace["first_empty"]["phases"]["pairs"]) == 2
          and len(trace["steps"]) == 5 and len(trace["contrasts"]) == 2 and len(trace["positions"]) == 10,
          "graded trace 驻位与公共空载配对")
    check(all(row["adopted"] for row in trace["contrasts"]), "graded trace 采用的去回证据")

    post(f"{run}/review", dict(revision=0, kind="reading", row_id="REF_A-1", action="exclude",
                               reason="分级公共空载参考行演练排除"))
    broken = get(run)["report"]
    check(not broken["ready"]
          and {(item["point"]) for item in broken["graded"]["missing"] if item["kind"] == "empty_coverage"}
          == {"Q1", "MID_I"},
          "graded 首空载公共窗缺配对阻止签出")
    post(f"{run}/release", {"revision": 1}, 409)
    restored = post(f"{run}/review", dict(revision=1, kind="reading", row_id="REF_A-1", action="restore",
                                          reason="恢复公共空载参考行"))
    check(restored["revision"] == 2 and get(run)["report"]["ready"], "graded 恢复后同代次重算")

    edition = post(f"{run}/release", {"revision": 2})
    archived = get(f"/api/editions/{edition['id']}/trace?hold=G1&point=MID_I")
    check(archived["graded"] == "G1" and archived["response"]["residual_um"] == 1
          and {row["id"] for row in archived["readings"]}.issuperset({"REF_A-1", "REF_A-4"})
          and archived["first_empty"]["phases"]["pair_count"] == 2, "graded 签件回溯逐轴驻位与公共空载")

    heavy = copy.deepcopy(sample)
    heavy["positions"] = heavy["positions"].replace("L_BACKR,L_BACK,AX_R,L1,13800,10050",
                                                    "L_BACKR,L_BACK,AX_R,L1,13800,10250")
    heavy_run = f"/api/holds/{post('/api/holds', heavy)['id']}"
    heavy_report = get(heavy_run)["report"]
    heavy_low = next(row for row in heavy_report["graded"]["contrasts"] if row["level"] == "LOW")
    heavy_high = next(row for row in heavy_report["graded"]["contrasts"] if row["level"] == "HIGH")
    check(heavy_low["state"] == "mass" and heavy_low["mass_delta_kg"] == 400
          and all(row["difference_um"] is None for row in heavy_low["points"])
          and heavy_high["state"] == "valid" and heavy_high["mass_delta_kg"] == 0,
          "graded 单台阶合格但对照超差只缺该级")
    post(f"{heavy_run}/release", {"revision": 0}, 409)
    heavy_trace = get(f"{heavy_run}/trace?hold=G1&point=MID_I")
    check(any(not row["adopted"] for row in heavy_trace["contrasts"] if row["level"] == "LOW")
          and any(row["adopted"] for row in heavy_trace["contrasts"] if row["level"] == "HIGH"),
          "graded 缺失对照留证且已成立高级可查")

    substituted = copy.deepcopy(sample)
    substituted["plan"]["graded"]["contrasts"][0]["forward"] = "PEAK"
    post("/api/holds", substituted, 400)
    adjacent = copy.deepcopy(sample)
    adjacent["plan"]["graded"]["contrasts"][0]["back"] = "H_BACK"
    post("/api/holds", adjacent, 400)
    check(True, "graded 峰值与邻级不得顶替去回台阶")

    ownership = get(f"{heavy_run}/inventory?kind=reading&match=L_BACK")
    check(ownership["rows"] and all(row["scope"] == "graded" and row["owner"] == "G1"
                                    and row["phase_label"].startswith("LOW") for row in ownership["rows"]),
          "graded inventory 原行归属分级台阶")


def main():
    with temporary_server() as url:
        exercise(url)
    with temporary_server() as url:
        exercise_graded(url)


if __name__ == "__main__":
    main()
