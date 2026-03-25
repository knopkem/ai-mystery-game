"""
Pydantic schemas for all LLM server request/response types.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Personality(str, Enum):
    nervous = "nervous"
    arrogant = "arrogant"
    charming = "charming"
    cold = "cold"
    paranoid = "paranoid"


class Relationship(str, Enum):
    spouse = "spouse"
    business_partner = "business partner"
    servant = "servant"
    old_friend = "old friend"
    estranged_sibling = "estranged sibling"


class NpcAction(str, Enum):
    move = "move"
    hide_evidence = "hide_evidence"
    destroy_evidence = "destroy_evidence"
    talk_to = "talk_to"
    plant_evidence = "plant_evidence"
    act_nervous = "act_nervous"
    stay_calm = "stay_calm"
    investigate = "investigate"


class Emotion(str, Enum):
    calm = "calm"
    nervous = "nervous"
    angry = "angry"
    defensive = "defensive"
    tearful = "tearful"
    smug = "smug"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class NpcIdentity(BaseModel):
    name: str
    personality: Personality
    relationship: Relationship
    secret: str
    is_killer: bool
    motive: str | None = None  # only set when is_killer=True


class NpcState(BaseModel):
    identity: NpcIdentity
    current_room: str
    action_history: list[str] = Field(default_factory=list)
    interrogation_count: int = 0
    pressure: int = Field(default=0, ge=0, le=10)
    lies_told: list[str] = Field(default_factory=list)
    alibi: str = ""


class GameState(BaseModel):
    turn_number: int = Field(ge=1, le=15)
    player_room: str
    player_suspicion_target: str | None = None
    known_evidence: list[str] = Field(default_factory=list)
    npcs: list[NpcState] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /setup-mystery
# ---------------------------------------------------------------------------

class SuspectBlueprint(BaseModel):
    name: str
    personality: Personality
    relationship: Relationship
    secret: str


class SetupMysteryRequest(BaseModel):
    suspects: list[SuspectBlueprint] = Field(min_length=5, max_length=6)
    rooms: list[str] = Field(min_length=3, max_length=8)
    evidence_items: list[str]
    # Pre-randomised structural choices (supplied by client for variety).
    # When present the LLM is told to treat them as hard constraints so only
    # narrative (motive text, alibi wording, critical evidence) is generated.
    forced_killer: str | None = None
    forced_positions: dict[str, str] | None = None   # npc_name → room
    forced_evidence_placements: dict[str, str] | None = None  # item → room


class MysterySetup(BaseModel):
    killer_name: str
    motive: str
    evidence_placements: dict[str, str]   # item_name → room_name
    true_alibis: dict[str, str]           # npc_name → true alibi
    false_alibis: dict[str, str]          # npc_name → lie to tell
    critical_evidence: list[str]          # items that prove guilt (min 3)
    initial_npc_positions: dict[str, str] # npc_name → starting room


# ---------------------------------------------------------------------------
# /npc-actions
# ---------------------------------------------------------------------------

class NpcActionsRequest(BaseModel):
    game_state: GameState


class NpcActionResult(BaseModel):
    npc_name: str
    action: NpcAction
    target: str | None = None
    secondary_target: str | None = None
    internal_thought: str = ""


class NpcActionsResponse(BaseModel):
    actions: list[NpcActionResult]


# ---------------------------------------------------------------------------
# /interrogate
# ---------------------------------------------------------------------------

class InterrogateRequest(BaseModel):
    npc_state: NpcState
    player_question: str
    evidence_shown: list[str] = Field(default_factory=list)
    game_state: GameState


class InterrogateResponse(BaseModel):
    dialogue: str
    lie: bool
    emotion: Emotion
    internal_thought: str = ""
