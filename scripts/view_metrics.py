#!/usr/bin/env python3
"""View current session management metrics."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.metrics import metrics_service


def main():
    """Display current metrics."""
    print("=" * 70)
    print("SESSION MANAGEMENT METRICS")
    print("=" * 70)
    print()

    metrics = metrics_service.get_metrics_summary()

    print(f"Sessions Created:        {metrics['sessions_created']}")
    print(f"Sessions Reused:         {metrics['sessions_reused']}")
    print(f"Session Reuse Ratio:     {metrics['session_reuse_ratio']:.2%}")
    print(f"Context Loss Incidents:  {metrics['context_loss_incidents']}")
    print()

    print("Health Status:")
    if metrics["reuse_ratio_healthy"]:
        print("  ✅ Session reuse ratio is HEALTHY (≥95%)")
        print("     Phase 2 fix is working correctly!")
    else:
        print("  ⚠️  Session reuse ratio is BELOW TARGET (<95%)")
        print("     Investigate session handling - possible race condition")

    print()
    print("=" * 70)

    # Alert if high creation rate detected
    total = metrics["sessions_created"] + metrics["sessions_reused"]
    if total > 0:
        create_pct = metrics["sessions_created"] / total
        if create_pct > 0.1:  # More than 10% creates
            print()
            print("⚠️  ALERT: High session creation rate detected!")
            print(f"   {create_pct:.1%} of session operations are creates")
            print("   Expected: <10% (most should be reuses)")
            print("   Check logs for duplicate session creation warnings")
            print()


if __name__ == "__main__":
    main()
