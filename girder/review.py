from .errors import Rejected
from .intake import parse_survey
from .runs import require_revision, snapshot
from .validation import fields, key, number, text

KINDS = ("position", "reading")


def is_manual(event):
    return event.get("scope", "manual") == "manual"


def manual_state(journal):
    """每个原始行最近一次手工裁定的状态；手工与故障单各自独立生效。"""
    state = {"position": {}, "reading": {}}
    for event in journal:
        if is_manual(event):
            state[event["kind"]][event["row_id"]] = event["action"]
    return state


def active_tickets(journal):
    """故障单号 -> 当前生效批次的逐行事件（整单撤销后不出现于映射）。"""
    state = {}
    for event in journal:
        if event.get("scope") != "ticket":
            continue
        ticket = event["ticket"]
        if event["action"] == "exclude":
            state.setdefault(ticket, {})["exclude"] = event["revision"]
        else:
            state.setdefault(ticket, {})["restore"] = event["revision"]
    active = {ticket: revisions["exclude"] for ticket, revisions in state.items()
              if revisions.get("exclude", -1) > revisions.get("restore", -1)}
    if not active:
        return {}
    latest = {}
    for event in journal:
        if event.get("scope") == "ticket" and event["action"] == "exclude" \
                and active.get(event["ticket"]) == event["revision"]:
            latest.setdefault(event["ticket"], []).append(event)
    return latest


def effective_reasons(journal):
    """返回 kind -> row_id -> 仍生效的理由列表（手工与每张故障单各占一条）。"""
    reasons = {"position": {}, "reading": {}}
    manual = manual_state(journal)
    for event in journal:
        if is_manual(event) and event["action"] == "exclude" \
                and manual[event["kind"]].get(event["row_id"]) == "exclude":
            reasons[event["kind"]].setdefault(event["row_id"], []).append(
                dict(scope="manual", reason=event["reason"], revision=event["revision"]))
    for ticket, events in active_tickets(journal).items():
        for event in events:
            reasons[event["kind"]].setdefault(event["row_id"], []).append(
                dict(scope="ticket", ticket=ticket, reason=event["reason"], revision=event["revision"]))
    return reasons


def exclusions(events):
    """归约只关心当前仍被排除的行号集合。"""
    groups = {"position": set(), "reading": set()}
    reasons = effective_reasons(events)
    for kind in KINDS:
        groups[kind] = set(reasons[kind])
    return groups


def _survey_rows(survey, kind):
    return survey.positions if kind == "position" else survey.readings


def _bump_and_append(store, run, expected, entries):
    """同一事务内推进一次代次并写入整组事件；任一行缺失则整次失败、不留部分成员。"""
    with store.transaction(write=True) as db:
        if db.execute("UPDATE girder_runs SET revision = revision + 1 WHERE id = ? AND revision = ?",
                      (run, expected)).rowcount != 1:
            raise Rejected("草稿已变化，请刷新后重试", 409)
        for seq, entry in enumerate(entries):
            db.execute("INSERT INTO girder_journal "
                       "(run, revision, seq, scope, ticket, kind, row_id, action, reason) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (run, expected + 1, seq, entry["scope"], entry.get("ticket"),
                        entry["kind"], entry["row_id"], entry["action"], entry["reason"]))
    return {"id": run, "revision": expected + 1}


def adjudicate(store, run, data):
    fields(data, "revision kind row_id action reason", "裁定")
    expected = number(data["revision"], "草稿代次")
    kind, action = data["kind"], data["action"]
    if kind not in KINDS or action not in ("exclude", "restore"):
        raise Rejected("只可排除或恢复驻位行和采样行")
    identity = key(data["row_id"], "原始行号")
    reason = text(data["reason"], "裁定理由", 160)
    row, journal = snapshot(store, run)
    require_revision(row, expected)
    survey = parse_survey(row["source"])
    if identity not in _survey_rows(survey, kind):
        raise Rejected("找不到该原始行", 404)
    if manual_state(journal)[kind].get(identity) == action:
        raise Rejected("该原始行已处在所请求的手工状态", 409)
    return _bump_and_append(store, run, expected,
                            [dict(scope="manual", kind=kind, row_id=identity, action=action, reason=reason)])


def parse_members(data, survey):
    raw = data.get("rows")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 16000:
        raise Rejected("故障单须包含 1 至 16000 个成员")

    def parse(item):
        if not isinstance(item, dict) or item.keys() != {"kind", "row_id"}:
            raise Rejected("故障单成员须包含 kind 和 row_id")
        kind = item["kind"]
        if kind not in KINDS:
            raise Rejected("故障单成员只可是驻位行或采样行")
        identity = key(item["row_id"], "原始行号")
        if identity not in _survey_rows(survey, kind):
            raise Rejected(f"故障单成员找不到原始行：{kind}/{identity}", 404)
        return kind, identity

    members = [parse(item) for item in raw]
    if len(set(members)) != len(members):
        raise Rejected("故障单成员不得重复")
    return members


def ticket_exclude(store, run, data):
    fields(data, "revision ticket reason rows", "故障单整组排除")
    expected = number(data["revision"], "草稿代次")
    ticket = key(data["ticket"], "故障单号")
    reason = text(data["reason"], "故障单理由", 160)
    row, journal = snapshot(store, run)
    require_revision(row, expected)
    if ticket in active_tickets(journal):
        raise Rejected("该故障单仍在生效，须先整单撤销", 409)
    survey = parse_survey(row["source"])
    members = parse_members(data, survey)
    entries = [dict(scope="ticket", ticket=ticket, kind=kind, row_id=identity,
                    action="exclude", reason=reason) for kind, identity in members]
    return _bump_and_append(store, run, expected, entries)


def ticket_revoke(store, run, data):
    fields(data, "revision ticket reason", "故障单整单撤销")
    expected = number(data["revision"], "草稿代次")
    ticket = key(data["ticket"], "故障单号")
    reason = text(data["reason"], "撤销理由", 160)
    row, journal = snapshot(store, run)
    require_revision(row, expected)
    batch = active_tickets(journal).get(ticket)
    if not batch:
        raise Rejected("找不到仍在生效的该故障单", 404)
    # 撤销只解除本故障单这一批理由；手工裁定和其他故障单继续独立生效。
    entries = [dict(scope="ticket", ticket=ticket, kind=event["kind"], row_id=event["row_id"],
                    action="restore", reason=reason) for event in sorted(batch, key=lambda item: item["seq"])]
    return _bump_and_append(store, run, expected, entries)
