## HUD — main UI overlay script.
##
## Displays:
##   - Turn counter and phase indicator
##   - Action points remaining
##   - Current room name
##   - "Thinking..." spinner during NPC phase
##   - Buttons: Examine, Interrogate, Accuse, Review Notes
##   - Slide-out Notes panel
##   - Interrogation dialog
##   - Accusation screen
##   - Game over screen

extends CanvasLayer

# ---------------------------------------------------------------------------
# Child refs — filled in _ready()
# ---------------------------------------------------------------------------
@onready var _turn_label: Label = $TopBar/TurnLabel
@onready var _phase_label: Label = $TopBar/PhaseLabel
@onready var _ap_label: Label = $TopBar/APLabel
@onready var _room_label: Label = $TopBar/RoomLabel
@onready var _thinking_spinner: Label = $ThinkingSpinner

@onready var _notes_panel: Panel = $NotesPanel
@onready var _notes_list: RichTextLabel = $NotesPanel/NotesList
@onready var _notes_toggle_btn: Button = $ActionBar/NotesBtn

@onready var _action_bar: HBoxContainer = $ActionBar
@onready var _examine_btn: Button = $ActionBar/ExamineBtn
@onready var _interrogate_btn: Button = $ActionBar/InterrogateBtn
@onready var _accuse_btn: Button = $ActionBar/AccuseBtn

@onready var _interrogate_dialog: Panel = $InterrogateDialog
@onready var _interrogate_npc_label: Label = $InterrogateDialog/NPCName
@onready var _question_input: LineEdit = $InterrogateDialog/QuestionInput
@onready var _ask_btn: Button = $InterrogateDialog/AskBtn
@onready var _cancel_btn: Button = $InterrogateDialog/CancelBtn
@onready var _response_label: RichTextLabel = $InterrogateDialog/ResponseLabel

@onready var _accuse_dialog: Panel = $AccuseDialog
@onready var _suspect_option: OptionButton = $AccuseDialog/SuspectOption
@onready var _motive_input: LineEdit = $AccuseDialog/MotiveInput
@onready var _confirm_accuse_btn: Button = $AccuseDialog/ConfirmBtn
@onready var _cancel_accuse_btn: Button = $AccuseDialog/CancelBtn

@onready var _game_over_panel: Panel = $GameOverPanel
@onready var _game_over_label: RichTextLabel = $GameOverPanel/OutcomeLabel
@onready var _restart_btn: Button = $GameOverPanel/RestartBtn

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------
var _active_interrogation_npc: String = ""
var _notes_open: bool = false

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
func _ready() -> void:
	_thinking_spinner.visible = false
	_notes_panel.visible = false
	_interrogate_dialog.visible = false
	_accuse_dialog.visible = false
	_game_over_panel.visible = false

	# Connect GameManager signals
	GameManager.connect("turn_started", _on_turn_started)
	GameManager.connect("phase_changed", _on_phase_changed)
	GameManager.connect("note_added", _on_note_added)
	GameManager.connect("game_over", _on_game_over)
	LLMClient.connect("interrogation_received", _on_interrogation_received)

	# Wire buttons
	_notes_toggle_btn.pressed.connect(_toggle_notes)
	_interrogate_dialog.get_node("CancelBtn").pressed.connect(_close_interrogate)
	_interrogate_dialog.get_node("AskBtn").pressed.connect(_submit_question)
	_accuse_dialog.get_node("CancelBtn").pressed.connect(func(): _accuse_dialog.visible = false)
	_accuse_dialog.get_node("ConfirmBtn").pressed.connect(_confirm_accusation)
	_accuse_btn.pressed.connect(_open_accuse_dialog)
	_restart_btn.pressed.connect(_on_restart)

	_refresh_top_bar()


