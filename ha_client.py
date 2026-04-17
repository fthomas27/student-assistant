"""
Home Assistant REST API client for Jarvis to control smart home devices.
"""

import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

log = logging.getLogger(__name__)


class HAClient:
    """Client for Home Assistant REST API."""

    def __init__(self, ha_url: str, ha_token: str):
        """Initialize with Home Assistant URL and token."""
        self.base_url = ha_url.rstrip("/")
        self.token = ha_token
        self.headers = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json"
        }
        self.device_cache: Dict[str, Any] = {}
        self._refresh_device_cache()

    def _refresh_device_cache(self):
        """Refresh the device cache from HA."""
        try:
            devices = self.get_devices()
            for device in devices:
                self.device_cache[device['entity_id']] = device
            log.info(f"Cached {len(self.device_cache)} HA devices")
        except Exception as e:
            log.error(f"Failed to cache devices: {e}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        timeout: int = 5
    ) -> Dict:
        """Make a request to Home Assistant API."""
        url = f"{self.base_url}/api/{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, json=data, headers=self.headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json() if response.text else {}

        except requests.exceptions.RequestException as e:
            log.error(f"HA API error: {e}")
            raise

    def get_devices(self) -> List[Dict]:
        """Get all devices/entities from Home Assistant."""
        try:
            states = self._make_request("GET", "states")
            return states if isinstance(states, list) else []
        except Exception as e:
            log.error(f"Failed to get devices: {e}")
            return []

    def get_device_state(self, entity_id: str) -> Optional[Dict]:
        """Get the current state of a device."""
        try:
            return self._make_request("GET", f"states/{entity_id}")
        except Exception as e:
            log.error(f"Failed to get state for {entity_id}: {e}")
            return None

    def call_service(self, domain: str, service: str, data: Dict = None) -> bool:
        """Call a Home Assistant service."""
        try:
            self._make_request("POST", f"services/{domain}/{service}", data=data or {})
            log.info(f"Called {domain}.{service}")
            return True
        except Exception as e:
            log.error(f"Failed to call {domain}.{service}: {e}")
            return False

    def turn_on_light(self, entity_id: str, brightness: int = None, color_temp: int = None) -> bool:
        """Turn on a light with optional brightness and color temperature."""
        data = {}
        if brightness is not None:
            data['brightness'] = max(0, min(255, brightness))
        if color_temp is not None:
            data['color_temp'] = color_temp

        return self.call_service("light", "turn_on", {"entity_id": entity_id, **data})

    def turn_off_light(self, entity_id: str) -> bool:
        """Turn off a light."""
        return self.call_service("light", "turn_off", {"entity_id": entity_id})

    def toggle_light(self, entity_id: str) -> bool:
        """Toggle a light on/off."""
        return self.call_service("light", "toggle", {"entity_id": entity_id})

    def set_climate(self, entity_id: str, temperature: float = None, mode: str = None) -> bool:
        """Set climate control (thermostat)."""
        data = {"entity_id": entity_id}
        if temperature is not None:
            data['temperature'] = temperature
        if mode is not None:
            data['hvac_mode'] = mode

        return self.call_service("climate", "set_temperature", data)

    def trigger_automation(self, automation_id: str) -> bool:
        """Trigger a Home Assistant automation."""
        return self.call_service("automation", "trigger", {"entity_id": automation_id})

    def activate_scene(self, scene_id: str) -> bool:
        """Activate a Home Assistant scene."""
        return self.call_service("scene", "turn_on", {"entity_id": scene_id})

    def get_lights(self) -> List[Dict]:
        """Get all light devices."""
        return [d for d in self.device_cache.values() if d.get('entity_id', '').startswith('light.')]

    def get_switches(self) -> List[Dict]:
        """Get all switch devices."""
        return [d for d in self.device_cache.values() if d.get('entity_id', '').startswith('switch.')]

    def get_climate_devices(self) -> List[Dict]:
        """Get all climate control devices."""
        return [d for d in self.device_cache.values() if d.get('entity_id', '').startswith('climate.')]

    def get_media_players(self) -> List[Dict]:
        """Get all media player devices."""
        return [d for d in self.device_cache.values() if d.get('entity_id', '').startswith('media_player.')]

    def find_device_by_name(self, name: str) -> Optional[Dict]:
        """Find a device by friendly name (case-insensitive)."""
        name_lower = name.lower()
        for device in self.device_cache.values():
            if device.get('attributes', {}).get('friendly_name', '').lower() == name_lower:
                return device
        return None

    def parse_control_command(self, command: str) -> Dict[str, Any]:
        """Parse a natural language control command and return action dict."""
        command_lower = command.lower()

        # Light commands
        if "light" in command_lower:
            if any(w in command_lower for w in ["on", "turn on", "enable"]):
                return {"action": "light_on", "command": command}
            elif any(w in command_lower for w in ["off", "turn off", "disable"]):
                return {"action": "light_off", "command": command}
            elif "toggle" in command_lower:
                return {"action": "light_toggle", "command": command}
            elif any(w in command_lower for w in ["bright", "dim"]):
                return {"action": "light_dim", "command": command}

        # Climate commands
        elif any(w in command_lower for w in ["climate", "temperature", "thermostat"]):
            if any(w in command_lower for w in ["up", "warm", "heat"]):
                return {"action": "climate_warm", "command": command}
            elif any(w in command_lower for w in ["down", "cool", "cold"]):
                return {"action": "climate_cool", "command": command}

        # Scene/automation
        elif "scene" in command_lower or "mode" in command_lower:
            return {"action": "activate_scene", "command": command}

        return {"action": "unknown", "command": command}

    def get_ha_status_summary(self) -> Dict[str, Any]:
        """Get a brief status summary of all devices."""
        summary = {
            "lights_on": 0,
            "lights_off": 0,
            "switches_on": 0,
            "switches_off": 0,
            "climate_devices": []
        }

        for device in self.device_cache.values():
            entity_id = device.get('entity_id', '')
            state = device.get('state', 'unknown')

            if entity_id.startswith('light.'):
                if state == 'on':
                    summary['lights_on'] += 1
                else:
                    summary['lights_off'] += 1

            elif entity_id.startswith('switch.'):
                if state == 'on':
                    summary['switches_on'] += 1
                else:
                    summary['switches_off'] += 1

            elif entity_id.startswith('climate.'):
                summary['climate_devices'].append({
                    'name': device.get('attributes', {}).get('friendly_name', entity_id),
                    'temperature': device.get('attributes', {}).get('current_temperature'),
                    'mode': state
                })

        return summary

    def health_check(self) -> bool:
        """Check if Home Assistant is reachable."""
        try:
            self._make_request("GET", "config")
            return True
        except Exception:
            return False
