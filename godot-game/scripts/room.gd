## Room — base script for each mansion room scene.
##
## Manages:
##   - Examination points (clickable areas with potential evidence)
##   - NPC spawn positions
##   - Door/exit buttons for player movement
##   - Visual highlighting of available evidence items

extends Node2D

# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
@export var room_name: String = ""
@export var room_display_name: String = ""
@export var room_color: Color = Color(0.15, 0.12, 0.10)   # dark background

# ---------------------------------------------------------------------------
# Child refs
# ---------------------------------------------------------------------------
@onready var _background: ColorRect = $Background
@onready var _room_label: Label = $RoomLabel
@onready var _evidence_container: Node2D = $EvidenceItems
@onready var _npc_container: Node2D = $NPCContainer
@onready var _doors_container: Node2D = $Doors

# ---------------------------------------------------------------------------
# Preloads
# ---------------------------------------------------------------------------
const EvidenceItemScene := preload("res://scenes/ui/evidence_item.tscn")
const NPCScene := preload("res://scenes/npcs/npc.tscn")

# NPC color palette
const NPC_COLORS := [
	Color.CORAL, Color.CORNFLOWER_BLUE, Color.MEDIUM_SEA_GREEN,
	Color.GOLD, Color.ORCHID,
]

var _npc_nodes: Dictionary = {}   # npc_name → NPC node

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	_background.color = room_color
	_room_label.text = room_display_name

	GameManager.connect("mystery_ready", _on_mystery_ready)
	GameManager.connect("npc_action_executed", _on_npc_action_executed)
	GameManager.connect("phase_changed", _on_phase_changed)


# ---------------------------------------------------------------------------
# Mystery start — populate evidence and NPCs
# ---------------------------------------------------------------------------
func _on_mystery_ready() -> void:
	_spawn_evidence()
	_spawn_npcs()


func _spawn_evidence() -> void:
	# Clear existing
	for child in _evidence_container.get_children():
		child.queue_free()

	var items_here := GameManager.get_evidence_in_room(room_name)
	var i := 0
	for item in items_here:
		var node = EvidenceItemScene.instantiate()
		node.item_name = item
		node.position = Vector2(80 + i * 90, 40)
		_evidence_container.add_child(node)
		i += 1


func _spawn_npcs() -> void:
	# Clear existing
	for child in _npc_container.get_children():
		child.queue_free()
	_npc_nodes.clear()

	var npcs_here := GameManager.get_npcs_in_room(room_name)
	var color_idx := 0
	for npc_data in npcs_here:
		var node = NPCScene.instantiate()
		node.npc_name = npc_data["name"]
		node.color = NPC_COLORS[color_idx % NPC_COLORS.size()]
		node.position = Vector2(120 + color_idx * 80, 320)
		_npc_container.add_child(node)
		_npc_nodes[npc_data["name"]] = node
		color_idx += 1


# ---------------------------------------------------------------------------
# Update on NPC movement
# ---------------------------------------------------------------------------
func _on_npc_action_executed(npc_name: String, action: String, target: String) -> void:
	if action != "move":
		return
	var npc_data = GameManager.npc_states.get(npc_name, {})
	var new_room: String = npc_data.get("current_room", "")

	if new_room == room_name and npc_name not in _npc_nodes:
		# NPC moved into this room — spawn them
		var node = NPCScene.instantiate()
		node.npc_name = npc_name
		node.color = NPC_COLORS[_npc_nodes.size() % NPC_COLORS.size()]
		node.position = Vector2(120 + _npc_nodes.size() * 80, 320)
		_npc_container.add_child(node)
		_npc_nodes[npc_name] = node
	elif new_room != room_name and npc_name in _npc_nodes:
		# NPC left this room
		_npc_nodes[npc_name].queue_free()
		_npc_nodes.erase(npc_name)


# ---------------------------------------------------------------------------
# Phase change — refresh evidence display at start of player phase
# ---------------------------------------------------------------------------
func _on_phase_changed(phase: String) -> void:
	if phase == "player":
		_spawn_evidence()
