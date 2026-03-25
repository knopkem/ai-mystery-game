## NPC — individual suspect node
##
## Visual: a colored circle with a name label underneath.
## Attached to each suspect in the room scene they currently occupy.
## Listens to GameManager signals and updates visually when actions occur.

extends Node2D

# ---------------------------------------------------------------------------
# Exports (set in scene editor or when spawning)
# ---------------------------------------------------------------------------
@export var npc_name: String = ""
@export var color: Color = Color.SLATE_GRAY

# ---------------------------------------------------------------------------
# State mirrored from GameManager.npc_states[npc_name]
# ---------------------------------------------------------------------------
var current_room: String = ""
var is_visible: bool = true

# ---------------------------------------------------------------------------
# Child node refs (set up in _ready)
# ---------------------------------------------------------------------------
@onready var _circle: ColorRect = $Circle
@onready var _label: Label = $NameLabel
@onready var _emotion_label: Label = $EmotionLabel
@onready var _anim: AnimationPlayer = $AnimationPlayer

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	_circle.color = color
	_label.text = npc_name
	_emotion_label.text = ""
	_emotion_label.modulate.a = 0.0

	GameManager.connect("npc_action_executed", _on_npc_action_executed)
	LLMClient.connect("interrogation_received", _on_interrogation_received)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
func set_emotion(emotion: String) -> void:
	var emoji := {
		"calm": "", "nervous": "😰", "angry": "😠",
		"defensive": "🛡", "tearful": "😢", "smug": "😏",
	}.get(emotion, "")
	_emotion_label.text = emoji
	# Fade in, hold, fade out
	var tween := create_tween()
	tween.tween_property(_emotion_label, "modulate:a", 1.0, 0.2)
	tween.tween_interval(2.0)
	tween.tween_property(_emotion_label, "modulate:a", 0.0, 0.5)


func play_action_animation(action: String) -> void:
	match action:
		"act_nervous":
			_shake()
		"hide_evidence", "destroy_evidence":
			_flash(Color.DARK_RED)
		"investigate":
			_flash(Color.CORNFLOWER_BLUE)
		"talk_to":
			_flash(Color.GOLD)
		"move":
			_flash(Color.WHITE, 0.15)
		_:
			pass  # stay_calm / plant_evidence — no visual


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------
func _on_npc_action_executed(acted_name: String, action: String, _target: String) -> void:
	if acted_name != npc_name:
		return
	# Only show animation if player is in the same room
	var npc_data: Dictionary = GameManager.npc_states.get(npc_name, {})
	if npc_data.get("current_room", "") == GameManager.player_room:
		play_action_animation(action)


func _on_interrogation_received(responded_name: String, response: Dictionary) -> void:
	if responded_name != npc_name:
		return
	set_emotion(response.get("emotion", "calm"))


# ---------------------------------------------------------------------------
# Tween helpers
# ---------------------------------------------------------------------------
func _shake() -> void:
	var original_pos := position
	var tween := create_tween()
	for i in range(6):
		var offset := Vector2(randf_range(-6, 6), randf_range(-4, 4))
		tween.tween_property(self, "position", original_pos + offset, 0.05)
	tween.tween_property(self, "position", original_pos, 0.05)


func _flash(flash_color: Color, duration: float = 0.3) -> void:
	var tween := create_tween()
	tween.tween_property(_circle, "color", flash_color, duration * 0.3)
	tween.tween_property(_circle, "color", color, duration * 0.7)
