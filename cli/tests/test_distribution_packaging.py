"""Distribution packaging tests: verifies wheel builds and installs in clean virtualenv."""
import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


def find_python_310_plus() -> str:
    """Find a Python >= 3.10 interpreter for packaging tests."""
    if "OPEN_CORE_PYTHON" in os.environ:
        return os.environ["OPEN_CORE_PYTHON"]
    if "VIRTUAL_ENV" in os.environ:
        venv_py = Path(os.environ["VIRTUAL_ENV"]) / "bin" / "python"
        if venv_py.exists():
            return str(venv_py)
    poetry_cache = Path.home() / "Library/Caches/pypoetry/virtualenvs"
    if poetry_cache.exists():
        for candidate in sorted(poetry_cache.glob("think-app-*-py3.12/bin/python")):
            return str(candidate)
    for p in ["python3.12", "python3.11", "python3.10"]:
        which = shutil.which(p)
        if which:
            return which
    return sys.executable


class TestDistributionPackaging(unittest.TestCase):

    def test_wheel_exists_and_contains_entry_point(self):
        pkg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        dist_dir = os.path.join(pkg_dir, "dist")
        wheels = glob.glob(os.path.join(dist_dir, "*.whl"))
        if not wheels:
            self.skipTest("No built wheels found in dist/. Run 'rav run open_build' first.")

        wheel_path = wheels[0]
        self.assertTrue(os.path.exists(wheel_path))
        self.assertIn("thinkument_cli-0.1.0", os.path.basename(wheel_path))

    def test_wheel_install_in_isolated_virtualenv(self):
        pkg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        dist_dir = os.path.join(pkg_dir, "dist")
        wheels = sorted(glob.glob(os.path.join(dist_dir, "*.whl")))
        if not wheels:
            self.skipTest("No wheel built yet")

        wheel_path = wheels[-1]
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_dir = os.path.join(tmpdir, "test_venv")
            py_bin = find_python_310_plus()
            # Create fresh venv
            res = subprocess.run([py_bin, "-m", "venv", venv_dir], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"venv creation failed: {res.stderr}")

            python_bin = os.path.join(venv_dir, "bin", "python")
            pip_bin = os.path.join(venv_dir, "bin", "pip")
            cli_bin = os.path.join(venv_dir, "bin", "thinkument")

            # Install wheel without dependencies for rapid inspection
            res = subprocess.run([pip_bin, "install", "--no-deps", wheel_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"pip install wheel failed: {res.stderr}")

            # Verify import works and exports version
            res = subprocess.run([python_bin, "-c", "import thinkument; print(thinkument.__version__)"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"import thinkument failed: {res.stderr}")
            self.assertEqual(res.stdout.strip(), "0.1.0")

            # Verify CLI entry point exists and runs --help
            res = subprocess.run([cli_bin, "--help"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"thinkument --help failed: {res.stderr}")
            self.assertIn("Thinkument CLI", res.stdout)
            self.assertIn("dev", res.stdout)
            self.assertIn("validate", res.stdout)
            self.assertIn("publish", res.stdout)
            self.assertIn("run", res.stdout)
            self.assertIn("balance", res.stdout)

    def test_single_binary_compilation_and_size_budget(self):
        pkg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        bin_path = os.path.join(pkg_dir, "dist", "bin", "thinkument")
        if not os.path.exists(bin_path):
            self.skipTest("No compiled single-binary found in dist/bin/. Run 'rav run open_build_binary' first.")

        size_mb = os.path.getsize(bin_path) / (1024 * 1024)
        self.assertLess(size_mb, 25.0, f"Binary size {size_mb:.2f}MB exceeds 25MB budget")

        res = subprocess.run([bin_path, "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Binary --help failed: {res.stderr}")
        self.assertIn("Thinkument CLI", res.stdout)
        self.assertIn("dev", res.stdout)

    def test_npm_wrapper_configuration(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
        npm_pkg = os.path.join(root_dir, "_cicd", "cicd_open", "packaging", "npm", "thinkument", "package.json")
        self.assertTrue(os.path.exists(npm_pkg), f"npm package.json not found at {npm_pkg}")

        import json
        with open(npm_pkg, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["name"], "@thinkument/cli")
        self.assertIn("thinkument", data["bin"])
        self.assertIn("@thinkument/cli-darwin-arm64", data["optionalDependencies"])
        self.assertIn("@thinkument/cli-linux-x64", data["optionalDependencies"])

        launcher_path = os.path.join(os.path.dirname(npm_pkg), "bin", "thinkument.js")
        self.assertTrue(os.path.exists(launcher_path))
        # Verify node launcher parses cleanly
        res = subprocess.run(["node", "-c", launcher_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in thinkument.js: {res.stderr}")

    def test_homebrew_formula_syntax(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
        formula_path = os.path.join(root_dir, "_cicd", "cicd_open", "packaging", "homebrew", "thinkument.rb")
        self.assertTrue(os.path.exists(formula_path))
        with open(formula_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("class Thinkument < Formula", content)
        self.assertIn("on_macos", content)
        self.assertIn("on_linux", content)

    def test_universal_posix_installer_syntax(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
        installer_path = os.path.join(root_dir, "_cicd", "cicd_open", "packaging", "shell", "install.sh")
        self.assertTrue(os.path.exists(installer_path))
        # Verify sh syntax
        res = subprocess.run(["sh", "-n", installer_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"POSIX shell syntax error in install.sh: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
