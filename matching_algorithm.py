#!/usr/bin/env python3
"""
=============================================================================
 Recruiter Night Matching Engine  (v2)
=============================================================================
 Builds a "scavenger hunt" match list pairing each student with N recruiters,
 optimising match quality while GUARANTEEING:
   (a) every recruiter gets a fair share of students  (no lonely small firms)
   (b) every STUDENT gets a floor of genuinely good conversations
       (no freshman handed five cards for senior-only jobs)

 Why not greedy?  A greedy "best score first" pass stampedes every student
 toward the 3-4 biggest-name companies and strands the small firms - which are
 exactly the firms this event exists to serve.  Instead this uses MIN-COST
 FLOW with CONVEX (escalating) capacity costs: each extra student above a
 recruiter's fair share costs progressively more match-quality points, so the
 optimiser only overloads a firm when the quality gain truly justifies it.

 Solve order
 -----------
   PHASE 0  Wildcards      student's own picks, capped, allocated by lottery
   PHASE 1  Student equity every student gets `equity_min` STRONG matches
                           (right-ish major AND right-ish grade level)
   PHASE 2  Recruiter floor every firm filled to `min_floor_share` of fair
                           share using only in-discipline students
   PHASE 3  General fill    remaining slots, convex load penalty
   PHASE 4  Backfill        anyone still short
   PHASE 5  Wave sequencing balanced edge-colouring so tables don't queue

 Usage
 -----
   python matching_algorithm.py --mst                  # demo, using the
                                                         # example population
                                                         # data in mst_data.py
   python matching_algorithm.py --mst --compare        # sensitivity sweep
   python matching_algorithm.py --recruiters r.csv --students s.csv --excel

 The --mst flag and mst_data.py are one school's (Missouri S&T's) real major
 and employer-industry numbers, bundled as a realistic example population for
 testing and demos. To model your own school, write an equivalent data module
 and pass --recruiters/--students CSVs built from your own real (or synthetic
 test) data instead — the matching logic itself has no school baked into it.

 Requires numpy + pandas (openpyxl only for --excel).
=============================================================================
"""

from __future__ import annotations

import argparse
import heapq
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

# =============================================================================
# 1. CONFIGURATION
# =============================================================================


@dataclass
class Config:
    # --- Event shape -------------------------------------------------------
    matches_per_student: int = 4
    wildcards_per_student: int = 2
    auto_wildcards: bool = True
    event_total_minutes: int = 180
    food_minutes: int = 30          # shared meal BEFORE the matching rounds
    open_minutes: int = 30          # unstructured mingling AFTER the matching rounds

    # --- Scoring rubric (sums to 100) -------------------------------------
    w_major: int = 35
    w_grade: int = 25
    w_position: int = 20
    w_interest: int = 15
    w_location: int = 5

    major_exact: float = 1.00
    major_adjacent: float = 0.60
    grade_exact: float = 1.00
    grade_one_off: float = 0.50
    interest_top_company: float = 1.00
    interest_industry: float = 0.50

    # --- Load balancing (recruiter side) ----------------------------------
    free_share: float = 0.80        # free allowance before penalties
    hard_cap_share: float = 1.25    # absolute ceiling
    min_floor_share: float = 0.70   # guaranteed floor, in-discipline only
    load_penalty: float = 6.0       # convex penalty strength
    off_discipline_penalty: float = 60.0

    # --- Equity (student side) --------------------------------------------
    # Minimum STRONG matches every student is guaranteed.  A strong match =
    # right/adjacent major AND grade level the firm actually wants.
    equity_min: int = 2

    # --- Wildcards ---------------------------------------------------------
    wildcard_cap_share: float = 0.60

    seed: int = 1901  # fixed seed for reproducible runs; change freely


# =============================================================================
# 2. INDUSTRY SPECTRUM (colour-ordered; neighbours are perceptually close)
# =============================================================================


@dataclass(frozen=True)
class Industry:
    idx: int
    name: str
    short: str
    hex_color: str
    color_name: str
    shape: str


INDUSTRIES: List[Industry] = [
    Industry(0, "Civil, Construction & Infrastructure", "CIVIL",  "#C62828", "Red",    "▲ Triangle"),
    Industry(1, "Manufacturing & Industrial",           "MFG",    "#EF6C00", "Orange", "■ Square"),
    Industry(2, "Mechanical, Aerospace & Defense",      "MECH",   "#F9A825", "Amber",  "◆ Diamond"),
    Industry(3, "Materials, Mining & Chemical",         "MATL",   "#9E9D24", "Olive",  "⬟ Pentagon"),
    Industry(4, "Energy, Power & Utilities",            "ENERGY", "#2E7D32", "Green",  "● Circle"),
    Industry(5, "Electrical, Controls & Automation",    "ELEC",   "#00838F", "Teal",   "⬢ Hexagon"),
    Industry(6, "Software & IT",                        "SOFT",   "#1565C0", "Blue",   "★ Star"),
    Industry(7, "Data, Systems & Analytics",            "DATA",   "#4527A0", "Indigo", "✚ Cross"),
    Industry(8, "Business, Finance & Consulting",       "BIZ",    "#6A1B9A", "Purple", "✦ Sparkle"),
]
IND_BY_SHORT: Dict[str, Industry] = {i.short: i for i in INDUSTRIES}


# =============================================================================
# 3. MAJOR TAXONOMY + ADJACENCY
# =============================================================================

