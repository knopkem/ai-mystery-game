## GameManager — Autoload Singleton
##
## Owns the canonical game state and drives the 3-phase turn loop:
##   1. Player Phase  (player has 2 action points)
##   2. NPC Phase     (LLM decides each suspect's action)
##   3. Event Phase   (random mansion events)
##
## Emitted signals are consumed by UI nodes and room scenes.

extends Node

# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
signal turn_started(turn_number: int)
signal phase_changed(phase: String)          # "player" | "npc" | "event"
signal npc_action_executed(npc_name: String, action: String, target: String)
signal evidence_found(item_name: String, room_name: String)
signal note_added(note_text: String)
signal game_over(outcome: String, message: String)  # outcome: "win" | "lose"
signal mystery_ready()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
const MAX_TURNS := 15
const PLAYER_ACTIONS_PER_TURN := 2

const ROOMS := ["foyer", "library", "kitchen", "bedroom", "garden"]
const EVIDENCE_ITEMS := [
	"kitchen_knife", "poison_bottle", "torn_fabric", "love_letter",
	"ledger_page", "will_amendment", "muddy_boots", "broken_vase",
	"bloodstained_glove", "mysterious_note"
]

# Suspects defined here; secrets are assigned by the LLM at mystery setup
const SUSPECT_BLUEPRINTS := [
	{"name": "Lady Ashworth",  "personality": "cold",      "relationship": "spouse",            "secret": "having an affair"},
	{"name": "Victor Crane",   "personality": "arrogant",  "relationship": "business partner",  "secret": "discovered to have embezzled from the victim"},
	{"name": "Nell Marsh",     "personality": "nervous",   "relationship": "servant",           "secret": "witnessed something she won't speak of"},
	{"name": "Thomas Hale",    "personality": "charming",  "relationship": "old friend",        "secret": "visited secretly the night before; owes the victim a fortune"},
	{"name": "Clara Voss",     "personality": "paranoid",  "relationship": "estranged sibling", "secret": "came to confront the victim over the father's will"},
]

# ---------------------------------------------------------------------------
# Game State
# ---------------------------------------------------------------------------
var turn_number: int = 1
var current_phase: String = "player"   # "player" | "npc" | "event"
var player_actions_remaining: int = PLAYER_ACTIONS_PER_TURN
var player_room: String = "foyer"
var player_suspicion_target: String = ""

# NPC state: dict keyed by npc_name
# Each entry: {identity, current_room, action_history, interrogation_count,
#              pressure, lies_told, alibi, is_visible_to_player}
var npc_states: Dictionary = {}

# Evidence: dict keyed by item_name → room_name (or "" if hidden/destroyed)
var evidence_locations: Dictionary = {}
var found_evidence: Array[String] = []         # items player has examined
var destroyed_evidence: Array[String] = []     # items permanently gone

# Notes: array of strings the player has recorded
var player_notes: Array[String] = []
var contradictions: Array[String] = []

# Mystery setup (from LLM)
var killer_name: String = ""
var killer_motive: String = ""
var critical_evidence: Array[String] = []

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	LLMClient.connect("mystery_setup_received", _on_mystery_setup_received)
	LLMClient.connect("npc_actions_received", _on_npc_actions_received)
	LLMClient.connect("request_failed", _on_llm_request_failed)


func start_new_game() -> void:
	_reset_state()
	LLMClient.request_mystery_setup(SUSPECT_BLUEPRINTS, ROOMS, EVIDENCE_ITEMS)


func _reset_state() -> void:
	turn_number = 1
	current_phase = "player"
	player_actions_remaining = PLAYER_ACTIONS_PER_TURN
	player_room = "foyer"
	player_suspicion_target = ""
	npc_states.clear()
	evidence_locations.clear()
	found_evidence.clear()
	destroyed_evidence.clear()
	player_notes.clear()
	contradictions.clear()
	killer_name = ""
	killer_motive = ""
	critical_evidence.clear()


