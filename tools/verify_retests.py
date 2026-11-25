"""补测登记与替补履约的端到端工作流核对（临时库 + 回环服务）。"""
import json
import tempfile
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from girder.httpd import Server
from girder.store import Store

CHANNELS = ["REF_A", "REF_B", "Q1", "MID_I", "MID_O"]


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
            raise AssertionError(f"{path}: HTTP {response.status}；预期 {expected}。{raw[:300]!r}")
        return json.loads(raw) if response.headers.get_content_type() == "application/json" else raw


def check(condition, label):
    if not condition:
        raise AssertionError(f"补测工作流核对失败：{label}")
    print(f"通过  {label}")


def retest_payload(retest_id, case, offset, *, lane="L1", bad_placement=False):
    """合成一轮完整补测：三相各三个同刻配对，驻位与总质量合格。"""
    base_ticks = [(1, 4, 7), (21, 24, 27), (41, 44, 47)]
    rows = []
    for phase, ticks in enumerate(base_ticks):
        for tick in ticks:
            for channel in CHANNELS:
                rows.append(f"{retest_id}-{channel}-{tick + offset},{channel},{tick + offset},{60 + phase * 20}")
    readings = "id,channel,tick,value_um\n" + "\n".join(rows) + "\n"
    lane_use = "L9" if bad_placement else lane
    positions = ("id,hold,axle,lane,station_mm,mass_kg\n"
                 f"RP-{retest_id}-F,{retest_id},AX_F,{lane_use},10110,8300\n"
                 f"RP-{retest_id}-R,{retest_id},AX_R,{lane_use},13790,9700\n")
    return dict(id=retest_id, label=f"补测{retest_id}", case=case,
                before=[offset, offset + 10], loaded=[offset + 20, offset + 30],
                after=[offset + 40, offset + 50], positions=positions, readings=readings)


def break_hold(url, root, revision, rows, reason):
    """连续排除若干采样行以击穿某轮驻载相（最低配对数 2）。"""
    for row_id in rows:
        request(url, f"{root}/review", dict(revision=revision, kind="reading", row_id=row_id,
                                            action="exclude", reason=reason))
        revision += 1
    return revision