CLUSTERS: Dict[str, List[str]] = {
    "MECH": ["Mechanical Engineering", "Aerospace Engineering",
             "Engineering Physics", "Materials Science & Engineering",
             "Physics"],
    "CIVIL": ["Civil Engineering", "Architectural Engineering",
              "Environmental Engineering", "Geological Engineering",
              "Geology", "Environmental Science"],
    "ELEC": ["Electrical Engineering", "Computer Engineering",
             "Engineering Physics", "Systems Engineering"],
    "COMP": ["Computer Science", "Computer Engineering",
             "Information Science & Technology", "Applied Mathematics"],
    "CHEM": ["Chemical Engineering", "Materials Science & Engineering",
             "Metallurgical Engineering", "Ceramic Engineering", "Chemistry"],
    "EARTH": ["Mining Engineering", "Petroleum Engineering",
              "Geological Engineering", "Geology"],
    "NUKE": ["Nuclear Engineering", "Engineering Physics", "Physics",
             "Chemical Engineering"],
    "BIZ": ["Engineering Management", "Business & Management Systems",
            "Economics", "Systems Engineering", "Technical Communication"],
    "SCI": ["Biological Sciences", "Chemistry", "Physics",
            "Applied Mathematics", "Psychology", "Environmental Science"],
    "HUM": ["Technical Communication", "History", "Psychology",
            "Elementary Education", "Business & Management Systems"],
}


def build_adjacency() -> Dict[str, Set[str]]:
    adj: Dict[str, Set[str]] = defaultdict(set)
    for members in CLUSTERS.values():
        for a in members:
            for b in members:
                if a != b:
                    adj[a].add(b)
    return dict(adj)


MAJOR_ADJACENCY = build_adjacency()

GRADE_ORDER = ["Freshman", "Sophomore", "Junior", "Senior", "Grad Student"]
GRADE_INDEX = {g: i for i, g in enumerate(GRADE_ORDER)}


# =============================================================================
# 4. DATA MODELS
# =============================================================================


@dataclass
class Recruiter:
    rid: str
    company: str
    industry: str
    reps: int
    target_majors: List[str]
    position_types: List[str]
    preferred_grades: List[str]
    sponsors_visa: bool
    location: str
    table: int = 0

    @property
    def industry_obj(self) -> Industry:
        return IND_BY_SHORT[self.industry]


@dataclass
class Student:
    sid: str
    name: str
    major: str
    grade: str
    seeking: List[str]
    interest_companies: List[str]
    interest_industries: List[str]
    needs_sponsorship: bool
    location_pref: str
    wildcards: List[str] = field(default_factory=list)


# =============================================================================
# 5. SCORING
# =============================================================================


def major_component(s: Student, r: Recruiter, cfg: Config) -> Tuple[float, str]:
    if s.major in r.target_majors:
        return cfg.major_exact, "exact"
    adj: Set[str] = set()
    for tm in r.target_majors:
        adj |= MAJOR_ADJACENCY.get(tm, set())
    if s.major in adj:
        return cfg.major_adjacent, "adjacent"
    return 0.0, "off"


def grade_component(s: Student, r: Recruiter, cfg: Config) -> float:
    if s.grade in r.preferred_grades:
        return cfg.grade_exact
    si = GRADE_INDEX[s.grade]
    if any(abs(si - GRADE_INDEX[g]) == 1 for g in r.preferred_grades):
        return cfg.grade_one_off
    return 0.0


def position_component(s: Student, r: Recruiter) -> float:
    return 1.0 if set(s.seeking) & set(r.position_types) else 0.0


def interest_component(s: Student, r: Recruiter, cfg: Config) -> float:
    if r.company in s.interest_companies:
        return cfg.interest_top_company
    if r.industry in s.interest_industries:
        return cfg.interest_industry
    return 0.0


def location_component(s: Student, r: Recruiter) -> float:
    if s.location_pref in ("Anywhere", "Midwest"):
        return 1.0
    if s.location_pref == "Missouri":
        return 1.0 if r.location.endswith(", MO") else 0.0
    return 0.0


def score_pair(s: Student, r: Recruiter, cfg: Config) -> Tuple[float, str, float]:
    """Returns (score, major_tier, grade_fit).  score = -1 => hard-blocked."""
    # Hard gate: work authorisation.  Not a penalty - a wall.
    if s.needs_sponsorship and not r.sponsors_visa:
        return -1.0, "blocked", 0.0
    m_val, tier = major_component(s, r, cfg)
    g_val = grade_component(s, r, cfg)
    total = (cfg.w_major * m_val + cfg.w_grade * g_val
             + cfg.w_position * position_component(s, r)
             + cfg.w_interest * interest_component(s, r, cfg)
             + cfg.w_location * location_component(s, r))
    return total, tier, g_val


# =============================================================================
# 6. MIN-COST FLOW  (successive shortest paths + Johnson potentials)
# =============================================================================


class MinCostFlow:
    def __init__(self, n: int):
        self.n = n
        self.graph: List[List[List[int]]] = [[] for _ in range(n)]

    def add_edge(self, u: int, v: int, cap: int, cost: int) -> None:
        self.graph[u].append([v, cap, cost, len(self.graph[v])])
        self.graph[v].append([u, 0, -cost, len(self.graph[u]) - 1])

    def flow(self, s: int, t: int, maxf: int) -> Tuple[int, int]:
        n, graph = self.n, self.graph
        INF = float("inf")
        res_flow = res_cost = 0
        h = [0] * n
        prev_v = [0] * n
        prev_e = [0] * n
        while maxf > 0:
            dist = [INF] * n
            dist[s] = 0
            pq = [(0, s)]
            while pq:
                d, v = heapq.heappop(pq)
                if dist[v] < d:
                    continue
                for i, (to, cap, cost, _) in enumerate(graph[v]):
                    if cap > 0 and dist[to] > d + cost + h[v] - h[to]:
                        dist[to] = d + cost + h[v] - h[to]
                        prev_v[to], prev_e[to] = v, i
                        heapq.heappush(pq, (dist[to], to))
            if dist[t] == INF:
                break
            for v in range(n):
                if dist[v] < INF:
                    h[v] += dist[v]
            d = maxf
            v = t
            while v != s:
                d = min(d, graph[prev_v[v]][prev_e[v]][1])
                v = prev_v[v]
            maxf -= d
            res_flow += d
            res_cost += d * h[t]
            v = t
            while v != s:
                e = graph[prev_v[v]][prev_e[v]]
                e[1] -= d
                graph[v][e[3]][1] += d
                v = prev_v[v]
        return res_flow, res_cost


