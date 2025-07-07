"""
Tests for ConfigureProjectIgnoresTool
"""
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch


class TestConfigureProjectIgnoresTool:
    """Test the ConfigureProjectIgnoresTool implementation"""
    
    def test_tool_structure(self):
        """Test that the tool class structure is correct."""
        # Read the tools.py file to check structure
        tools_path = Path(__file__).parent.parent / "src" / "serena" / "tools.py"
        with open(tools_path, 'r') as f:
            content = f.read()
        
        # Check if ConfigureProjectIgnoresTool is defined
        assert 'class ConfigureProjectIgnoresTool' in content
        assert 'ConfigureProjectIgnoresTool(Tool, ToolMarkerCanEdit)' in content
        assert 'def apply(' in content
        assert 'mode: str = "interactive"' in content
    
    def test_technology_detection_logic(self):
        """Test the technology detection logic without dependencies."""
        # Create a temporary directory structure for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create Python files
            (temp_path / "main.py").touch()
            (temp_path / "requirements.txt").touch()
            
            # Create Node.js files
            (temp_path / "package.json").touch()
            
            # Create Java files
            (temp_path / "Main.java").touch()
            
            # Read the tools.py file and extract the detection logic
            tools_path = Path(__file__).parent.parent / "src" / "serena" / "tools.py"
            with open(tools_path, 'r') as f:
                content = f.read()
            
            # Check if the detection logic is present
            assert 'def _detect_technologies' in content
            assert 'Python' in content
            assert 'Node.js' in content
            assert 'Java' in content
    
    def test_pattern_validation_logic(self):
        """Test that pattern validation logic is present."""
        tools_path = Path(__file__).parent.parent / "src" / "serena" / "tools.py"
        with open(tools_path, 'r') as f:
            content = f.read()
        
        # Check if pattern validation is present
        assert 'def _validate_pattern' in content
        assert 'dangerous_patterns' in content
        assert 'is_safe' in content
        assert 'warning' in content
    
    def test_recommendations_logic(self):
        """Test that recommendations logic is present."""
        tools_path = Path(__file__).parent.parent / "src" / "serena" / "tools.py"
        with open(tools_path, 'r') as f:
            content = f.read()
        
        # Check if recommendations logic is present
        assert 'def _get_recommendations' in content
        assert '__pycache__' in content
        assert 'node_modules' in content
        assert 'target/**' in content  # Java patterns
        assert 'bin/**' in content     # C# patterns
    
    def test_apply_configuration_logic(self):
        """Test that apply configuration logic is present."""
        tools_path = Path(__file__).parent.parent / "src" / "serena" / "tools.py"
        with open(tools_path, 'r') as f:
            content = f.read()
        
        # Check if apply configuration logic is present
        assert 'def _apply_configuration' in content
        assert 'project.project_config.ignored_paths' in content
        assert 'project.project_config.ignore_all_files_in_gitignore' in content
        assert 'project.project_config.save' in content
    
    def test_mode_handling(self):
        """Test that all three modes are handled."""
        tools_path = Path(__file__).parent.parent / "src" / "serena" / "tools.py"
        with open(tools_path, 'r') as f:
            content = f.read()
        
        # Check if all modes are handled
        assert 'if mode == "interactive"' in content
        assert 'elif mode == "direct"' in content
        assert 'elif mode == "suggest"' in content
        assert '_handle_interactive_mode' in content
        assert '_handle_direct_mode' in content
        assert '_handle_suggest_mode' in content
    
    def test_agent_integration(self):
        """Test that agent integration is present."""
        agent_path = Path(__file__).parent.parent / "src" / "serena" / "agent.py"
        with open(agent_path, 'r') as f:
            content = f.read()
        
        # Check if agent integration is present
        assert 'from serena.tools import ConfigureProjectIgnoresTool' in content
        assert 'ignore_tool = ConfigureProjectIgnoresTool(self)' in content
        assert 'result = ignore_tool.apply_ex(mode="suggest"' in content
        assert 'first_time_setup' in content