def exercise(url):
    sample = request(url, "/example")
    created = request(url, "/api/holds", sample)
    run = created["id"]
    root = f"/api/holds/{run}"

    # 基线：无补测时沿用 v1 合同且可签出
    draft = request(url, root)
    check(draft["report"]["contract"] == "hold-reduction-v1" and draft["report"]["ready"], "baseline 无补测沿用 v1 归约")

    # 制造 H1 缺证义务（H2/H3 仍合格自行履约）
    revision = break_hold(url, root, 0, ["REF_A-21", "REF_A-24"], "制造H1缺证")
    check(revision == 2, "review 两次排除推进两个代次")
    blocked = request(url, root)["report"]
    check(not blocked["ready"], "obligation 缺证原轮在无补测时阻断签出")

    # 登记同工况（CENTER）合格补测 R1
    request(url, f"{root}/retests", dict(retest_payload("R1", "CENTER", 300), revision=revision))
    revision += 1
    report = request(url, root)["report"]
    check([o["hold"] for o in report["obligations"]["missing"]] == ["H1"], "obligation 缺证原轮成为待履行义务")
    check(report["contract"] == "hold-reduction-v2", "v2 一旦存在补测登记即启用新合同")
    check(report["retests"][0]["retest_id"] == "R1" and report["retests"][0]["qualified"]
          and report["obligations"]["eligible_edges"] == {"H1": ["R1"]}, "retest-register 同工况整轮合格补测入库")
    check(report["obligations"]["forced"] == {"H1": "R1"} and report["obligations"]["max_fill"] == 1,
          "forced 单项义务与唯一合格补测构成强制归属")
    check(not report["ready"], "pending 未确认归属前仍不可签出")
    request(url, f"{root}/release", {"revision": revision}, expected=409)

    # 非强制/无资格配对须拒绝；强制边可确认
    request(url, f"{root}/substitutions",
            dict(revision=revision, hold="H1", retest_id="NOPE", reason="x"), expected=409)
    request(url, f"{root}/substitutions",
            dict(revision=revision, hold="H1", retest_id="R1", reason="负责人确认R1补H1"))
    revision += 1
    report = request(url, root)["report"]
    check(report["ready"] and report["obligations"]["confirmed"][0]["retest_id"] == "R1",
          "confirm 强制归属确认后义务落实")

    # 重复差按原轮义务归约；包络控制值可追溯到实测轮
    center = next(row for row in report["repeats"] if row["case"] == "CENTER" and row["point"] == "MID_I")
    check("R1" not in center["holds"] and "H1" in center["holds"] and "H2" in center["holds"],
          "repeats 重复差按原轮义务归约，不出现补测轮号")
    envelope = report["envelopes"][1]
    origins = {entry["origin"] for edge in (envelope["low"], envelope["high"]) if edge for entry in edge["evidence"]}
    check("R1" in origins, "envelope 包络控制值可追溯到实测补测轮")
    effective = next(row for row in report["effective_responses"]
                     if row["hold"] == "H1" and row["point"] == "MID_I")
    check(effective["origin"] == "R1" and effective["fulfillment"] == "retest",
          "effective 替补响应记录当代归属")

    # 追溯补测轮原始证据（带 scope，供前端路由补测裁定）
    trace = request(url, f"{root}/trace?hold=R1&point=MID_I")
    check(any(item["id"].startswith("R1-") for item in trace["readings"]), "trace 补测轮回查原始采样")
    check(all(item["scope"] == "retest" and item["retest_id"] == "R1" for item in trace["readings"])
          and all(item["scope"] == "retest" for item in trace["positions"]),
          "trace-scope 补测证据标记来源轮次")
    base_trace = request(url, f"{root}/trace?hold=H2&point=MID_I")
    check(all(item["scope"] == "base" for item in base_trace["readings"]), "trace-scope 原计划轮证据保持 base 来源")

    # 签出冻结；之后新的裁定不改变旧签件
    edition = request(url, f"{root}/release", {"revision": revision})
    revision = break_hold(url, root, revision, ["REF_B-24"], "签出后再裁定")
    package = request(url, f"/api/editions/{edition['id']}")
    doc = package["document"]
    check(doc["report"]["obligations"]["confirmed"][0]["retest_id"] == "R1"
          and doc["retest_records"][0]["retest_id"] == "R1", "freeze 签件保留补测登记与当代归属")
    frozen = request(url, f"/api/editions/{edition['id']}/trace?hold=R1&point=MID_I")
    check(any(item["id"].startswith("R1-") for item in frozen["readings"]), "archive 补测证据随签件冻结可追溯")
    request(url, f"{root}/review", dict(revision=revision, kind="reading", row_id="REF_B-24",
                                        action="restore", reason="恢复"))
    revision += 1

    # 第二版签出并与含补测归属的旧版比对：有效义务按原轮号对齐，归属未变则无差异
    edition_two = request(url, f"{root}/release", {"revision": revision})
    diff = request(url, f"/api/diff/{edition['id']}/{edition_two['id']}")
    check(len(diff["rows"]) == len(request(url, root)["report"]["effective_responses"])
          and all(row["origin_before"] == row["origin_after"] for row in diff["rows"]),
          "diff-v2 两份 v2 签出版按已落实义务对齐并保留实测轮归属")

    # 晚到且未采用的补测：驻位不合格，不入重复观测，也不阻止齐全签出
    request(url, f"{root}/retests",
            dict(retest_payload("R9", "CENTER", 400, bad_placement=True), revision=revision))
    report = request(url, root)["report"]
    check(not report["retests"][1]["qualified"] and not report["retests"][1]["adopted"],
          "late 不合格补测不具资格")
    check(all("R9" not in row["holds"] for row in report["repeats"]) and report["ready"],
          "unadopted 未采用补测不新增重复观测且不阻断签出")


def exercise_ambiguity(url):
    """两项缺证、两个同工况补测：K2,2 无强制边，整次不能签出。"""
    run = request(url, "/api/holds", request(url, "/example"))["id"]
    root = f"/api/holds/{run}"
    revision = break_hold(url, root, 0, ["REF_A-21", "REF_A-24"], "H1缺证")
    revision = break_hold(url, root, revision, ["REF_A-121", "REF_A-124"], "H2缺证")
    request(url, f"{root}/retests", dict(retest_payload("R1", "CENTER", 300), revision=revision))
    revision += 1
    request(url, f"{root}/retests", dict(retest_payload("R2", "CENTER", 400), revision=revision))
    revision += 1
    obligations = request(url, root)["report"]["obligations"]
    check(obligations["max_fill"] == 2 and obligations["forced"] == {},
          "ambiguous 两个补测均能替两轮时无强制归属")
    check(sorted(obligations["eligible_edges"]) == ["H1", "H2"], "edges 两项义务同工况连通")
    request(url, f"{root}/substitutions",
            dict(revision=revision, hold="H1", retest_id="R1", reason="尝试确认非强制边"), expected=409)
    request(url, f"{root}/release", {"revision": revision}, expected=409)

def exercise_shortage(url):
    """补测不足：最多补一项，另一项持续缺失，整次不能签出。"""
    run2 = request(url, "/api/holds", request(url, "/example"))["id"]
    root2 = f"/api/holds/{run2}"
    revision2 = break_hold(url, root2, 0, ["REF_A-21", "REF_A-24"], "H1缺证")
    revision2 = break_hold(url, root2, revision2, ["REF_A-121", "REF_A-124"], "H2缺证")
    request(url, f"{root2}/retests", dict(retest_payload("R1", "CENTER", 300), revision=revision2))
    short = request(url, root2)["report"]["obligations"]
    check(short["max_fill"] == 1 and short["outstanding"] == ["H2"] and short["forced"] == {},
          "shortage 单补测面对两项义务归属不唯一且留下缺项")
    request(url, f"{root2}/release", {"revision": revision2 + 1}, expected=409)


