"""
Game rules, prize tables and exact theoretical probabilities for the 6-number Vietlott games.

Every draw in ``data/*.jsonl`` stores ``result`` as the main numbers followed, for Power 6/55, by one
bonus ("số đặc biệt") number. Scoring a ticket must therefore split the result first: the bonus only
matters for the Jackpot 2 tier and must never be counted as a regular match.

Jackpot values vary per draw; the tables below use the guaranteed minimum (giá trị khởi điểm), so any
ROI computed from them is an optimistic upper bound for the lower tiers and a conservative one for the
jackpots.
"""

from dataclasses import dataclass, field
from math import comb
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class PrizeTier:
    """One prize tier: ``matches`` main numbers (plus the bonus when ``needs_bonus``)."""

    key: str
    label: str
    matches: int
    value: int
    needs_bonus: bool = False


@dataclass(frozen=True)
class GameSpec:
    """Rules of a "pick ``pick`` of ``max_val``" game with an optional bonus number."""

    key: str
    title: str
    min_val: int
    max_val: int
    pick: int
    has_bonus: bool
    ticket_price: int
    tiers: Tuple[PrizeTier, ...] = field(default_factory=tuple)

    @property
    def pool(self) -> int:
        """Number of balls in the drum."""
        return self.max_val - self.min_val + 1

    def split(self, result: Sequence[int]) -> Tuple[List[int], Optional[int]]:
        """Split a stored result into ``(main_numbers, bonus)``."""
        numbers = [int(n) for n in result]
        main = numbers[: self.pick]
        bonus = numbers[self.pick] if self.has_bonus and len(numbers) > self.pick else None
        return main, bonus

    def score(self, ticket: Sequence[int], result: Sequence[int]) -> Tuple[int, bool, Optional[PrizeTier]]:
        """Score one ticket: ``(main_matches, bonus_hit, winning_tier_or_None)``."""
        main, bonus = self.split(result)
        ticket_set = set(int(n) for n in ticket)
        matches = len(ticket_set & set(main))
        bonus_hit = bonus is not None and bonus in ticket_set
        return matches, bonus_hit, self.tier_for(matches, bonus_hit)

    def tier_for(self, matches: int, bonus_hit: bool) -> Optional[PrizeTier]:
        """Return the best tier won by ``matches`` main numbers and ``bonus_hit``."""
        for tier in sorted(self.tiers, key=lambda t: -t.value):
            if tier.matches == matches and (bonus_hit or not tier.needs_bonus):
                return tier
        return None

    def prize(self, ticket: Sequence[int], result: Sequence[int]) -> int:
        """Prize in VND won by ``ticket`` against ``result``."""
        _, _, tier = self.score(ticket, result)
        return tier.value if tier else 0

    def match_probabilities(self) -> List[float]:
        """Exact hypergeometric ``P(k main matches)`` for ``k = 0..pick`` for one random ticket."""
        total = comb(self.pool, self.pick)
        return [comb(self.pick, k) * comb(self.pool - self.pick, self.pick - k) / total for k in range(self.pick + 1)]

    def tier_probabilities(self) -> Dict[str, float]:
        """Exact probability of winning each tier with one random ticket."""
        p_match = self.match_probabilities()
        out: Dict[str, float] = {}
        for tier in self.tiers:
            p = p_match[tier.matches]
            if self.has_bonus:
                # the bonus is drawn from the balls left after the main draw; a ticket with k main
                # matches holds (pick - k) of those leftover balls
                p_bonus = (self.pick - tier.matches) / (self.pool - self.pick)
                has_bonus_tier = any(t.matches == tier.matches and t.needs_bonus for t in self.tiers)
                if tier.needs_bonus:
                    p *= p_bonus
                elif has_bonus_tier:
                    p *= 1 - p_bonus
            out[tier.key] = p
        return out

    def expected_value(self) -> float:
        """Expected prize (VND) of one random ticket, using the minimum jackpot values."""
        probs = self.tier_probabilities()
        return sum(probs[t.key] * t.value for t in self.tiers)

    def expected_matches(self) -> float:
        """Expected number of main matches for one random ticket (``pick² / pool``)."""
        return self.pick * self.pick / self.pool


POWER_655 = GameSpec(
    key="power_655",
    title="Power 6/55",
    min_val=1,
    max_val=55,
    pick=6,
    has_bonus=True,
    ticket_price=10_000,
    tiers=(
        PrizeTier("jackpot1", "Jackpot 1 (6 số)", 6, 30_000_000_000),
        PrizeTier("jackpot2", "Jackpot 2 (5 số + số đặc biệt)", 5, 3_000_000_000, needs_bonus=True),
        PrizeTier("first", "Giải Nhất (5 số)", 5, 40_000_000),
        PrizeTier("second", "Giải Nhì (4 số)", 4, 500_000),
        PrizeTier("third", "Giải Ba (3 số)", 3, 50_000),
    ),
)

MEGA_645 = GameSpec(
    key="power_645",
    title="Mega 6/45",
    min_val=1,
    max_val=45,
    pick=6,
    has_bonus=False,
    ticket_price=10_000,
    tiers=(
        PrizeTier("jackpot1", "Jackpot (6 số)", 6, 12_000_000_000),
        PrizeTier("first", "Giải Nhất (5 số)", 5, 10_000_000),
        PrizeTier("second", "Giải Nhì (4 số)", 4, 300_000),
        PrizeTier("third", "Giải Ba (3 số)", 3, 30_000),
    ),
)

GAMES: Dict[str, GameSpec] = {g.key: g for g in (POWER_655, MEGA_645)}


def get_game(key: str) -> GameSpec:
    """Look up a game by product key (``power_655`` / ``power_645``)."""
    if key not in GAMES:
        raise ValueError(f"Unknown game {key!r}, expected one of {sorted(GAMES)}")
    return GAMES[key]
