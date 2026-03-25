# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS & GAME DATA
# ═══════════════════════════════════════════════════════════════════════════

WIN_W, WIN_H = 1280, 720
FPS = 60
TITLE = "AI Murder Mystery"
SERVER = "http://127.0.0.1:8000"

ROOMS = ["foyer", "library", "kitchen", "bedroom", "garden"]

EVIDENCE_ITEMS = [
    "kitchen_knife", "poison_bottle", "torn_fabric", "love_letter",
    "ledger_page", "will_amendment", "muddy_boots", "bloodstained_glove",
]

SUSPECT_BLUEPRINTS = [
    {"name": "Lady Ashworth", "personality": "cold",     "relationship": "spouse",           "secret": "having an affair"},
    {"name": "Victor Crane",  "personality": "arrogant", "relationship": "business partner", "secret": "embezzled from the victim"},
    {"name": "Nell Marsh",    "personality": "nervous",  "relationship": "servant",          "secret": "witnessed something she won't speak of"},
    {"name": "Thomas Hale",   "personality": "charming", "relationship": "old friend",       "secret": "visited secretly the night before"},
    {"name": "Clara Voss",    "personality": "paranoid", "relationship": "estranged sibling","secret": "came to confront the victim over the will"},
]

PLAYER_AP = 2
MAX_TURNS = 15

NPC_PALETTE = [
    (230, 110, 95),   # coral
    (95,  155, 230),  # cornflower
    (95,  210, 125),  # sea green
    (225, 185, 65),   # gold
    (185, 105, 230),  # orchid
]
