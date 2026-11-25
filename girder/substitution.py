from collections import deque

# 义务（缺证原轮）与合格补测轮之间的同工况二分匹配。
# 先求最大基数匹配（最多补齐项），再在交替有向图上判定在每一最大匹配中
# 都由同一补测轮承担的强制边，即归属唯一、可由负责人确认的边。


def build_edges(obligations, retests):
    """obligations/retests 均为 (id, case) 序列，返回 {obligation: [retest, ...]}。"""
    by_case = {}
    for retest_id, case in retests:
        by_case.setdefault(case, []).append(retest_id)
    edges = {}
    for hold_id, case in obligations:
        edges[hold_id] = sorted(by_case.get(case, ()))
    return edges


def hopcroft_karp(edges):
    """返回最大匹配 {obligation: retest}。"""
    left = sorted(edges)
    pair_left = {hold: None for hold in left}
    pair_right = {}
    dist = {}

    def bfs():
        queue = deque()
        for hold in left:
            if pair_left[hold] is None:
                dist[hold] = 0
                queue.append(hold)
            else:
                dist[hold] = None
        found = False
        while queue:
            hold = queue.popleft()
            for retest in edges[hold]:
                owner = pair_right.get(retest)
                if owner is None:
                    found = True
                elif dist[owner] is None:
                    dist[owner] = dist[hold] + 1
                    queue.append(owner)
        return found

    def dfs(hold):
        for retest in edges[hold]:
            owner = pair_right.get(retest)
            if owner is None or (dist[owner] == dist[hold] + 1 and dfs(owner)):
                pair_left[hold] = retest
                pair_right[retest] = hold
                return True
        dist[hold] = None
        return False

    while bfs():
        for hold in left:
            if pair_left[hold] is None:
                dfs(hold)
    return {hold: retest for hold, retest in pair_left.items() if retest is not None}


def _alternating_graph(edges, matching):
    """构造交替有向图：非匹配边 L->R，匹配边 R->L。节点为 ("L", id)/("R", id)。"""
    graph = {}
    for hold, candidates in edges.items():
        left = ("L", hold)
        graph.setdefault(left, [])
        for retest in candidates:
            right = ("R", retest)
            graph.setdefault(right, [])
            if matching.get(hold) == retest:
                graph[right].append(left)
            else:
                graph[left].append(right)
    return graph


def _components(graph):
    """Tarjan 强连通分量，返回 {node: component_index}。"""
    index = {}
    low = {}
    stack = []
    on_stack = set()
    counter = 0
    component = {}
    component_count = 0

    def visit(node):
        nonlocal counter, component_count
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in graph.get(node, ()):
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component[member] = component_count
                if member == node:
                    break
            component_count += 1

    for node in graph:
        if node not in index:
            visit(node)
    return component


def forced_edges(edges, matching):
    """求在每一最大匹配中都出现的边。

    匹配边 (L, R) 非强制，当且仅当它位于交替环（L、R 同 SCC）上，
    或可从自由左点沿交替有向图到达 R（换配后仍为最大匹配）。
    """
    graph = _alternating_graph(edges, matching)
    component = _components(graph)

    reachable = set()
    queue = deque(("L", hold) for hold in edges if matching.get(hold) is None)
    for node in queue:
        reachable.add(node)
    while queue:
        node = queue.popleft()
        for nxt in graph.get(node, ()):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)

    result = {}
    for hold, retest in matching.items():
        left, right = ("L", hold), ("R", retest)
        if component[left] != component[right] and right not in reachable:
            result[hold] = retest
    return result


def analyze(edges, confirmed):
    """计算可补齐规模、强制归属和仍缺义务。

    edges 为领域层给出的资格图 {义务原轮: [可承担的补测轮, ...]}；
    confirmed 为已确认的 {hold: retest}，先从图中移除其两端；
    返回的 forced 仅包含当前图里归属唯一、尚待确认的边。
    """
    edges = {hold: list(candidates) for hold, candidates in edges.items()}
    for hold, retest in confirmed.items():
        edges.pop(hold, None)
        for candidates in edges.values():
            if retest in candidates:
                candidates.remove(retest)
    matching = hopcroft_karp(edges)
    forced = forced_edges(edges, matching)
    matched_holds = set(matching)
    missing = sorted(hold for hold in edges if hold not in confirmed and hold not in matched_holds)
    return dict(max_fill=len(matching) + len(confirmed), matching=matching, forced=forced,
                missing=missing, edges=edges)


def is_forced(edges, confirmed, hold, retest):
    solution = analyze(edges, confirmed)
    return solution["forced"].get(hold) == retest
