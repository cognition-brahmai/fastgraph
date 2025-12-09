#!/usr/bin/env python3
"""
FastGraph Package Validation Script

This script validates the FastGraph package structure to ensure
it meets PyPI publishing requirements and quality standards.
"""

import sys
import os
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
import importlib.util


def check_file_exists(file_path: str, required: bool = True) -> bool:
    """Check if a file exists."""
    exists = Path(file_path).exists()
    if required and not exists:
        print(f"❌ Missing required file: {file_path}")
        return False
    elif exists:
        print(f"✅ Found: {file_path}")
    return True


def check_importable(module_name: str) -> bool:
    """Check if a module can be imported."""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            print(f"❌ Cannot import module: {module_name}")
            return False
        
        module = importlib.import_module(module_name)
        print(f"✅ Importable: {module_name}")
        return True
    except Exception as e:
        print(f"❌ Import error for {module_name}: {e}")
        return False


def run_command(cmd: list, description: str) -> bool:
    """Run a command and check if it succeeds."""
    print(f"\n🔧 {description}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {e}")
        if e.stdout:
            print(f"Stdout: {e.stdout[:500]}")
        if e.stderr:
            print(f"Stderr: {e.stderr[:500]}")
        return False


def validate_package_structure():
    """Validate the package structure."""
    print("📋 Validating FastGraph Package Structure")
    print("=" * 50)
    
    # Required files for PyPI
    required_files = [
        "pyproject.toml",
        "setup.py", 
        "README.md",
        "LICENSE",
        "MANIFEST.in",
        ".gitignore",
        "CHANGELOG.md"
    ]
    
    print("\n📁 Checking required files...")
    all_files_exist = True
    for file_path in required_files:
        if not check_file_exists(file_path):
            all_files_exist = False
    
    # Package structure
    package_dirs = [
        "fastgraph",
        "fastgraph/core",
        "fastgraph/config", 
        "fastgraph/cli",
        "fastgraph/utils",
        "examples",
        "tests",
        ".github/workflows"
    ]
    
    print("\n📂 Checking package directories...")
    for dir_path in package_dirs:
        if check_file_exists(dir_path, required=True):
            # Check for __init__.py in package directories
            if dir_path.startswith("fastgraph"):
                init_file = f"{dir_path}/__init__.py"
                check_file_exists(init_file, required=True)
    
    # Check key files
    key_files = [
        "fastgraph/__init__.py",
        "fastgraph/core/__init__.py", 
        "fastgraph/config/__init__.py",
        "fastgraph/cli/__init__.py",
        "fastgraph/utils/__init__.py",
        "example_config.json"
    ]
    
    print("\n📄 Checking key files...")
    for file_path in key_files:
        check_file_exists(file_path, required=True)
    
    return all_files_exist


def validate_imports():
    """Validate package imports."""
    print("\n🔍 Validating imports...")
    print("=" * 30)
    
    # Core imports
    core_imports = [
        "fastgraph",
        "fastgraph.core.graph",
        "fastgraph.core.edge",
        "fastgraph.core.subgraph",
        "fastgraph.core.indexing",
        "fastgraph.core.traversal",
        "fastgraph.core.persistence",
        "fastgraph.config",
        "fastgraph.cli",
        "fastgraph.utils"
    ]
    
    all_importable = True
    for module in core_imports:
        if not check_importable(module):
            all_importable = False
    
    return all_importable


def validate_build():
    """Validate package building."""
    print("\n🔨 Validating package build...")
    print("=" * 30)
    
    # Check if build tools are available
    build_commands = [
        ([sys.executable, "-m", "build", "--version"], "Build tool version"),
        ([sys.executable, "-m", "pip", "show", "build"], "Build tool installation")
    ]
    
    for cmd, desc in build_commands:
        run_command(cmd, desc)
    
    # Try building the package
    build_success = run_command(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", "dist"],
        "Build package"
    )
    
    return build_success


