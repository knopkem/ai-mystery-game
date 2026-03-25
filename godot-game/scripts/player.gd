## Player — handles player input and action dispatching.
##
## The player is represented by a colored square icon in the current room.
## Movement is point-and-click on door/exit nodes in each room.
## Other actions are triggered through the HUD action menu.

extends Node2D

# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
signal action_requested(action_type: String, params: Dictionary)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
var actions_remaining: int = 2
var selected_evidence_to_show: Array[String] = []

# ---------------------------------------------------------------------------
# Child refs
# ---------------------------------------------------------------------------
@onready var _sprite: ColorRect = $PlayerSprite
@onready var _action_points_label: Label = $ActionPointsLabel   # shown in-world near player

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	GameManager.connect("phase_changed", _on_phase_changed)
	GameManager.connect("turn_started", _on_turn_started)
	_update_display()


# ---------------------------------------------------------------------------
# Called by HUD buttons / room clicks
# ---------------------------------------------------------------------------
func request_move(room_name: String) -> void:
	if not _can_act():
		return
	if GameManager.player_move(room_name):
		action_requested.emit("move", {"room": room_name})
		_update_display()


func request_examine(item_name: String) -> void:
	if not _can_act():
		return
	if GameManager.player_examine(item_name):
		action_requested.emit("examine", {"item": item_name})
		_update_display()


func request_interrogate(npc_name: String, question: String) -> void:
	if not _can_act():
		return
	if GameManager.player_interrogate(npc_name, question, selected_evidence_to_show):
		action_requested.emit("interrogate", {"npc": npc_name, "question": question})
		selected_evidence_to_show.clear()
		_update_display()


func request_accuse(suspect_name: String, motive: String) -> void:
	GameManager.player_accuse(suspect_name, motive)


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------
func _on_phase_changed(phase: String) -> void:
	set_process_input(phase == "player")


func _on_turn_started(_turn: int) -> void:
	actions_remaining = GameManager.PLAYER_ACTIONS_PER_TURN
	selected_evidence_to_show.clear()
	_update_display()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
func _can_act() -> bool:
	return GameManager.current_phase == "player" and GameManager.player_actions_remaining > 0


func _update_display() -> void:
	actions_remaining = GameManager.player_actions_remaining
	if _action_points_label:
		_action_points_label.text = "AP: %d" % actions_remaining
