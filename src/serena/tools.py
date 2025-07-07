"""
The Serena Model Context Protocol (MCP) Server
"""

import inspect
import json
import os
import platform
import re
import shutil
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Sequence
from copy import copy
from fnmatch import fnmatch
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self, TypeVar

from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata, func_metadata
from sensai.util import logging
from sensai.util.string import dict_string

from serena.config.context_mode import SerenaAgentMode
from serena.prompt_factory import PromptFactory
from serena.symbol import SymbolManager
from serena.text_utils import search_files
from serena.util.file_system import scan_directory
from serena.util.inspection import iter_subclasses
from serena.util.shell import execute_shell_command
from solidlsp import SolidLanguageServer
from solidlsp.ls_types import SymbolKind

if TYPE_CHECKING:
    from .agent import LinesRead, MemoriesManager, SerenaAgent

log = logging.getLogger(__name__)
T = TypeVar("T")
SUCCESS_RESULT = "OK"


def _sanitize_symbol_dict(symbol_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize a symbol dictionary inplace by removing unnecessary information.
    """
    # We replace the location entry, which repeats line information already included in body_location
    # and has unnecessary information on column, by just the relative path.
    symbol_dict = copy(symbol_dict)
    s_relative_path = symbol_dict.get("location", {}).get("relative_path")
    if s_relative_path is not None:
        symbol_dict["relative_path"] = s_relative_path
    symbol_dict.pop("location", None)
    # also remove name, name_path should be enough
    symbol_dict.pop("name")
    return symbol_dict


class Component(ABC):
    def __init__(self, agent: "SerenaAgent"):
        self.agent = agent

    @property
    def language_server(self) -> SolidLanguageServer:
        assert self.agent.language_server is not None
        return self.agent.language_server

    def get_project_root(self) -> str:
        """
        :return: the root directory of the active project, raises a ValueError if no active project configuration is set
        """
        return self.agent.get_project_root()

    @property
    def prompt_factory(self) -> PromptFactory:
        return self.agent.prompt_factory

    @property
    def memories_manager(self) -> "MemoriesManager":
        assert self.agent.memories_manager is not None
        return self.agent.memories_manager

    @property
    def symbol_manager(self) -> SymbolManager:
        assert self.agent.symbol_manager is not None
        return self.agent.symbol_manager

    @property
    def lines_read(self) -> "LinesRead":
        assert self.agent.lines_read is not None
        return self.agent.lines_read


_DEFAULT_MAX_ANSWER_LENGTH = int(2e5)


class ToolMarkerCanEdit:
    """
    Marker class for all tools that can perform editing operations on files.
    """


class ToolMarkerDoesNotRequireActiveProject:
    pass


class ToolInterface(ABC):
    """Protocol defining the complete interface that make_tool() expects from a tool."""

    @abstractmethod
    def get_name(self) -> str:
        """Get the tool name."""
        ...

    @abstractmethod
    def get_apply_docstring(self) -> str:
        """Get the docstring for the tool application, used by the MCP server."""
        ...

    @abstractmethod
    def get_apply_fn_metadata(self) -> FuncMetadata:
        """Get the metadata for the tool application function, used by the MCP server."""
        ...

    @abstractmethod
    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs: Any) -> str:
        """Apply the tool with logging and exception handling."""
        ...


class Tool(Component, ToolInterface):
    # NOTE: each tool should implement the apply method, which is then used in
    # the central method of the Tool class `apply_ex`.
    # Failure to do so will result in a RuntimeError at tool execution time.
    # The apply method is not declared as part of the base Tool interface since we cannot
    # know the signature of the (input parameters of the) method in advance.
    #
    # The docstring and types of the apply method are used to generate the tool description
    # (which is use by the LLM, so a good description is important)
    # and to validate the tool call arguments.

    @classmethod
    def get_name_from_cls(cls) -> str:
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # convert to snake_case
        name = "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")
        return name

    def get_name(self) -> str:
        return self.get_name_from_cls()

    def get_apply_fn(self) -> Callable:
        apply_fn = getattr(self, "apply")
        if apply_fn is None:
            raise RuntimeError(f"apply not defined in {self}. Did you forget to implement it?")
        return apply_fn

    @classmethod
    def can_edit(cls) -> bool:
        """
        Returns whether this tool can perform editing operations on code.

        :return: True if the tool can edit code, False otherwise
        """
        return issubclass(cls, ToolMarkerCanEdit)

    @classmethod
    def get_tool_description(cls) -> str:
        docstring = cls.__doc__
        if docstring is None:
            return ""
        return docstring.strip()

    @classmethod
    def get_apply_docstring_from_cls(cls) -> str:
        """Get the docstring for the apply method from the class (static metadata).
        Needed for creating MCP tools in a separate process without running into serialization issues.
        """
        # First try to get from __dict__ to handle dynamic docstring changes
        if "apply" in cls.__dict__:
            apply_fn = cls.__dict__["apply"]
        else:
            # Fall back to getattr for inherited methods
            apply_fn = getattr(cls, "apply", None)
            if apply_fn is None:
                raise AttributeError(f"apply method not defined in {cls}. Did you forget to implement it?")

        docstring = apply_fn.__doc__
        if not docstring:
            raise AttributeError(f"apply method has no (or empty) docstring in {cls}. Did you forget to implement it?")
        return docstring.strip()

    def get_apply_docstring(self) -> str:
        """Get the docstring for the apply method (instance method implementing ToolProtocol)."""
        return self.get_apply_docstring_from_cls()

    def get_apply_fn_metadata(self) -> FuncMetadata:
        """Get the metadata for the apply method (instance method implementing ToolProtocol)."""
        return self.get_apply_fn_metadata_from_cls()

    @classmethod
    def get_apply_fn_metadata_from_cls(cls) -> FuncMetadata:
        """Get the metadata for the apply method from the class (static metadata).
        Needed for creating MCP tools in a separate process without running into serialization issues.
        """
        # First try to get from __dict__ to handle dynamic docstring changes
        if "apply" in cls.__dict__:
            apply_fn = cls.__dict__["apply"]
        else:
            # Fall back to getattr for inherited methods
            apply_fn = getattr(cls, "apply", None)
            if apply_fn is None:
                raise AttributeError(f"apply method not defined in {cls}. Did you forget to implement it?")

        return func_metadata(apply_fn, skip_names=["self", "cls"])

    def _log_tool_application(self, frame: Any) -> None:
        params = {}
        ignored_params = {"self", "log_call", "catch_exceptions", "args", "apply_fn"}
        for param, value in frame.f_locals.items():
            if param in ignored_params:
                continue
            if param == "kwargs":
                params.update(value)
            else:
                params[param] = value
        log.info(f"{self.get_name_from_cls()}: {dict_string(params)}")

    @staticmethod
    def _limit_length(result: str, max_answer_chars: int) -> str:
        if (n_chars := len(result)) > max_answer_chars:
            result = (
                f"The answer is too long ({n_chars} characters). "
                + "Please try a more specific tool query or raise the max_answer_chars parameter."
            )
        return result

    def is_active(self) -> bool:
        return self.agent.tool_is_active(self.__class__)

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs) -> str:  # type: ignore
        """
        Applies the tool with the given arguments
        """

        def task() -> str:
            apply_fn = self.get_apply_fn()

            try:
                if not self.is_active():
                    return f"Error: Tool '{self.get_name_from_cls()}' is not active. Active tools: {self.agent.get_active_tool_names()}"
            except Exception as e:
                return f"RuntimeError while checking if tool {self.get_name_from_cls()} is active: {e}"

            if log_call:
                self._log_tool_application(inspect.currentframe())
            try:
                # check whether the tool requires an active project and language server
                if not isinstance(self, ToolMarkerDoesNotRequireActiveProject):
                    if self.agent._active_project is None:
                        return (
                            "Error: No active project. Ask to user to select a project from this list: "
                            + f"{self.agent.serena_config.project_names}"
                        )
                    if not self.agent.is_language_server_running():
                        log.info("Language server is not running. Starting it ...")
                        self.agent.reset_language_server()

                # apply the actual tool
                result = apply_fn(**kwargs)

            except Exception as e:
                if not catch_exceptions:
                    raise
                msg = f"Error executing tool: {e}\n{traceback.format_exc()}"
                log.error(
                    f"Error executing tool: {e}. "
                    f"Consider restarting the language server to solve this (especially, if it's a timeout of a symbolic operation)",
                    exc_info=e,
                )
                result = msg

            if log_call:
                log.info(f"Result: {result}")

            try:
                self.language_server.save_cache()
            except Exception as e:
                log.error(f"Error saving language server cache: {e}")

            return result

        future = self.agent.issue_task(task, name=self.__class__.__name__)
        return future.result(timeout=self.agent.serena_config.tool_timeout)


class RestartLanguageServerTool(Tool):
    """Restarts the language server, may be necessary when edits not through Serena happen."""

    def apply(self) -> str:
        """Use this tool only on explicit user request or after confirmation.
        It may be necessary to restart the language server if the user performs edits
        not through Serena, so the language server state becomes outdated and further editing attempts lead to errors.

        If such editing errors happen, you should suggest using this tool.
        """
        self.agent.reset_language_server()
        return SUCCESS_RESULT


class ReadFileTool(Tool):
    """
    Reads a file within the project directory.
    """

    def apply(
        self, relative_path: str, start_line: int = 0, end_line: int | None = None, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH
    ) -> str:
        """
        Reads the given file or a chunk of it. Generally, symbolic operations
        like find_symbol or find_referencing_symbols should be preferred if you know which symbols you are looking for.
        Reading the entire file is only recommended if there is no other way to get the content required for the task.

        :param relative_path: the relative path to the file to read
        :param start_line: the 0-based index of the first line to be retrieved.
        :param end_line: the 0-based index of the last line to be retrieved (inclusive). If None, read until the end of the file.
        :param max_answer_chars: if the file (chunk) is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: the full text of the file at the given relative path
        """
        self.agent.validate_relative_path(relative_path)

        result = self.language_server.retrieve_full_file_content(relative_path)
        result_lines = result.splitlines()
        if end_line is None:
            result_lines = result_lines[start_line:]
        else:
            self.lines_read.add_lines_read(relative_path, (start_line, end_line))
            result_lines = result_lines[start_line : end_line + 1]
        result = "\n".join(result_lines)

        return self._limit_length(result, max_answer_chars)


class CreateTextFileTool(Tool, ToolMarkerCanEdit):
    """
    Creates/overwrites a file in the project directory.
    """

    def apply(self, relative_path: str, content: str) -> str:
        """
        Write a new file (or overwrite an existing file). For existing files, it is strongly recommended
        to use symbolic operations like replace_symbol_body or insert_after_symbol/insert_before_symbol, if possible.
        You can also use insert_at_line to insert content at a specific line for existing files if the symbolic operations
        are not the right choice for what you want to do.

        If ever used on an existing file, the content has to be the complete content of that file (so it
        may never end with something like "The remaining content of the file is left unchanged.").
        For operations that just replace a part of a file, use the replace_lines or the symbolic editing tools instead.

        :param relative_path: the relative path to the file to create
        :param content: the (utf-8-encoded) content to write to the file
        :return: a message indicating success or failure
        """
        self.agent.validate_relative_path(relative_path)

        abs_path = (Path(self.get_project_root()) / relative_path).resolve()
        will_overwrite_existing = abs_path.exists()

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        answer = f"File created: {relative_path}."
        if will_overwrite_existing:
            answer += " Overwrote existing file."
        return answer


class ListDirTool(Tool):
    """
    Lists files and directories in the given directory (optionally with recursion).
    """

    def apply(self, relative_path: str, recursive: bool, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Lists all non-gitignored files and directories in the given directory (optionally with recursion).

        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object with the names of directories and files within the given directory
        """
        self.agent.validate_relative_path(relative_path)

        dirs, files = scan_directory(
            os.path.join(self.get_project_root(), relative_path),
            relative_to=self.get_project_root(),
            recursive=recursive,
            is_ignored_dir=self.agent.path_is_gitignored,
            is_ignored_file=self.agent.path_is_gitignored,
        )

        result = json.dumps({"dirs": dirs, "files": files})
        return self._limit_length(result, max_answer_chars)


class FindFileTool(Tool):
    """
    Finds files in the given relative paths
    """

    def apply(self, file_mask: str, relative_path: str) -> str:
        """
        Finds non-gitignored files matching the given file mask within the given relative path

        :param file_mask: the filename or file mask (using the wildcards * or ?) to search for
        :param relative_path: the relative path to the directory to search in; pass "." to scan the project root
        :return: a JSON object with the list of matching files
        """
        self.agent.validate_relative_path(relative_path)

        dir_to_scan = os.path.join(self.get_project_root(), relative_path)

        # find the files by ignoring everything that doesn't match
        def is_ignored_file(abs_path: str) -> bool:
            if self.agent.path_is_gitignored(abs_path):
                return True
            filename = os.path.basename(abs_path)
            return not fnmatch(filename, file_mask)

        dirs, files = scan_directory(
            path=dir_to_scan,
            recursive=True,
            is_ignored_dir=self.agent.path_is_gitignored,
            is_ignored_file=is_ignored_file,
            relative_to=self.get_project_root(),
        )

        result = json.dumps({"files": files})
        return result


class GetSymbolsOverviewTool(Tool):
    """
    Gets an overview of the top-level symbols defined in a given file or directory.
    """

    def apply(self, relative_path: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Gets an overview of the given file or directory.
        For each analyzed file, we list the top-level symbols in the file (name_path, kind).
        Use this tool to get a high-level understanding of the code symbols.
        Calling this is often a good idea before more targeted reading, searching or editing operations on the code symbols.

        :param relative_path: the relative path to the file or directory to get the overview of
        :param max_answer_chars: if the overview is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. If the overview is too long, you should use a smaller directory instead,
            (e.g. a subdirectory).
        :return: a JSON object mapping relative paths of all contained files to info about top-level symbols in the file (name_path, kind).
        """
        path_to_symbol_infos = self.language_server.request_overview(relative_path)
        result = {}
        for file_path, symbols in path_to_symbol_infos.items():
            # TODO: maybe include not just top-level symbols? We could filter by kind to exclude variables
            #  The language server methods would need to be adjusted for this.
            result[file_path] = [{"name_path": symbol[0], "kind": int(symbol[1])} for symbol in symbols]

        result_json_str = json.dumps(result)
        return self._limit_length(result_json_str, max_answer_chars)


class FindSymbolTool(Tool):
    """
    Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
    """

    def apply(
        self,
        name_path: str,
        depth: int = 0,
        relative_path: str | None = None,
        include_body: bool = False,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        substring_matching: bool = False,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given `name_path`,
        which represents a pattern for the symbol's path within the symbol tree of a single file.
        The returned symbol location can be used for edits or further queries.
        Specify `depth > 0` to retrieve children (e.g., methods of a class).

        The matching behavior is determined by the structure of `name_path`, which can
        either be a simple name (e.g. "method") or a name path like "class/method" (relative name path)
        or "/class/method" (absolute name path). Note that the name path is not a path in the file system
        but rather a path in the symbol tree **within a single file**. Thus, file or directory names should never
        be included in the `name_path`. For restricting the search to a single file or directory,
        the `within_relative_path` parameter should be used instead. The retrieved symbols' `name_path` attribute
        will always be composed of symbol names, never file or directory names.

        Key aspects of the name path matching behavior:
        - Trailing slashes in `name_path` play no role and are ignored.
        - The name of the retrieved symbols will match (either exactly or as a substring)
          the last segment of `name_path`, while other segments will restrict the search to symbols that
          have a desired sequence of ancestors.
        - If there is no starting or intermediate slash in `name_path`, there is no
          restriction on the ancestor symbols. For example, passing `method` will match
          against symbols with name paths like `method`, `class/method`, `class/nested_class/method`, etc.
        - If `name_path` contains a `/` but doesn't start with a `/`, the matching is restricted to symbols
          with the same ancestors as the last segment of `name_path`. For example, passing `class/method` will match against
          `class/method` as well as `nested_class/class/method` but not `method`.
        - If `name_path` starts with a `/`, it will be treated as an absolute name path pattern, meaning
          that the first segment of it must match the first segment of the symbol's name path.
          For example, passing `/class` will match only against top-level symbols like `class` but not against `nested_class/class`.
          Passing `/class/method` will match against `class/method` but not `nested_class/class/method` or `method`.


        :param name_path: The name path pattern to search for, see above for details.
        :param depth: Depth to retrieve descendants (e.g., 1 for class methods/attributes).
        :param relative_path: Optional. Restrict search to this file or directory. If None, searches entire codebase.
            If a directory is passed, the search will be restricted to the files in that directory.
            If a file is passed, the search will be restricted to that file.
            If you have some knowledge about the codebase, you should use this parameter, as it will significantly
            speed up the search as well as reduce the number of results.
        :param include_body: If True, include the symbol's source code. Use judiciously.
        :param include_kinds: Optional. List of LSP symbol kind integers to include. (e.g., 5 for Class, 12 for Function).
            Valid kinds: 1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter
        :param exclude_kinds: Optional. List of LSP symbol kind integers to exclude. Takes precedence over `include_kinds`.
        :param substring_matching: If True, use substring matching for the last segment of `name`.
        :param max_answer_chars: Max characters for the JSON result. If exceeded, no content is returned.
        :return: JSON string: a list of symbols (with locations) matching the name.
        """
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbols = self.symbol_manager.find_by_name(
            name_path,
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
            substring_matching=substring_matching,
            within_relative_path=relative_path,
        )
        symbol_dicts = [_sanitize_symbol_dict(s.to_dict(kind=True, location=True, depth=depth, include_body=include_body)) for s in symbols]
        result = json.dumps(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingSymbolsTool(Tool):
    """
    Finds symbols that reference the symbol at the given location (optionally filtered by type).
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Finds symbols that reference the symbol at the given `name_path`. The result will contain metadata about the referencing symbols
        as well as a short code snippet around the reference (unless `include_body` is True, then the short snippet will be omitted).
        Note that among other kinds of references, this function can be used to find (direct) subclasses of a class,
        as subclasses are referencing symbols that have the kind class.

        :param name_path: for finding the symbol to find references for, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol for which to find references.
            Note that here you can't pass a directory but must pass a file.
        :param include_kinds: same as in the `find_symbol` tool.
        :param exclude_kinds: same as in the `find_symbol` tool.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        include_body = False  # It is probably never a good idea to include the body of the referencing symbols
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        references_in_symbols = self.symbol_manager.find_referencing_symbols(
            name_path,
            relative_file_path=relative_path,
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
        )
        reference_dicts = []
        for ref in references_in_symbols:
            ref_dict = ref.symbol.to_dict(kind=True, location=True, depth=0, include_body=include_body)
            ref_dict = _sanitize_symbol_dict(ref_dict)
            if not include_body:
                ref_relative_path = ref.symbol.location.relative_path
                assert ref_relative_path is not None, f"Referencing symbol {ref.symbol.name} has no relative path, this is likely a bug."
                content_around_ref = self.language_server.retrieve_content_around_line(
                    relative_file_path=ref_relative_path, line=ref.line, context_lines_before=1, context_lines_after=1
                )
                ref_dict["content_around_reference"] = content_around_ref.to_display_string()
            reference_dicts.append(ref_dict)
        result = json.dumps(reference_dicts)
        return self._limit_length(result, max_answer_chars)


class ReplaceSymbolBodyTool(Tool, ToolMarkerCanEdit):
    """
    Replaces the full definition of a symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        r"""
        Replaces the body of the symbol with the given `name_path`.

        :param name_path: for finding the symbol to replace, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol
        :param body: the new symbol body. Important: Begin directly with the symbol definition and provide no
            leading indentation for the first line (but do indent the rest of the body according to the context).
        """
        self.symbol_manager.replace_body(
            name_path,
            relative_file_path=relative_path,
            body=body,
            use_same_indentation=False,
        )
        return SUCCESS_RESULT


class InsertAfterSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content after the end of the definition of a given symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        """
        Inserts the given body/content after the end of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.

        :param name_path: name path of the symbol after which to insert content (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted. The inserted code shall begin with the next line after
            the symbol.
        """
        self.symbol_manager.insert_after_symbol(name_path, relative_file_path=relative_path, body=body, use_same_indentation=False)
        return SUCCESS_RESULT


class InsertBeforeSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content before the beginning of the definition of a given symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        """
        Inserts the given body/content before the beginning of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.
        It also can be used to insert a new import statement before the first symbol in the file.

        :param name_path: name path of the symbol before which to insert content (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted before the line in which the referenced symbol is defined
        """
        self.symbol_manager.insert_before_symbol(name_path, relative_file_path=relative_path, body=body, use_same_indentation=False)
        return SUCCESS_RESULT


class EditedFileContext:
    """
    Context manager for file editing.

    Create the context, then use `set_updated_content` to set the new content, the original content
    being provided in `original_content`.
    When exiting the context without an exception, the updated content will be written back to the file.
    """

    def __init__(self, relative_path: str, agent: "SerenaAgent"):
        self._project = agent.get_active_project()
        assert self._project is not None
        self._abs_path = os.path.join(self._project.project_root, relative_path)
        if not os.path.isfile(self._abs_path):
            raise FileNotFoundError(f"File {self._abs_path} does not exist.")
        with open(self._abs_path, encoding=self._project.project_config.encoding) as f:
            self._original_content = f.read()
        self._updated_content: str | None = None

    def __enter__(self) -> Self:
        return self

    def get_original_content(self) -> str:
        """
        :return: the original content of the file before any modifications.
        """
        return self._original_content

    def set_updated_content(self, content: str) -> None:
        """
        Sets the updated content of the file, which will be written back to the file
        when the context is exited without an exception.

        :param content: the updated content of the file
        """
        self._updated_content = content

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        if self._updated_content is not None and exc_type is None:
            assert self._project is not None
            with open(self._abs_path, "w", encoding=self._project.project_config.encoding) as f:
                f.write(self._updated_content)
            log.info(f"Updated content written to {self._abs_path}")
            # Language servers should automatically detect the change and update its state accordingly.
            # If they do not, we may have to add a call to notify it.


class ReplaceRegexTool(Tool, ToolMarkerCanEdit):
    """
    Replaces content in a file by using regular expressions.
    """

    def apply(
        self,
        relative_path: str,
        regex: str,
        repl: str,
        allow_multiple_occurrences: bool = False,
    ) -> str:
        r"""
        Replaces one or more occurrences of the given regular expression.
        This is the preferred way to replace content in a file whenever the symbol-level
        tools are not appropriate.
        Even large sections of code can be replaced by providing a concise regular expression of
        the form "beginning.*?end-of-text-to-be-replaced".
        Always try to use wildcards to avoid specifying the exact content of the code to be replaced,
        especially if it spans several lines.

        IMPORTANT: REMEMBER TO USE WILDCARDS WHEN APPROPRIATE! I WILL BE VERY UNHAPPY IF YOU WRITE LONG REGEXES WITHOUT USING WILDCARDS INSTEAD!

        :param relative_path: the relative path to the file
        :param regex: a Python-style regular expression, matches of which will be replaced.
            Dot matches all characters, multi-line matching is enabled.
        :param repl: the string to replace the matched content with, which may contain
            backreferences like \1, \2, etc.
        :param allow_multiple_occurrences: if True, the regex may match multiple occurrences in the file
            and all of them will be replaced.
            If this is set to False and the regex matches multiple occurrences, an error will be returned
            (and you may retry with a revised, more specific regex).
        """
        self.agent.validate_relative_path(relative_path)
        with EditedFileContext(relative_path, self.agent) as context:
            original_content = context.get_original_content()
            updated_content, n = re.subn(regex, repl, original_content, flags=re.DOTALL | re.MULTILINE)
            if n == 0:
                return f"Error: No matches found for regex '{regex}' in file '{relative_path}'."
            if not allow_multiple_occurrences and n > 1:
                return (
                    f"Error: Regex '{regex}' matches {n} occurrences in file '{relative_path}'. "
                    "Please revise the regex to be more specific or enable allow_multiple_occurrences if this is expected."
                )
            context.set_updated_content(updated_content)
        return SUCCESS_RESULT


class DeleteLinesTool(Tool, ToolMarkerCanEdit):
    """
    Deletes a range of lines within a file.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Deletes the given lines in the file.
        Requires that the same range of lines was previously read using the `read_file` tool to verify correctness
        of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        """
        if not self.lines_read.were_lines_read(relative_path, (start_line, end_line)):
            read_lines_tool = self.agent.get_tool(ReadFileTool)
            return f"Error: Must call `{read_lines_tool.get_name_from_cls()}` first to read exactly the affected lines."
        self.symbol_manager.delete_lines(relative_path, start_line, end_line)
        return SUCCESS_RESULT


class ReplaceLinesTool(Tool, ToolMarkerCanEdit):
    """
    Replaces a range of lines within a file with new content.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int,
        end_line: int,
        content: str,
    ) -> str:
        """
        Replaces the given range of lines in the given file.
        Requires that the same range of lines was previously read using the `read_file` tool to verify correctness
        of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        :param content: the content to insert
        """
        if not content.endswith("\n"):
            content += "\n"
        result = self.agent.get_tool(DeleteLinesTool).apply(relative_path, start_line, end_line)
        if result != SUCCESS_RESULT:
            return result
        self.agent.get_tool(InsertAtLineTool).apply(relative_path, start_line, content)
        return SUCCESS_RESULT


class InsertAtLineTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content at a given line in a file.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        content: str,
    ) -> str:
        """
        Inserts the given content at the given line in the file, pushing existing content of the line down.
        In general, symbolic insert operations like insert_after_symbol or insert_before_symbol should be preferred if you know which
        symbol you are looking for.
        However, this can also be useful for small targeted edits of the body of a longer symbol (without replacing the entire body).

        :param relative_path: the relative path to the file
        :param line: the 0-based index of the line to insert content at
        :param content: the content to be inserted
        """
        if not content.endswith("\n"):
            content += "\n"
        self.symbol_manager.insert_at_line(relative_path, line, content)
        return SUCCESS_RESULT


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
        list_memories_tool = self.agent.get_tool(ListMemoriesTool)
        memories = json.loads(list_memories_tool.apply())
        if len(memories) == 0:
            return (
                "Onboarding not performed yet (no memories available). "
                + "You should perform onboarding by calling the `onboarding` tool before proceeding with the task."
            )
        else:
            return f"""The onboarding was already performed, below is the list of available memories.
            Do not read them immediately, just remember that they exist and that you can read them later, if it is necessary
            for the current task.
            Some memories may be based on previous conversations, others may be general for the current project.
            You should be able to tell which one you need based on the name of the memory.
            
            {memories}"""


class OnboardingTool(Tool):
    """
    Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
    """

    def apply(self) -> str:
        """
        Call this tool if onboarding was not performed yet.
        You will call this tool at most once per conversation.

        :return: instructions on how to create the onboarding information
        """
        system = platform.system()
        return self.prompt_factory.create_onboarding_prompt(system=system)


class WriteMemoryTool(Tool):
    """
    Writes a named memory (for future reference) to Serena's project-specific memory store.
    """

    def apply(self, memory_name: str, content: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Write some information about this project that can be useful for future tasks to a memory.
        Use markdown formatting for the content.
        The information should be short and to the point.
        The memory name should be meaningful, such that from the name you can infer what the information is about.
        It is better to have multiple small memories than to have a single large one because
        memories will be read one by one and we only ever want to read relevant memories.

        This tool is either called during the onboarding process or when you have identified
        something worth remembering about the project from the past conversation.
        
        **Token Efficiency Guidelines:**
        - Store high-level concepts, patterns, and relationships, not detailed code
        - Focus on insights that would be expensive to rediscover
        - Use references to files/symbols rather than including full implementations
        - Avoid storing temporary or easily discoverable information
        - Keep individual memories focused on single topics
        """
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_name} is too long. Max length is {max_answer_chars} characters. " + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_name, content)


class ReadMemoryTool(Tool):
    """
    Reads the memory with the given name from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Read the content of a memory file. This tool should only be used if the information
        is relevant to the current task. You can infer whether the information
        is relevant from the memory file name.
        You should not read the same memory file multiple times in the same conversation.
        """
        return self.memories_manager.load_memory(memory_file_name)


class ListMemoriesTool(Tool):
    """
    Lists memories in Serena's project-specific memory store.
    """

    def apply(self) -> str:
        """
        List available memories. Any memory can be read using the `read_memory` tool.
        """
        return json.dumps(self.memories_manager.list_memories())


class DeleteMemoryTool(Tool):
    """
    Deletes a memory from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str) -> str:
        """
        Delete a memory file. Should only happen if a user asks for it explicitly,
        for example by saying that the information retrieved from a memory file is no longer correct
        or no longer relevant for the project.
        """
        return self.memories_manager.delete_memory(memory_file_name)


class ThinkAboutCollectedInformationTool(Tool):
    """
    Thinking tool for pondering the completeness of collected information.
    """

    def apply(self) -> str:
        """
        Think about the collected information and whether it is sufficient and relevant.
        This tool should ALWAYS be called after you have completed a non-trivial sequence of searching steps like
        find_symbol, find_referencing_symbols, search_files_for_pattern, read_file, etc.
        """
        return self.prompt_factory.create_think_about_collected_information()


class ThinkAboutTaskAdherenceTool(Tool):
    """
    Thinking tool for determining whether the agent is still on track with the current task.
    """

    def apply(self) -> str:
        """
        Think about the task at hand and whether you are still on track.
        Especially important if the conversation has been going on for a while and there
        has been a lot of back and forth.

        This tool should ALWAYS be called before you insert, replace, or delete code.
        """
        return self.prompt_factory.create_think_about_task_adherence()


class ThinkAboutWhetherYouAreDoneTool(Tool):
    """
    Thinking tool for determining whether the task is truly completed.
    """

    def apply(self) -> str:
        """
        Whenever you feel that you are done with what the user has asked for, it is important to call this tool.
        """
        return self.prompt_factory.create_think_about_whether_you_are_done()


class SummarizeChangesTool(Tool):
    """
    Provides instructions for summarizing the changes made to the codebase.
    """

    def apply(self) -> str:
        """
        Summarize the changes you have made to the codebase.
        This tool should always be called after you have fully completed any non-trivial coding task,
        but only after the think_about_whether_you_are_done call.
        """
        return self.prompt_factory.create_summarize_changes()


class PrepareForNewConversationTool(Tool):
    """
    Provides instructions for preparing for a new conversation (in order to continue with the necessary context).
    """

    def apply(self) -> str:
        """
        Instructions for preparing for a new conversation. This tool should only be called on explicit user request.
        """
        return self.prompt_factory.create_prepare_for_new_conversation()


class SearchForPatternTool(Tool):
    """
    Performs a search for a pattern in the project.
    """

    def apply(
        self,
        substring_pattern: str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
        relative_path: str = "",
        restrict_search_to_code_files: bool = False,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Offers a flexible search for arbitrary patterns in the codebase, including the
        possibility to search in non-code files.
        Generally, symbolic operations like find_symbol or find_referencing_symbols
        should be preferred if you know which symbols you are looking for.

        Pattern Matching Logic:
            For each match, the returned result will contain the full lines where the
            substring pattern is found, as well as optionally some lines before and after it. The pattern will be compiled with
            DOTALL, meaning that the dot will match all characters including newlines.
            This also means that it never makes sense to have .* at the beginning or end of the pattern,
            but it may make sense to have it in the middle for complex patterns.
            If a pattern matches multiple lines, all those lines will be part of the match.
            Be careful to not use greedy quantifiers unnecessarily, it is usually better to use non-greedy quantifiers like .*? to avoid
            matching too much content.

        File Selection Logic:
            The files in which the search is performed can be restricted very flexibly.
            Using `restrict_search_to_code_files` is useful if you are only interested in code symbols (i.e., those
            symbols that can be manipulated with symbolic tools like find_symbol).
            You can also restrict the search to a specific file or directory,
            and provide glob patterns to include or exclude certain files on top of that.
            The globs are matched against relative file paths from the project root (not to the `relative_path` parameter that
            is used to further restrict the search).
            Smartly combining the various restrictions allows you to perform very targeted searches.


        :param substring_pattern: Regular expression for a substring pattern to search for
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: optional glob pattern specifying files to include in the search.
            Matches against relative file paths from the project root (e.g., "*.py", "src/**/*.ts").
            Only matches files, not directories.
        :param paths_exclude_glob: optional glob pattern specifying files to exclude from the search.
            Matches against relative file paths from the project root (e.g., "*test*", "**/*_generated.py").
            Takes precedence over paths_include_glob. Only matches files, not directories.
        :param relative_path: only subpaths of this path (relative to the repo root) will be analyzed. If a path to a single
            file is passed, only that will be searched. The path must exist, otherwise a `FileNotFoundError` is raised.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :param restrict_search_to_code_files: whether to restrict the search to only those files where
            analyzed code symbols can be found. Otherwise, will search all non-ignored files.
            Set this to True if your search is only meant to discover code that can be manipulated with symbolic tools.
            For example, for finding classes or methods from a name pattern.
            Setting to False is a better choice if you also want to search in non-code files, like in html or yaml files,
            which is why it is the default.
        :return: A JSON object mapping file paths to lists of matched consecutive lines (with context, if requested).
        """
        abs_path = os.path.join(self.get_project_root(), relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Relative path {relative_path} does not exist.")

        if restrict_search_to_code_files:
            matches = self.language_server.search_files_for_pattern(
                pattern=substring_pattern,
                relative_path=relative_path,
                context_lines_before=context_lines_before,
                context_lines_after=context_lines_after,
                paths_include_glob=paths_include_glob,
                paths_exclude_glob=paths_exclude_glob,
            )
        else:
            if os.path.isfile(abs_path):
                rel_paths_to_search = [relative_path]
            else:
                dirs, rel_paths_to_search = scan_directory(
                    path=abs_path,
                    recursive=True,
                    is_ignored_dir=self.agent.path_is_gitignored,
                    is_ignored_file=self.agent.path_is_gitignored,
                    relative_to=self.get_project_root(),
                )
            # TODO (maybe): not super efficient to walk through the files again and filter if glob patterns are provided
            #   but it probably never matters and this version required no further refactoring
            matches = search_files(
                rel_paths_to_search,
                substring_pattern,
                root_path=self.get_project_root(),
                paths_include_glob=paths_include_glob,
                paths_exclude_glob=paths_exclude_glob,
            )
        # group matches by file
        file_to_matches: dict[str, list[str]] = defaultdict(list)
        for match in matches:
            assert match.source_file_path is not None
            file_to_matches[match.source_file_path].append(match.to_display_string())
        result = json.dumps(file_to_matches)
        return self._limit_length(result, max_answer_chars)


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit):
    """
    Executes a shell command.
    """

    def apply(
        self,
        command: str,
        cwd: str | None = None,
        capture_stderr: bool = True,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Execute a shell command and return its output.

        IMPORTANT: you should always consider the memory about suggested shell commands before using this tool.
        If this memory was not loaded in the current conversation, you should load it using the `read_memory` tool
        before using this tool.

        You should have at least once looked at the suggested shell commands from the corresponding memory
        created during the onboarding process before using this tool.
        Never execute unsafe shell commands like `rm -rf /` or similar! Generally be very careful with deletions.

        :param command: the shell command to execute
        :param cwd: the working directory to execute the command in. If None, the project root will be used.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        _cwd = cwd or self.get_project_root()
        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        return self._limit_length(result, max_answer_chars)


class MovePathsTool(Tool, ToolMarkerCanEdit):
    """
    Moves one or more files or directories to a new location within the project.
    """

    def apply(
        self,
        source_paths: list[str],
        destination_path: str,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> str:
        """
        Moves one or more files or directories to a new location within the project.
        The operation is performed in two phases: first, all validations are run. If all validations pass,
        the files are moved. If any validation fails, no files are moved.
        Note: If the operation fails during the execution phase, the project may be left in a partially modified state.

        :param source_paths: A list of relative paths to the files or directories to be moved.
        :param destination_path: The relative path to the destination directory.
        :param overwrite: If False, the operation will fail if a file with the same name already exists
                          at the destination. If True, existing files will be overwritten. Defaults to False.
        :param dry_run: If True, performs all validations but does not move any files.
                        Returns a report of what would have happened. Defaults to False.
        :return: A JSON string reporting the overall status and the result of each planned move.
        """
        # --- Phase 1: Validation (Fail-Fast) ---
        project_root = Path(self.get_project_root())
        abs_destination_path = project_root / destination_path

        try:
            # Empty input validation
            if not source_paths:
                raise ValueError("No source paths provided.")

            # Validate destination path itself
            self.agent.validate_relative_path(destination_path)
            if abs_destination_path.exists() and not abs_destination_path.is_dir():
                raise ValueError(f"Destination '{destination_path}' exists but is not a directory.")

            # Validate all source paths and check for collisions
            for source_path in source_paths:
                self.agent.validate_relative_path(source_path)
                abs_source_path = project_root / source_path

                if not abs_source_path.exists():
                    raise FileNotFoundError(f"Source path '{source_path}' does not exist.")

                # Self-move detection
                if abs_source_path.resolve() == abs_destination_path.resolve():
                    raise ValueError(f"Source and destination path ('{source_path}') are the same.")

                if abs_destination_path.resolve().is_relative_to(abs_source_path.resolve()):
                    raise ValueError(f"Cannot move a directory ('{source_path}') into itself or a subdirectory.")

                # Name collision check
                destination_file_path = abs_destination_path / abs_source_path.name
                if destination_file_path.exists() and not overwrite:
                    raise FileExistsError(
                        f"File '{abs_source_path.name}' already exists in destination '{destination_path}'. Use overwrite=True to replace it."
                    )

        except Exception as e:
            return json.dumps({"status": "validation_failed", "error": str(e)})

        # --- Dry Run Check ---
        if dry_run:
            return json.dumps(
                {
                    "status": "dry_run_success",
                    "message": "All validations passed. No files were moved.",
                }
            )

        # --- Phase 2: Execution (Continue-on-Error) ---
        execution_results = []
        try:
            abs_destination_path.mkdir(parents=True, exist_ok=True)

            for source_path in source_paths:
                abs_source_path = project_root / source_path
                try:
                    # This is the actual move operation
                    shutil.move(str(abs_source_path), str(abs_destination_path))

                    self.agent.mark_file_modified(source_path)
                    new_relative_path = (abs_destination_path / abs_source_path.name).relative_to(project_root)
                    self.agent.mark_file_modified(str(new_relative_path))

                    execution_results.append({"path": source_path, "status": "success"})
                except Exception as move_error:
                    execution_results.append({"path": source_path, "status": "error", "reason": str(move_error)})

        except Exception as e:
            return json.dumps(
                {
                    "status": "execution_failed",
                    "error": f"A critical error occurred during the move process: {e}",
                    "results": execution_results,
                }
            )

        return json.dumps({"status": "execution_success", "results": execution_results})


class GetCurrentConfigTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
    """

    def apply(self) -> str:
        """
        Print the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
        """
        return self.agent.get_current_config_overview()


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


class ConfigureProjectIgnoresTool(Tool, ToolMarkerCanEdit):
    """
    Configures project ignore patterns for better code analysis and project management.
    Supports interactive mode for guided configuration, direct mode for batch updates,
    and suggest mode for technology-aware recommendations.
    """

    def apply(
        self,
        mode: str = "interactive",
        patterns: list[str] | None = None,
        enable_gitignore: bool | None = None,
        preview_only: bool = False,
    ) -> str:
        """
        Configure project ignore patterns to improve code analysis and project management.
        
        Supports three modes:
        - 'interactive': Step-by-step guidance with validation and pattern preview
        - 'direct': Apply a list of patterns instantly
        - 'suggest': Auto-detect project technologies and apply recommended patterns
        
        :param mode: Operation mode ('interactive', 'direct', or 'suggest')
        :param patterns: List of ignore patterns (required for 'direct' mode)
        :param enable_gitignore: Whether to enable gitignore integration (optional override)
        :param preview_only: If True, shows what would be ignored without making changes
        :return: Status message with configuration results
        """
        try:
            project = self.agent.get_active_project()
            if project is None:
                return "❌ No active project. Please activate a project first."
            
            project_root = Path(project.project_root)
            
            if mode == "interactive":
                return self._handle_interactive_mode(project, project_root, enable_gitignore, preview_only)
            elif mode == "direct":
                if patterns is None:
                    return "❌ Direct mode requires 'patterns' parameter with a list of ignore patterns."
                return self._handle_direct_mode(project, project_root, patterns, enable_gitignore, preview_only)
            elif mode == "suggest":
                return self._handle_suggest_mode(project, project_root, enable_gitignore, preview_only)
            else:
                return f"❌ Invalid mode '{mode}'. Supported modes: 'interactive', 'direct', 'suggest'"
                
        except Exception as e:
            return f"❌ Error configuring project ignores: {str(e)}"

    def _handle_interactive_mode(
        self, project: "Project", project_root: Path, enable_gitignore: bool | None, preview_only: bool
    ) -> str:
        """Handle interactive mode with step-by-step guidance."""
        result = []
        result.append("🔧 **Interactive Project Ignore Configuration**")
        result.append("")
        
        # Show current configuration
        current_config = self._get_current_config(project)
        result.append("**Current Configuration:**")
        result.append(f"• GitIgnore integration: {'✅ Enabled' if current_config['gitignore_enabled'] else '❌ Disabled'}")
        result.append(f"• Custom ignore patterns: {len(current_config['patterns'])} patterns")
        if current_config['patterns']:
            for pattern in current_config['patterns']:
                result.append(f"  - {pattern}")
        result.append("")
        
        # Detect technologies
        detected_tech = self._detect_technologies(project_root)
        if detected_tech:
            result.append("**Detected Technologies:**")
            for tech in detected_tech:
                result.append(f"• {tech}")
            result.append("")
        
        # Show recommendations
        recommendations = self._get_recommendations(detected_tech)
        if recommendations:
            result.append("**Recommended Ignore Patterns:**")
            for pattern in recommendations:
                validation = self._validate_pattern(pattern, project_root)
                status = "✅" if validation['is_safe'] else "⚠️"
                result.append(f"{status} {pattern}")
                if validation['warning']:
                    result.append(f"    Warning: {validation['warning']}")
            result.append("")
        
        # Interactive prompts (placeholder for conversational I/O)
        result.append("**Next Steps:**")
        result.append("1. To apply recommended patterns, use: `configure_project_ignores(mode='suggest')`")
        result.append("2. To add custom patterns, use: `configure_project_ignores(mode='direct', patterns=['your/pattern'])`")
        result.append("3. To enable GitIgnore integration, use: `configure_project_ignores(mode='direct', enable_gitignore=True)`")
        
        return "\n".join(result)

    def _handle_direct_mode(
        self, project: "Project", project_root: Path, patterns: list[str], enable_gitignore: bool | None, preview_only: bool
    ) -> str:
        """Handle direct mode with immediate pattern application."""
        result = []
        result.append("🔧 **Direct Project Ignore Configuration**")
        result.append("")
        
        # Validate patterns
        validation_results = []
        for pattern in patterns:
            validation = self._validate_pattern(pattern, project_root)
            validation_results.append((pattern, validation))
        
        # Show validation results
        result.append("**Pattern Validation:**")
        for pattern, validation in validation_results:
            status = "✅" if validation['is_safe'] else "⚠️"
            result.append(f"{status} {pattern}")
            if validation['warning']:
                result.append(f"    Warning: {validation['warning']}")
        result.append("")
        
        # Check if any patterns are unsafe
        unsafe_patterns = [p for p, v in validation_results if not v['is_safe']]
        if unsafe_patterns and not preview_only:
            result.append("❌ **Cannot apply configuration due to unsafe patterns:**")
            for pattern in unsafe_patterns:
                result.append(f"• {pattern}")
            result.append("")
            result.append("Please review and fix the patterns above, or use `preview_only=True` to see what would be ignored.")
            return "\n".join(result)
        
        # Preview affected files if requested
        if preview_only or len(patterns) > 0:
            preview_results = self._preview_ignore_patterns(patterns, project_root)
            result.append("**Preview of files that would be ignored:**")
            if preview_results:
                for pattern, files in preview_results.items():
                    result.append(f"• Pattern '{pattern}': {len(files)} files")
                    for file in files[:5]:  # Show first 5 files
                        result.append(f"  - {file}")
                    if len(files) > 5:
                        result.append(f"  ... and {len(files) - 5} more files")
            else:
                result.append("• No files would be ignored by the specified patterns")
            result.append("")
        
        # Apply changes if not preview only
        if not preview_only:
            success = self._apply_configuration(project, patterns, enable_gitignore)
            if success:
                result.append("✅ **Configuration applied successfully!**")
                result.append("")
                result.append("**Changes made:**")
                if patterns:
                    result.append(f"• Added {len(patterns)} ignore patterns")
                if enable_gitignore is not None:
                    status = "enabled" if enable_gitignore else "disabled"
                    result.append(f"• GitIgnore integration {status}")
                result.append("")
                result.append("💡 **Tip:** Restart your language server to apply the changes immediately.")
            else:
                result.append("❌ **Failed to apply configuration.** Please check the logs for details.")
        
        return "\n".join(result)

    def _handle_suggest_mode(
        self, project: "Project", project_root: Path, enable_gitignore: bool | None, preview_only: bool
    ) -> str:
        """Handle suggest mode with technology-aware recommendations."""
        result = []
        result.append("🔧 **Technology-Aware Project Ignore Configuration**")
        result.append("")
        
        # Detect technologies
        detected_tech = self._detect_technologies(project_root)
        result.append("**Detected Technologies:**")
        if detected_tech:
            for tech in detected_tech:
                result.append(f"• {tech}")
        else:
            result.append("• No specific technologies detected")
        result.append("")
        
        # Get recommendations
        recommendations = self._get_recommendations(detected_tech)
        if not recommendations:
            result.append("**No specific recommendations available.**")
            result.append("The project appears to be a generic project without specific technology patterns.")
            return "\n".join(result)
        
        result.append("**Recommended Ignore Patterns:**")
        for pattern in recommendations:
            validation = self._validate_pattern(pattern, project_root)
            status = "✅" if validation['is_safe'] else "⚠️"
            result.append(f"{status} {pattern}")
            if validation['warning']:
                result.append(f"    Warning: {validation['warning']}")
        result.append("")
        
        # Preview what would be ignored
        if recommendations:
            preview_results = self._preview_ignore_patterns(recommendations, project_root)
            result.append("**Preview of files that would be ignored:**")
            if preview_results:
                total_files = sum(len(files) for files in preview_results.values())
                result.append(f"• Total files to ignore: {total_files}")
                for pattern, files in preview_results.items():
                    if files:
                        result.append(f"• Pattern '{pattern}': {len(files)} files")
                        for file in files[:3]:  # Show first 3 files
                            result.append(f"  - {file}")
                        if len(files) > 3:
                            result.append(f"  ... and {len(files) - 3} more files")
            else:
                result.append("• No files would be ignored by the recommended patterns")
            result.append("")
        
        # Apply changes if not preview only
        if not preview_only:
            success = self._apply_configuration(project, recommendations, enable_gitignore)
            if success:
                result.append("✅ **Technology-aware configuration applied successfully!**")
                result.append("")
                result.append("**Changes made:**")
                result.append(f"• Added {len(recommendations)} recommended ignore patterns")
                if enable_gitignore is not None:
                    status = "enabled" if enable_gitignore else "disabled"
                    result.append(f"• GitIgnore integration {status}")
                result.append("")
                result.append("💡 **Tip:** Restart your language server to apply the changes immediately.")
            else:
                result.append("❌ **Failed to apply configuration.** Please check the logs for details.")
        
        return "\n".join(result)

    def _get_current_config(self, project: "Project") -> dict[str, Any]:
        """Get current project ignore configuration."""
        return {
            'gitignore_enabled': project.project_config.ignore_all_files_in_gitignore,
            'patterns': project.project_config.ignored_paths,
        }

    def _detect_technologies(self, project_root: Path) -> list[str]:
        """Detect project technologies based on files and directories."""
        technologies = []
        
        # Check for common files and directories
        checks = [
            ('Python', lambda: any(project_root.glob('*.py')) or (project_root / 'requirements.txt').exists() or (project_root / 'pyproject.toml').exists()),
            ('Node.js', lambda: (project_root / 'package.json').exists() or (project_root / 'node_modules').exists()),
            ('TypeScript', lambda: any(project_root.glob('*.ts')) or (project_root / 'tsconfig.json').exists()),
            ('Java', lambda: any(project_root.glob('*.java')) or (project_root / 'pom.xml').exists() or any(project_root.glob('*.gradle'))),
            ('C#', lambda: any(project_root.glob('*.cs')) or any(project_root.glob('*.sln')) or any(project_root.glob('*.csproj'))),
            ('Rust', lambda: (project_root / 'Cargo.toml').exists() or any(project_root.glob('*.rs'))),
            ('Go', lambda: (project_root / 'go.mod').exists() or any(project_root.glob('*.go'))),
            ('C++', lambda: any(project_root.glob('*.cpp')) or any(project_root.glob('*.hpp')) or any(project_root.glob('*.cc'))),
            ('Ruby', lambda: any(project_root.glob('*.rb')) or (project_root / 'Gemfile').exists()),
            ('Docker', lambda: (project_root / 'Dockerfile').exists() or (project_root / 'docker-compose.yml').exists()),
            ('VS Code', lambda: (project_root / '.vscode').exists()),
            ('Git', lambda: (project_root / '.git').exists()),
        ]
        
        for tech_name, check_func in checks:
            try:
                if check_func():
                    technologies.append(tech_name)
            except Exception:
                # Ignore errors during detection
                pass
        
        return technologies

    def _get_recommendations(self, technologies: list[str]) -> list[str]:
        """Get recommended ignore patterns based on detected technologies."""
        recommendations = []
        
        # Technology-specific patterns
        tech_patterns = {
            'Python': [
                '__pycache__/**',
                '*.pyc',
                '*.pyo',
                '*.pyd',
                '.Python',
                'env/**',
                'venv/**',
                '.venv/**',
                'ENV/**',
                'env.bak/**',
                'venv.bak/**',
                '.pytest_cache/**',
                '.coverage',
                'htmlcov/**',
                'dist/**',
                'build/**',
                '*.egg-info/**',
                '.tox/**',
                '.mypy_cache/**',
            ],
            'Node.js': [
                'node_modules/**',
                'npm-debug.log*',
                'yarn-debug.log*',
                'yarn-error.log*',
                '.npm/**',
                '.yarn/**',
                'coverage/**',
                '.nyc_output/**',
                'dist/**',
                'build/**',
            ],
            'TypeScript': [
                '*.tsbuildinfo',
                'dist/**',
                'build/**',
                '.tscache/**',
            ],
            'Java': [
                'target/**',
                '*.class',
                '*.jar',
                '*.war',
                '*.ear',
                'hs_err_pid*',
                '.gradle/**',
                'build/**',
                'gradle-app.setting',
                '.gradletasknamecache',
            ],
            'C#': [
                'bin/**',
                'obj/**',
                '*.user',
                '*.userosscache',
                '*.sln.docstates',
                '.vs/**',
                'packages/**',
                'TestResults/**',
            ],
            'Rust': [
                'target/**',
                'Cargo.lock',
                '*.rs.bk',
                '*.pdb',
            ],
            'Go': [
                'vendor/**',
                '*.exe',
                '*.exe~',
                '*.dll',
                '*.so',
                '*.dylib',
                '*.test',
                '*.out',
                'go.work',
                'go.work.sum',
            ],
            'C++': [
                '*.o',
                '*.obj',
                '*.exe',
                '*.out',
                '*.app',
                '*.i*86',
                '*.x86_64',
                '*.hex',
                'CMakeFiles/**',
                'CMakeCache.txt',
                'cmake_install.cmake',
                'Makefile',
                'build/**',
            ],
            'Ruby': [
                '*.gem',
                '*.rbc',
                '/.config',
                '/coverage/',
                '/InstalledFiles',
                '/pkg/',
                '/spec/reports/',
                '/spec/examples.txt',
                '/test/tmp/',
                '/test/version_tmp/',
                '/tmp/',
                '.bundle/**',
                'vendor/bundle/**',
                'log/**',
            ],
            'Docker': [
                '.dockerignore',
                'docker-compose.override.yml',
            ],
            'VS Code': [
                '.vscode/settings.json',
                '.vscode/launch.json',
                '.vscode/extensions.json',
                '.vscode/c_cpp_properties.json',
            ],
        }
        
        # Add patterns for detected technologies
        for tech in technologies:
            if tech in tech_patterns:
                recommendations.extend(tech_patterns[tech])
        
        # Add common patterns
        common_patterns = [
            '.DS_Store',
            'Thumbs.db',
            '*.tmp',
            '*.temp',
            '*.log',
            '.env',
            '.env.local',
            '.env.*.local',
            '*.orig',
            '*.swp',
            '*.swo',
            '*~',
        ]
        
        # Only add common patterns if we have some technology detected
        if technologies:
            recommendations.extend(common_patterns)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for pattern in recommendations:
            if pattern not in seen:
                seen.add(pattern)
                unique_recommendations.append(pattern)
        
        return unique_recommendations

    def _validate_pattern(self, pattern: str, project_root: Path) -> dict[str, Any]:
        """Validate an ignore pattern for safety and correctness."""
        validation = {
            'is_safe': True,
            'warning': None,
        }
        
        # Check for dangerous patterns
        dangerous_patterns = [
            ('**', "Very broad pattern that might ignore too many files"),
            ('*', "Very broad pattern that might ignore too many files"),
            ('/', "Root path pattern might ignore important files"),
            ('..', "Parent directory references can be dangerous"),
            ('src/**', "Ignoring source directory might hide important code"),
            ('lib/**', "Ignoring library directory might hide important code"),
        ]
        
        for dangerous, warning in dangerous_patterns:
            if pattern.strip() == dangerous:
                validation['is_safe'] = False
                validation['warning'] = warning
                break
        
        # Check for common mistakes
        if pattern.startswith('/'):
            validation['warning'] = "Leading slash is not needed in gitignore patterns"
        elif pattern.endswith('/') and not pattern.endswith('/**'):
            validation['warning'] = "Consider using '/**' for directory patterns"
        
        return validation

    def _preview_ignore_patterns(self, patterns: list[str], project_root: Path) -> dict[str, list[str]]:
        """Preview which files would be ignored by the given patterns."""
        preview = {}
        
        try:
            # Get all files in the project
            all_files = []
            for root, dirs, files in os.walk(project_root):
                for file in files:
                    file_path = Path(root) / file
                    relative_path = file_path.relative_to(project_root)
                    all_files.append(str(relative_path))
            
            # Check each pattern
            for pattern in patterns:
                matching_files = []
                for file_path in all_files:
                    if self._matches_pattern(file_path, pattern):
                        matching_files.append(file_path)
                preview[pattern] = matching_files[:10]  # Limit to first 10 files
        
        except Exception:
            # If preview fails, return empty dict
            preview = {}
        
        return preview

    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if a file path matches an ignore pattern."""
        # Simple glob-like matching
        # This is a simplified version - real gitignore matching is more complex
        try:
            return fnmatch(file_path, pattern) or fnmatch(file_path, pattern.rstrip('*'))
        except Exception:
            return False

    def _apply_configuration(self, project: "Project", patterns: list[str], enable_gitignore: bool | None) -> bool:
        """Apply the configuration changes to the project."""
        try:
            # Update project configuration
            if patterns:
                # Add new patterns to existing ones, avoiding duplicates
                existing_patterns = set(project.project_config.ignored_paths)
                new_patterns = [p for p in patterns if p not in existing_patterns]
                if new_patterns:
                    project.project_config.ignored_paths.extend(new_patterns)
            
            if enable_gitignore is not None:
                project.project_config.ignore_all_files_in_gitignore = enable_gitignore
            
            # Save the configuration
            project.project_config.save(project.project_root)
            
            return True
        except Exception as e:
            log.error(f"Failed to apply project ignore configuration: {e}")
            return False


def _iter_tool_classes(same_module_only: bool = True) -> Generator[type[Tool], None, None]:
    """
    Iterate over Tool subclasses.

    :param same_module_only: Whether to only iterate over tools defined in the same module as the Tool class
        or over all subclasses of Tool.
    """
    for tool_class in iter_subclasses(Tool):
        if same_module_only and tool_class.__module__ != Tool.__module__:
            continue
        yield tool_class


_TOOL_REGISTRY_DICT: dict[str, type[Tool]] = {tool_class.get_name_from_cls(): tool_class for tool_class in _iter_tool_classes()}
"""maps tool name to the corresponding tool class"""


class ToolRegistry:
    @staticmethod
    def get_tool_class_by_name(tool_name: str) -> type[Tool]:
        try:
            return _TOOL_REGISTRY_DICT[tool_name]
        except KeyError as e:
            available_tools = "\n".join(ToolRegistry.get_tool_names())
            raise ValueError(f"Tool with name {tool_name} not found. Available tools:\n{available_tools}") from e

    @staticmethod
    def get_all_tool_classes() -> list[type[Tool]]:
        return list(_TOOL_REGISTRY_DICT.values())

    @staticmethod
    def get_tool_names() -> list[str]:
        return list(_TOOL_REGISTRY_DICT.keys())

    @staticmethod
    def tool_dict() -> dict[str, type[Tool]]:
        """Maps tool name to the corresponding tool class"""
        return copy(_TOOL_REGISTRY_DICT)

    @staticmethod
    def print_tool_overview(tools: Iterable[type[Tool] | Tool] | None = None) -> None:
        """
        Print a summary of the tools. If no tools are passed, a summary of all tools is printed.
        """
        if tools is None:
            tools = _TOOL_REGISTRY_DICT.values()

        tool_dict: dict[str, type[Tool] | Tool] = {}
        for tool_class in tools:
            tool_dict[tool_class.get_name_from_cls()] = tool_class
        for tool_name in sorted(tool_dict.keys()):
            tool_class = tool_dict[tool_name]
            print(f" * `{tool_name}`: {tool_class.get_tool_description().strip()}")