def validate_installation():
    """Validate package installation."""
    print("\n📦 Validating installation...")
    print("=" * 30)
    
    # Install the built package
    install_success = run_command(
        [sys.executable, "-m", "pip", "install", "dist/*.whl"],
        "Install package"
    )
    
    if install_success:
        # Test basic functionality
        test_code = """
import fastgraph
from fastgraph import FastGraph
g = FastGraph()
g.add_node("test", value=1)
print("Basic functionality works")
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_code)
            test_file = f.name
        
        try:
            result = subprocess.run([sys.executable, test_file], 
                                  capture_output=True, text=True, check=True)
            print("✅ Basic functionality test passed")
            print(f"Output: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Basic functionality test failed: {e}")
            return False
        finally:
            os.unlink(test_file)
    
    return install_success


def validate_metadata():
    """Validate package metadata."""
    print("\n📊 Validating metadata...")
    print("=" * 25)
    
    # Check pyproject.toml
    try:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        
        project_data = data.get("project", {})
        
        required_fields = ["name", "version", "description", "authors"]
        missing_fields = []
        
        for field in required_fields:
            if field not in project_data:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"❌ Missing metadata fields: {missing_fields}")
            return False
        else:
            print("✅ All required metadata fields present")
            
        print(f"✅ Package name: {project_data['name']}")
        print(f"✅ Version: {project_data['version']}")
        print(f"✅ Description: {project_data['description'][:50]}...")
        
    except Exception as e:
        print(f"❌ Error reading pyproject.toml: {e}")
        return False
    
    # Check README length (PyPI recommends descriptive README)
    try:
        with open("README.md", 'r') as f:
            readme_content = f.read()
        
        if len(readme_content) < 500:
            print("⚠️  README is quite short, consider adding more details")
        else:
            print("✅ README length is adequate")
        
    except Exception as e:
        print(f"❌ Error reading README: {e}")
        return False
    
    return True


def validate_code_quality():
    """Validate code quality."""
    print("\n🧹 Validating code quality...")
    print("=" * 30)
    
    # Check if linting tools are available
    linting_tools = ["black", "flake8", "isort"]
    
    for tool in linting_tools:
        try:
            subprocess.run([tool, "--version"], capture_output=True, check=True)
            print(f"✅ {tool} available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"⚠️  {tool} not available (install with: pip install {tool})")
    
    return True


def main():
    """Main validation function."""
    print("🚀 FastGraph Package Validation")
    print("=" * 40)
    
    # Change to package directory
    if not Path("pyproject.toml").exists():
        print("❌ Not in package root directory (pyproject.toml not found)")
        return False
    
    # Run validations
    validations = [
        ("Package Structure", validate_package_structure),
        ("Imports", validate_imports),
        ("Metadata", validate_metadata),
        ("Code Quality", validate_code_quality),
    ]
    
    results = {}
    for name, validator in validations:
        results[name] = validator()
    
    # Build and installation validate (may create files)
    print("\n🏗️  Build and Installation Validation...")
    print("=" * 40)
    
    try:
        results["Build"] = validate_build()
        if results["Build"]:
            results["Installation"] = validate_installation()
        else:
            results["Installation"] = False
    except Exception as e:
        print(f"❌ Build/installation validation error: {e}")
        results["Build"] = False
        results["Installation"] = False
    
    # Summary
    print("\n📋 Validation Summary")
    print("=" * 20)
    
    total_checks = len(results)
    passed_checks = sum(1 for result in results.values() if result)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status.ljust(8)} {name}")
    
    print(f"\nResult: {passed_checks}/{total_checks} checks passed")
    
    if passed_checks == total_checks:
        print("\n🎉 Package validation successful! Ready for PyPI publishing.")
        
        # Additional publishing tips
        print("\n📝 Publishing Checklist:")
        print("1. Run: python -m build")
        print("2. Test: twine check dist/*")
        print("3. Upload to Test PyPI: twine upload --repository testpypi dist/*")
        print("4. Install from Test PyPI: pip install --index-url https://test.pypi.org/simple/ fastgraph")
        print("5. Upload to PyPI: twine upload dist/*")
        
    else:
        print(f"\n⚠️  {total_checks - passed_checks} validation(s) failed.")
        print("Please fix the issues before publishing to PyPI.")
    
    return passed_checks == total_checks


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)