# ---------------------------------------------------------------------------
# Mystery Setup (called when LLM returns mystery data)
# ---------------------------------------------------------------------------
func _on_mystery_setup_received(data: Dictionary) -> void:
	killer_name = data.get("killer_name", "")
	killer_motive = data.get("motive", "")
	critical_evidence = data.get("critical_evidence", [])

	var evidence_placements: Dictionary = data.get("evidence_placements", {})
	var true_alibis: Dictionary = data.get("true_alibis", {})
	var false_alibis: Dictionary = data.get("false_alibis", {})
	var initial_positions: Dictionary = data.get("initial_npc_positions", {})

	# Initialise evidence locations
	for item in evidence_placements:
		evidence_locations[item] = evidence_placements[item]

	# Initialise NPC states
	for blueprint in SUSPECT_BLUEPRINTS:
		var name: String = blueprint["name"]
		npc_states[name] = {
			"name": name,
			"personality": blueprint["personality"],
			"relationship": blueprint["relationship"],
			"secret": blueprint["secret"],
			"is_killer": name == killer_name,
			"motive": killer_motive if name == killer_name else "",
			"current_room": initial_positions.get(name, ROOMS[randi() % ROOMS.size()]),
			"action_history": [],
			"interrogation_count": 0,
			"pressure": 0,
			"lies_told": [],
			"alibi": true_alibis.get(name, "was elsewhere"),
			"false_alibi": false_alibis.get(name, ""),
			"is_visible_to_player": false,
		}

	add_note("Lord Ashworth has been found dead in the foyer. Investigate before the killer escapes.")
	mystery_ready.emit()
	emit_signal("turn_started", turn_number)
	_set_phase("player")


# ---------------------------------------------------------------------------
# Player Actions
# ---------------------------------------------------------------------------
func player_move(room_name: String) -> bool:
	if current_phase != "player" or player_actions_remaining <= 0:
		return false
	if room_name not in ROOMS:
		return false
	player_room = room_name
	_update_npc_visibility()
	_spend_action()
	return true


func player_examine(item_name: String) -> bool:
	if current_phase != "player" or player_actions_remaining <= 0:
		return false
	var item_room: String = evidence_locations.get(item_name, "")
	if item_room != player_room or item_name in destroyed_evidence:
		return false
	if item_name not in found_evidence:
		found_evidence.append(item_name)
		evidence_found.emit(item_name, item_room)
		add_note("Found %s in the %s." % [item_name.replace("_", " "), item_room])
	_spend_action()
	return true


func player_interrogate(npc_name: String, question: String, evidence_to_show: Array) -> bool:
	if current_phase != "player" or player_actions_remaining <= 0:
		return false
	if npc_name not in npc_states:
		return false
	var npc = npc_states[npc_name]
	npc["interrogation_count"] += 1
	npc["pressure"] = mini(npc["pressure"] + 1 + evidence_to_show.size(), 10)
	if npc_name != player_suspicion_target and npc["interrogation_count"] >= 2:
		player_suspicion_target = npc_name
	LLMClient.request_interrogate(npc, question, evidence_to_show, _build_game_state_dict())
	_spend_action()
	return true


func player_accuse(suspect_name: String, motive: String) -> void:
	if suspect_name == killer_name and motive.to_lower() in killer_motive.to_lower():
		game_over.emit("win", "Correct! %s is the killer. Motive: %s" % [suspect_name, killer_motive])
	elif suspect_name == killer_name:
		game_over.emit("partial", "You identified the right person but the wrong motive.")
	else:
		game_over.emit("lose", "Wrong. %s was innocent. The real killer escapes." % suspect_name)


func add_note(text: String) -> void:
	player_notes.append(text)
	note_added.emit(text)


# ---------------------------------------------------------------------------
# Turn Flow
# ---------------------------------------------------------------------------
func _spend_action() -> void:
	player_actions_remaining -= 1
	if player_actions_remaining <= 0:
		_end_player_phase()


func _end_player_phase() -> void:
	_set_phase("npc")
	LLMClient.request_npc_actions(_build_game_state_dict())


func _on_npc_actions_received(actions: Array) -> void:
	for action_data in actions:
		_apply_npc_action(action_data)
	await get_tree().create_timer(0.5).timeout
	_set_phase("event")
	_run_event_phase()


