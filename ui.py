"""Canvas-based desktop game interface. No third-party packages required."""
import math
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont

from cards import KINDS, Card, make_card
from engine import BLESSINGS, FLOORS, ROUTES, Battle, Campaign, Records


PALETTE = {
    "bg": "#111718", "panel": "#1b2426", "card": "#273134", "edge": "#435052",
    "text": "#f0e8d6", "dim": "#afb9b6", "gold": "#edb773", "muted": "#697874",
    "red": "#dc8074", "blue": "#82b9ce", "green": "#9dc5a3", "purple": "#b8a1d5",
}


class GameUI:
    WIDTH, HEIGHT = 1280, 800

    def __init__(self, root, save_path=None):
        self.root = root
        root.title("Ember Tower")
        root.geometry("1280x800")
        root.minsize(1024, 680)
        self.canvas = tk.Canvas(root, bg=PALETTE["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        fonts = set(tkfont.families(root))
        self.font = next((name for name in ("Segoe UI", "Arial", "Helvetica", "DejaVu Sans") if name in fonts), "TkDefaultFont")
        self.records = Records(save_path or Path(__file__).parent / "save" / "records.json")
        self.game = None
        self.screen = "title"
        self.route = "strength"
        self.blessing = "attack"
        self.demo_choice = False
        self.modal = None
        self.hits = []
        self.hover = None
        self.scale = 1
        self.ox = self.oy = 0
        self.notice = ""
        self.busy = False
        self.hand_page = 0
        self.offer = []
        self.reward_selected = None
        self.reward_remaining = 0
        self.reward_origin = "battle"
        self.recorded = False
        self.epoch = 0
        self.feedback = ""
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", lambda _: self.set_hover(None))
        self.canvas.bind("<Button-1>", self.on_click)
        root.bind("<Escape>", self.escape)
        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        self.render()

    def on_resize(self, event):
        self.scale = min(event.width / self.WIDTH, event.height / self.HEIGHT)
        self.ox = (event.width - self.WIDTH * self.scale) / 2
        self.oy = (event.height - self.HEIGHT * self.scale) / 2
        self.render()

    def pos(self, event):
        return ((event.x - self.ox) / self.scale, (event.y - self.oy) / self.scale)

    def on_motion(self, event):
        x, y = self.pos(event)
        hit = next((hit for hit in reversed(self.hits) if hit[0] <= x <= hit[2] and hit[1] <= y <= hit[3]), None)
        key = hit[5] if hit else None
        self.canvas.configure(cursor="hand2" if hit else "")
        self.set_hover(key)

    def set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.render()

    def on_click(self, event):
        x, y = self.pos(event)
        hit = next((hit for hit in reversed(self.hits) if hit[0] <= x <= hit[2] and hit[1] <= y <= hit[3]), None)
        if hit:
            self.hover = None
            hit[4]()

    def on_key(self, event):
        if event.keysym == "Escape":
            return
        if self.screen != "battle" or self.modal or self.busy or not self.game:
            return
        if event.char.lower() == "e":
            self.end_turn()
        elif event.char in "1234567" and event.char:
            index = self.hand_page * 7 + int(event.char) - 1
            if index < len(self.game.battle.hand):
                self.play(self.game.battle.hand[index].uid)

    def escape(self, _=None):
        if self.busy:
            return
        if self.modal:
            if self.modal.get("required"):
                return
            self.modal = None
        elif self.game and self.screen not in ("title", "contract", "result"):
            self.open_pause()
            return
        else:
            self.screen = "title"
        self.render()

    def rect(self, x, y, w, h, fill, outline=None, width=1):
        return self.canvas.create_rectangle(self.ox + x*self.scale, self.oy + y*self.scale,
                                            self.ox + (x+w)*self.scale, self.oy + (y+h)*self.scale,
                                            fill=fill, outline=outline or fill, width=width*self.scale)

    def oval(self, x, y, w, h, fill, outline=None, width=1):
        return self.canvas.create_oval(self.ox+x*self.scale, self.oy+y*self.scale,
                                       self.ox+(x+w)*self.scale, self.oy+(y+h)*self.scale,
                                       fill=fill, outline=outline or fill, width=width*self.scale)

    def poly(self, points, fill, outline=None, width=1):
        coords = []
        for x, y in points:
            coords.extend((self.ox+x*self.scale, self.oy+y*self.scale))
        return self.canvas.create_polygon(*coords, fill=fill, outline=outline or fill, width=width*self.scale)

    def line(self, points, fill, width=1):
        coords = []
        for x, y in points:
            coords.extend((self.ox+x*self.scale, self.oy+y*self.scale))
        return self.canvas.create_line(*coords, fill=fill, width=width*self.scale)

    def text(self, x, y, value, size=16, fill=None, anchor="nw", width=0, bold=False, justify="left"):
        return self.canvas.create_text(self.ox+x*self.scale, self.oy+y*self.scale, text=str(value),
                                       font=(self.font, -max(10, round(size*self.scale)), "bold" if bold else "normal"),
                                       fill=fill or PALETTE["text"], anchor=anchor,
                                       width=width*self.scale, justify=justify)

    def hit(self, x, y, w, h, callback, key):
        self.hits.append((x,y,x+w,y+h,callback,key))

    def button(self, x, y, w, h, label, callback, primary=False, enabled=True, key=None, small=False):
        key = key or ("button", label, x, y)
        active = self.hover == key and enabled
        color = PALETTE["gold"] if primary and enabled else ("#354346" if active else PALETTE["panel"])
        self.rect(x,y,w,h,color,PALETTE["gold"] if active else PALETTE["edge"])
        fg = PALETTE["bg"] if primary and enabled else (PALETTE["text"] if enabled else PALETTE["muted"])
        self.text(x+w/2,y+h/2,label,13 if small else 16,fg,"center")
        if enabled:
            self.hit(x,y,w,h,callback,key)

    def backdrop(self):
        self.rect(0,0,1280,800,PALETTE["bg"])
        # Original procedural stonework and embers; no external graphics required.
        for row in range(8):
            for col in range(10):
                x = col*150 - (75 if row % 2 else 0)
                self.rect(x,row*66+90,145,61,"#151d1f",outline="#192224")
        for x in (85,1195):
            self.rect(x-20,115,40,405,"#232b2c",outline="#303c3d")
            self.rect(x-32,125,64,18,"#354042")
            self.rect(x-29,489,58,24,"#354042")
            self.oval(x-30,215,60,90,"#342d24")
            self.poly([(x-10,276),(x-16,248),(x+2,218),(x+15,252),(x+9,276)],"#cc754a")
            self.poly([(x-5,274),(x-6,254),(x+3,237),(x+8,258),(x+5,274)],PALETTE["gold"])
        self.rect(0,491,1280,309,"#151e20")
        for i in range(24):
            x = (i*197+67) % 1280
            y = 140 + ((i*83) % 330)
            self.oval(x,y,2+(i%2),2+(i%2),"#6d543a")

    def header(self):
        self.rect(0,0,1280,75,PALETTE["panel"])
        self.rect(0,73,1280,2,PALETTE["edge"])
        self.text(30,15,"EMBER TOWER",25,PALETTE["gold"],bold=True)
        self.text(31,48,"DECKBUILDING ROGUELIKE",10,PALETTE["dim"])
        if not self.game:
            return
        g,p=self.game,self.game.player
        self.text(245,21,f"Floor {g.floor:02d} / 20 · {g.current_floor[1]}",18)
        self.text(660,23,f"HP {p.hp} / {p.max_hp}",16,PALETTE["red"])
        self.text(843,23,f"Gold {p.gold}",16,PALETTE["gold"])
        self.button(970,16,126,43,f"Deck · {len(p.deck)}",lambda:self.show_cards(p.deck,"Your Deck"),small=True)
        self.button(1112,16,135,43,"Pause / Help",self.open_pause,small=True,enabled=not self.busy)
        self.text(30,86,f"{ROUTES[g.route]}   /   {BLESSINGS[g.blessing]}" + ("   ·   DEMO" if g.demo else ""),13,PALETTE["dim"])
        for i in range(1,21):
            x=760+(i-1)*24
            color=PALETTE["gold"] if i==g.floor else ("#577769" if i<g.floor else "#354042")
            self.rect(x,87,15,7,color)

    def knight(self, x, y, scale=1, enemy=False, crown=False, art="guard"):
        def pt(a,b): return (x+a*scale,y+b*scale)
        def p(points,color,edge=None): self.poly([pt(a,b) for a,b in points],color,edge)
        def r(a,b,w,h,color,edge=None):
            xx,yy=pt(a,b);self.rect(xx,yy,w*scale,h*scale,color,edge)
        metal="#879da5" if not enemy else ("#bb785e" if art in ("knight","lord") else "#9a927a")
        dark="#425763" if not enemy else "#665043"
        cape="#793b38" if not enemy else "#47303b"
        p([(-45,40),(-65,143),(52,143),(38,39)],cape)
        r(-27,127,20,55,dark);r(8,127,20,55,dark)
        r(-35,175,30,10,metal);r(7,175,30,10,metal)
        p([(-43,49),(-24,36),(24,36),(43,49),(32,123),(15,142),(-18,142),(-34,121)],dark)
        p([(-29,52),(0,44),(29,52),(24,93),(0,108),(-25,93)],metal)
        r(-29,111,57,9,"#c9a36a")
        p([(-28,4),(-17,-10),(19,-10),(30,6),(24,33),(0,44),(-24,32)],metal)
        r(-21,10,43,8,"#182123")
        r(-2,0,5,36,dark)
        p([(-45,39),(-67,52),(-59,77),(-31,70)],metal)
        p([(42,39),(61,52),(57,77),(31,70)],metal)
        p([(-67,70),(-31,67),(-25,112),(-48,143),(-69,112)],dark,metal)
        p([(-60,79),(-39,77),(-34,107),(-48,127),(-61,107)],metal)
        r(56,6,6,102,"#d5cdb7");r(44,96,30,6,PALETTE["gold"]);r(56,102,6,22,"#725c43")
        if crown:
            p([(-29,-10),(-34,-37),(-12,-25),(0,-42),(14,-25),(34,-37),(29,-10)],PALETTE["gold"])
        if art in ("smith","furnace"):
            p([(-14,57),(14,57),(20,80),(0,94),(-20,80)],"#d08349")
        if art=="thief":
            p([(-29,0),(-4,-22),(27,-1),(22,20),(-23,20)],"#59634c")
        if art=="cultist":
            p([(-45,54),(0,27),(45,54),(65,177),(-62,177)],"#665474")
            r(-11,53,22,29,PALETTE["gold"])

    def draw_enemy(self,x,y,enemy):
        art=enemy.definition.art
        if art=="worm":
            for i in range(6):
                self.oval(x-85+i*28,y+55-math.sin(i*.8)*25,58,65,"#887b56",outline="#b1a071",width=2)
            self.oval(x+58,y+25,70,72,"#b2a16c",outline="#d0b47a",width=2)
            self.oval(x+96,y+42,7,8,PALETTE["bg"])
            self.poly([(x+104,y+76),(x+129,y+70),(x+120,y+92)],PALETTE["red"])
            for i in range(7):
                self.line([(x-80+i*28,y+106),(x-94+i*28,y+129)],"#b4a06b",4)
        else:
            scale=1.04 if art in ("lord","smith","knight") else .88
            self.knight(x,y-58,scale,True,art=="lord",art)

    def health_bar(self,x,y,w,h,hp,max_hp):
        self.rect(x,y,w,h,"#3c3333")
        if hp>0:
            self.rect(x,y,w*min(1,hp/max_hp),h,PALETTE["red"])

    def draw_card(self,card,x,y,w=180,h=230,callback=None,key=None,disabled="",live="",selected=False,battle=False):
        key=key or ("card",card.uid,x,y)
        raised=self.hover==key and callback is not None
        if raised: y-=7
        color={"attack":PALETTE["gold"],"skill":PALETTE["blue"],"power":PALETTE["purple"]}[card.kind]
        border=PALETTE["gold"] if selected or raised else PALETTE["edge"]
        self.rect(x+3,y+5,w,h,"#0f1516")
        self.rect(x,y,w,h,PALETTE["panel"] if disabled else PALETTE["card"],border,2 if selected else 1)
        self.rect(x,y,w,4,color if not disabled else PALETTE["muted"])
        self.oval(x+10,y+13,31,31,"#172022",color)
        self.text(x+25.5,y+28,card.cost,16,color,"center",bold=True)
        name_size=15 if w<170 else 17
        self.text(x+w/2,y+58,card.name,name_size,PALETTE["green"] if card.upgraded else PALETTE["text"],"center",bold=True)
        self.text(x+w-10,y+22,KINDS[card.kind],11,PALETTE["dim"],"ne")
        self.line([(x+12,y+85),(x+w-12,y+85)],PALETTE["edge"])
        # Text wraps inside the card; long descriptions use a smaller readable size.
        description=card.description()
        size=12 if h<=210 or len(description)>52 else 13
        self.text(x+13,y+98,description,size,PALETTE["dim"],width=w-26)
        if disabled or live:
            self.text(x+12,y+h-40,disabled or live,11,PALETTE["muted"] if disabled else color,width=w-24)
        if callback:
            self.hit(x,y,w,h,callback,key)

    def render(self):
        self.canvas.delete("all")
        self.hits=[]
        self.backdrop()
        if self.screen=="title": self.render_title()
        elif self.screen=="contract": self.render_contract()
        else:
            self.header()
            getattr(self,"render_"+self.screen)()
        if self.modal:
            self.render_modal()

    def render_title(self):
        self.text(640,95,"E M B E R   T O W E R",18,PALETTE["gold"],"center")
        self.text(640,164,"EMBER TOWER",58,PALETTE["text"],"center",bold=True)
        self.text(640,225,"Break the tower with Strength. Endure the embers with iron.",18,PALETTE["dim"],"center")
        self.knight(340,332,1.4)
        self.knight(955,321,1.5,True,True,"lord")
        self.button(490,320,300,62,"New Run",lambda:self.choose_contract(False),primary=True)
        self.button(490,402,300,56,"Demo Battle · Ready-made Deck",lambda:self.choose_contract(True))
        self.button(490,478,142,48,"How to Play",self.help)
        self.button(648,478,142,48,"Quit",self.root.destroy)
        self.text(640,614,"20 floors  /  24 regular cards  /  2 pacts",15,PALETTE["dim"],"center")
        d=self.records.data
        self.text(640,657,f"Wins {d['wins']}    Losses {d['losses']}    Best Floor {d['best_floor']}",14,PALETTE["dim"],"center")
        self.text(640,718,self.records.warning or "Mouse controls · 1–7: play card · E: end turn · Esc: pause",13,PALETTE["muted"],"center")

    def choose_contract(self,demo):
        self.game=None
        self.demo_choice=demo
        self.screen="contract"
        self.modal=None
        self.render()

    def render_contract(self):
        self.text(640,62,"Choose Your Pact",32,PALETTE["gold"],"center",bold=True)
        self.text(640,108,"Demo mode uses a prepared deck and does not affect your records." if self.demo_choice else "Your pact determines starting cards and one shop offer. Combat rewards are random.",15,PALETTE["dim"],"center")
        for route,x,title,desc in [
            ("strength",200,"Demon Pact","Inflame + Heavy Blade\nBuild Strength, then double it with Limit Break."),
            ("block",660,"Guardian Pact","Impervious + Body Slam\nBuild Block and turn defense into damage.")]:
            selected=self.route==route
            self.rect(x,155,420,190,PALETTE["panel"],PALETTE["gold"] if selected else PALETTE["edge"],2)
            self.text(x+28,179,title,25,PALETTE["gold"] if selected else PALETTE["text"],bold=True)
            self.text(x+28,232,desc,17,PALETTE["dim"],width=365)
            self.hit(x,155,420,190,lambda r=route:self.select_route(r),("route",route))
        self.text(640,382,"Choose One Blessing",21,anchor="center")
        options=[("attack","Forged Blades","Attack cards from rewards\nand shops arrive upgraded."),("defense","Iron Resolve","Block Skills from rewards\nand shops arrive upgraded."),("core","Pact Gift","Add one extra card:\nLimit Break / Barricade.")]
        for i,(key,title,desc) in enumerate(options):
            x=170+i*320
            self.rect(x,421,300,145,PALETTE["panel"],PALETTE["gold"] if self.blessing==key else PALETTE["edge"],2)
            self.text(x+20,439,title,20,PALETTE["gold"] if self.blessing==key else PALETTE["text"])
            self.text(x+20,480,desc,16,PALETTE["dim"],width=260)
            self.hit(x,421,300,145,lambda k=key:self.select_blessing(k),("blessing",key))
        self.button(465,626,350,60,"Enter Demo Battle" if self.demo_choice else "Enter Floor 1",self.start_game,primary=True)
        self.button(40,712,145,45,"Main Menu",self.to_title)
        self.text(640,737,"Blessings do not upgrade starting cards. Pact Gift adds one card to your deck.",13,PALETTE["dim"],"center")

    def select_route(self,route):
        self.route=route;self.render()

    def select_blessing(self,blessing):
        self.blessing=blessing;self.render()

    def start_game(self):
        self.epoch+=1
        self.recorded=False
        self.busy=False
        self.modal=None
        self.game=Campaign(self.route,self.blessing)
        if self.demo_choice:
            self.setup_demo()
        else:
            self.game.enter_floor()
        self.enter_screen()

    def setup_demo(self):
        g=self.game;g.demo=True;g.floor=20;g.player.max_energy=4
        keys=(["inflame","limit","heavy","bloodletting","offering","pommel","shockwave","trance","defend","spot","heavy","bandage"] if g.route=="strength" else ["impervious","entrench","slam","shrug","offering","defend","shrug","trance","shockwave","slam","bloodletting","metal"])
        g.player.deck=[make_card(k,True) for k in keys]
        g.enter_floor()
        b=g.battle;b.hand=list(g.player.deck[:5]);b.draw_pile=list(reversed(g.player.deck[5:]));b.discard=[]
        if g.route=="strength": b.strength=4
        else: b.barricade=True;b.metal=6
        b.emit("Demo: some abilities are already active. Try a card combination.")

    def enter_screen(self):
        self.modal=None;self.notice="";self.feedback="";self.hand_page=0
        kind=self.game.current_floor[0]
        self.screen="battle" if self.game.battle else ("camp" if kind=="camp" else "shop" if kind=="shop" else "event")
        self.render()

    def advance(self):
        if self.game.next_floor(): self.enter_screen()
        else: self.finish(True)

    def render_battle(self):
        b,p=self.game.battle,self.game.player
        enemy=b.enemy
        self.oval(160,399,265,25,"#0d1213")
        self.oval(846,399,270,25,"#0d1213")
        self.knight(292,202,1.05)
        self.draw_enemy(977,260,enemy)
        self.text(292,411,"Ember Warrior",19,anchor="center",bold=True)
        self.health_bar(165,434,254,10,p.hp,p.max_hp)
        self.text(292,458,f"HP {p.hp} / {p.max_hp}",13,anchor="center")
        self.text(292,484,f"Block {b.block}   ·   Strength {b.strength}",16,PALETTE["blue"],"center")
        buffs=[]
        if b.barricade: buffs.append("Barricade")
        if b.metal: buffs.append(f"Metallicize {b.metal}")
        if b.demon: buffs.append(f"Demon Form {b.demon}")
        self.text(460,167,"  /  ".join(buffs) or "Ember Core · Heal 6 HP after combat",13,PALETTE["dim"],width=330)
        self.text(977,411,enemy.definition.name,20,anchor="center",bold=True)
        self.health_bar(850,434,254,10,enemy.hp,enemy.definition.hp)
        self.text(977,458,f"HP {enemy.hp} / {enemy.definition.hp}",13,anchor="center")
        self.text(977,484,f"Block {enemy.block} · Strength {enemy.strength}"+(f" · Vulnerable {enemy.vulnerable}" if enemy.vulnerable else ""),14,PALETTE["red"],"center")
        self.rect(823,116,310,39,PALETTE["panel"],PALETTE["edge"])
        self.text(978,135,"Intent: "+enemy.intent(),15,PALETTE["gold"],"center")
        self.text(640,270,"TURN",13,PALETTE["muted"],"center")
        self.text(640,307,f"{b.turn:02d}",42,PALETTE["dim"],"center")
        self.text(640,359,self.feedback,19,PALETTE["gold"],"center",width=300,justify="center")
        message=self.notice or (b.log[-1] if b.log else "")
        self.rect(0,505,1280,34,PALETTE["panel"])
        self.text(640,522,message,13,PALETTE["gold"],"center",width=1190,justify="center")
        self.oval(19,571,87,87,PALETTE["panel"],PALETTE["gold"],2)
        self.text(62,601,b.energy,27,PALETTE["gold"],"center",bold=True)
        self.text(62,636,f"/ {p.max_energy} Energy",11,PALETTE["dim"],"center")
        pages=max(1,math.ceil(len(b.hand)/7));self.hand_page=min(self.hand_page,pages-1)
        hand=b.hand[self.hand_page*7:(self.hand_page+1)*7]
        n=len(hand);w=min(174,(992-max(0,n-1)*10)/max(1,n));start=130+(992-(n*w+max(0,n-1)*10))/2
        for i,c in enumerate(hand):
            reason=b.unavailable(c)
            self.draw_card(c,start+i*(w+10),552,w,214,callback=(lambda uid=c.uid:self.play(uid)) if not self.busy else None,key=("hand",c.uid),disabled=reason,live=b.live_text(c))
        if not hand: self.text(640,657,"Your hand is empty. End your turn to draw new cards.",17,PALETTE["dim"],"center")
        self.button(18,679,92,36,f"Draw {len(b.draw_pile)}",lambda:self.show_cards(sorted(b.draw_pile,key=lambda c:c.name),"Draw Pile (Unordered)"),enabled=not self.busy,small=True)
        self.button(18,728,92,36,f"Discard {len(b.discard)}",lambda:self.show_cards(b.discard,"Discard Pile"),enabled=not self.busy,small=True)
        self.button(1137,552,120,40,f"Exhaust {len(b.exhausted)}",lambda:self.show_cards(b.exhausted,"Exhaust Pile"),enabled=not self.busy,small=True)
        self.button(1137,608,120,40,"Powers / Log",lambda:self.show_log(),enabled=not self.busy,small=True)
        self.button(1137,690,120,65,"Enemy Turn" if self.busy else "End Turn",self.end_turn,primary=True,enabled=not self.busy and not b.result,small=True)
        if pages>1:
            self.button(533,771,62,25,"Previous",lambda:self.hand_next(-1),small=True,enabled=self.hand_page>0)
            self.text(640,784,f"Hand {self.hand_page+1} / {pages}",11,anchor="center")
            self.button(685,771,62,25,"Next",lambda:self.hand_next(1),small=True,enabled=self.hand_page<pages-1)

    def hand_next(self,amount):
        self.hand_page+=amount;self.render()

    def play(self,uid):
        if self.busy or self.modal or self.screen!="battle": return
        b=self.game.battle
        before=b.enemy.hp
        ok,message=b.play(uid)
        self.notice=message
        if ok:
            dealt=before-b.enemy.hp
            self.feedback=f"−{dealt}" if dealt else "Effect applied"
            self.hand_page=min(self.hand_page,max(0,(len(b.hand)-1)//7))
            if b.result:
                self.busy=True
                self.render()
                epoch=self.epoch
                self.root.after(650,lambda:self.after_battle() if self.epoch==epoch else None)
                return
        self.render()

    def end_turn(self):
        if self.busy or self.modal or self.screen!="battle" or self.game.battle.result: return
        self.busy=True
        b=self.game.battle
        self.notice=b.resolve_enemy_turn()
        self.feedback="Enemy action"
        self.render()
        epoch=self.epoch
        def complete():
            if epoch!=self.epoch: return
            self.busy=False
            if b.result: self.after_battle()
            else:
                b.start_turn();self.notice="";self.feedback="";self.hand_page=0;self.render()
        self.root.after(700,complete)

    def after_battle(self):
        self.busy=False
        if self.game.battle.result=="loss": self.finish(False);return
        loot=self.game.settle_battle()
        if loot is None: return
        if self.game.floor==20: self.finish(True);return
        self.notice=f"Victory · +{loot['gold']} Gold · Healed {loot['healed']} HP"+(" · Maximum Energy increased to 4" if loot['energy_up'] else "")
        self.begin_reward("battle",1)

    def begin_reward(self,origin,count):
        self.reward_origin=origin;self.reward_remaining=count
        self.offer=self.game.reward();self.reward_selected=None;self.screen="reward";self.modal=None;self.render()

    def render_reward(self):
        chain=f"Reward {7-self.reward_remaining} / 6" if self.reward_origin=="legacy" else "Card Reward"
        self.text(640,145,chain,30,PALETTE["gold"],"center",bold=True)
        self.text(640,191,self.notice or "Choose one card to add, or decline for +2 Max HP and heal 2.",15,PALETTE["dim"],"center",width=1100)
        for i,c in enumerate(self.offer):
            self.draw_card(c,295+i*240,235,210,292,lambda card=c:self.select_reward(card),selected=self.reward_selected==c.uid)
        selected=next((c for c in self.offer if c.uid==self.reward_selected),None)
        if selected:
            self.button(470,569,340,53,"Add Card to Deck",lambda:self.take_reward(selected),primary=True)
        else:
            self.text(640,595,"Select a card above to add it to your deck.",16,PALETTE["dim"],"center")
        self.button(420,660,440,50,"Decline Cards: +2 Max HP and Heal 2",self.skip_reward,primary=False)
        self.text(640,744,"Rewards only add cards. Declining raises both maximum and current HP by 2.",12,PALETTE["dim"],"center")

    def select_reward(self,card): self.reward_selected=card.uid;self.render()

    def take_reward(self,card):
        if self.screen!="reward" or not any(c.uid==card.uid for c in self.offer):return
        self.game.receive(card);self.finish_reward()

    def skip_reward(self):
        if self.screen!="reward":return
        self.game.player.increase_max_hp(2);self.finish_reward()

    def finish_reward(self):
        self.modal=None
        self.reward_remaining-=1
        if self.reward_remaining>0:
            self.offer=self.game.reward();self.reward_selected=None;self.notice="";self.render()
        elif self.reward_origin=="legacy": self.event_done("All six card rewards have been resolved.")
        else: self.advance()

    def render_camp(self):
        heal=30 if self.game.floor==19 else 25
        self.text(640,162,"The Last Campfire" if self.game.floor==19 else "Ember Campfire",34,PALETTE["gold"],"center",bold=True)
        self.draw_fire(640,335)
        self.text(640,487,"Rest in the warmth, or forge a stronger card.",18,PALETTE["dim"],"center")
        self.button(310,555,300,70,f"Rest · Heal {heal} HP",lambda:self.rest(heal),primary=True)
        self.button(670,555,300,70,"Forge · Upgrade a Card",lambda:self.select_upgrade(lambda c:self.event_done(f"Upgraded {c.definition.name}.")),enabled=any(not c.upgraded for c in self.game.player.deck))
        self.text(640,696,"Choose only one action on this floor.",14,PALETTE["dim"],"center")

    def draw_fire(self,x,y):
        self.oval(x-105,y+65,210,30,"#343433")
        self.poly([(x-87,y+68),(x+65,y+92),(x+75,y+73),(x-76,y+50)],"#705640")
        self.poly([(x+86,y+62),(x-65,y+94),(x-78,y+74),(x+73,y+44)],"#8a6746")
        self.poly([(x-52,y+66),(x-65,y+5),(x-20,y-61),(x-4,y-12),(x+28,y-97),(x+62,y+5),(x+37,y+65)],"#bc6541")
        self.poly([(x-23,y+65),(x-33,y+13),(x+4,y-35),(x+13,y+2),(x+29,y-18),(x+34,y+34),(x+15,y+66)],PALETTE["gold"])

    def rest(self,amount):
        healed=self.game.player.heal(amount);self.event_done(f"Restored {healed} HP at the campfire.")

    def select_upgrade(self,callback):
        def selected(card):
            card.upgraded=True;callback(card)
        self.show_cards([c for c in self.game.player.deck if not c.upgraded],"Choose a Card to Upgrade","upgrade",selected)

    def render_event(self):
        key=self.game.current_floor[2]
        if key=="altar":
            self.text(640,166,"Abandoned Altar",34,PALETTE["gold"],"center",bold=True)
            self.text(640,232,"Firelight falls across the stone altar.\nChoose a change before continuing your climb.",18,PALETTE["dim"],"center",justify="center")
            self.option(170,350,"Forget","Remove one card.\nKeep at least 1 card.",lambda:self.select_remove("Choose a Card to Remove",lambda c:self.event_done(f"Removed {c.name}.")),len(self.game.player.deck)>1)
            self.option(500,350,"Forge","Upgrade one card that is\nnot already upgraded.",lambda:self.select_upgrade(lambda c:self.event_done(f"Upgraded {c.name}.")),any(not c.upgraded for c in self.game.player.deck))
            self.option(830,350,"Transform","Transform one card into a\nrandom non-basic card.\nKeep its upgrade.",self.select_transform)
            self.button(540,668,200,49,"Leave the Altar",lambda:self.event_done("You keep your current deck."))
        elif key=="treasure":
            self.text(640,164,"Forgotten Chest",34,PALETTE["gold"],"center",bold=True)
            self.rect(535,295,210,137,"#6e533b",PALETTE["gold"],3)
            self.rect(535,295,210,38,"#8c6c47",PALETTE["gold"],2)
            self.rect(625,318,30,42,PALETTE["gold"])
            self.text(640,487,"Heal 20 HP  ·  Upgrade one card  ·  Gain 40 Gold",19,anchor="center")
            self.button(470,580,340,61,"Open Chest",self.open_treasure,primary=True)
        else:
            self.text(640,163,"Warrior's Legacy",34,PALETTE["gold"],"center",bold=True)
            self.text(640,226,"Three gifts. Choose only one.",18,PALETTE["dim"],"center")
            has_bash=any(c.key=="bash" for c in self.game.player.deck)
            self.option(170,330,"Shatter","Turn one Bash into Shatter.\nKeep its upgrade.",self.select_break,has_bash)
            self.option(500,330,"Sixfold Gift","Receive six consecutive\nthree-card rewards.",lambda:self.begin_reward("legacy",6))
            self.option(830,330,"Enduring Body","Gain 20 Max HP\nand heal 20 HP.",self.legacy_health)

    def option(self,x,y,title,desc,callback,enabled=True):
        self.rect(x,y,280,230,PALETTE["panel"],PALETTE["edge"])
        self.text(x+140,y+34,title,24,PALETTE["gold"] if enabled else PALETTE["muted"],"center")
        self.text(x+25,y+82,desc,16,PALETTE["dim"],width=230)
        self.button(x+35,y+165,210,44,"Choose" if enabled else "Unavailable",callback,primary=enabled,enabled=enabled)

    def select_remove(self,title,callback):
        if len(self.game.player.deck)<=1: return
        def remove(card):
            old=self.game.remove_card(card.uid);callback(old)
        self.show_cards(self.game.player.deck,title,"remove",remove)

    def select_transform(self):
        def transform(card):
            old,new=self.game.transform(card.uid);self.event_done(f"{old.name} transformed into {new.name}.")
        self.show_cards(self.game.player.deck,"Choose a Card to Transform","transform",transform)

    def open_treasure(self):
        p=self.game.player
        healed=p.heal(20);p.gold+=40
        message=f"Gained 40 Gold and restored {healed} HP. "
        if any(not c.upgraded for c in p.deck):
            # Treasure is already claimed; cancel closes the upgrade choice without claiming it again.
            self.screen="event_result";self.notice=message
            self.select_upgrade(lambda c:self.event_done(message+f"Upgraded {c.name}."))
            self.modal["required"]=True
            self.render()
        else: self.event_done(message+"All cards are already upgraded.")

    def select_break(self):
        def replace(card):
            card.key="break";self.event_done(f"Bash became {card.name}.")
        self.show_cards([c for c in self.game.player.deck if c.key=="bash"],"Choose a Bash to Shatter","break",replace)

    def legacy_health(self):
        self.game.player.increase_max_hp(20);self.event_done("Gained 20 Max HP and restored 20 HP.")

    def event_done(self,message):
        self.modal=None;self.notice=message;self.screen="event_result";self.render()

    def render_event_result(self):
        self.text(640,248,"The Journey Continues",34,PALETTE["gold"],"center",bold=True)
        self.text(640,373,self.notice,21,anchor="center",width=950,justify="center")
        self.button(475,531,330,66,"Continue to Next Floor",self.advance,primary=True)

    def render_shop(self):
        p=self.game.player
        self.text(640,147,"Tower Merchant",32,PALETTE["gold"],"center",bold=True)
        self.text(640,191,self.notice or "40 Gold per card · At least one offer matches your pact · One purchase per item",15,PALETTE["dim"],"center",width=1100)
        for i,c in enumerate(self.game.shop_cards):
            x=130+i*207;sold=c.uid in self.game.shop_sold
            self.draw_card(c,x,235,190,282,lambda card=c:self.show_buy(card) if card.uid not in self.game.shop_sold else None,disabled="Sold out" if sold else "",live="40 Gold")
        self.button(220,565,245,53,"Remove a Card · 25 Gold",self.shop_remove,enabled=p.gold>=25 and not self.game.shop_removed and len(p.deck)>1)
        self.button(500,565,245,53,"Heal 15 HP · 30 Gold",self.shop_heal,enabled=p.gold>=30 and not self.game.shop_healed and p.hp<p.max_hp,small=True)
        self.button(780,565,245,53,"Leave Shop",self.advance,primary=True)
        self.text(640,689,"Removal and healing can each be purchased once. Cards are added to your deck.",14,PALETTE["dim"],"center")

    def show_buy(self,card):
        if card.uid in self.game.shop_sold: return
        if self.game.player.gold<40:
            self.notice="Not enough Gold. A card costs 40 Gold.";self.render();return
        self.modal={"type":"buy","card":card};self.render()

    def buy(self,card):
        try: self.game.buy(card)
        except ValueError as error: self.notice=str(error)
        else: self.notice=f"Purchased {card.name}."
        self.modal=None;self.render()

    def shop_remove(self):
        g=self.game
        if g.shop_removed or g.player.gold<25:return
        def remove(card):
            if g.shop_removed or g.player.gold<25:return
            g.remove_card(card.uid);g.player.gold-=25;g.shop_removed=True
            self.modal=None;self.notice=f"Spent 25 Gold to remove {card.name}.";self.render()
        self.show_cards(g.player.deck,"Remove a Card · 25 Gold","remove",remove)

    def shop_heal(self):
        g=self.game
        if g.shop_healed or g.player.gold<30 or g.player.hp>=g.player.max_hp:return
        g.player.gold-=30;g.shop_healed=True
        healed=g.player.heal(15);self.notice=f"Spent 30 Gold to restore {healed} HP.";self.render()

    def finish(self,won):
        self.screen="result";self.modal=None;self.busy=False
        self.won=won
        if not self.recorded:
            self.records.add(self.game,won);self.recorded=True
        self.render()

    def render_result(self):
        g=self.game;p=g.player
        title="The Tower Has Fallen" if self.won else "The Embers Remain"
        self.text(640,188,title,43,PALETTE["gold"],"center",bold=True)
        self.text(640,252,"Demo complete. This battle does not affect your records." if g.demo else ("You defeated the Ember Lord and completed all 20 floors." if self.won else "Refine your deck and your decisions. The tower awaits."),18,PALETTE["dim"],"center")
        self.text(640,342,f"{ROUTES[g.route]}  /  {BLESSINGS[g.blessing]}",21,anchor="center")
        self.text(640,395,f"Floor {g.floor} reached · HP {p.hp}/{p.max_hp} · Deck {len(p.deck)} cards",18,PALETTE["dim"],"center")
        self.button(260,491,230,60,"View Final Deck",lambda:self.show_cards(p.deck,"Final Deck"))
        self.button(525,491,230,60,"Try Again",lambda:self.choose_contract(g.demo),primary=True)
        self.button(790,491,230,60,"Main Menu",self.to_title)
        self.text(640,652,self.records.warning or "Every choice is a lesson for the next climb.",15,PALETTE["dim"],"center")

    def to_title(self):
        self.epoch+=1;self.game=None;self.modal=None;self.screen="title";self.busy=False;self.render()

    def open_pause(self):
        if self.busy:return
        self.modal={"type":"pause"};self.render()

    def help(self):
        self.modal={"type":"help"};self.render()

    def show_log(self):
        self.modal={"type":"log"};self.render()

    def show_cards(self,cards,title,mode="view",callback=None):
        self.modal={"type":"cards","cards":list(cards),"title":title,"mode":mode,"callback":callback,"page":0,"selected":None}
        self.render()

    def close_modal(self):
        if self.modal and self.modal.get("required"):
            return
        self.modal=None;self.render()

    def select_modal_card(self,card):
        if self.modal["mode"]=="view":return
        self.modal["selected"]=card.uid;self.render()

    def modal_page(self,delta):
        self.modal["page"]+=delta;self.modal["selected"]=None;self.render()

    def confirm_modal_card(self):
        m=self.modal
        card=next((c for c in m["cards"] if c.uid==m["selected"]),None)
        if not card:return
        callback=m["callback"];self.modal=None
        if callback:callback(card)

    def render_modal(self):
        # A modal replaces all background hit targets, so clicks cannot leak through.
        self.hits=[]
        m=self.modal;kind=m["type"]
        self.rect(62,112,1156,652,"#1a2426",PALETTE["gold"],2)
        self.button(1090,128,102,40,"Choose a Card" if m.get("required") else "Close",self.close_modal,small=True,enabled=not m.get("required"))
        if kind=="cards":
            self.text(90,140,m["title"],24,PALETTE["gold"])
            cards=m["cards"];pages=max(1,math.ceil(len(cards)/8));m["page"]=min(m["page"],pages-1)
            visible=cards[m["page"]*8:(m["page"]+1)*8]
            selected=next((c for c in cards if c.uid==m["selected"]),None)
            for i,c in enumerate(visible):
                col,row=i%4,i//4
                self.draw_card(c,102+col*279,198+row*233,255,216,lambda card=c:self.select_modal_card(card),selected=c.uid==m["selected"])
            if not cards:self.text(640,360,"There are no cards here.",20,PALETTE["dim"],"center")
            self.button(95,704,93,38,"Previous",lambda:self.modal_page(-1),small=True,enabled=m["page"]>0)
            self.text(240,722,f"{m['page']+1} / {pages}",13,anchor="center")
            self.button(288,704,93,38,"Next",lambda:self.modal_page(1),small=True,enabled=m["page"]<pages-1)
            if m["mode"]!="view":
                label={"upgrade":"Confirm Upgrade","remove":"Confirm Removal","transform":"Confirm Transform","break":"Confirm Shatter"}.get(m["mode"],"Confirm")
                self.button(982,699,205,47,label,self.confirm_modal_card,primary=True,enabled=selected is not None)
                if selected:
                    if m["mode"]=="upgrade":
                        upgraded=Card(selected.key,True)
                        info=f"Upgraded: {upgraded.cost} Energy · "+upgraded.description().replace("\n"," ")
                    elif m["mode"]=="break":info=f"Bash → Shatter{'+' if selected.upgraded else ''} · 1 Energy"
                    else:info="Selected: "+selected.name
                    self.text(412,701,info,12,PALETTE["gold"],width=540)
            else:self.text(475,716,"Sorted by name. Draw order is hidden." if "Draw Pile" in m["title"] else f"{len(cards)} cards",13,PALETTE["dim"])
        elif kind=="buy":
            c=m["card"]
            self.text(640,158,"Buy a Card · 40 Gold",26,PALETTE["gold"],"center")
            self.draw_card(c,530,218,220,300)
            self.button(470,570,340,55,"Buy and Add to Deck",lambda:self.buy(c),primary=True)
            self.text(640,677,"Gold is charged only when you confirm. Purchased cards are added to your deck.",15,PALETTE["dim"],"center")
        elif kind=="pause":
            self.text(640,183,"Take a Breath",31,PALETTE["gold"],"center")
            self.text(640,268,"There is no mid-run save. Returning to the menu ends this run.",18,PALETTE["dim"],"center")
            self.button(470,360,340,60,"Resume Run",self.close_modal,primary=True)
            self.button(470,445,340,55,"How to Play",self.help)
            self.button(470,525,340,55,"Main Menu",self.to_title)
        elif kind=="log":
            b=self.game.battle
            self.text(100,142,"Powers and Combat Log",24,PALETTE["gold"])
            powers=", ".join(c.name for c in b.powers) or "None"
            self.text(102,198,"Active powers: "+powers,15,PALETTE["dim"],width=1030)
            self.text(102,274,"\n\n".join(b.log[-9:]),15,width=1030)
        else:
            self.text(640,166,"How to Play Ember Tower",29,PALETTE["gold"],"center")
            content=("GOAL: Defeat the Ember Lord on Floor 20. At 0 HP, your run ends.\n\n"
                     "PLAY: Click a card. Attacks target the enemy; Skills and Powers resolve automatically.\n"
                     "INTENT: The enemy's next attack, defense or buff is shown before you act.\n"
                     "END TURN: Discard your hand, let the enemy act, then refill Energy and draw 5 cards.\n\n"
                     "STRENGTH adds damage. Heavy Blade scales it further; Limit Break doubles it.\n"
                     "BLOCK absorbs attacks. It normally expires next turn; Barricade preserves it.\n"
                     "Body Slam deals damage equal to your Block without spending that Block.\n"
                     "VULNERABLE increases attack damage by 50%, rounded down for each hit.\n"
                     "EXHAUST removes a card for this combat only. Powers stay active until combat ends.\n\n"
                     "REWARDS: Add one of three cards, or decline for +2 Max HP and heal 2 HP.\n"
                     "Rewards never replace cards. Max HP gains always heal by the same amount.\n"
                     "SHOPS add purchased cards. Paid removal and Altar events can still thin your deck.\n"
                     "After Floor 10, maximum Energy increases from 3 to 4.\n\n"
                     "KEYS: 1–7 plays a card on the current page; E ends your turn; Esc closes or pauses.")
            self.text(138,228,content,16,PALETTE["dim"],width=1000)


def run():
    root=tk.Tk()
    GameUI(root)
    root.mainloop()