def exercise_case_isolation(url):
    """跨工况隔离：CENTER 补测不能替 EDGE（H3）义务。"""
    run3 = request(url, "/api/holds", request(url, "/example"))["id"]
    root3 = f"/api/holds/{run3}"
    revision3 = break_hold(url, root3, 0, ["REF_A-221", "REF_A-224"], "H3缺证")
    request(url, f"{root3}/retests", dict(retest_payload("R1", "CENTER", 300), revision=revision3))
    isolated = request(url, root3)["report"]["obligations"]
    check(isolated["eligible_edges"] == {"H3": []}
          and [item["hold"] for item in isolated["missing"]] == ["H3"]
          and isolated["outstanding"] == ["H3"],
          "case-isolation 不同工况补测无资格替代")


def exercise_exclusion(url):
    """补测行被排除后丧失资格，恢复后重新具备资格；代次冲突返回 409。"""
    run = request(url, "/api/holds", request(url, "/example"))["id"]
    root = f"/api/holds/{run}"
    revision = break_hold(url, root, 0, ["REF_A-21", "REF_A-24"], "H1缺证")
    request(url, f"{root}/retests", dict(retest_payload("R1", "CENTER", 300), revision=revision))
    revision += 1
    row_ids = ["R1-MID_I-321", "R1-MID_I-324"]
    request(url, f"{root}/retest-review",
            dict(revision=revision, retest_id="R1", kind="retest_reading", row_id=row_ids[0],
                 action="exclude", reason="补测采样异常1"))
    revision += 1
    request(url, f"{root}/retest-review",
            dict(revision=revision, retest_id="R1", kind="retest_reading", row_id=row_ids[1],
                 action="exclude", reason="补测采样异常2"))
    revision += 1
    report = request(url, root)["report"]
    check(not report["retests"][0]["qualified"] and report["obligations"]["eligible_edges"] == {"H1": []},
          "retest-exclude 排除补测整相有效证据后整轮丧失资格")
    request(url, f"{root}/retest-review",
            dict(revision=revision - 2, retest_id="R1", kind="retest_reading", row_id=row_ids[0],
                 action="exclude", reason="过期"), expected=409)
    for row_id in reversed(row_ids):
        request(url, f"{root}/retest-review",
                dict(revision=revision, retest_id="R1", kind="retest_reading", row_id=row_id,
                     action="restore", reason="复核有效"))
        revision += 1
    report = request(url, root)["report"]
    check(report["retests"][0]["qualified"] and report["obligations"]["forced"] == {"H1": "R1"},
          "retest-restore 恢复补测行后资格与强制边恢复")


def exercise_broken_confirmation(url):
    """确认归属后补测又被裁定失效：签出重新被阻断，工作台暴露失效归属。"""
    run = request(url, "/api/holds", request(url, "/example"))["id"]
    root = f"/api/holds/{run}"
    revision = break_hold(url, root, 0, ["REF_A-21", "REF_A-24"], "H1缺证")
    request(url, f"{root}/retests", dict(retest_payload("R1", "CENTER", 300), revision=revision))
    revision += 1
    request(url, f"{root}/substitutions",
            dict(revision=revision, hold="H1", retest_id="R1", reason="确认归属"))
    revision += 1
    check(request(url, root)["report"]["ready"], "broken 确认后原本可签出")
    for row_id in ["R1-MID_I-321", "R1-MID_I-324"]:
        request(url, f"{root}/retest-review",
                dict(revision=revision, retest_id="R1", kind="retest_reading", row_id=row_id,
                     action="exclude", reason="裁定补测失效"))
        revision += 1
    report = request(url, root)["report"]
    check(not report["ready"] and report["obligations"]["broken_confirmations"] == ["H1"]
          and report["obligations"]["outstanding"] == ["H1"],
          "broken 已确认补测失效后义务重回缺失并阻断签出")
    request(url, f"{root}/release", {"revision": revision}, expected=409)


def main():
    # 相同演练输入会按摘要复用同一 run，故各场景使用独立数据库。
    scenarios = [exercise, exercise_ambiguity, exercise_shortage, exercise_case_isolation,
                 exercise_exclusion, exercise_broken_confirmation]
    for scenario in scenarios:
        with tempfile.TemporaryDirectory(prefix="girder-retest-") as folder:
            with Server(("127.0.0.1", 0), Store(Path(folder) / "retest.sqlite")) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                scenario(f"http://127.0.0.1:{server.server_port}")
                server.shutdown()
                worker.join()
    print("全部补测工作流核对通过")


if __name__ == "__main__":
    main()