# =============================================================================
# 7. MATCHER
# =============================================================================

SCALE = 100
STRONG_MIN_SCORE = 45.0   # a "strong" match must also clear this


class Matcher:
    def __init__(self, students: List[Student], recruiters: List[Recruiter], cfg: Config):
        self.students = students
        self.recruiters = recruiters
        self.cfg = cfg
        self.rid_index = {r.rid: i for i, r in enumerate(recruiters)}
        self.assignments: Dict[str, List[Tuple[str, float, str, str]]] = defaultdict(list)
        nS, nR = len(students), len(recruiters)
        self.scores = np.full((nS, nR), -1.0)
        self.tiers = np.empty((nS, nR), dtype=object)
        self.gradefit = np.zeros((nS, nR))
        for i, s in enumerate(students):
            for j, r in enumerate(recruiters):
                sc, tier, gf = score_pair(s, r, cfg)
                self.scores[i, j] = sc
                self.tiers[i, j] = tier
                self.gradefit[i, j] = gf
        # strong = in-discipline AND grade the firm wants AND decent score
        self.strong = ((self.gradefit > 0)
                       & np.isin(self.tiers.astype(str), ["exact", "adjacent"])
                       & (self.scores >= STRONG_MIN_SCORE))

    # -- capacity -----------------------------------------------------------
    def capacity_plan(self, total_slots: int) -> Tuple[float, Dict[str, int]]:
        total_reps = sum(r.reps for r in self.recruiters)
        per_rep = total_slots / total_reps
        caps = {r.rid: int(math.ceil(per_rep * r.reps * self.cfg.hard_cap_share))
                for r in self.recruiters}
        return per_rep, caps

    def _load(self) -> Dict[str, int]:
        load: Dict[str, int] = defaultdict(int)
        for lst in self.assignments.values():
            for rid, *_ in lst:
                load[rid] += 1
        return load

    # -- wildcards ----------------------------------------------------------
    def grant_wildcards(self) -> Dict[str, int]:
        cfg = self.cfg
        total_slots = len(self.students) * cfg.matches_per_student
        per_rep, _ = self.capacity_plan(total_slots)
        wc_cap = {r.rid: max(1, int(round(per_rep * r.reps * cfg.wildcard_cap_share)))
                  for r in self.recruiters}
        load: Dict[str, int] = defaultdict(int)
        granted = 0
        order = list(range(len(self.students)))
        random.Random(cfg.seed).shuffle(order)   # lottery, not first-come
        for si in order:
            s = self.students[si]
            for rid in s.wildcards[: cfg.wildcards_per_student]:
                j = self.rid_index.get(rid)
                if j is None or self.scores[si, j] < 0:
                    continue
                if load[rid] >= wc_cap[rid]:
                    continue
                if any(a[0] == rid for a in self.assignments[s.sid]):
                    continue
                load[rid] += 1
                granted += 1
                self.assignments[s.sid].append(
                    (rid, float(self.scores[si, j]), self.tiers[si, j], "wildcard"))
        self.wildcards_granted = granted
        return dict(load)

    # -- generic flow pass --------------------------------------------------
    def _flow_pass(self, need: List[int], sink: Dict[int, List[int]],
                   allow: Optional[np.ndarray], label: str) -> int:
        cfg = self.cfg
        nS, nR = len(self.students), len(self.recruiters)
        SRC, SNK = 0, nS + nR + 1
        mcf = MinCostFlow(nS + nR + 2)
        for i in range(nS):
            if need[i] > 0:
                mcf.add_edge(SRC, 1 + i, need[i], 0)
        any_pair = False
        for i in range(nS):
            if need[i] <= 0:
                continue
            taken = {a[0] for a in self.assignments[self.students[i].sid]}
            for j in range(nR):
                if self.recruiters[j].rid in taken or self.scores[i, j] < 0:
                    continue
                if allow is not None and not allow[i, j]:
                    continue
                cost = 100.0 - self.scores[i, j]
                if self.tiers[i, j] == "off":
                    cost += cfg.off_discipline_penalty
                mcf.add_edge(1 + i, 1 + nS + j, 1, int(round(cost * SCALE)))
                any_pair = True
        cap_total = 0
        for j, costs in sink.items():
            for c in costs:
                mcf.add_edge(1 + nS + j, SNK, 1, int(c))
                cap_total += 1
        if not any_pair or cap_total == 0:
            return 0
        placed, _ = mcf.flow(SRC, SNK, min(sum(need), cap_total))
        for i in range(nS):
            for (to, cap, _c, _r) in mcf.graph[1 + i]:
                j = to - (1 + nS)
                if 0 <= j < nR and cap == 0:
                    self.assignments[self.students[i].sid].append(
                        (self.recruiters[j].rid, float(self.scores[i, j]),
                         self.tiers[i, j], label))
        return placed

    # -- solve --------------------------------------------------------------
    def solve(self) -> None:
        cfg = self.cfg
        nS = len(self.students)
        M = cfg.matches_per_student
        total_slots = nS * M
        per_rep, hard_caps = self.capacity_plan(total_slots)

        # PHASE 0 - wildcards
        self.grant_wildcards()

        # PHASE 1 - student equity: guarantee `equity_min` STRONG matches
        load = self._load()
        strong_now = {s.sid: sum(1 for rid, *_ in self.assignments[s.sid]
                                 if self.strong[i, self.rid_index[rid]])
                      for i, s in enumerate(self.students)}
        need = [max(0, min(cfg.equity_min - strong_now[s.sid],
                           M - len(self.assignments[s.sid])))
                for s in self.students]
        sink: Dict[int, List[int]] = {}
        for j, r in enumerate(self.recruiters):
            room = max(0, hard_caps[r.rid] - load.get(r.rid, 0))
            if room:
                sink[j] = [0] * room
        self.phase_equity = self._flow_pass(need, sink, self.strong, "equity")

        # PHASE 2 - recruiter floor (in-discipline only)
        load = self._load()
        self.floor_target = {}
        sink = {}
        for j, r in enumerate(self.recruiters):
            tgt = max(1, int(round(per_rep * r.reps * cfg.min_floor_share)))
            self.floor_target[r.rid] = tgt
            gap = tgt - load.get(r.rid, 0)
            if gap > 0:
                sink[j] = [0] * gap
        in_disc = np.isin(self.tiers.astype(str), ["exact", "adjacent"])
        need = [M - len(self.assignments[s.sid]) for s in self.students]
        self.phase_floor = self._flow_pass(need, sink, in_disc, "floor") if sink else 0

        # PHASE 3 - general fill with convex load penalty
        load = self._load()
        sink = {}
        for j, r in enumerate(self.recruiters):
            placed = load.get(r.rid, 0)
            free = int(math.floor(per_rep * r.reps * cfg.free_share))
            room = max(0, hard_caps[r.rid] - placed)
            costs = []
            for k in range(1, room + 1):
                over = max(0, (placed + k) - free)
                costs.append(int(round(cfg.load_penalty *
                                       (over ** 2 - max(0, over - 1) ** 2) * SCALE)))
            if costs:
                sink[j] = costs
        need = [M - len(self.assignments[s.sid]) for s in self.students]
        self.phase_fill = self._flow_pass(need, sink, None, "algorithm")

        self._backfill()
        self._sequence()

    # -- backfill -----------------------------------------------------------
    def _backfill(self) -> None:
        cfg = self.cfg
        load = self._load()
        _, hard_caps = self.capacity_plan(len(self.students) * cfg.matches_per_student)
        self.short_students: List[str] = []
        for i, s in enumerate(self.students):
            while len(self.assignments[s.sid]) < cfg.matches_per_student:
                taken = {a[0] for a in self.assignments[s.sid]}
                best_j, best_val = None, -1e9
                for j, r in enumerate(self.recruiters):
                    if r.rid in taken or self.scores[i, j] < 0:
                        continue
                    val = self.scores[i, j] - 3.0 * max(0, load[r.rid] - hard_caps[r.rid])
                    if val > best_val:
                        best_j, best_val = j, val
                if best_j is None:
                    self.short_students.append(s.sid)
                    break
                rid = self.recruiters[best_j].rid
                load[rid] += 1
                self.assignments[s.sid].append(
                    (rid, float(self.scores[i, best_j]),
                     self.tiers[i, best_j], "backfill"))

    # -- wave sequencing (balanced edge colouring) --------------------------
    def _sequence(self) -> None:
        rng = random.Random(self.cfg.seed)
        W = self.cfg.matches_per_student
        cards = {s.sid: [a[0] for a in self.assignments[s.sid]] for s in self.students}
        slot: Dict[Tuple[str, int], int] = defaultdict(int)
        total: Dict[str, int] = defaultdict(int)
        order: Dict[str, List[str]] = {}
        for sid, recs in cards.items():
            perm = recs[:]
            rng.shuffle(perm)
            order[sid] = perm
            for w, rid in enumerate(perm):
                slot[(rid, w)] += 1
                total[rid] += 1
        target = {rid: total[rid] / W for rid in total}

        def cost(rid, w):
            return (slot[(rid, w)] - target[rid]) ** 2

        sids = list(order)
        for _ in range(60):
            improved = False
            rng.shuffle(sids)
            for sid in sids:
                seq = order[sid]
                if len(seq) < 2:
                    continue
                for _t in range(W):
                    w1, w2 = rng.sample(range(len(seq)), 2)
                    r1, r2 = seq[w1], seq[w2]
                    if r1 == r2:
                        continue
                    before = cost(r1, w1) + cost(r1, w2) + cost(r2, w1) + cost(r2, w2)
                    slot[(r1, w1)] -= 1; slot[(r1, w2)] += 1
                    slot[(r2, w2)] -= 1; slot[(r2, w1)] += 1
                    after = cost(r1, w1) + cost(r1, w2) + cost(r2, w1) + cost(r2, w2)
                    if after < before:
                        seq[w1], seq[w2] = r2, r1
                        improved = True
                    else:
                        slot[(r1, w1)] += 1; slot[(r1, w2)] -= 1
                        slot[(r2, w2)] += 1; slot[(r2, w1)] -= 1
            if not improved:
                break
        self.sequence = order
        self.slot_load = slot
        self.wave_excess = max((slot[(rid, w)] - math.ceil(target[rid])
                                for rid in total for w in range(W)), default=0)


