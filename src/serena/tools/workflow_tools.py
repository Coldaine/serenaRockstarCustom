"""
Tools supporting the general workflow of the agent
"""

import json
import platform

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject


class CheckOnboardingPerformedTool(Tool):
    """
    Checks whether project onboarding was already performed.
    """

    def apply(self) -> str:
        """
        Checks whether project onboarding was already performed.
        You should always call this tool before beginning to actually work on the project/after activating a project,
        but after calling the initial instructions tool.
        """
        from .memory_tools import ListMemoriesTool

        list_memories_tool = self.agent.get_tool(ListMemoriesTool)
        memories = json.loads(list_memories_tool.apply())
        if len(memories) == 0:
            return "No onboarding has been performed yet. Please run the onboarding tool first."
        return "Onboarding has been performed. Memories are available."


class InitialInstructionsTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Gets the initial instructions for the current project.
    Should only be used in settings where the system prompt cannot be set,
    e.g. in clients you have no control over, like Claude Desktop.
    """

    def apply(self) -> str:
        """
        Get the initial instructions for the current coding project.
        You should always call this tool before starting to work (including using any other tool) on any programming task!
        The only exception is when a user asks you to activate a project, in which case you should call the `activate_project` first
        instead and then call this tool.
        """
        return self.agent.create_system_prompt()