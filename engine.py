"""Pure Python rules. The engine has no dependency on the graphical interface."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import random

from cards import DEFINITIONS, REWARD_POOL, Card, make_card


@dataclass
class Player:
    hp: int = 80
    max_hp: int = 80
    gold: int = 50
    max_energy: int = 3
    deck: list[Card] = field(default_factory=list)

    def heal(self, amount):
        actual = min(amount, self.max_hp - self.hp)
        self.hp += actual
        return actual

    def increase_max_hp(self, amount):
        """Raise maximum HP and restore exactly the same amount of current HP."""
        if amount < 0:
            raise ValueError("Maximum HP gain cannot be negative")
        self.max_hp += amount
        return self.heal(amount)


@dataclass(frozen=True)
class Action:
    kind: str
    amount: int = 0
    hits: int = 1


@dataclass(frozen=True)
class EnemyDefinition:
    name: str
    hp: int
    actions: tuple[Action, ...]
    art: str
    tier: str = "normal"


ENEMIES = {
    "worm": EnemyDefinition("Cinderworm", 28, (Action("attack", 6),), "worm"),
    "worm_plus": EnemyDefinition("Greater Cinderworm", 55, (Action("attack", 11),), "worm"),
    "thief": EnemyDefinition("Tower Bandit", 40, (Action("attack", 8), Action("block", 7), Action("attack", 11)), "thief"),
    "thief_plus": EnemyDefinition("Veteran Tower Bandit", 80, (Action("attack", 13), Action("block", 11), Action("attack", 15)), "thief"),
    "guard": EnemyDefinition("Iron Guard", 48, (Action("attack", 9), Action("block", 9)), "guard"),
    "guard_plus": EnemyDefinition("Hardened Iron Guard", 90, (Action("attack", 17), Action("block", 15)), "guard"),
    "cultist": EnemyDefinition("Cultist", 55, (Action("ritual", 3), Action("attack", 3)), "cultist"),
    "cultist_plus": EnemyDefinition("Ascended Cultist", 110, (Action("ritual", 5), Action("attack", 6)), "cultist"),
    "furnace": EnemyDefinition("Furnace Sentinel", 80, (Action("attack", 8), Action("block", 12), Action("attack", 20)), "furnace", "elite"),
    "knight": EnemyDefinition("Bloodsworn Knight", 200, (Action("attack", 10), Action("strength", 3), Action("attack", 20)), "knight", "elite"),
    "smith": EnemyDefinition("Forge Warden", 140, (Action("attack", 10), Action("attack", 16), Action("charge"), Action("attack", 24)), "smith", "boss"),
    "lord": EnemyDefinition("Ember Lord", 300, (Action("attack", 18), Action("block", 20), Action("attack", 14, 2), Action("attack", 40)), "lord", "boss"),
}


@dataclass
class Enemy:
    key: str
    hp: int = 0
    block: int = 0
    strength: int = 0
    vulnerable: int = 0
    step: int = 0
    ritual: int = 0
    awakened: bool = False

    def __post_init__(self):
        self.hp = self.definition.hp

    @property
    def definition(self):
        return ENEMIES[self.key]

    @property
    def action(self):
        # Cultists perform the ritual once, then attack forever.
        if self.key.startswith("cultist") and self.step > 0:
            return self.definition.actions[1]
        return self.definition.actions[self.step % len(self.definition.actions)]

    def intent(self):
        action = self.action
        if action.kind == "attack":
            damage = action.amount + self.strength + self.ritual
            return f"Attack {damage}" + (f" × {action.hits}" if action.hits > 1 else "")
        return {
            "block": f"Gain {action.amount} Block",
            "strength": f"Gain {action.amount} Strength",
            "ritual": f"Ritual: +{action.amount} Strength each turn",
            "charge": "Charging · No attack this turn",
        }[action.kind]


class Battle:
    def __init__(self, player, enemy_key, rng=None):
        self.player = player
        self.enemy = Enemy(enemy_key)
        self.rng = rng or random.Random()
        self.draw_pile = list(player.deck)
        self.rng.shuffle(self.draw_pile)
        self.hand = []
        self.discard = []
        self.exhausted = []
        self.powers = []
        self.strength = 0
        self.block = 0
        self.demon = 0
        self.metal = 0
        self.barricade = False
        self.no_draw = False
        self.energy = 0
        self.turn = 0
        self.rampage = {}
        self.result = None
        self.log = []
        self.damage_dealt = 0
        self.start_turn()

    def emit(self, message):
        self.log.append(message)
        self.log = self.log[-12:]

    def start_turn(self):
        if self.result:
            return
        self.turn += 1
        if not self.barricade:
            self.block = 0
        self.energy = self.player.max_energy
        self.no_draw = False
        self.strength += self.demon
        self.draw(5)
        self.emit(f"Turn {self.turn} · Enemy intent: {self.enemy.intent()}")

    def draw(self, amount):
        if self.no_draw:
            return 0
        count = 0
        for _ in range(amount):
            if not self.draw_pile:
                if not self.discard:
                    break
                self.draw_pile, self.discard = self.discard, []
                self.rng.shuffle(self.draw_pile)
            self.hand.append(self.draw_pile.pop())
            count += 1
        return count

    def unavailable(self, card):
        if self.result:
            return "Combat has ended"
        if not any(c.uid == card.uid for c in self.hand):
            return "Card is no longer in hand"
        v = card.values
        if card.cost > self.energy:
            return "Not enough Energy"
        if v.get("life", 0) >= self.player.hp:
            return "Not enough HP to pay"
        if v.get("requires_attack") and self.enemy.action.kind != "attack":
            return "Enemy is not attacking"
        if v.get("double_strength") and self.strength <= 0:
            return "Requires positive Strength"
        if v.get("barricade") and self.barricade:
            return "Barricade is already active"
        return ""

    def attack_damage(self, card):
        v = card.values
        if v.get("slam"):
            value = self.block
        else:
            value = v.get("damage", 0) + self.strength * v.get("strength_scale", 1)
            value += self.rampage.get(card.uid, 0)
        value = max(0, value)
        return value * 3 // 2 if self.enemy.vulnerable > 0 else value

    def live_text(self, card):
        v = card.values
        if card.kind == "attack":
            damage = self.attack_damage(card)
            absorbed = min(damage, self.enemy.block)
            return f"Damage: {damage}" + (f" · Blocked: {absorbed}" if absorbed else "")
        if v.get("double_strength"):
            return f"Strength {self.strength} → {self.strength * 2}"
        if v.get("double_block"):
            return f"Block {self.block} → {self.block * 2}"
        if v.get("draw") and self.no_draw:
            return "No more draws this turn"
        if v.get("block"):
            return f"Block {self.block} → {self.block + v['block']}"
        return "Click to play"

    def play(self, uid):
        card = next((c for c in self.hand if c.uid == uid), None)
        if card is None:
            return False, "Card is no longer in hand"
        reason = self.unavailable(card)
        if reason:
            return False, reason
        self.hand.remove(card)
        self.energy -= card.cost
        v = card.values
        self.player.hp -= v.get("life", 0)
        summary = f"Played {card.name}"
        if card.kind == "attack":
            damage = self.attack_damage(card)
            absorbed = min(self.enemy.block, damage)
            self.enemy.block -= absorbed
            actual = min(self.enemy.hp, damage - absorbed)
            self.enemy.hp -= actual
            self.damage_dealt += actual
            summary += f" · Dealt {damage - absorbed} damage"
            if v.get("rampage"):
                self.rampage[card.uid] = self.rampage.get(card.uid, 0) + v["rampage"]
            if self.enemy.key == "lord" and self.enemy.hp <= 150 and not self.enemy.awakened:
                self.enemy.awakened = True
                self.enemy.strength += 3
                summary += " · Ember Awakening: enemy gains 3 Strength"
        # Killing an enemy immediately finishes the combat.
        if self.enemy.hp > 0:
            self.block += v.get("block", 0)
            self.strength += v.get("strength", 0)
            if v.get("double_strength"):
                self.strength *= 2
            if v.get("double_block"):
                self.block *= 2
            self.enemy.vulnerable += v.get("vulnerable", 0)
            self.player.heal(v.get("heal", 0))
            self.energy += v.get("energy", 0)
            self.demon += v.get("demon", 0)
            self.metal += v.get("metal", 0)
            self.barricade = self.barricade or v.get("barricade", False)
            self.draw(v.get("draw", 0))
            if v.get("no_draw"):
                self.no_draw = True
        if card.kind == "power":
            self.powers.append(card)
        elif v.get("exhaust"):
            self.exhausted.append(card)
        else:
            self.discard.append(card)
        self.emit(summary)
        if self.enemy.hp <= 0:
            self.result = "win"
        return True, summary

    def resolve_enemy_turn(self):
        """Resolve the enemy action; the UI starts the next turn after feedback."""
        if self.result:
            return "Combat has ended"
        self.discard.extend(self.hand)
        self.hand.clear()
        self.block += self.metal
        enemy = self.enemy
        enemy.block = 0
        enemy.strength += enemy.ritual
        action = enemy.action
        if action.kind == "attack":
            lost = 0
            for _ in range(action.hits):
                damage = max(0, action.amount + enemy.strength)
                absorbed = min(self.block, damage)
                self.block -= absorbed
                actual = min(self.player.hp, damage - absorbed)
                self.player.hp -= actual
                lost += actual
                if self.player.hp <= 0:
                    self.result = "loss"
                    break
            message = f"{enemy.definition.name} attacks · Lost {lost} HP"
        elif action.kind == "block":
            enemy.block = action.amount
            message = f"Enemy gains {action.amount} Block"
        elif action.kind == "strength":
            enemy.strength += action.amount
            message = f"Enemy gains {action.amount} Strength"
        elif action.kind == "ritual":
            enemy.ritual = action.amount
            message = f"Ritual active · +{action.amount} Strength each turn"
        else:
            message = "The enemy charges a heavy attack for next turn"
        enemy.vulnerable = max(0, enemy.vulnerable - 1)
        enemy.step += 1
        self.emit(message)
        return message

    def end_turn(self):
        message = self.resolve_enemy_turn()
        if not self.result:
            self.start_turn()
        return message


FLOORS = (
    ("battle", "Cinderworm", "worm"), ("battle", "Tower Bandit", "thief"),
    ("event", "Abandoned Altar", "altar"), ("battle", "Iron Guard", "guard"),
    ("camp", "Ember Campfire", "camp"), ("elite", "Furnace Sentinel", "furnace"),
    ("treasure", "Forgotten Chest", "treasure"), ("battle", "Cultist", "cultist"),
    ("camp", "Ember Campfire", "camp"), ("boss", "Forge Warden", "smith"),
    ("battle", "Greater Cinderworm", "worm_plus"), ("shop", "Tower Merchant", "shop"),
    ("event", "Warrior's Legacy", "legacy"), ("battle", "Hardened Iron Guard", "guard_plus"),
    ("elite", "Bloodsworn Knight", "knight"), ("shop", "Tower Merchant", "shop"),
    ("battle", "Veteran Tower Bandit", "thief_plus"), ("battle", "Ascended Cultist", "cultist_plus"),
    ("camp", "The Last Campfire", "camp"), ("boss", "Ember Lord", "lord"),
)
ROUTES = {"strength": "Demon Pact", "block": "Guardian Pact"}
BLESSINGS = {"attack": "Forged Blades", "defense": "Iron Resolve", "core": "Pact Gift"}


class Campaign:
    def __init__(self, route="strength", blessing="attack", seed=None):
        if route not in ROUTES or blessing not in BLESSINGS:
            raise ValueError("Invalid route or blessing")
        self.route, self.blessing = route, blessing
        self.rng = random.Random(seed)
        self.player = Player()
        self.player.deck = [make_card(k) for k in ["strike"] * 3 + ["defend"] * 4 + ["bash"]]
        keys = ("inflame", "heavy") if route == "strength" else ("impervious", "slam")
        self.player.deck.extend(make_card(k) for k in keys)
        if blessing == "core":
            self.player.deck.append(make_card("limit" if route == "strength" else "barricade"))
        self.floor = 1
        self.battle = None
        self.settled = False
        self.finished = False
        self.demo = False
        self.shop_cards = []
        self.shop_sold = set()
        self.shop_removed = False
        self.shop_healed = False
        self.total_turns = 0
        self.battles_won = 0

    @property
    def current_floor(self):
        return FLOORS[self.floor - 1]

    def blessed_card(self, key):
        definition = DEFINITIONS[key]
        upgraded = ((self.blessing == "attack" and definition.kind == "attack") or
                    (self.blessing == "defense" and definition.defensive))
        return make_card(key, upgraded)

    def reward(self):
        return [self.blessed_card(key) for key in self.rng.sample(REWARD_POOL, 3)]

    def enter_floor(self):
        self.settled = False
        kind, _, key = self.current_floor
        self.battle = None
        if kind in ("battle", "elite", "boss"):
            self.battle = Battle(self.player, key, self.rng)
        elif kind == "shop":
            route_pool = [k for k in REWARD_POOL if DEFINITIONS[k].route == self.route]
            first = self.rng.choice(route_pool)
            keys = [first] + self.rng.sample([k for k in REWARD_POOL if k != first], 4)
            self.rng.shuffle(keys)
            self.shop_cards = [self.blessed_card(k) for k in keys]
            self.shop_sold = set()
            self.shop_removed = self.shop_healed = False

    def settle_battle(self):
        if self.settled or not self.battle or self.battle.result != "win":
            return None
        self.settled = True
        self.battles_won += 1
        self.total_turns += self.battle.turn
        kind = self.current_floor[0]
        coins = {"battle": 15, "elite": 35, "boss": 60}[kind] if self.floor != 20 else 0
        self.player.gold += coins
        healed = self.player.heal(6)
        extra = 0
        if self.floor == 10:
            self.player.max_energy = 4
            extra = self.player.heal(20)
        if self.floor == 20:
            self.finished = True
        return {"gold": coins, "healed": healed + extra, "energy_up": self.floor == 10}

    def next_floor(self):
        if self.floor >= 20:
            self.finished = True
            return False
        self.floor += 1
        self.enter_floor()
        return True

    def receive(self, card):
        if any(c.uid == card.uid for c in self.player.deck):
            raise ValueError("This card has already been acquired")
        self.player.deck.append(card)

    def remove_card(self, uid):
        if len(self.player.deck) <= 1:
            raise ValueError("Your deck must contain at least 1 card")
        card = next((c for c in self.player.deck if c.uid == uid), None)
        if card is None:
            raise ValueError("Card not found")
        self.player.deck.remove(card)
        return card

    def transform(self, uid):
        old = next(c for c in self.player.deck if c.uid == uid)
        keys = [key for key in REWARD_POOL if key != old.key]
        # Transform is an event, so it preserves upgrades without invoking a blessing.
        new = make_card(self.rng.choice(keys), old.upgraded)
        self.player.deck[self.player.deck.index(old)] = new
        return old, new

    def buy(self, card):
        if not any(c.uid == card.uid for c in self.shop_cards) or card.uid in self.shop_sold:
            raise ValueError("Item is sold out or unavailable")
        if self.player.gold < 40:
            raise ValueError("Not enough Gold")
        self.receive(card)
        self.player.gold -= 40
        self.shop_sold.add(card.uid)


class Records:
    """Completed results only. A missing or damaged file must not prevent play."""
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"wins": 0, "losses": 0, "best_floor": 0, "runs": []}
        self.warning = ""
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Invalid records")
            for key in ("wins", "losses", "best_floor"):
                if not isinstance(value.get(key), int) or value[key] < 0:
                    raise ValueError("Invalid record counters")
            if not isinstance(value.get("runs"), list):
                raise ValueError("Invalid run list")
            self.data = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.warning = "Records could not be loaded. You can still play."

    def add(self, campaign, won):
        if campaign.demo:
            return
        self.data["wins" if won else "losses"] += 1
        self.data["best_floor"] = max(self.data["best_floor"], campaign.floor)
        self.data["runs"].append({
            "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "won": won, "floor": campaign.floor, "contract": campaign.route,
            "blessing": campaign.blessing,
            "deck": [{"key": c.key, "upgraded": c.upgraded} for c in campaign.player.deck],
        })
        self.data["runs"] = self.data["runs"][-30:]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            self.warning = ""
        except OSError:
            self.warning = "This result could not be saved. You can still play."
