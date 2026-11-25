import json
import re
from urllib.parse import parse_qs

from .archived_trace import edition_trace
from .compare import compare_editions
from .draft import inspect_draft, materialize
from .editions import list_editions, read_edition, release
from .errors import Rejected
from .intake import parse_survey
from .inventory import inventory
from .retest_reduction import reduce_with_retests
from .retests import adjudicate_retest, confirm, load_retests, load_substitutions, register, retest_exclusions, retest_votes
from .review import adjudicate, exclusions
from .runs import list_runs, snapshot, submit
from .trace import explain, explain_extended
from .validation import key


def trace_coordinates(params):
    hold = key(params.get("hold", [None])[0], "轮次号")
    point = key(params.get("point", [None])[0], "测点号")
    return hold, point


class API:
    def __init__(self, store):
        self.store = store

    def _plan(self, row):
        source = row["source"]
        if isinstance(source, str):
            source = json.loads(source)
        return parse_survey(source).plan

    def _solution(self, db, row):
        """供替补确认使用：在当前事务快照上重算强制归属。"""
        source = row["source"]
        if isinstance(source, str):
            source = json.loads(source)
        survey = parse_survey(source)
        records = load_retests(db, row["id"])
        base_events = [dict(event) for event in
                       db.execute("SELECT kind, row_id, action FROM girder_votes WHERE run = ?", (row["id"],))]
        base_excluded = exclusions(base_events)
        retest_excluded = retest_exclusions(retest_votes(db, row["id"]))
        confirmed = load_substitutions(db, row["id"])
        report = reduce_with_retests(survey, survey.plan, records, base_excluded, retest_excluded, confirmed)
        return report["obligations"]

    def read(self, path, query):
        if path == "/api/holds":
            return list_runs(self.store), None
        if path == "/api/editions":
            return list_editions(self.store), None
        match = re.fullmatch(r"/api/holds/([1-9][0-9]{0,14})(/trace|/inventory)?", path)
        if match:
            run = int(match[1])
            if not match[2]:
                return inspect_draft(self.store, run), None
            params = parse_qs(query, keep_blank_values=True, max_num_fields=8)
            if match[2] == "/inventory":
                row, journal = snapshot(self.store, run)
                result = inventory(parse_survey(row["source"]), journal, params)
                return result | {"revision": row["revision"]}, None
            hold, point = trace_coordinates(params)
            row, _, survey, report, _ = materialize(self.store, run)
            if hold in report["placement"]:
                result = explain(survey, report, hold, point)
            else:
                result = explain_extended(self.store, run, survey, report, hold, point)
            return result | {"revision": row["revision"]}, None
        match = re.fullmatch(r"/api/editions/([1-9][0-9]{0,14})(/download|/trace)?", path)
        if match:
            edition = int(match[1])
            if match[2] == "/trace":
                params = parse_qs(query, keep_blank_values=True, max_num_fields=8)
                hold, point = trace_coordinates(params)
                return edition_trace(self.store, edition, hold, point), None
            filename = f"girder-edition-{edition}.json" if match[2] else None
            return read_edition(self.store, edition), filename
        match = re.fullmatch(r"/api/diff/([1-9][0-9]{0,14})/([1-9][0-9]{0,14})", path)
        if match:
            return compare_editions(self.store, int(match[1]), int(match[2])), None
        raise Rejected("找不到数据入口", 404)

    def write(self, path, data):
        if path == "/api/holds":
            return submit(self.store, data)
        match = re.fullmatch(
            r"/api/holds/([1-9][0-9]{0,14})/(review|release|retests|retest-review|substitutions)", path)
        if match:
            run = int(match[1])
            action = match[2]
            if action == "review":
                return adjudicate(self.store, run, data)
            if action == "release":
                return release(self.store, run, data)
            if action == "retests":
                return register(self.store, run, data, self._plan)
            if action == "retest-review":
                return adjudicate_retest(self.store, run, data)
            return confirm(self.store, run, data, self._solution)
        raise Rejected("找不到数据入口", 404)
