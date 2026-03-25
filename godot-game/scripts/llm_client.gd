## LLMClient — Autoload Singleton
##
## Handles all HTTP communication with the Python LLM server running on localhost:8000.
## All requests are async. Results are emitted as signals consumed by GameManager.
##
## Endpoints:
##   POST /setup-mystery
##   POST /npc-actions
##   POST /interrogate
##   GET  /health

extends Node

# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
signal mystery_setup_received(data: Dictionary)
signal npc_actions_received(actions: Array)
signal interrogation_received(npc_name: String, response: Dictionary)
signal request_failed(endpoint: String)
signal health_checked(model_loaded: bool)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
const BASE_URL := "http://127.0.0.1:8000"
const TIMEOUT_SEC := 30.0

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------
var _pending_npc_names: Array[String] = []  # tracks order of npcs in batch request


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
func check_health() -> void:
	var http := _make_request()
	http.request_completed.connect(_on_health_completed.bind(http))
	http.request(BASE_URL + "/health", [], HTTPClient.METHOD_GET)


func _on_health_completed(result, response_code, _headers, body, http: HTTPRequest) -> void:
	http.queue_free()
	if response_code == 200:
		var data = JSON.parse_string(body.get_string_from_utf8())
		health_checked.emit(data.get("model_loaded", false))
	else:
		health_checked.emit(false)


# ---------------------------------------------------------------------------
# /setup-mystery
# ---------------------------------------------------------------------------
func request_mystery_setup(suspects: Array, rooms: Array, evidence_items: Array) -> void:
	var body := JSON.stringify({
		"suspects": suspects,
		"rooms": rooms,
		"evidence_items": evidence_items,
	})
	var http := _make_request()
	http.request_completed.connect(_on_setup_completed.bind(http))
	http.request(BASE_URL + "/setup-mystery", _json_headers(), HTTPClient.METHOD_POST, body)


func _on_setup_completed(result, response_code, _headers, body, http: HTTPRequest) -> void:
	http.queue_free()
	if response_code == 200:
		var data = JSON.parse_string(body.get_string_from_utf8())
		if data:
			mystery_setup_received.emit(data)
			return
	push_warning("LLMClient: /setup-mystery failed (code %d)" % response_code)
	request_failed.emit("/setup-mystery")


# ---------------------------------------------------------------------------
# /npc-actions  (batch)
# ---------------------------------------------------------------------------
func request_npc_actions(game_state: Dictionary) -> void:
	_pending_npc_names.clear()
	for npc in game_state.get("npcs", []):
		_pending_npc_names.append(npc["identity"]["name"])

	var body := JSON.stringify({"game_state": game_state})
	var http := _make_request()
	http.request_completed.connect(_on_npc_actions_completed.bind(http))
	http.request(BASE_URL + "/npc-actions", _json_headers(), HTTPClient.METHOD_POST, body)


func _on_npc_actions_completed(result, response_code, _headers, body, http: HTTPRequest) -> void:
	http.queue_free()
	if response_code == 200:
		var data = JSON.parse_string(body.get_string_from_utf8())
		if data and "actions" in data:
			npc_actions_received.emit(data["actions"])
			return

	push_warning("LLMClient: /npc-actions failed (code %d) — using fallback" % response_code)
	# Emit fallback actions so the game can continue
	npc_actions_received.emit(_fallback_actions())
	request_failed.emit("/npc-actions")


# ---------------------------------------------------------------------------
# /interrogate
# ---------------------------------------------------------------------------
func request_interrogate(
	npc: Dictionary,
	question: String,
	evidence_shown: Array,
	game_state: Dictionary
) -> void:
	var body := JSON.stringify({
		"npc_state": npc,
		"player_question": question,
		"evidence_shown": evidence_shown,
		"game_state": game_state,
	})
	var http := _make_request()
	var npc_name: String = npc.get("name", "Unknown")
	http.request_completed.connect(_on_interrogation_completed.bind(http, npc_name))
	http.request(BASE_URL + "/interrogate", _json_headers(), HTTPClient.METHOD_POST, body)


func _on_interrogation_completed(
	result, response_code, _headers, body, http: HTTPRequest, npc_name: String
) -> void:
	http.queue_free()
	if response_code == 200:
		var data = JSON.parse_string(body.get_string_from_utf8())
		if data and "dialogue" in data:
			interrogation_received.emit(npc_name, data)
			return

	push_warning("LLMClient: /interrogate failed (code %d)" % response_code)
	interrogation_received.emit(npc_name, _fallback_interrogation(npc_name))
	request_failed.emit("/interrogate")


# ---------------------------------------------------------------------------
# Fallback responses (used when LLM server is unreachable)
# ---------------------------------------------------------------------------
func _fallback_actions() -> Array:
	var actions := []
	for name in _pending_npc_names:
		actions.append({
			"npc_name": name,
			"action": "stay_calm",
			"target": null,
			"secondary_target": null,
			"internal_thought": "(offline fallback)",
		})
	return actions


func _fallback_interrogation(npc_name: String) -> Dictionary:
	return {
		"dialogue": "I... I don't know what you want from me.",
		"lie": false,
		"emotion": "nervous",
		"internal_thought": "(offline fallback)",
	}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
func _make_request() -> HTTPRequest:
	var http := HTTPRequest.new()
	http.timeout = TIMEOUT_SEC
	add_child(http)
	return http


func _json_headers() -> PackedStringArray:
	return PackedStringArray(["Content-Type: application/json"])
