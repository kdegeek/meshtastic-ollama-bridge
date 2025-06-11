import json
import os
import logging

# Configure basic logging for the config manager
logger = logging.getLogger(__name__)
# Example: if you want to see logs from this module directly
# logging.basicConfig(level=logging.INFO)

DEFAULT_SETTINGS = {
    "ollama_model": "",
    "meshtastic_connection_type": "Serial", # "Serial" or "Network"
    "meshtastic_serial_port": "",
    "meshtastic_network_host": "",
    "web_service_enabled": False,
    "selected_tab_index": 0, # To remember the last active tab (Settings or Conversation)
    # Future settings can be added here with their defaults
    # "some_future_setting": "default_value",
}

def load_settings(filepath="settings.json"):
    """
    Loads settings from a JSON file.
    If the file doesn't exist or is corrupted, returns default settings.
    Merges loaded settings with defaults to ensure all keys are present.
    """
    settings = DEFAULT_SETTINGS.copy() # Start with defaults

    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                loaded_settings = json.load(f)

            # Merge loaded settings into defaults. Loaded values take precedence.
            # This ensures that if new default settings are added, they are present
            # even if the settings file is older.
            for key in settings:
                if key in loaded_settings:
                    settings[key] = loaded_settings[key]
            # Also add any settings that might be in loaded_settings but not in defaults (e.g. from a newer version)
            # This is less critical if DEFAULT_SETTINGS is the master list.
            # for key in loaded_settings:
            #     if key not in settings:
            #         settings[key] = loaded_settings[key]

            logger.info(f"Settings loaded successfully from {filepath}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {filepath}: {e}. Returning default settings.")
            return DEFAULT_SETTINGS.copy() # Return a fresh copy of defaults
        except IOError as e:
            logger.error(f"IOError reading {filepath}: {e}. Returning default settings.")
            return DEFAULT_SETTINGS.copy() # Return a fresh copy of defaults
        except Exception as e:
            logger.error(f"Unexpected error loading settings from {filepath}: {e}. Returning default settings.")
            return DEFAULT_SETTINGS.copy()
    else:
        logger.info(f"Settings file {filepath} not found. Returning default settings.")
        # No need to do anything, 'settings' is already a copy of DEFAULT_SETTINGS

    return settings

def save_settings(settings_data, filepath="settings.json"):
    """
    Saves the provided settings data to a JSON file.
    """
    try:
        with open(filepath, 'w') as f:
            json.dump(settings_data, f, indent=4)
        logger.info(f"Settings saved successfully to {filepath}")
        return True
    except IOError as e:
        logger.error(f"IOError writing settings to {filepath}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error saving settings to {filepath}: {e}")
        return False

if __name__ == '__main__':
    # Example Usage (for testing)
    logging.basicConfig(level=logging.INFO) # So we can see logs for the test

    # Test 1: Load settings when file doesn't exist
    print("Test 1: Initial load (no file)")
    current_settings = load_settings("test_settings.json")
    print(f"Loaded settings: {current_settings}")
    assert current_settings["meshtastic_connection_type"] == "Serial"

    # Test 2: Modify and save settings
    print("\nTest 2: Modify and save")
    current_settings["ollama_model"] = "test_model_123"
    current_settings["web_service_enabled"] = True
    current_settings["selected_tab_index"] = 1
    save_settings(current_settings, "test_settings.json")

    # Test 3: Load modified settings
    print("\nTest 3: Load modified settings")
    reloaded_settings = load_settings("test_settings.json")
    print(f"Reloaded settings: {reloaded_settings}")
    assert reloaded_settings["ollama_model"] == "test_model_123"
    assert reloaded_settings["web_service_enabled"] is True
    assert reloaded_settings["selected_tab_index"] == 1

    # Test 4: Load settings with an older file (missing a new default key)
    print("\nTest 4: Simulate loading an older settings file")
    # Create a dummy settings file that's "older" (missing a key from current DEFAULT_SETTINGS)
    older_settings_data = {
        "ollama_model": "old_model",
        # "meshtastic_connection_type" is present in DEFAULT_SETTINGS but not here,
        # "selected_tab_index" is also missing
    }
    with open("test_old_settings.json", 'w') as f:
        json.dump(older_settings_data, f, indent=4)

    # Add a temporary new default setting for this test case
    DEFAULT_SETTINGS["new_temp_setting"] = "temp_default_value"

    loaded_old_settings = load_settings("test_old_settings.json")
    print(f"Loaded 'old' settings, merged with defaults: {loaded_old_settings}")
    assert loaded_old_settings["ollama_model"] == "old_model" # From file
    assert loaded_old_settings["meshtastic_connection_type"] == "Serial" # From default
    assert loaded_old_settings["selected_tab_index"] == 0 # From default
    assert loaded_old_settings["new_temp_setting"] == "temp_default_value" # New default merged in

    # Clean up test files
    del DEFAULT_SETTINGS["new_temp_setting"] # remove temp default
    os.remove("test_settings.json")
    os.remove("test_old_settings.json")
    print("\nTests complete. Cleaned up test files.")