# =============================================================================
# 8. ROOM LAYOUT
# =============================================================================


def assign_tables(recruiters: List[Recruiter]) -> None:
    for n, r in enumerate(sorted(recruiters,
                                 key=lambda x: (x.industry_obj.idx, x.company)), 1):
        r.table = n


def room_map(recruiters: List[Recruiter], per_row: int = 10) -> str:
    ordered = sorted(recruiters, key=lambda r: r.table)
    lines = []
    for start in range(0, len(ordered), per_row):
        row = ordered[start:start + per_row]
        lines.append("  " + "  ".join(f"[{r.table:>2}]" for r in row))
        lines.append("  " + "  ".join(f" {r.industry_obj.short[:4]:<4}" for r in row))
        lines.append("")
    return "\n".join(lines)


# =============================================================================
# 9. MST-CALIBRATED POPULATION GENERATOR
# =============================================================================

FIRST = ["Aaron", "Blake", "Caleb", "Dylan", "Ethan", "Grant", "Hunter", "Isaac",
         "Jacob", "Kyle", "Logan", "Mason", "Nathan", "Owen", "Parker", "Quinn",
         "Ryan", "Seth", "Trevor", "Wyatt", "Austin", "Brady", "Cole", "Derek",
         "Evan", "Garrett", "Hayden", "Ian", "Jared", "Keith", "Liam", "Miles",
         "Noah", "Oscar", "Preston", "Reid", "Simon", "Tanner", "Victor", "Wade"]
