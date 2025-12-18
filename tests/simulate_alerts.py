"""Simulate alerts being sent to the AI service."""
import sys
import os
import time
import argparse

# Add project root to path (go up 2 levels: tests -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.alert_generator import simulate_robusta_alert


def main():
    parser = argparse.ArgumentParser(description="Simulate alerts")
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of alerts to simulate (default: 5)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Interval between alerts in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8001",
        help="AI service URL (default: http://localhost:8001)"
    )
    
    args = parser.parse_args()
    
    print(f"Simulating {args.count} alerts to {args.url}")
    print("-" * 60)
    
    for i in range(args.count):
        print(f"\n[{i+1}/{args.count}] Generating alert...")
        result = simulate_robusta_alert(args.url)
        
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            incident_id = result.get("incident_id")
            triage = result.get("triage", {})
            severity = triage.get("severity", "unknown")
            summary = triage.get("summary", "N/A")
            
            print(f" Incident ID: {incident_id}")
            print(f"  Severity: {severity}")
            print(f"  Summary: {summary[:100]}...")
        
        if i < args.count - 1:
            time.sleep(args.interval)
    
    print("\n" + "-" * 60)
    print("Simulation complete!")


if __name__ == "__main__":
    main()



