import subprocess
result = subprocess.run(['pip', 'install', '-r', 'requirements.txt'], capture_output=True, text=True)
print("STDOUT:", result.stdout[-500:] if result.stdout else "none")
print("STDERR:", result.stderr[-500:] if result.stderr else "none")
print("Return code:", result.returncode)