LAST = ["Anderson", "Barnes", "Carter", "Dunn", "Ellis", "Fischer", "Grant",
        "Hoffman", "Ingram", "Jensen", "Keller", "Lawson", "Mueller", "Novak",
        "Osborne", "Pace", "Reyes", "Schmidt", "Tucker", "Vance", "Walsh",
        "Yates", "Zimmerman", "Brennan", "Callahan", "Doyle", "Erickson",
        "Farrell", "Gallagher", "Hendricks", "Iverson", "Jacobs", "Kowalski",
        "Lindgren", "Marsh", "Nolan", "Ortiz", "Pruitt", "Quinlan", "Rasmussen"]

INDUSTRY_MAJOR_POOL: Dict[str, List[str]] = {
    "CIVIL": ["Civil Engineering", "Architectural Engineering",
              "Environmental Engineering", "Geological Engineering",
              "Engineering Management", "Geology"],
    "MFG": ["Mechanical Engineering", "Engineering Management",
            "Metallurgical Engineering", "Electrical Engineering",
            "Chemical Engineering", "Business & Management Systems"],
    "MECH": ["Mechanical Engineering", "Aerospace Engineering",
             "Engineering Physics", "Physics", "Computer Engineering"],
    "MATL": ["Metallurgical Engineering", "Ceramic Engineering",
             "Chemical Engineering", "Mining Engineering", "Chemistry",
             "Petroleum Engineering", "Environmental Science",
             "Biological Sciences"],
    "ENERGY": ["Electrical Engineering", "Nuclear Engineering",
               "Mechanical Engineering", "Petroleum Engineering",
               "Chemical Engineering"],
    "ELEC": ["Electrical Engineering", "Computer Engineering",
             "Engineering Physics", "Physics"],
    "SOFT": ["Computer Science", "Computer Engineering",
             "Information Science & Technology"],
    "DATA": ["Computer Science", "Applied Mathematics",
             "Information Science & Technology", "Physics", "Chemistry"],
    "BIZ": ["Engineering Management", "Business & Management Systems",
            "Applied Mathematics", "Technical Communication", "Psychology",
            "History"],
}


def student_weighted_mix(n_students: int, cfg: Config) -> Dict[str, float]:
    """Industry mix that mirrors what YOUR students study, rather than the
    Handshake population. Use this to decide who to invite."""
    import mst_data as D
    w: Dict[str, float] = {i.short: 0.0 for i in INDUSTRIES}
    for maj, pct in D.MST_MAJOR_PCT.items():
        hits = [b for b in w if maj in INDUSTRY_MAJOR_POOL[b]]
        if not hits:
            continue
        for b in hits:
            w[b] += pct / len(hits)
    tot = sum(w.values())
    return {k: v / tot for k, v in sorted(w.items(), key=lambda x: -x[1])}


