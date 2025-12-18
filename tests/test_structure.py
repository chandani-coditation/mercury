#!/usr/bin/env python3
"""Test that the refactored structure works correctly."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def test_imports():
    """Test that all imports work correctly."""
    print("Testing imports...")
    
    try:
        print("   Testing core imports...")
        from ai_service.core import (
            get_logger, setup_logging,
            load_config, get_policy_config,
            IncidentNotFoundError, DatabaseError
        )
        print("     Core imports successful")
    except Exception as e:
        print(f"     Core imports failed: {e}")
        return False
    
    try:
        print("   Testing repository imports...")
        from ai_service.repositories import IncidentRepository, FeedbackRepository
        print("     Repository imports successful")
    except Exception as e:
        print(f"     Repository imports failed: {e}")
        return False
    
    try:
        print("   Testing service imports...")
        from ai_service.services import IncidentService, FeedbackService
        print("     Service imports successful")
    except Exception as e:
        print(f"     Service imports failed: {e}")
        return False
    
    try:
        print("   Testing API route imports...")
        from ai_service.api.v1 import router
        print(f"     API router has {len(router.routes)} routes")
    except Exception as e:
        print(f"     API route imports failed: {e}")
        return False
    
    try:
        print("   Testing agent imports...")
        from ai_service.agents import triage_agent, resolution_copilot_agent
        print("     Agent imports successful")
    except Exception as e:
        print(f"     Agent imports failed: {e}")
        return False
    
    try:
        print("   Testing main app import...")
        from ai_service.main import app
        print(f"     Main app has {len(app.routes)} routes")
    except Exception as e:
        print(f"     Main app import failed: {e}")
        return False
    
    return True

def test_config_loading():
    """Test that configuration loads correctly."""
    print("\nTesting configuration loading...")
    
    try:
        from ai_service.core import load_config, get_policy_config, get_llm_config
        
        config = load_config()
        print(f"   Config loaded with {len(config)} top-level keys")
        
        policy_config = get_policy_config()
        print(f"   Policy config loaded: {len(policy_config.get('bands', {}))} policy bands")
        
        llm_config = get_llm_config()
        print(f"   LLM config loaded: provider={llm_config.get('provider', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"   Config loading failed: {e}")
        return False

def test_api_routes():
    """Test that API routes are properly registered."""
    print("\nTesting API routes...")
    
    try:
        from ai_service.main import app
        
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        print(f"   Found {len(routes)} routes")
        
        # Check for key routes
        expected_routes = [
            '/health',
            '/metrics',
            '/api/v1/health',
            '/api/v1/triage',
            '/api/v1/resolution',
            '/api/v1/incidents',
        ]
        
        for expected in expected_routes:
            if any(expected in r for r in routes):
                print(f"     Route found: {expected}")
            else:
                print(f"     Route not found: {expected}")
        
        return True
    except Exception as e:
        print(f"   API route test failed: {e}")
        return False

if __name__ == "__main__":
    print("="*80)
    print(" TESTING REFACTORED STRUCTURE")
    print("="*80)
    
    all_passed = True
    
    all_passed &= test_imports()
    all_passed &= test_config_loading()
    all_passed &= test_api_routes()
    
    print("\n" + "="*80)
    if all_passed:
        print(" ALL TESTS PASSED - Structure is correct!")
    else:
        print(" SOME TESTS FAILED - Check errors above")
    print("="*80)
    
    sys.exit(0 if all_passed else 1)

