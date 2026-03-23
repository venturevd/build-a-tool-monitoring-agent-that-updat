# Step 3: Create update handler

**File to create:** `tool_updater.py`
**Estimated size:** ~70 lines

## Instructions

Write a Python script that handles tool updates using the agent_representation_broker. The script should:
1. Connect to the broker
2. Check for available updates
3. Apply updates safely with rollback capability
4. Provide a simple CLI interface with --help support

## Verification

Run: `python3 tool_updater.py --help`