def make_mst(n_students: int, n_recruiters: int, cfg: Config,
             underclass_friendly: Optional[float] = None,
             mix_override: Optional[Dict[str, float]] = None
             ) -> Tuple[List[Student], List[Recruiter]]:
    """Generate a population calibrated to Missouri S&T's real major mix and
    the real Handshake employer industry mix."""
    import mst_data as D

    rng = random.Random(cfg.seed)
    nprng = np.random.default_rng(cfg.seed)

    # ---- recruiters: industry mix follows Handshake ----------------------
    mix = mix_override or D.bucket_mix()
    mix = {k: v for k, v in mix.items() if v > 0}
    buckets = list(mix)
    probs = np.array([mix[b] for b in buckets])
    probs /= probs.sum()
    counts = np.floor(probs * n_recruiters).astype(int)
    while counts.sum() < n_recruiters:            # largest-remainder top-up
        counts[np.argmax(probs * n_recruiters - counts)] += 1

    grade_profiles = D.RECRUITER_GRADE_PROFILES
    gp_choices = [g for g, _ in grade_profiles]
    gp_w = np.array([w for _, w in grade_profiles], dtype=float)
    gp_w /= gp_w.sum()

    recruiters: List[Recruiter] = []
    used_names: Set[str] = set()
    k = 0
    for b, cnt in zip(buckets, counts):
        names = D.FIRMS_BY_BUCKET[b][:]
        rng.shuffle(names)
        for n in range(int(cnt)):
            k += 1
            company, loc = names[n % len(names)]
            if company in used_names:            # pool exhausted for this bucket
                suffix = 2
                while f"{company} ({suffix})" in used_names:
                    suffix += 1
                company = f"{company} ({suffix})"
            used_names.add(company)
            pool = INDUSTRY_MAJOR_POOL[b]
            tm = rng.sample(pool, k=min(len(pool), rng.choice([2, 3, 3, 4])))
            if underclass_friendly is not None and rng.random() < underclass_friendly:
                grades = ["Sophomore", "Junior", "Senior"]
            else:
                grades = list(gp_choices[nprng.choice(len(gp_choices), p=gp_w)])
            pos = rng.choice([["Internship"], ["Internship", "Co-op"],
                              ["Internship", "Full-Time"],
                              ["Internship", "Co-op", "Full-Time"],
                              ["Co-op", "Full-Time"]])
            recruiters.append(Recruiter(
                rid=f"R{k:02d}", company=company, industry=b,
                reps=rng.choice([1, 1, 1, 2]), target_majors=tm,
                position_types=list(pos), preferred_grades=grades,
                sponsors_visa=rng.random() < 0.35, location=loc))
    assign_tables(recruiters)

    # ---- students: majors + grades follow MST ----------------------------
    majors = list(D.MST_MAJOR_PCT)
    mw = np.array([D.MST_MAJOR_PCT[m] for m in majors], dtype=float)
    mw /= mw.sum()
    grades = list(D.GRADE_PCT)
    gw = np.array([D.GRADE_PCT[g] for g in grades], dtype=float)
    gw /= gw.sum()

    students: List[Student] = []
    used: Set[str] = set()
    for k in range(1, n_students + 1):
        while True:
            nm = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if nm not in used:
                used.add(nm)
                break
        major = majors[nprng.choice(len(majors), p=mw)]
        grade = grades[nprng.choice(len(grades), p=gw)]
        if grade in ("Freshman", "Sophomore"):
            seeking = rng.choice([["Internship"], ["Internship", "Co-op"]])
        elif grade == "Junior":
            seeking = rng.choice([["Internship"], ["Internship", "Co-op"],
                                  ["Internship", "Full-Time"]])
        else:
            seeking = rng.choice([["Full-Time"], ["Internship", "Full-Time"],
                                  ["Co-op", "Full-Time"]])
        rel = [i.short for i in INDUSTRIES if major in INDUSTRY_MAJOR_POOL[i.short]]
        if not rel:
            rel = [rng.choice(INDUSTRIES).short]
        inds = list(dict.fromkeys(rel + [rng.choice(INDUSTRIES).short]))[:2]
        near = {IND_BY_SHORT[x].idx for x in rel}
        near |= {i - 1 for i in list(near)} | {i + 1 for i in list(near)}
        warm = [r.company for r in recruiters if r.industry_obj.idx in near]
        cold = [r.company for r in recruiters if r.company not in warm]
        picks = rng.sample(warm, k=min(2, len(warm)))
        if cold:
            picks += rng.sample(cold, k=1)
        picks = list(dict.fromkeys(picks))
        students.append(Student(
            sid=f"S{k:03d}", name=nm, major=major, grade=grade,
            seeking=list(seeking), interest_companies=picks,
            interest_industries=inds,
            needs_sponsorship=rng.random() < 0.18,
            location_pref=rng.choices(["Missouri", "Midwest", "Anywhere"],
                                      weights=[25, 35, 40])[0],
            wildcards=[r.rid for r in recruiters if r.company in picks][:2]))
    return students, recruiters


# =============================================================================
# 10. REPORTING
# =============================================================================


def build_frames(m: Matcher) -> Dict[str, pd.DataFrame]:
    recs = {r.rid: r for r in m.recruiters}
    studs = {s.sid: s for s in m.students}
    si = {s.sid: i for i, s in enumerate(m.students)}

    rows = []
    for sid, lst in m.assignments.items():
        seq = m.sequence.get(sid, [a[0] for a in lst])
        pos = {rid: i + 1 for i, rid in enumerate(seq)}
        for rid, sc, tier, src in lst:
            s, r = studs[sid], recs[rid]
            rows.append({
                "Stop": pos.get(rid, 0), "StudentID": sid, "Student": s.name,
                "Major": s.major, "Grade": s.grade, "Table": r.table,
                "Company": r.company, "Industry": r.industry_obj.name,
                "Color": r.industry_obj.color_name, "Shape": r.industry_obj.shape,
                "Hex": r.industry_obj.hex_color, "Score": round(sc, 1),
                "MajorFit": tier,
                "Strong": bool(m.strong[si[sid], m.rid_index[rid]]),
                "Source": src,
                "WhyMatched": f"{'/'.join(r.position_types)} • "
                              f"{', '.join(r.target_majors[:3])}",
            })
    a = pd.DataFrame(rows).sort_values(["Student", "Stop"]).reset_index(drop=True)

    grp = a.groupby("Company", as_index=False).agg(
        Students=("StudentID", "count"), AvgScore=("Score", "mean"))
    pool = {r.company: int(sum(1 for i in range(len(m.students))
                               if m.scores[i, j] >= 0
                               and m.tiers[i, j] in ("exact", "adjacent")))
            for j, r in enumerate(m.recruiters)}
    meta = pd.DataFrame([{
        "Company": r.company, "Table": r.table, "Industry": r.industry_obj.name,
        "Color": r.industry_obj.color_name, "Shape": r.industry_obj.shape,
        "Reps": r.reps, "Sponsors": "Yes" if r.sponsors_visa else "No",
        "TargetMajors": ", ".join(r.target_majors),
        "Grades": ", ".join(r.preferred_grades),
        "Roles": ", ".join(r.position_types), "Location": r.location,
        "EligiblePool": pool[r.company],
    } for r in m.recruiters])
    load = meta.merge(grp, on="Company", how="left").fillna({"Students": 0})
    load["FloorTarget"] = load["Company"].map(
        {r.company: m.floor_target[r.rid] for r in m.recruiters})
    load["PerRep"] = (load["Students"] / load["Reps"]).round(1)
    load["AvgScore"] = load["AvgScore"].round(1)
    load = load.sort_values("Table").reset_index(drop=True)

    palette = pd.DataFrame([{
        "Table Block": i.idx + 1, "Industry": i.name, "Code": i.short,
        "Color": i.color_name, "Hex": i.hex_color, "Shape": i.shape,
        "Tables": ", ".join(str(r.table) for r in
                            sorted(m.recruiters, key=lambda x: x.table)
                            if r.industry == i.short) or "-",
    } for i in INDUSTRIES])

    by_grade = (a.groupby(["StudentID", "Grade"], as_index=False)
                .agg(Strong=("Strong", "sum"), Avg=("Score", "mean"))
                .groupby("Grade", as_index=False)
                .agg(Students=("StudentID", "count"),
                     AvgStrong=("Strong", "mean"),
                     PctWith2Plus=("Strong", lambda x: (x >= 2).mean() * 100),
                     PctWith0=("Strong", lambda x: (x == 0).mean() * 100),
                     AvgScore=("Avg", "mean")))
    by_grade["Order"] = by_grade["Grade"].map(GRADE_INDEX)
    by_grade = by_grade.sort_values("Order").drop(columns="Order")
    for c in ("AvgStrong", "PctWith2Plus", "PctWith0", "AvgScore"):
        by_grade[c] = by_grade[c].round(1)

    return {"assignments": a, "recruiter_load": load, "palette": palette,
            "grade_equity": by_grade}


