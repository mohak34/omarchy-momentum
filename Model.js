.pragma library

var noiseModes = [
  { value: "adaptive", label: "Adaptive" },
  { value: "custom", label: "Custom" },
  { value: "off", label: "Off" }
]

var antiWindModes = [
  { value: "off", label: "Off" },
  { value: "auto", label: "Auto" },
  { value: "max", label: "Max" }
]

// Minutes, as m4.py reports them; 0 is never.
var autoOffChoices = [
  { value: 0, arg: "never", label: "Never" },
  { value: 15, arg: "15", label: "15m" },
  { value: 30, arg: "30", label: "30m" },
  { value: 60, arg: "60", label: "60m" }
]

// On/off settings: the m4.py setting name and the status key it reports.
// Settings the firmware does not support come back null and are hidden.
var sound = [
  { setting: "bass-boost", key: "bassBoost", label: "Bass boost" },
  { setting: "speech", key: "speech", label: "Speech clarity" }
]

var behaviour = [
  { setting: "on-head", key: "onHead", label: "On-head detection" },
  { setting: "smart-pause", key: "smartPause", label: "Smart pause" },
  { setting: "touch", key: "touch", label: "Touch controls" },
  { setting: "auto-answer", key: "autoAnswer", label: "Auto-answer calls" },
  { setting: "comfort-call", key: "comfortCall", label: "Comfort call" }
]

// Nerd Font md-headphones / md-headphones-off.
function glyph(connected) {
  return String.fromCodePoint(connected ? 0xF02CB : 0xF07CE)
}

function copy(obj) {
  var out = {}
  for (var k in obj) out[k] = obj[k]
  return out
}

function nextNoise(noise) {
  for (var i = 0; i < noiseModes.length; i++)
    if (noiseModes[i].value === noise) return noiseModes[(i + 1) % noiseModes.length].value
  return "adaptive"
}

// The state with one `m4.py set` applied, so the panel moves before the
// headphones answer. The helper's reply replaces it with the real state.
function apply(state, setting, value) {
  var s = copy(state)
  if (setting === "noise") s.noise = value
  else if (setting === "transparency") s.transparency = parseInt(value, 10)
  else if (setting === "anti-wind") s.antiWind = value
  else if (setting === "auto-off") s.autoOff = value === "never" ? 0 : parseInt(value, 10)
  else {
    var all = sound.concat(behaviour)
    for (var i = 0; i < all.length; i++) if (all[i].setting === setting) s[all[i].key] = value === "on"
  }
  return s
}

// "aptX HD · 44.1 kHz", "USB · 16-bit 48 kHz", or why there is nothing to show.
function status(state, error) {
  if (!state) return error || "Looking for the headphones"
  var o = state.output
  if (o && o.kind === "bluetooth") return [o.codec || "Bluetooth", rate(o.rate), o.call ? "call" : ""].filter(Boolean).join(" · ")
  if (o && o.kind === "usb") return ["USB", bits(o.format) + rate(o.rate)].filter(Boolean).join(" · ")
  return state.connected ? "Not the audio output" : "Not connected"
}

function rate(hz) {
  return hz ? (hz / 1000) + " kHz" : ""
}

// pactl sample formats like "s16le" as "16-bit ".
function bits(format) {
  var m = /(\d+)/.exec(format || "")
  return m ? m[1] + "-bit " : ""
}

function noiseLabel(state) {
  if (!state || !state.connected) return ""
  if (state.noise === "off") return "ANC off"
  return state.noise === "adaptive" ? "Adaptive" : "Transparency " + state.transparency + "%"
}

function tooltip(state, error) {
  if (!state || !state.connected) return "Momentum 4: " + status(state, error)
  return "Momentum 4: " + state.battery + "% · " + noiseLabel(state)
}
