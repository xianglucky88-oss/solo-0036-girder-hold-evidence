import re
from urllib.parse import parse_qs

from .archived_trace import edition_trace
from .compare import compare_editions
from .draft import inspect_draft, materialize
from .editions import list_editions, read_edition, release
from .errors import Rejected
from .intake import parse_survey
from .inventory import inventory
from .review import adjudicate
from .runs import list_runs, snapshot, submit
from .trace import explain
from .validation import key


def trace_coordinates(params):
    hold = key(params.get("hold", [None])[0], "轮次号")
    point = key(params.get("point", [None])[0], "测点号")
    return hold, point


class API:
    def __init__(self, store):
        self.store = store

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
            row, _, survey, report = materialize(self.store, run)
            return explain(survey, report, hold, point) | {"revision": row["revision"]}, None
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
        match = re.fullmatch(r"/api/holds/([1-9][0-9]{0,14})/(review|release)", path)
        if match:
            action = adjudicate if match[2] == "review" else release
            return action(self.store, int(match[1]), data)
        raise Rejected("找不到数据入口", 404)
