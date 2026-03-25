## EvidenceItem — small clickable node shown in a room when evidence is present.
##
## Displays as a colored rectangle with the item name.
## When clicked during the player phase, triggers an examine action.

extends Node2D

# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
@export var item_name: String = ""

# ---------------------------------------------------------------------------
# Child refs
# ---------------------------------------------------------------------------
@onready var _rect: ColorRect = $Rect
@onready var _label: Label = $Label
@onready var _click_area: Area2D = $ClickArea

const EVIDENCE_COLOR := Color(0.9, 0.85, 0.2)       # gold
const HIDDEN_COLOR := Color(0.4, 0.4, 0.4, 0.3)     # dim grey

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	_label.text = item_name.replace("_", "\n")
	_rect.color = EVIDENCE_COLOR
	_click_area.input_event.connect(_on_click_area_input)
	GameManager.connect("phase_changed", _on_phase_changed)
	_update_interactability()


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
func _on_click_area_input(_viewport, event: InputEvent, _shape_idx) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if GameManager.current_phase == "player":
			var player := get_tree().get_first_node_in_group("player")
			if player:
				player.request_examine(item_name)


# ---------------------------------------------------------------------------
# Phase change — enable/disable interaction
# ---------------------------------------------------------------------------
func _on_phase_changed(phase: String) -> void:
	_update_interactability()


func _update_interactability() -> void:
	var active := GameManager.current_phase == "player" and \
	              GameManager.player_room == get_parent().get_parent().room_name
	_rect.color = EVIDENCE_COLOR if active else HIDDEN_COLOR
	_click_area.input_pickable = active