def diagnostics(m: Matcher, cfg: Config, frames=None) -> str:
    f = frames or build_frames(m)
    a, load, bg = f["assignments"], f["recruiter_load"], f["grade_equity"]
    nS, nR = len(m.students), len(m.recruiters)
    hunt = cfg.event_total_minutes - cfg.food_minutes - cfg.open_minutes
    mins = hunt / (len(a) / sum(r.reps for r in m.recruiters))
    tier = a["MajorFit"].value_counts(normalize=True).mul(100).round(1).to_dict()

    o = []
    o.append("=" * 78)
    o.append(" MATCH DIAGNOSTICS")
    o.append("=" * 78)
    o.append(f" Students {nS} | Recruiters {nR} | Matches each {cfg.matches_per_student}"
             f" | Wildcards {cfg.wildcards_per_student} | Equity floor {cfg.equity_min}")
    o.append(f" Conversations scheduled: {len(a)}")
    o.append("")
    o.append(" RECRUITER LOAD")
    o.append(f"   per-rep workload   min {load['PerRep'].min():.1f}"
             f" | median {load['PerRep'].median():.1f}"
             f" | max {load['PerRep'].max():.1f} | std {load['PerRep'].std():.2f}")
    starved = load[load["Students"] < load["FloorTarget"]]
    o.append(f"   below guaranteed floor: {len(starved)}")
    for _, r in starved.iterrows():
        o.append(f"     ! T{r['Table']:>2} {r['Company'][:32]:<32} got {r['Students']:.0f},"
                 f" floor {r['FloorTarget']:.0f}, eligible pool {r['EligiblePool']:.0f}")
    o.append("")
    o.append(" STUDENT EQUITY  (strong = right-ish major AND grade the firm wants)")
    o.append(f"   {'Grade':<14}{'N':>5}{'avg strong':>12}{'% with 2+':>11}"
             f"{'% with 0':>10}{'avg score':>11}")
    for _, r in bg.iterrows():
        o.append(f"   {r['Grade']:<14}{r['Students']:>5.0f}{r['AvgStrong']:>12.1f}"
                 f"{r['PctWith2Plus']:>11.1f}{r['PctWith0']:>10.1f}{r['AvgScore']:>11.1f}")
    o.append("")
    o.append(" MATCH QUALITY")
    o.append(f"   mean {a['Score'].mean():.1f}/100 | median {a['Score'].median():.1f}"
             f" | 10th pct {a['Score'].quantile(.10):.1f}")
    o.append(f"   exact major {tier.get('exact', 0)}% | adjacent {tier.get('adjacent', 0)}%"
             f" | off-discipline {tier.get('off', 0)}%")
    o.append(f"   strong matches: {a['Strong'].mean()*100:.1f}% of all conversations")
    o.append(f"   source mix: {a['Source'].value_counts().to_dict()}")
    o.append(f"   wildcards granted {m.wildcards_granted}"
             f"/{nS*cfg.wildcards_per_student} | students short {len(m.short_students)}")
    o.append("")
    o.append(" TIMING")
    o.append(f"   {cfg.event_total_minutes} min total − {cfg.food_minutes} food"
             f" − {cfg.open_minutes} open-mingle = {hunt} min matching")
    o.append(f"   {cfg.matches_per_student} waves × {hunt/cfg.matches_per_student:.0f} min"
             f" | {mins:.1f} min per conversation")
    o.append(f"   worst table backlog {m.wave_excess:+d} above wave target")
    o.append(f"   verdict: " + ("HEALTHY" if mins >= 6 else
                                "TIGHT" if mins >= 4.5 else "TOO THIN"))
    o.append("")
    o.append(" ROOM (spectrum order)")
    o.append(room_map(m.recruiters))
    return "\n".join(o)


