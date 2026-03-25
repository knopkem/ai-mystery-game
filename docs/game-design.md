# Game Design Document — AI Murder Mystery

## Overview

A turn-based 2D murder mystery set in a Victorian mansion. The twist: all NPC behavior is driven by a locally-running fine-tuned language model. Each playthrough is procedurally generated — a different killer, motive, evidence trail, and set of NPC decisions every time.

**Engine**: Pygame-CE (Python) — all UI drawn programmatically, no external assets required.
**Target hardware**: MacBook M4, 16 GB RAM.

---

## Setting

**Thornfield Manor** — a dark Victorian mansion on an isolated hill.

### Rooms (5)

| Room | Description | Key Items |
|------|-------------|-----------|
| **Foyer** | Grand entrance. Body discovered here. | Chandelier, front door, blood stain |
| **Library** | Bookshelves, fireplace, writing desk | Books, hidden compartment, journal |
| **Kitchen** | Servants' domain. Access to poisons. | Knives, poison cabinet, back door |
| **Bedroom** | Victim's private quarters | Personal letters, locked box, wardrobe |
| **Garden** | Overgrown grounds, tool shed | Shovel, hedge maze entrance, muddy path |

---

## Characters

### The Victim
**Lord Ashworth** — wealthy patriarch, recently changed his will.

### The Suspects (5)

| Name | Personality | Relationship | Secret |
|------|------------|--------------|--------|
| **Lady Ashworth** | Cold | Spouse | Having an affair; stands to inherit everything |
| **Victor Crane** | Arrogant | Business Partner | Ashworth discovered Victor's embezzlement |
| **Nell Marsh** | Nervous | Servant | Witnessed something she won't speak of |
| **Thomas Hale** | Charming | Old Friend | Visited secretly the night before; owes Ashworth a fortune |
| **Clara Voss** | Paranoid | Estranged Sibling | Came to confront Ashworth over their father's will |

> Each playthrough, the **killer and motive are randomly assigned** from plausible pairings. Not every suspect's secret is a motive — some are red herrings.

---

## Turn Structure

Each game round has 3 phases:

### 1. Player Phase (2 actions)

| Action | Description |
|--------|-------------|
| `move <room>` | Travel to an adjacent room |
| `examine <object>` | Search for evidence at a specific location |
| `interrogate <suspect>` | Question a suspect (LLM generates response) |
| `accuse <suspect>` | Final accusation — ends the game |
| `review_notes` | Read collected evidence and testimony |

### 2. NPC Phase (LLM-driven)

Each suspect decides one action:

| Action | Who would do it | Effect |
|--------|----------------|--------|
| `move <room>` | Anyone | Relocate |
| `hide_evidence <item>` | Guilty / covering up | Evidence becomes harder to find |
| `destroy_evidence <item>` | Desperate killer | Evidence permanently removed |
| `talk_to <npc>` | Anyone | May coordinate alibis or spread rumors |
| `plant_evidence <item> <room>` | Guilty / strategic | Frame another suspect |
| `act_nervous` | Nervous/guilty | Visible tell for the player |
| `stay_calm` | Innocent / composed guilty | No notable behavior |
| `investigate` | Curious/suspicious innocent | May find or misinterpret evidence |

**Fog of war**: Player only sees NPC actions if they share the same room.

### 3. Event Phase (random)

| Event | Probability | Effect |
|-------|------------|--------|
| Power outage | 10% | All rooms dark for 1 turn — NPCs can act unseen |
| Suspect demands to leave | 8% | Must interrogate or lose them for 2 turns |
| New evidence surfaces | 15% | A hidden item becomes visible |
| Servants' gossip | 12% | One random NPC's location is revealed |
| Thunderstorm | 5% | Garden becomes inaccessible for 1 turn |

---

## Evidence System

### Physical Evidence
- **The Weapon**: Always exists. May be hidden or planted.
- **Poison Bottle**: Present if poison method.
- **Torn Fabric**: From killer's clothing; location-dependent.
- **Love Letter**: Reveals affair.
- **Ledger Page**: Shows embezzlement.
- **Will Amendment**: Reveals motive for spouse.
- **Muddy Boots**: Places someone in the garden.

### Testimonial Evidence
- Recorded when player interrogates suspects.
- Contradictions between testimonies are automatically flagged in notes.

### Behavioral Evidence
- If player witnesses an NPC hide or destroy evidence, it's logged.
- Nervousness is visible but not conclusive.

---

## Accusation System

When the player is ready to accuse:
1. Select a suspect
2. Select the motive (from a list derived from evidence found)
3. Confirm

**Correct**: Killer + correct motive → Victory screen
**Wrong suspect**: Game over — killer reveals themselves mockingly
**Wrong motive on right suspect**: Partial credit; story ends with ambiguous resolution

---

## Win/Lose Conditions

| Outcome | Condition |
|---------|-----------|
| **Win** | Correct suspect + correct motive |
| **Lose: Wrong Accusation** | Accused innocent person |
| **Lose: Evidence Destroyed** | Killer destroys all 3 critical evidence pieces |
| **Lose: Escape** | 15 turns pass without accusation |

---

## Pressure System

Each suspect has a **pressure counter** (0–10).

- Increases each time player interrogates them
- Increases when player shows them hard evidence
- Increases when contradictions are pointed out

**Effects by pressure level**:
- 0–3: NPC responds as normal
- 4–6: Guilty NPC starts making small inconsistencies; innocent NPCs may become annoyed
- 7–9: Guilty NPC may accidentally reveal partial truth; may try to destroy evidence that turn
- 10: Guilty NPC cracks — reveals something significant (but may still not fully confess)

---

## LLM Integration

### Mystery Generation (game start)
The LLM is given the 5 suspects and returns:
- Which suspect is the killer
- The motive
- Initial evidence placement in rooms
- Each suspect's true alibi and false alibi
- What secrets each NPC will guard

### NPC Decision (each NPC turn)
Each NPC receives:
- Their identity (name, personality, relationship, secret, guilty/innocent)
- Full current game state (room locations, known evidence, player suspicion)
- Their action history

Returns: `{action, target, secondary_target, internal_thought}`

### Interrogation (during player phase)
The NPC receives:
- Player's question
- Their identity and guilt status
- Current pressure level and lies already told
- Evidence the player has shown them

Returns: `{dialogue, lie, emotion, internal_thought}`

---

## Difficulty Scaling (future)

| Difficulty | Killer behavior | Innocent behavior | Turns |
|------------|----------------|-------------------|-------|
| Easy | Killer avoids player, rarely destroys evidence | Helpful when questioned | 20 |
| Normal | Killer actively hides evidence, coordinates alibi | Mildly suspicious when pressured | 15 |
| Hard | Killer plants false evidence, actively frames others | NPCs form misleading alliances | 12 |
