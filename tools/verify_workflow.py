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
    exercise_tickets(url, sample, get, post)


def reason_index(draft):
    return {kind: {row_id: items for row_id, items in rows.items()}
            for kind, rows in draft["active_reasons"].items()}


def exercise_tickets(url, sample, get, post):
    """整组排除、整单撤销、理由叠加与并发原子性。"""
    from threading import Barrier, Thread
    # 使用独立标签生成一份独立草稿，避免与主流程的裁定历史互相干扰。
    own = copy.deepcopy(sample)
    own["plan"]["label"] = f"{sample['plan']['label']} 故障单演练"
    created = post("/api/holds", own)
    check(created["created"], "ticket 独立草稿导入")
    run = f"/api/holds/{created['id']}"

    def exclude(ticket, revision, rows, reason, expected=200):
        return post(f"{run}/tickets/exclude",
                    dict(revision=revision, ticket=ticket, reason=reason, rows=rows), expected)

    def revoke(ticket, revision, reason, expected=200):
        return post(f"{run}/tickets/revoke",
                    dict(revision=revision, ticket=ticket, reason=reason), expected)

    ref = {"kind": "reading", "row_id": "REF_A-21"}
    ref24 = {"kind": "reading", "row_id": "REF_A-24"}
    # 甲单：两条共享参考 + 驻位 P11；乙单：同两条参考 + 驻位 P12。
    exclude("FT-A", 0, [ref, ref24, {"kind": "position", "row_id": "P11"}], "甲单理由")
    exclude("FT-B", 1, [ref, ref24, {"kind": "position", "row_id": "P12"}], "乙单理由")
    draft = get(run)
    check(draft["revision"] == 2, "ticket 整组排除各推进一次代次")
    reasons = reason_index(draft)
    check({item["ticket"] for item in reasons["reading"]["REF_A-21"]} == {"FT-A", "FT-B"}
          and {item["ticket"] for item in reasons["position"]["P11"]} == {"FT-A"}
          and {item["ticket"] for item in reasons["position"]["P12"]} == {"FT-B"}, "ticket 共享参考叠加多单理由")
    excluded = get(f"{run}/inventory?kind=reading&state=excluded")
    ref_row = next(row for row in excluded["rows"] if row["id"] == "REF_A-21")
    check([item["ticket"] for item in ref_row["reasons"]] == ["FT-A", "FT-B"], "inventory 每行可核对生效故障单理由")
    # 手工也排除同一参考：手工与故障单各自生效。
    post(f"{run}/review", dict(revision=2, kind="reading", row_id="REF_A-21",
                               action="exclude", reason="手工参考裁定"))
    # 撤甲：参考仍被乙单和手工排除；P11 恢复、P12 继续排除。
    revoke("FT-A", 3, "撤销甲单")
    draft = get(run)
    reasons = reason_index(draft)
    scopes = {(item["scope"], item.get("ticket")) for item in reasons["reading"]["REF_A-21"]}
    check(scopes == {("ticket", "FT-B"), ("manual", None)}
          and "P11" not in reasons["position"] and "P12" in reasons["position"], "ticket 撤甲后参考与乙单驻位仍排除")
    # 撤乙只恢复驻位；参考待手工恢复后才重新配对。
    revoke("FT-B", 4, "撤销乙单")
    draft = get(run)
    reasons = reason_index(draft)
    check("REF_A-21" in reasons["reading"] and "REF_A-24" not in reasons["reading"]
          and not reasons["position"], "ticket 撤乙只恢复驻位与乙单参考，手工参考仍排除")
    blocked = {(row["hold"], row["point"]) for row in draft["report"]["responses"] if row["state"] == "coverage"}
    check(not blocked, "ticket 仅剩一条手工参考排除时配对仍达标")
    # 手工补上 REF_A-24 后才缺覆盖，恢复两条手工参考后重新配对。
    post(f"{run}/review", dict(revision=5, kind="reading", row_id="REF_A-24",
                               action="exclude", reason="手工补排第二参考"))
    blocked = {(row["hold"], row["point"]) for row in get(run)["report"]["responses"] if row["state"] == "coverage"}
    check(blocked == {("H1", "MID_I"), ("H1", "Q1")}, "ticket 两条手工参考排除后配对缺口出现")
    post(f"{run}/review", dict(revision=6, kind="reading", row_id="REF_A-21",
                               action="restore", reason="手工恢复参考"))
    post(f"{run}/review", dict(revision=7, kind="reading", row_id="REF_A-24",
                               action="restore", reason="手工恢复参考"))
    check(get(run)["report"]["ready"], "ticket 手工恢复后重新配对并可签出")
    # 任一成员找不到则整次失败，代次不推进、不留部分成员。
    before = get(run)["revision"]
    post(f"{run}/tickets/exclude",
         dict(revision=before, ticket="FT-BAD", reason="x",
              rows=[{"kind": "position", "row_id": "P11"}, {"kind": "reading", "row_id": "MISSING-9"}]), 404)
    draft = get(run)
    check(draft["revision"] == before and all(item.get("ticket") != "FT-BAD" for item in draft["journal"]),
          "ticket 成员缺失整次失败不留部分成员")
    # 过期代次与状态冲突。
    post(f"{run}/tickets/exclude",
         dict(revision=before - 1, ticket="FT-OLD", reason="x", rows=[{"kind": "position", "row_id": "P11"}]), 409)
    exclude("FT-LIVE", before, [{"kind": "position", "row_id": "P11"}], "生效单")
    post(f"{run}/tickets/exclude",
         dict(revision=before + 1, ticket="FT-LIVE", reason="x", rows=[{"kind": "position", "row_id": "P12"}]), 409)
    post(f"{run}/tickets/revoke", dict(revision=before + 1, ticket="FT-GONE", reason="x"), 404)
    # 撤销后可重新立单，重新推进代次。
    revoke("FT-LIVE", before + 1, "先撤销")
    check("P11" not in reason_index(get(run))["position"], "ticket 撤销后驻位恢复")
    out = exclude("FT-LIVE", before + 2, [{"kind": "position", "row_id": "P12"}], "重新立单")
    check(out["revision"] == before + 3, "ticket 撤销后允许重新整组排除")
    revoke("FT-LIVE", before + 3, "再撤销")
    # 签出冻结含故障单的裁定流水，旧签件仍可回查生效理由。
    ticket_rev = get(run)["revision"]
    exclude("FT-FREEZE", ticket_rev, [ref, ref24], "签出前故障单")
    frozen_rev = ticket_rev + 1
    post(f"{run}/release", {"revision": frozen_rev}, 409)
    # 恢复后签出，确认签出版冻结在恢复代次且保留完整故障单历史。
    revoke("FT-FREEZE", frozen_rev, "恢复以便签出")
    ready_rev = frozen_rev + 1
    edition = post(f"{run}/release", {"revision": ready_rev})
    archived = get(f"/api/editions/{edition['id']}/trace?hold=H1&point=MID_I")
    check("exclusion_reasons" in archived, "archive 签出证据可核对有效理由")
    downloaded = get(f"/api/editions/{edition['id']}")["document"]
    check(any(item.get("scope") == "ticket" for item in downloaded["journal"])
          and downloaded["revision"] == ready_rev, "archive 签出包冻结故障单裁定历史")
    # 并发到达的同代次整单：只允许一个生效，另一个 409，无部分成员。
    base = get(run)["revision"]
    barrier = Barrier(2)
    results = []

    def worker(ticket):
        barrier.wait()
        try:
            results.append(post(f"{run}/tickets/exclude",
                                dict(revision=base, ticket=ticket, reason="并发",
                                     rows=[{"kind": "position", "row_id": "P11"},
                                           {"kind": "position", "row_id": "P12"}]), 200))
        except RuntimeError as exc:
            results.append(exc)

    threads = [Thread(target=worker, args=(name,)) for name in ("FT-C1", "FT-C2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ok = [item for item in results if not isinstance(item, Exception)]
    failed = [item for item in results if isinstance(item, Exception)]
    draft = get(run)
    live = {item.get("ticket") for kind in draft["active_reasons"].values() for row in kind.values()
            for item in row if item.get("scope") == "ticket"}
    check(len(ok) == 1 and len(failed) == 1 and draft["revision"] == base + 1
          and live in ({"FT-C1"}, {"FT-C2"}) and len(live) == 1, "ticket 并发整单原子生效、过期者不留部分成员")


def main():
    with temporary_server() as url:
        exercise(url)


if __name__ == "__main__":
    main()