# =============================================================================
# 11. CLI
# =============================================================================


def load_csv(pr: str, ps: str) -> Tuple[List[Student], List[Recruiter]]:
    rdf, sdf = pd.read_csv(pr), pd.read_csv(ps)
    sp = lambda v: [x.strip() for x in str(v).split(";") if x.strip()]
    recruiters = [Recruiter(
        rid=str(r["rid"]), company=r["company"], industry=r["industry"],
        reps=int(r.get("reps", 1)), target_majors=sp(r["target_majors"]),
        position_types=sp(r["position_types"]), preferred_grades=sp(r["preferred_grades"]),
        sponsors_visa=str(r.get("sponsors_visa", "No")).lower() in ("yes", "true", "1"),
        location=str(r.get("location", ""))) for _, r in rdf.iterrows()]
    assign_tables(recruiters)
    students = [Student(
        sid=str(s["sid"]), name=s["name"], major=s["major"], grade=s["grade"],
        seeking=sp(s["seeking"]), interest_companies=sp(s.get("interest_companies", "")),
        interest_industries=sp(s.get("interest_industries", "")),
        needs_sponsorship=str(s.get("needs_sponsorship", "No")).lower() in ("yes", "true", "1"),
        location_pref=str(s.get("location_pref", "Anywhere")),
        wildcards=sp(s.get("wildcards", ""))) for _, s in sdf.iterrows()]
    return students, recruiters


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mst", action="store_true",
                   help="demo/test mode using the example population data in mst_data.py")
    p.add_argument("--students-n", type=int, default=120)
    p.add_argument("--recruiters-n", type=int, default=30)
    p.add_argument("--recruiters", type=str)
    p.add_argument("--students", type=str)
    p.add_argument("--matches", type=int, default=4)
    p.add_argument("--wildcards", type=int, default=2)
    p.add_argument("--equity", type=int, default=2)
    p.add_argument("--event-minutes", type=int, default=180)
    p.add_argument("--food-minutes", type=int, default=30)
    p.add_argument("--open-minutes", type=int, default=30,
                   help="unstructured mingling time after the matching rounds")
    p.add_argument("--student-weighted-mix", action="store_true",
                   help="invite firms in proportion to student majors")
    p.add_argument("--underclass-friendly", type=float, default=None,
                   help="fraction of firms asked to open up to sophomores")
    p.add_argument("--outdir", type=str, default=".")
    p.add_argument("--excel", action="store_true")
    p.add_argument("--compare", action="store_true")
    args = p.parse_args()

    cfg = Config(matches_per_student=args.matches,
                 wildcards_per_student=args.wildcards,
                 equity_min=args.equity,
                 event_total_minutes=args.event_minutes,
                 food_minutes=args.food_minutes,
                 open_minutes=args.open_minutes)
    random.seed(cfg.seed)

    def build(c):
        if args.recruiters and args.students:
            return load_csv(args.recruiters, args.students)
        mo = (student_weighted_mix(args.students_n, c)
              if args.student_weighted_mix else None)
        return make_mst(args.students_n, args.recruiters_n, c,
                        args.underclass_friendly, mo)

    if args.compare:
        rows = []
        for mt in (3, 4, 5, 6):
            for eq in (0, 2):
                c2 = Config(matches_per_student=mt, wildcards_per_student=args.wildcards,
                            equity_min=eq, event_total_minutes=args.event_minutes,
                            food_minutes=args.food_minutes, open_minutes=args.open_minutes)
                random.seed(c2.seed)
                st2, rc2 = build(c2)
                mm = Matcher(st2, rc2, c2)
                mm.solve()
                fr = build_frames(mm)
                aa, ll, bg = fr["assignments"], fr["recruiter_load"], fr["grade_equity"]
                hunt = c2.event_total_minutes - c2.food_minutes - c2.open_minutes
                mins = hunt / (len(aa) / sum(r.reps for r in rc2))
                under = bg[bg["Grade"].isin(["Freshman", "Sophomore"])]
                rows.append({
                    "matches": mt, "equity": eq, "meetings": len(aa),
                    "min_each": round(mins, 1),
                    "perrep_std": round(ll["PerRep"].std(), 2),
                    "mean": round(aa["Score"].mean(), 1),
                    "strong_%": round(aa["Strong"].mean() * 100, 1),
                    "underclass_0strong_%": round(
                        (under["PctWith0"] * under["Students"]).sum()
                        / max(1, under["Students"].sum()), 1)})
        print("\n SENSITIVITY (MST population)\n")
        print(pd.DataFrame(rows).to_string(index=False))
        return

    students, recruiters = build(cfg)
    m = Matcher(students, recruiters, cfg)
    m.solve()
    frames = build_frames(m)
    report = diagnostics(m, cfg, frames)
    print(report)

    import os
    for name, df in frames.items():
        out_df = df
        if name == "assignments":
            # MajorFit/Strong are used internally (Grade Equity, Recruiter Load
            # averages) but shouldn't appear in the CSV recruiters or students
            # could end up seeing — we don't expose the algorithm's exact/
            # adjacent/off judgment call, that's for humans to decide.
            out_df = df.drop(columns=[c for c in ("MajorFit", "Strong") if c in df.columns])
        out_df.to_csv(os.path.join(args.outdir, f"{name}.csv"), index=False)
    with open(os.path.join(args.outdir, "diagnostics.txt"), "w") as fh:
        fh.write(report)
    if args.excel:
        from excel_out import write_workbook
        write_workbook(frames, m, cfg,
                       os.path.join(args.outdir, "recruiter_night_plan.xlsx"))


if __name__ == "__main__":
    main()