# ---------------------------------------------------------------------------
# Top bar refresh
# ---------------------------------------------------------------------------
func _refresh_top_bar() -> void:
	_turn_label.text = "Turn %d / %d" % [GameManager.turn_number, GameManager.MAX_TURNS]
	_ap_label.text = "AP: %d" % GameManager.player_actions_remaining
	_room_label.text = GameManager.player_room.capitalize()

	var phase_text := {
		"player": "[color=lime]Your Turn[/color]",
		"npc":    "[color=orange]NPCs Acting…[/color]",
		"event":  "[color=cyan]Event[/color]",
	}.get(GameManager.current_phase, "")
	_phase_label.text = phase_text


# ---------------------------------------------------------------------------
# GameManager signal handlers
# ---------------------------------------------------------------------------
func _on_turn_started(turn: int) -> void:
	_refresh_top_bar()


func _on_phase_changed(phase: String) -> void:
	_refresh_top_bar()
	var is_player_turn := phase == "player"
	_examine_btn.disabled = not is_player_turn
	_interrogate_btn.disabled = not is_player_turn
	_accuse_btn.disabled = not is_player_turn
	_thinking_spinner.visible = phase == "npc"


func _on_note_added(note: String) -> void:
	_notes_list.append_text("• " + note + "\n")


func _on_game_over(outcome: String, message: String) -> void:
	_game_over_panel.visible = true
	var color := {
		"win": "lime", "lose": "tomato", "partial": "gold"
	}.get(outcome, "white")
	_game_over_label.text = "[color=%s]%s[/color]\n\n%s" % [color, outcome.to_upper(), message]


# ---------------------------------------------------------------------------
# Notes panel
# ---------------------------------------------------------------------------
func _toggle_notes() -> void:
	_notes_open = not _notes_open
	_notes_panel.visible = _notes_open
	_notes_toggle_btn.text = "Close Notes" if _notes_open else "Notes"


# ---------------------------------------------------------------------------
# Interrogation dialog
# ---------------------------------------------------------------------------
func open_interrogate_dialog(npc_name: String) -> void:
	_active_interrogation_npc = npc_name
	_interrogate_npc_label.text = "Interrogating: %s" % npc_name
	_question_input.text = ""
	_response_label.text = ""
	_interrogate_dialog.visible = true
	_question_input.grab_focus()


func _submit_question() -> void:
	var question := _question_input.text.strip_edges()
	if question.is_empty():
		return
	_ask_btn.disabled = true
	_response_label.text = "[i]Waiting for response…[/i]"
	# Delegate to Player node via signal or direct call
	var player := get_tree().get_first_node_in_group("player")
	if player:
		player.request_interrogate(_active_interrogation_npc, question)


func _on_interrogation_received(npc_name: String, response: Dictionary) -> void:
	if npc_name != _active_interrogation_npc:
		return
	_ask_btn.disabled = false
	var dialogue: String = response.get("dialogue", "…")
	var emotion: String = response.get("emotion", "calm")
	_response_label.text = "[b]%s[/b] [i](%s)[/i]\n\n\"%s\"" % [npc_name, emotion, dialogue]
	GameManager.add_note("[Testimony] %s (%s): \"%s\"" % [npc_name, emotion, dialogue])


func _close_interrogate() -> void:
	_interrogate_dialog.visible = false
	_active_interrogation_npc = ""


# ---------------------------------------------------------------------------
# Accusation dialog
# ---------------------------------------------------------------------------
func _open_accuse_dialog() -> void:
	_suspect_option.clear()
	for name in GameManager.npc_states.keys():
		_suspect_option.add_item(name)
	_motive_input.text = ""
	_accuse_dialog.visible = true


func _confirm_accusation() -> void:
	var suspect := _suspect_option.get_item_text(_suspect_option.selected)
	var motive := _motive_input.text.strip_edges()
	if suspect.is_empty() or motive.is_empty():
		return
	_accuse_dialog.visible = false
	var player := get_tree().get_first_node_in_group("player")
	if player:
		player.request_accuse(suspect, motive)


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------
func _on_restart() -> void:
	_game_over_panel.visible = false
	_notes_list.text = ""
	GameManager.start_new_game()
