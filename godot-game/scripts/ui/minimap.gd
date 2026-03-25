## Minimap — shows which NPCs are in which room at a glance.
##
## Displayed as a small panel in the top-right corner.
## Updates every NPC phase completion.

extends Panel

@onready var _room_labels: Dictionary = {}   # room_name → Label node

const ROOMS := ["foyer", "library", "kitchen", "bedroom", "garden"]

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	# Build a label per room from children named by room
	for room in ROOMS:
		var label := Label.new()
		label.name = room
		label.text = room.capitalize() + ": —"
		label.add_theme_font_size_override("font_size", 11)
		add_child(label)
		_room_labels[room] = label

	_layout_labels()
	GameManager.connect("npc_action_executed", _on_npc_action)
	GameManager.connect("mystery_ready", _refresh)


func _layout_labels() -> void:
	var y := 8
	for room in ROOMS:
		_room_labels[room].position = Vector2(8, y)
		y += 20


# ---------------------------------------------------------------------------
# Refresh occupant list per room
# ---------------------------------------------------------------------------
func _refresh() -> void:
	for room in ROOMS:
		var occupants := GameManager.get_npcs_in_room(room)
		var names := occupants.map(func(npc): return npc["name"].split(" ")[0])  # first name only
		if names.is_empty():
			_room_labels[room].text = room.capitalize() + ": —"
		else:
			_room_labels[room].text = room.capitalize() + ": " + ", ".join(names)


func _on_npc_action(_name: String, _action: String, _target: String) -> void:
	_refresh()
