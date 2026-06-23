"""斗地主规则引擎：确定性、无 LLM、唯一裁判。

职责：牌库与发牌、阶段机（叫/抢地主 → 出牌 → 结算）、牌型识别/比较/校验、
计分与倍数、启发式提示（供 AI 兜底与"提示"按钮）。

牌力顺序：3 < 4 < … < A < 2 < 小王 < 大王，用"牌力值"比较：
    3..10 → 3..10，J=11，Q=12，K=13，A=14，2=15，小王=16，大王=17
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# 普通牌力值 → 显示文本
RANK_TEXT = {
    3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K", 14: "A", 15: "2",
}
JOKER_POWER = {"small": 16, "big": 17}
SUITS = ["s", "h", "c", "d"]  # 黑桃 红心 梅花 方块
RED_SUITS = {"h", "d"}


@dataclass(slots=True)
class Card:
    """一张牌。suit 为 None 表示大小王。"""

    id: str
    power: int
    suit: str | None
    text: str  # 显示文本：3..10 / J / Q / K / A / 2 / 小 / 大

    @property
    def color(self) -> str:
        if self.suit is None:
            return "red" if self.power == 17 else "black"
        return "red" if self.suit in RED_SUITS else "black"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "power": self.power,
            "suit": self.suit,
            "text": self.text,
            "color": self.color,
        }


@dataclass(slots=True)
class Combo:
    """一手牌的牌型描述（用于比较）。

    kind  牌型名；rank 主牌力（比较键）；size 总张数；chain 连子长度（顺子/连对/飞机）。
    同型可压条件：kind/size/chain 相同且 rank 更大。炸弹/王炸特判。
    """

    kind: str
    rank: int
    size: int
    chain: int = 1


BOMB_KINDS = {"bomb", "rocket"}


def build_deck() -> list[Card]:
    """构造一副 54 张牌。"""
    deck: list[Card] = []
    for power in range(3, 16):
        for suit in SUITS:
            deck.append(Card(id=f"{suit}{power}", power=power, suit=suit, text=RANK_TEXT[power]))
    deck.append(Card(id="j16", power=16, suit=None, text="小"))
    deck.append(Card(id="j17", power=17, suit=None, text="大"))
    return deck


def _is_consecutive(uniq: list[int]) -> bool:
    return len(uniq) >= 1 and (max(uniq) - min(uniq) + 1) == len(uniq)


def identify(powers: list[int]) -> Combo | None:
    """识别一组牌力值的牌型；不合法返回 None。"""
    n = len(powers)
    if n == 0:
        return None
    cnt = Counter(powers)
    uniq = sorted(cnt)
    vals = sorted(cnt.values())

    # 王炸
    if n == 2 and set(powers) == {16, 17}:
        return Combo("rocket", 17, 2, 1)
    # 单张
    if n == 1:
        return Combo("single", powers[0], 1, 1)
    # 全同点
    if len(cnt) == 1:
        p = uniq[0]
        if n == 2:
            return Combo("pair", p, 2, 1)
        if n == 3:
            return Combo("trio", p, 3, 1)
        if n == 4:
            return Combo("bomb", p, 4, 1)
        return None
    # 三带一 / 三带二
    if n == 4 and vals == [1, 3]:
        trio = next(p for p, c in cnt.items() if c == 3)
        return Combo("trio_single", trio, 4, 1)
    if n == 5 and vals == [2, 3]:
        trio = next(p for p, c in cnt.items() if c == 3)
        return Combo("trio_pair", trio, 5, 1)
    # 单顺（≥5 连，不含 2/王）
    if n >= 5 and all(c == 1 for c in cnt.values()) and max(uniq) <= 14 and _is_consecutive(uniq):
        return Combo("straight", max(uniq), n, n)
    # 双顺（连对 ≥3 对，不含 2/王）
    if n >= 6 and n % 2 == 0 and all(c == 2 for c in cnt.values()) and max(uniq) <= 14 and _is_consecutive(uniq):
        return Combo("double_straight", max(uniq), n, len(uniq))
    # 纯飞机（连续三张，无翼）
    if n >= 6 and n % 3 == 0 and all(c == 3 for c in cnt.values()) and max(uniq) <= 14 and _is_consecutive(uniq):
        return Combo("airplane", max(uniq), n, len(uniq))
    # 飞机带翼
    air = _identify_airplane_wings(cnt, n)
    if air:
        return air
    # 四带二（两单）
    if n == 6:
        quads = [p for p, c in cnt.items() if c == 4]
        if len(quads) == 1 and vals == [1, 1, 4]:
            return Combo("four_two_single", quads[0], 6, 1)
    # 四带二（两对）
    if n == 8:
        quads = [p for p, c in cnt.items() if c == 4]
        if len(quads) == 1 and vals == [2, 2, 4]:
            return Combo("four_two_pair", quads[0], 8, 1)
    return None


def _identify_airplane_wings(cnt: Counter, n: int) -> Combo | None:
    """飞机带单/带对：k 个连续三张 + k 个单 或 k 个对。"""
    trios = sorted(p for p, c in cnt.items() if c >= 3 and p <= 14)
    for k in range(len(trios), 1, -1):
        for start in range(0, len(trios) - k + 1):
            window = trios[start:start + k]
            if window[-1] - window[0] != k - 1:
                continue
            remaining: list[int] = []
            ok = True
            tmp = dict(cnt)
            for p in window:
                tmp[p] -= 3
            for p, c in tmp.items():
                if c < 0:
                    ok = False
                    break
                remaining += [p] * c
            if not ok:
                continue
            wing = len(remaining)
            if wing == k:
                return Combo("airplane_single", window[-1], n, k)
            if wing == 2 * k:
                rc = Counter(remaining)
                if len(rc) == k and all(c == 2 for c in rc.values()):
                    return Combo("airplane_pair", window[-1], n, k)
    return None


def can_beat(prev: Combo | None, cur: Combo) -> bool:
    """cur 能否压过 prev（prev 为 None 表示自由出牌）。"""
    if cur.kind == "rocket":
        return True
    if prev is None:
        return True
    if cur.kind == "bomb":
        if prev.kind == "rocket":
            return False
        if prev.kind == "bomb":
            return cur.rank > prev.rank
        return True
    if prev.kind in BOMB_KINDS:
        return False
    return (
        cur.kind == prev.kind
        and cur.size == prev.size
        and cur.chain == prev.chain
        and cur.rank > prev.rank
    )


class IllegalMove(ValueError):
    """非法操作，附带可回灌给 LLM 的中文原因。"""


@dataclass(slots=True)
class SeatAction:
    """某座位最近一次动作（用于展示）。"""

    type: str  # "play" | "pass"
    cards: list[Card] = field(default_factory=list)


class DoudizhuGame:
    """斗地主单局状态机。座位固定 0/1/2。"""

    MAX_REDEAL = 3

    def __init__(self, seed: int | None = None, base_score: int = 1) -> None:
        self._rng = random.Random(seed)
        self.base_score = base_score
        self.hands: list[list[Card]] = [[], [], []]
        self.bottom: list[Card] = []
        self.phase = "dealing"
        self.landlord: int | None = None
        self.first_bidder = 0
        self.turn = 0
        self.multiplier = 1
        self.last_move: Combo | None = None
        self.last_cards: list[Card] = []
        self.last_player: int | None = None
        self.passes = 0
        self.play_counts = [0, 0, 0]
        self.seat_action: list[SeatAction | None] = [None, None, None]
        # 叫抢地主
        self.callers: list[int] = []
        self.bids_done = 0
        self._redeals = 0
        # 结算
        self.winner: int | None = None
        self.winner_side: str | None = None
        self.score = 0
        self.bottom_revealed = False
        self.start()

    # ---------------- 发牌与叫抢 ----------------

    def start(self) -> None:
        self._deal()
        self.first_bidder = self._rng.randrange(3)
        self._begin_bidding()

    def _deal(self) -> None:
        deck = build_deck()
        self._rng.shuffle(deck)
        self.hands = [deck[0:17], deck[17:34], deck[34:51]]
        self.bottom = deck[51:54]
        for h in self.hands:
            h.sort(key=lambda c: c.power)

    def _begin_bidding(self) -> None:
        self.phase = "bidding"
        self.turn = self.first_bidder
        self.callers = []
        self.bids_done = 0
        self.last_move = None
        self.last_cards = []
        self.last_player = None
        self.passes = 0
        self.seat_action = [None, None, None]
        self.landlord = None
        self.bottom_revealed = False
        self.multiplier = 1
        self.play_counts = [0, 0, 0]

    def apply_bid(self, seat: int, action: str) -> None:
        """叫/抢地主：action 为 'call'（叫/抢）或 'pass'（不叫/不抢）。"""
        if self.phase != "bidding":
            raise IllegalMove("当前不是叫地主阶段")
        if seat != self.turn:
            raise IllegalMove("还没轮到你叫地主")
        if action not in ("call", "pass"):
            raise IllegalMove("叫地主动作只能是 call 或 pass")

        if action == "call":
            self.callers.append(seat)
        self.seat_action[seat] = SeatAction("call" if action == "call" else "pass")
        self.bids_done += 1
        self.turn = (self.turn + 1) % 3

        if self.bids_done >= 3:
            self._resolve_bidding()

    def _resolve_bidding(self) -> None:
        if not self.callers:
            self._redeals += 1
            if self._redeals > self.MAX_REDEAL:
                # 多次流局：强制首叫者当地主，避免死循环
                self.callers = [self.first_bidder]
            else:
                self.first_bidder = (self.first_bidder + 1) % 3
                self._deal()
                self._begin_bidding()
                return
        landlord = self.callers[-1]
        # 第一个为"叫"，其余每个"抢"翻倍
        if len(self.callers) > 1:
            self.multiplier *= 2 ** (len(self.callers) - 1)
        self.landlord = landlord
        self.hands[landlord].extend(self.bottom)
        self.hands[landlord].sort(key=lambda c: c.power)
        self.bottom_revealed = True
        self.phase = "playing"
        self.turn = landlord
        self.last_move = None
        self.last_cards = []
        self.last_player = None
        self.passes = 0
        self.seat_action = [None, None, None]

    # ---------------- 出牌 ----------------

    def _take_cards(self, seat: int, card_ids: list[str]) -> list[Card]:
        hand = self.hands[seat]
        by_id = {c.id: c for c in hand}
        picked: list[Card] = []
        seen: set[str] = set()
        for cid in card_ids:
            if cid in seen:
                raise IllegalMove("出牌包含重复的牌")
            if cid not in by_id:
                raise IllegalMove("出的牌不在手牌中")
            seen.add(cid)
            picked.append(by_id[cid])
        if not picked:
            raise IllegalMove("没有选择要出的牌")
        return picked

    def apply_play(self, seat: int, card_ids: list[str]) -> None:
        if self.phase != "playing":
            raise IllegalMove("当前不是出牌阶段")
        if seat != self.turn:
            raise IllegalMove("还没轮到你出牌")
        picked = self._take_cards(seat, card_ids)
        combo = identify([c.power for c in picked])
        if combo is None:
            raise IllegalMove("这不是合法的牌型")
        free = self.last_move is None or self.last_player == seat
        if not free and not can_beat(self.last_move, combo):
            raise IllegalMove("这手牌压不过上家")

        picked_ids = {c.id for c in picked}
        self.hands[seat] = [c for c in self.hands[seat] if c.id not in picked_ids]
        self.play_counts[seat] += 1
        if combo.kind in BOMB_KINDS:
            self.multiplier *= 2
        self.last_move = combo
        self.last_cards = sorted(picked, key=lambda c: c.power)
        self.last_player = seat
        self.passes = 0
        self.seat_action[seat] = SeatAction("play", self.last_cards)

        if not self.hands[seat]:
            self._settle(seat)
            return
        self.turn = (seat + 1) % 3

    def apply_pass(self, seat: int) -> None:
        if self.phase != "playing":
            raise IllegalMove("当前不是出牌阶段")
        if seat != self.turn:
            raise IllegalMove("还没轮到你")
        if self.last_move is None or self.last_player == seat:
            raise IllegalMove("当前可自由出牌，必须出牌，不能过")
        self.seat_action[seat] = SeatAction("pass")
        self.passes += 1
        self.turn = (seat + 1) % 3
        if self.passes >= 2:
            # 其余两家连过，出牌权回到最后出牌者
            self.last_move = None
            self.last_cards = []
            self.passes = 0
            self.turn = self.last_player if self.last_player is not None else self.turn

    def _settle(self, winner: int) -> None:
        self.winner = winner
        self.phase = "finished"
        side = "landlord" if winner == self.landlord else "farmers"
        self.winner_side = side
        # 春天 / 反春天
        if side == "landlord":
            farmers = [s for s in range(3) if s != self.landlord]
            if all(self.play_counts[s] == 0 for s in farmers):
                self.multiplier *= 2
        else:
            if self.landlord is not None and self.play_counts[self.landlord] <= 1:
                self.multiplier *= 2
        self.score = self.base_score * self.multiplier

    # ---------------- 启发式提示（兜底 / 提示按钮） ----------------

    def hint(self, seat: int) -> dict[str, Any]:
        """给出一个合法动作建议：{'type':'play','cards':[id...]} 或 {'type':'pass'}。"""
        hand = self.hands[seat]
        if not hand:
            return {"type": "pass"}
        free = self.last_move is None or self.last_player == seat
        if free:
            low = min(hand, key=lambda c: c.power)
            return {"type": "play", "cards": [low.id]}
        move = self._find_beating(seat)
        if move is not None:
            return {"type": "play", "cards": [c.id for c in move]}
        bomb = self._find_bomb_or_rocket(seat)
        if bomb is not None:
            return {"type": "play", "cards": [c.id for c in bomb]}
        return {"type": "pass"}

    def _by_power(self, seat: int) -> dict[int, list[Card]]:
        groups: dict[int, list[Card]] = {}
        for c in self.hands[seat]:
            groups.setdefault(c.power, []).append(c)
        return groups

    def _find_beating(self, seat: int) -> list[Card] | None:
        """找一个与 last_move 同型、刚好压过的最小牌组。覆盖常见牌型。"""
        prev = self.last_move
        if prev is None:
            return None
        groups = self._by_power(seat)
        powers_sorted = sorted(groups)

        def pick(power: int, count: int) -> list[Card]:
            return groups[power][:count]

        if prev.kind == "single":
            for p in powers_sorted:
                if p > prev.rank:
                    return pick(p, 1)
        elif prev.kind == "pair":
            for p in powers_sorted:
                if p > prev.rank and len(groups[p]) >= 2:
                    return pick(p, 2)
        elif prev.kind == "trio":
            for p in powers_sorted:
                if p > prev.rank and len(groups[p]) >= 3:
                    return pick(p, 3)
        elif prev.kind in ("trio_single", "trio_pair"):
            wing = 1 if prev.kind == "trio_single" else 2
            for p in powers_sorted:
                if p > prev.rank and len(groups[p]) >= 3:
                    extra = self._pick_wings(groups, exclude={p}, count=1, each=wing)
                    if extra is not None:
                        return pick(p, 3) + extra
        elif prev.kind == "straight":
            res = self._find_straight(groups, prev.chain, prev.rank, each=1)
            if res:
                return res
        elif prev.kind == "double_straight":
            res = self._find_straight(groups, prev.chain, prev.rank, each=2)
            if res:
                return res
        return None

    def _pick_wings(
        self, groups: dict[int, list[Card]], *, exclude: set[int], count: int, each: int
    ) -> list[Card] | None:
        """挑 count 组、每组 each 张的最小翼牌（不与 exclude 重叠）。"""
        out: list[Card] = []
        for p in sorted(groups):
            if p in exclude:
                continue
            if len(groups[p]) >= each:
                out.extend(groups[p][:each])
                if len(out) >= count * each:
                    return out[: count * each]
        return None

    def _find_straight(
        self, groups: dict[int, list[Card]], chain: int, prev_rank: int, *, each: int
    ) -> list[Card] | None:
        """找长度 chain、每点 each 张、最高点 > prev_rank 的最小顺/连对。"""
        for high in range(prev_rank + 1, 15):  # 顶点不超过 A(14)
            low = high - chain + 1
            if low < 3:
                continue
            ok = all(p in groups and len(groups[p]) >= each for p in range(low, high + 1))
            if ok:
                out: list[Card] = []
                for p in range(low, high + 1):
                    out.extend(groups[p][:each])
                return out
        return None

    def _find_bomb_or_rocket(self, seat: int) -> list[Card] | None:
        groups = self._by_power(seat)
        prev = self.last_move
        # 王炸
        if 16 in groups and 17 in groups:
            return [groups[16][0], groups[17][0]]
        # 炸弹
        for p in sorted(groups):
            if len(groups[p]) >= 4:
                cand = identify([p, p, p, p])
                if prev is None or can_beat(prev, cand):
                    return groups[p][:4]
        return None

    # ---------------- 快照 ----------------

    def snapshot_core(self, viewer: int) -> dict[str, Any]:
        """核心状态快照；仅下发 viewer 自己的手牌，绝不泄露他人手牌。"""

        def action_dict(a: SeatAction | None) -> dict[str, Any] | None:
            if a is None:
                return None
            return {"type": a.type, "cards": [c.to_dict() for c in a.cards]}

        seats = []
        for i in range(3):
            seats.append(
                {
                    "index": i,
                    "remaining": len(self.hands[i]),
                    "isLandlord": self.landlord == i,
                    "playCount": self.play_counts[i],
                    "lastAction": action_dict(self.seat_action[i]),
                }
            )
        return {
            "phase": self.phase,
            "turn": self.turn,
            "landlord": self.landlord,
            "firstBidder": self.first_bidder,
            "multiplier": self.multiplier,
            "baseScore": self.base_score,
            "seats": seats,
            "bottom": [c.to_dict() for c in self.bottom] if self.bottom_revealed else [],
            "tableCards": [c.to_dict() for c in self.last_cards],
            "tablePlayer": self.last_player,
            "yourSeat": viewer,
            "yourHand": [c.to_dict() for c in sorted(self.hands[viewer], key=lambda c: c.power)],
            "freePlay": self.last_move is None or self.last_player == self.turn,
            "winner": self.winner,
            "winnerSide": self.winner_side,
            "score": self.score,
        }
