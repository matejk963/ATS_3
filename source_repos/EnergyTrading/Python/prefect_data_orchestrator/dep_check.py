import os
import ast
import sys
from pprint import pprint
from pkg_resources import working_set  # To get installed packages

# Fallback list of standard library modules for Python < 3.10
FALLBACK_STDLIB_MODULES = {
    "abc", "argparse", "array", "asyncio", "base64", "binascii", "calendar",
    "cmath", "collections", "contextlib", "copy", "csv", "datetime", "decimal",
    "enum", "functools", "glob", "hashlib", "heapq", "http", "io", "itertools",
    "json", "logging", "math", "os", "pathlib", "pickle", "random", "re",
    "shutil", "socket", "sqlite3", "statistics", "string", "struct",
    "subprocess", "sys", "tempfile", "time", "typing", "unittest",
    "urllib", "uuid", "warnings", "xml"
}

def get_standard_library_modules():
    """
    Get the list of standard library modules.
    """
    if hasattr(sys, 'stdlib_module_names'):
        return sys.stdlib_module_names  # Available in Python 3.10+
    return FALLBACK_STDLIB_MODULES

def get_installed_packages():
    """
    Get a set of all installed packages in the current environment.
    
    Returns:
        set: A set of installed package names.
    """
    return {pkg.key for pkg in working_set}

def get_installed_packages_with_dependencies():
    """Get a dictionary of installed packages and their dependencies."""
    installed_packages = {}
    for dist in working_set:
        installed_packages[dist.key] = {req.key for req in dist.requires()}
    return installed_packages

def get_top_level_package(module_name):
    """Extract the top-level package from a module name."""
    return module_name.split('.')[0]


def should_exclude_path(path, exclude_dirs):
    """
    Check if a path should be excluded based on the exclude_dirs list.
    """
    for exclude_dir in exclude_dirs:
        if exclude_dir in path.split(os.sep):  # Check if any part of the path matches an excluded directory
            return True
    return False


def resolve_relative_import(current_file, module_name, level):
    """
    Resolve a relative import to an absolute path.
    
    Args:
        current_file (str): The file where the import is located.
        module_name (str): The name of the module being imported.
        level (int): The number of dots in the relative import (e.g., 1 for '.', 2 for '..').
    
    Returns:
        str: The resolved absolute path of the imported module.
    """
    # Start from the directory of the current file
    base_dir = os.path.dirname(current_file)

    # Go up 'level' directories
    for _ in range(level):
        base_dir = os.path.dirname(base_dir)

    # Append the module name to get its full path
    return os.path.join(base_dir, *module_name.split('.'))


def is_local_file_or_directory(importing_file, module_name, level):
    """
    Check if an imported module corresponds to a local file or directory.

    Args:
        importing_file (str): The file where the import is located.
        module_name (str): The name of the module being imported.
        level (int): The number of dots in the relative import.

    Returns:
        bool: True if the module corresponds to a local file or directory, False otherwise.
    """
    # Start from the directory of the importing file
    base_dir = os.path.dirname(importing_file)

    # Go up 'level' directories for relative imports
    for _ in range(level):
        base_dir = os.path.dirname(base_dir)

    # Check if it's a .py file or a directory with or without __init__.py
    possible_paths = [
        os.path.join(base_dir, f"{module_name}.py"),
        os.path.join(base_dir, module_name),
        os.path.join(base_dir, module_name, "__init__.py"),
    ]
    return any(os.path.exists(path) for path in possible_paths)


def get_top_level_package(module_name):
    """
    Extract the top-level package from a module name.

    Args:
        module_name (str): The full module name (e.g., 'sklearn.utils').

    Returns:
        str: The top-level package name (e.g., 'sklearn').
    """
    return module_name.split('.')[0]


