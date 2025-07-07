
import os
import shutil
import pytest
from pathlib import Path
from serena.tools import MovePathsTool

@pytest.fixture
def tool():
    return MovePathsTool()

@pytest.fixture
def test_dir(tmp_path):
    """Creates a test directory structure:
    test_dir/
    ├── dir1/
    │   ├── file1.txt
    │   └── subdir1/
    │       └── subfile1.txt
    ├── dir2/
    ├── file2.txt
    └── file3.txt
    """
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    (dir1 / "file1.txt").write_text("file1 content")
    subdir1 = dir1 / "subdir1"
    subdir1.mkdir()
    (subdir1 / "subfile1.txt").write_text("subfile1 content")

    dir2 = tmp_path / "dir2"
    dir2.mkdir()

    (tmp_path / "file2.txt").write_text("file2 content")
    (tmp_path / "file3.txt").write_text("file3 content")
    
    return tmp_path

def test_move_single_file_dry_run(tool, test_dir):
    src = str(test_dir / "file2.txt")
    dest = str(test_dir / "dir1" / "file2_moved.txt")
    
    result = tool.run(sources=[src], destination=dest, dry_run=True)
    
    assert result["success"]
    assert "planned_moves" in result
    assert len(result["planned_moves"]) == 1
    assert result["planned_moves"][0]["source"] == src
    assert result["planned_moves"][0]["destination"] == dest
    assert os.path.exists(src)
    assert not os.path.exists(dest)

def test_move_single_file_execute(tool, test_dir):
    src = str(test_dir / "file2.txt")
    dest = str(test_dir / "dir1" / "file2_moved.txt")
    
    result = tool.run(sources=[src], destination=dest)
    
    assert result["success"]
    assert "moves" in result
    assert len(result["moves"]) == 1
    assert result["moves"][0]["source"] == src
    assert result["moves"][0]["destination"] == dest
    assert not os.path.exists(src)
    assert os.path.exists(dest)
    assert (test_dir / "dir1" / "file2_moved.txt").read_text() == "file2 content"

def test_move_directory_to_directory(tool, test_dir):
    src = str(test_dir / "dir1")
    dest = str(test_dir / "dir2")

    result = tool.run(sources=[src], destination=dest)
    
    assert result["success"]
    assert not os.path.exists(src)
    assert os.path.exists(os.path.join(dest, "dir1"))
    assert os.path.exists(os.path.join(dest, "dir1", "file1.txt"))

def test_move_multiple_files_to_directory(tool, test_dir):
    sources = [str(test_dir / "file2.txt"), str(test_dir / "file3.txt")]
    dest = str(test_dir / "dir1")

    result = tool.run(sources=sources, destination=dest)

    assert result["success"]
    assert not os.path.exists(sources[0])
    assert not os.path.exists(sources[1])
    assert os.path.exists(os.path.join(dest, "file2.txt"))
    assert os.path.exists(os.path.join(dest, "file3.txt"))

def test_error_source_not_found(tool, test_dir):
    src = str(test_dir / "non_existent_file.txt")
    dest = str(test_dir / "dir1")

    result = tool.run(sources=[src], destination=dest)

    assert not result["success"]
    assert "errors" in result
    assert len(result["errors"]) == 1
    assert "not found" in result["errors"][0]["message"]

def test_error_destination_is_file(tool, test_dir):
    sources = [str(test_dir / "file2.txt"), str(test_dir / "file3.txt")]
    dest = str(test_dir / "dir1" / "file1.txt")

    result = tool.run(sources=sources, destination=dest)

    assert not result["success"]
    assert "errors" in result
    assert "is a file" in result["errors"][0]["message"]

def test_error_overwrite_disallowed(tool, test_dir):
    src = str(test_dir / "file2.txt")
    dest = str(test_dir / "dir1" / "file1.txt")

    result = tool.run(sources=[src], destination=dest, overwrite=False)

    assert not result["success"]
    assert "errors" in result
    assert "already exists" in result["errors"][0]["message"]

def test_overwrite_allowed(tool, test_dir):
    src = str(test_dir / "file2.txt")
    dest = str(test_dir / "dir1" / "file1.txt")

    result = tool.run(sources=[src], destination=dest, overwrite=True)

    assert result["success"]
    assert not os.path.exists(src)
    assert (test_dir / "dir1" / "file1.txt").read_text() == "file2 content"

def test_error_move_into_itself(tool, test_dir):
    src = str(test_dir / "dir1")
    dest = str(test_dir / "dir1" / "subdir1")

    result = tool.run(sources=[src], destination=dest)

    assert not result["success"]
    assert "errors" in result
    assert "Cannot move a directory into itself" in result["errors"][0]["message"]

def test_collision_detection(tool, test_dir):
    sources = [str(test_dir / "file2.txt"), str(test_dir / "dir1" / "file1.txt")]
    # Intentionally create a name collision
    shutil.copy(str(test_dir / "file2.txt"), str(test_dir / "file_to_move.txt"))
    shutil.copy(str(test_dir / "dir1" / "file1.txt"), str(test_dir / "file_to_move.txt"))
    
    sources = [str(test_dir / "file_to_move.txt"), str(test_dir / "dir1" / "file1.txt")]
    dest = str(test_dir / "dir2")

    # This should fail because both files would be named "file_to_move.txt" in dir2
    # Let's adjust the test to reflect the tool's logic.
    # The tool renames if the destination is a file, but moves into if it's a directory.
    # A better collision test is moving two files with the same name into the same directory.
    (test_dir / "another_dir").mkdir()
    (test_dir / "another_dir" / "file.txt").write_text("content")
    
    sources = [str(test_dir / "dir1" / "file1.txt"), str(test_dir / "another_dir" / "file.txt")]
    # rename file1.txt to file.txt to create collision
    os.rename(str(test_dir / "dir1" / "file1.txt"), str(test_dir / "dir1" / "file.txt"))

    sources = [str(test_dir / "dir1" / "file.txt"), str(test_dir / "another_dir" / "file.txt")]
    dest = str(test_dir / "dir2")
    
    result = tool.run(sources=sources, destination=dest, dry_run=True)
    
    assert not result["success"]
    assert "errors" in result
    assert "Collision detected" in result["errors"][0]["message"]

def test_continue_on_error(tool, test_dir):
    sources = [
        str(test_dir / "file2.txt"),
        str(test_dir / "non_existent.txt"),
        str(test_dir / "file3.txt")
    ]
    dest = str(test_dir / "dir1")

    result = tool.run(sources=sources, destination=dest, continue_on_error=True)

    assert not result["success"]
    assert "moves" in result
    assert len(result["moves"]) == 2
    assert "errors" in result
    assert len(result["errors"]) == 1
    assert "not found" in result["errors"][0]["message"]
    assert os.path.exists(os.path.join(dest, "file2.txt"))
    assert not os.path.exists(os.path.join(dest, "non_existent.txt"))
    assert os.path.exists(os.path.join(dest, "file3.txt"))
