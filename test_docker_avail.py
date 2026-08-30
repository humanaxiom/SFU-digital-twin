import subprocess
import os

def test_docker_available():
    """Test that docker command is available."""
    print("PATH:", os.environ.get("PATH"))
    result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    assert result.returncode == 0, f"docker --version failed: {result.stderr}"
