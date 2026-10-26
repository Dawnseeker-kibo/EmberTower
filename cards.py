"""Card data for Ember Tower. All numbers are editable here."""
from dataclasses import dataclass, field
from itertools import count


@dataclass(frozen=True)
class CardDefinition:
    name: str
    kind: str
    cost: int
    values: dict = field(default_factory=dict)
    upgrades: dict = field(default_factory=dict)
    upgraded_cost: int | None = None
    route: str = "common"
    defensive: bool = False


DEFINITIONS = {
    "strike": CardDefinition("Strike", "attack", 1, {"damage": 6}, {"damage": 9}),
    "defend": CardDefinition("Defend", "skill", 1, {"block": 5}, {"block": 8}, defensive=True),
    "bash": CardDefinition("Bash", "attack", 2, {"damage": 8, "vulnerable": 2}, {"damage": 10, "vulnerable": 3}),
    "break": CardDefinition("Shatter", "attack", 1, {"damage": 15, "vulnerable": 3}, {"damage": 20, "vulnerable": 5}),
    "inflame": CardDefinition("Inflame", "power", 1, {"strength": 2}, {"strength": 3}, route="strength"),
    "spot": CardDefinition("Spot Weakness", "skill", 1, {"strength": 3, "requires_attack": True}, {"strength": 4}, route="strength"),
    "blood_rage": CardDefinition("Blood Oath", "skill", 0, {"life": 1, "strength": 2}, {"strength": 3}, route="strength"),
    "demon": CardDefinition("Demon Form", "power", 3, {"demon": 3}, {"demon": 4}, route="strength"),
    "limit": CardDefinition("Limit Break", "skill", 1, {"double_strength": True, "exhaust": True}, {"exhaust": False}, route="strength"),
    "heavy": CardDefinition("Heavy Blade", "attack", 2, {"damage": 16, "strength_scale": 3}, {"strength_scale": 5}, route="strength"),
    "impervious": CardDefinition("Impervious", "skill", 2, {"block": 30, "exhaust": True}, {"block": 40}, route="block", defensive=True),
    "shrug": CardDefinition("Shrug It Off", "skill", 1, {"block": 8, "draw": 1}, {"block": 11}, route="block", defensive=True),
    "barricade": CardDefinition("Barricade", "power", 3, {"barricade": True}, upgraded_cost=2, route="block"),
    "entrench": CardDefinition("Entrench", "skill", 2, {"double_block": True}, upgraded_cost=1, route="block", defensive=True),
    "slam": CardDefinition("Body Slam", "attack", 1, {"slam": True}, upgraded_cost=0, route="block"),
    "metal": CardDefinition("Metallicize", "power", 1, {"metal": 4}, {"metal": 6}, route="block"),
    "bludgeon": CardDefinition("Bludgeon", "attack", 3, {"damage": 32}, {"damage": 42}),
    "shockwave": CardDefinition("Expose", "skill", 1, {"vulnerable": 3, "exhaust": True}, {"vulnerable": 5}),
    "trance": CardDefinition("Battle Trance", "skill", 0, {"draw": 3, "no_draw": True}, {"draw": 4}),
    "bloodletting": CardDefinition("Bloodletting", "skill", 0, {"life": 3, "energy": 2, "exhaust": True}, {"energy": 3}),
    "pommel": CardDefinition("Pommel Strike", "attack", 1, {"damage": 9, "draw": 1}, {"damage": 10, "draw": 2}),
    "offering": CardDefinition("Offering", "skill", 0, {"life": 6, "draw": 3, "energy": 2, "exhaust": True}, {"draw": 5}),
    "rampage": CardDefinition("Rampage", "attack", 1, {"damage": 9, "rampage": 5}, {"rampage": 8}),
    "bandage": CardDefinition("Bandage", "skill", 0, {"heal": 4, "exhaust": True}, {"heal": 6}),
    "intimidate": CardDefinition("Provoke", "skill", 1, {"block": 7, "vulnerable": 1}, {"block": 8, "vulnerable": 2}, defensive=True),
}

BASIC = ("strike", "defend", "bash")
REWARD_POOL = tuple(key for key in DEFINITIONS if key not in (*BASIC, "break"))
KINDS = {"attack": "Attack", "skill": "Skill", "power": "Power"}
_ids = count(1)


@dataclass
class Card:
    key: str
    upgraded: bool = False
    uid: int = field(default_factory=lambda: next(_ids))

    @property
    def definition(self):
        return DEFINITIONS[self.key]

    @property
    def name(self):
        return self.definition.name + ("+" if self.upgraded else "")

    @property
    def kind(self):
        return self.definition.kind

    @property
    def cost(self):
        d = self.definition
        return d.upgraded_cost if self.upgraded and d.upgraded_cost is not None else d.cost

    @property
    def values(self):
        data = dict(self.definition.values)
        if self.upgraded:
            data.update(self.definition.upgrades)
        return data

    def description(self):
        v = self.values
        lines = []
        if v.get("life"):
            lines.append(f"Lose {v['life']} HP.")
        if v.get("slam"):
            lines.append("Deal damage equal to Block.\nKeep your Block.")
        elif "damage" in v:
            if v.get("strength_scale", 1) > 1:
                lines.append(f"Base damage: {v['damage']}.\nStrength scales {v['strength_scale']}x.")
            else:
                lines.append(f"Deal {v['damage']} damage.")
        if v.get("block"):
            lines.append(f"Gain {v['block']} Block.")
        if v.get("strength"):
            prefix = "If the enemy intends to\nattack, " if v.get("requires_attack") else ""
            lines.append(f"{prefix}gain {v['strength']} Strength." if prefix else f"Gain {v['strength']} Strength.")
        if v.get("double_strength"):
            lines.append("Double your Strength.")
        if v.get("double_block"):
            lines.append("Double your Block.")
        if v.get("vulnerable"):
            lines.append(f"Apply {v['vulnerable']} Vulnerable.")
        if v.get("heal"):
            lines.append(f"Heal {v['heal']} HP.")
        if v.get("energy"):
            lines.append(f"Gain {v['energy']} Energy.")
        if v.get("draw"):
            lines.append(f"Draw {v['draw']} cards.")
        if v.get("no_draw"):
            lines.append("No more draws this turn.")
        if v.get("rampage"):
            lines.append(f"This copy gains +{v['rampage']}\ndamage this combat.")
        if v.get("demon"):
            lines.append(f"At turn start, gain\n{v['demon']} Strength. Starts\nnext turn.")
        if v.get("barricade"):
            lines.append("Keep Block between turns\nfor this combat.")
        if v.get("metal"):
            lines.append(f"At turn end, gain\n{v['metal']} Block.")
        if v.get("exhaust"):
            lines.append("Exhaust.")
        return "\n".join(lines)


def make_card(key, upgraded=False):
    if key not in DEFINITIONS:
        raise ValueError(f"Unknown card: {key}")
    return Card(key, upgraded)