def get_imported_modules_with_files(project_root, exclude_dirs=None):
    """
    Extract all imported modules and their specific imports from Python files in the project,
    along with their file locations.
    
    Args:
        project_root (str): Root directory of your project.
        exclude_dirs (list): Directories to exclude from traversal.

    Returns:
        dict: A dictionary mapping imported modules to their locations.
    """
    if exclude_dirs is None:
        exclude_dirs = ['env', 'venv', '.venv', '__pycache__', 'Production']  # Default directories to exclude

    imported_modules = {}
    
    for root, dirs, files in os.walk(project_root):
        # Skip any directories that should be excluded
        if should_exclude_path(root, exclude_dirs):
            continue

        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        try:
                            tree = ast.parse(f.read(), filename=filepath)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.Import):
                                    for alias in node.names:
                                        top_level_package = get_top_level_package(alias.name)
                                        imported_modules.setdefault(top_level_package, []).append(
                                            os.path.relpath(filepath, project_root)
                                        )
                                elif isinstance(node, ast.ImportFrom):
                                    if node.module:
                                        top_level_package = get_top_level_package(node.module)
                                        # Handle relative imports and directories
                                        if node.level > 0:  # Relative import
                                            if is_local_file_or_directory(filepath, node.module, node.level):
                                                continue  # Skip because it's a valid local file or directory
                                        elif is_local_file_or_directory(filepath, top_level_package, level=0):
                                            continue  # Skip because it's a valid local directory/module
                                        imported_modules.setdefault(top_level_package, []).append(
                                            os.path.relpath(filepath, project_root)
                                        )
                        except SyntaxError:
                            print(f"Skipping {filepath} due to syntax error.")
                except UnicodeDecodeError:
                    print(f"Skipping {filepath} due to encoding issues.")
    
    return imported_modules


def get_local_modules_and_folders(project_root, exclude_dirs=None):
    """
    Get a list of all possible local modules or packages in the project.
    
      - Directories (treated as packages even without __init__.py).
      - Python files (.py).
      
      Args:
          project_root: Root directory of your project.
          exclude_dirs: Directories to skip during traversal.

      Returns:
          set: Local modules and packages found.
      """
    if exclude_dirs is None:
        exclude_dirs = ['env', 'venv', '.venv', '__pycache__', 'Production']  # Default directories to exclude

    local_modules = set()
    
    for root, dirs, files in os.walk(project_root):
        # Skip any directories that should be excluded
        if should_exclude_path(root, exclude_dirs):
            continue

        # Add directories as potential packages
        for directory in dirs:
            module_name = os.path.relpath(os.path.join(root, directory), project_root).replace(os.sep, '.')
            local_modules.add(module_name)

        # Add Python files as potential modules
        for file in files:
            if file.endswith(".py"):
                module_name = os.path.splitext(os.path.relpath(os.path.join(root, file), project_root))[0].replace(os.sep, '.')
                local_modules.add(module_name)

    return local_modules


def compare_imports_and_packages(imported_modules, local_modules):
    """
    Compare imported modules with local modules.
    
      Args:
          imported_modules: Modules found during AST parsing.
          local_modules: Local modules found in the project.

      Returns:
          tuple: Missing packages and unused packages.
      """
    stdlib_modules = get_standard_library_modules()

    missing_packages = {
        module: files
        for module, files in imported_modules.items()
        if module not in local_modules and module not in stdlib_modules
    }
    
    return missing_packages

def compare_imports_and_packages(imported_modules, local_modules):
    """
    Compare imported modules with local modules, standard library modules, and installed packages.
    
      Args:
          imported_modules: Modules found during AST parsing.
          local_modules: Local modules found in the project.

      Returns:
          dict: Missing packages and unused packages.
    """
    stdlib_modules = get_standard_library_modules()
    installed_packages = get_installed_packages()

    missing_packages = {
        module: files
        for module, files in imported_modules.items()
        if module not in local_modules and module not in stdlib_modules and module not in installed_packages
    }
    
    return missing_packages

def detect_unused_libraries(imported_modules, installed_packages):
    """Detect unused libraries that are not dependencies of used libraries."""
    
    # Identify direct dependencies of used libraries
    used_dependencies = set()
    for module in imported_modules:
        if module in installed_packages:
            used_dependencies.update(installed_packages[module])
    
    # Combine used modules and their dependencies
    all_used = used_dependencies.union(imported_modules.keys())
    
    # Find unused libraries by subtracting all_used from installed packages
    unused_libraries = set(installed_packages.keys()) - all_used
    
    return unused_libraries

if __name__ == "__main__":
    # Dynamically resolve the project root directory inside "Python"
    current_working_directory = os.getcwd()
    
    project_root = os.path.join(current_working_directory, "Python")
    
    print(f"Scanning Project Root: {project_root}\n")

    # Get imported modules and their locations (excluding standard library imports)
    imported_modules_with_files = get_imported_modules_with_files(project_root)

    # Get all local modules/packages (folders and .py files)
    local_modules = get_local_modules_and_folders(project_root)
    installed_packages = get_installed_packages_with_dependencies()
    # Compare imports and installed packages
    missing_packages = compare_imports_and_packages(imported_modules_with_files, local_modules)
    # Pretty print results
    print("\nMissing Packages (Imports not Installed):")
    
    pprint(missing_packages)

    unused_libraries = detect_unused_libraries(imported_modules_with_files, installed_packages)
    
    # Output results
    print("\nUnused Libraries:")
    pprint(unused_libraries)
