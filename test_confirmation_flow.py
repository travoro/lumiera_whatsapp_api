#!/usr/bin/env python3
"""Test progress update confirmation flow."""

import asyncio
from src.services.progress_update.agent import progress_update_agent
from src.integrations.supabase import supabase_client
from src.integrations.planradar import planradar_client
from src.utils.logger import log

# Test user and project IDs
TEST_USER_ID = "24e79a44-cc68-45a0-8430-5e8fcb3a59ee"
TEST_PROJECT_ID = "fc15e8c0-dd6b-4f40-9a95-bd74b8b8ddae"  # Champigny
PLANRADAR_PROJECT_ID = "4f86e32c-8a8c-4cc9-95e8-0d2ab831a36c"
TEST_TASK_ID = "a9a6e65f-e04c-4dff-a40c-ae1e8c85b5ae"  # Task test 1

async def test_confirmation_extraction():
    """Test that confirmation data is extracted and added to tool_outputs."""

    print("\n" + "="*80)
    print("TEST: Confirmation Data Extraction")
    print("="*80)

    # Get task details from PlanRadar
    print(f"\n1. Getting task details from PlanRadar...")
    task = await planradar_client.get_task(TEST_TASK_ID, PLANRADAR_PROJECT_ID)
    if task:
        task_data = task.get("data", {})
        task_attrs = task_data.get("attributes", {})
        task_title = task_attrs.get("subject", "Unknown Task")
        print(f"   ✅ Task: {task_title}")
        print(f"   ✅ Task ID: {TEST_TASK_ID}")
        print(f"   ✅ Project ID: {PLANRADAR_PROJECT_ID}")
    else:
        print(f"   ❌ Failed to get task")
        return

    # Process message with progress update agent
    print(f"\n2. Processing message with progress update agent...")
    result = await progress_update_agent.process(
        user_id=TEST_USER_ID,
        user_name="Traian ANGHELINA",
        language="fr",
        message="je souhaite mettre a jour la progression de ma tache"
    )

    print(f"\n3. Checking result...")
    if result.get("success"):
        print(f"   ✅ Agent processed successfully")
        print(f"   Response: {result['message'][:200]}...")

        # Check if tool_outputs are in the result
        if 'tool_outputs' in result:
            tool_outputs = result['tool_outputs']
            print(f"\n4. Checking tool_outputs...")
            print(f"   Found {len(tool_outputs)} tool outputs")

            for idx, tool_output in enumerate(tool_outputs):
                print(f"\n   Tool Output #{idx + 1}:")
                print(f"   - Tool: {tool_output.get('tool')}")
                print(f"   - Output keys: {list(tool_output.get('output', {}).keys())}")

                if 'confirmation' in tool_output.get('output', {}):
                    confirmation = tool_output['output']['confirmation']
                    print(f"   ✅ FOUND CONFIRMATION DATA:")
                    print(f"      - Task ID: {confirmation.get('task_id')}")
                    print(f"      - Project ID: {confirmation.get('project_id')}")
                    print(f"      - Task Title: {confirmation.get('task_title')}")

                    # Verify data is correct
                    if confirmation.get('task_id') == TEST_TASK_ID:
                        print(f"   ✅ Task ID matches!")
                    else:
                        print(f"   ❌ Task ID mismatch: expected {TEST_TASK_ID}, got {confirmation.get('task_id')}")

                    if confirmation.get('project_id') == PLANRADAR_PROJECT_ID:
                        print(f"   ✅ Project ID matches!")
                    else:
                        print(f"   ❌ Project ID mismatch: expected {PLANRADAR_PROJECT_ID}, got {confirmation.get('project_id')}")
        else:
            print(f"   ❌ No tool_outputs in result")
    else:
        print(f"   ❌ Agent failed: {result.get('error')}")

    print(f"\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_confirmation_extraction())