func _apply_npc_action(data: Dictionary) -> void:
	var npc_name: String = data.get("npc_name", "")
	if npc_name not in npc_states:
		return

	var npc = npc_states[npc_name]
	var action: String = data.get("action", "stay_calm")
	var target: String = data.get("target", "")

	npc["action_history"].append(action)

	match action:
		"move":
			if target in ROOMS:
				npc["current_room"] = target
		"hide_evidence":
			if target in evidence_locations and evidence_locations[target] != "":
				evidence_locations[target] = "__hidden__"
		"destroy_evidence":
			if target in evidence_locations:
				evidence_locations[target] = ""
				if target not in destroyed_evidence:
					destroyed_evidence.append(target)
				_check_evidence_win_condition()
		"plant_evidence":
			var secondary: String = data.get("secondary_target", "")
			if target in evidence_locations and secondary in ROOMS:
				evidence_locations[target] = secondary
		"talk_to":
			pass  # NPC-to-NPC talk: narrative only
		"act_nervous":
			npc["pressure"] = mini(npc["pressure"] + 1, 10)

	_update_npc_visibility()

	# Player witnesses action only if in same room
	if npc["current_room"] == player_room:
		var target_str := " → %s" % target if target else ""
		add_note("[Turn %d] Witnessed: %s %s%s" % [turn_number, npc_name, action.replace("_", " "), target_str])

	npc_action_executed.emit(npc_name, action, target)


func _run_event_phase() -> void:
	var roll := randf()
	var event_message := ""
	if roll < 0.10:
		event_message = "The lights flicker and go out! NPCs move unseen for this turn."
	elif roll < 0.18:
		event_message = "One of the suspects demands to be allowed to leave the manor!"
	elif roll < 0.33:
		# Reveal a hidden piece of evidence
		for item in evidence_locations:
			if evidence_locations[item] == "__hidden__":
				evidence_locations[item] = _random_room()
				event_message = "A servant finds something hidden: %s has reappeared." % item.replace("_", " ")
				break
	elif roll < 0.45:
		# Gossip reveals an NPC location
		var names = npc_states.keys()
		if names.size() > 0:
			var revealed: String = names[randi() % names.size()]
			var room: String = npc_states[revealed]["current_room"]
			event_message = "Servants' gossip: %s was seen in the %s." % [revealed, room]
			add_note(event_message)

	if event_message:
		add_note("[Event] " + event_message)

	_end_turn()


func _end_turn() -> void:
	if turn_number >= MAX_TURNS:
		game_over.emit("lose", "Time is up. The killer escapes into the night.")
		return
	turn_number += 1
	player_actions_remaining = PLAYER_ACTIONS_PER_TURN
	turn_started.emit(turn_number)
	_set_phase("player")


# ---------------------------------------------------------------------------
# Win/Lose helpers
# ---------------------------------------------------------------------------
func _check_evidence_win_condition() -> void:
	var critical_remaining := critical_evidence.filter(
		func(item): return item not in destroyed_evidence
	)
	if critical_remaining.is_empty():
		game_over.emit("lose", "The killer has destroyed all critical evidence. Case unsolvable.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
func _set_phase(phase: String) -> void:
	current_phase = phase
	phase_changed.emit(phase)


func _update_npc_visibility() -> void:
	for npc_name in npc_states:
		npc_states[npc_name]["is_visible_to_player"] = \
			npc_states[npc_name]["current_room"] == player_room


func _random_room() -> String:
	return ROOMS[randi() % ROOMS.size()]


func _on_llm_request_failed(endpoint: String) -> void:
	if endpoint == "/npc-actions":
		# Trigger fallback in LLMClient; actions will still be emitted
		push_warning("LLM unavailable for NPC actions; fallback used.")
	elif endpoint == "/setup-mystery":
		push_error("Mystery setup failed — cannot start game without LLM.")


func _build_game_state_dict() -> Dictionary:
	var npc_list := []
	for name in npc_states:
		var npc = npc_states[name]
		npc_list.append({
			"identity": {
				"name": npc["name"],
				"personality": npc["personality"],
				"relationship": npc["relationship"],
				"secret": npc["secret"],
				"is_killer": npc["is_killer"],
				"motive": npc["motive"],
			},
			"current_room": npc["current_room"],
			"action_history": npc["action_history"],
			"interrogation_count": npc["interrogation_count"],
			"pressure": npc["pressure"],
			"lies_told": npc["lies_told"],
			"alibi": npc["alibi"],
		})
	return {
		"turn_number": turn_number,
		"player_room": player_room,
		"player_suspicion_target": player_suspicion_target,
		"known_evidence": found_evidence,
		"npcs": npc_list,
	}


func get_npcs_in_room(room_name: String) -> Array:
	var result := []
	for name in npc_states:
		if npc_states[name]["current_room"] == room_name:
			result.append(npc_states[name])
	return result


func get_evidence_in_room(room_name: String) -> Array[String]:
	var result: Array[String] = []
	for item in evidence_locations:
		if evidence_locations[item] == room_name:
			result.append(item)
	return result
